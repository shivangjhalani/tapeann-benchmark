#!/usr/bin/env bash
# Download SIFT10M from BIGANN (INRIA TEXMEX).
#
# KEY DESIGN: two clean steps instead of a fragile streaming pipeline.
#
#   Step 1 — byte-range FTP download
#     curl -r 0-N  fetches only the compressed prefix we need.
#     The FTP server confirmed it supports REST (byte-range).
#     N is sized with a 25% safety margin so decompression always
#     yields at least 10M vectors.  File is resumable with -C -.
#
#   Step 2 — local decompress + truncate (no network)
#     gunzip -c from disk, piped to head -c.  Runs in a subshell
#     with pipefail OFF to absorb the SIGPIPE when head exits.
#
# Measured numbers (from probing the actual server):
#   Compression ratio:  1.353x  (5 MB compressed → 6.76 MB uncompressed)
#   Compressed bytes to cover 1.32 GB uncompressed:  ~976 MB
#   With 25% safety margin:  ~1.22 GB to download
#   Transfer speed:  ~300 KB/s  →  expected download time ~68 min
#
# Each bvec record: [int32 dim=128][128 × uint8] = 132 bytes
# 10M records = 1,320,000,000 bytes uncompressed.

set -euo pipefail

RAW_DIR="$(cd "$(dirname "$0")/../../data/raw" && pwd)"
cd "$RAW_DIR"

NVECS=10000000
RECORD_SIZE=132
TARGET_BYTES=$(( NVECS * RECORD_SIZE ))   # 1,320,000,000 uncompressed

# 1.22 GB of compressed data gives ~1.65 GB decompressed (25% safety margin).
COMPRESSED_RANGE=1219784162

FTP_BASE="ftp://ftp.irisa.fr/local/texmex/corpus"

# ── Query file ────────────────────────────────────────────────────────────────
echo "[1/3] Query set  (bigann_query.bvecs.gz → bigann_query.bvecs)"
echo "      ~1 MB compressed, completes in seconds."
echo ""
curl --progress-bar --retry 5 --retry-delay 5 \
     "${FTP_BASE}/bigann_query.bvecs.gz" \
    | gunzip -c > bigann_query.bvecs

Q_ACTUAL=$(stat -c%s bigann_query.bvecs)
Q_EXPECTED=$(( 10000 * RECORD_SIZE ))
if [ "$Q_ACTUAL" -ne "$Q_EXPECTED" ]; then
    echo "[!] Query file size mismatch: got ${Q_ACTUAL}, expected ${Q_EXPECTED}."
    exit 1
fi
echo ""
echo "[+] Query OK: ${Q_ACTUAL} bytes (10,000 vectors × 132 bytes)."

# ── Base file — Step 1: byte-range download ────────────────────────────────
echo ""
echo "[2/3] Base set — Step 1: range download"
echo "      Fetching first ${COMPRESSED_RANGE} bytes of bigann_base.bvecs.gz"
echo "      (~1.22 GB compressed  →  guaranteed ≥1.32 GB when decompressed)"
echo "      Speed ~300 KB/s on INRIA FTP  →  expected ~68 min."
echo "      Resumable: re-running this script continues from where it left off."
echo ""

# -C - resumes a partial download; --retry retries on transient errors.
curl --progress-bar --retry 5 --retry-delay 10 --retry-max-time 7200 \
     -C - \
     -r "0-${COMPRESSED_RANGE}" \
     -o partial_base.gz \
     "${FTP_BASE}/bigann_base.bvecs.gz"

P_ACTUAL=$(stat -c%s partial_base.gz)
if [ "$P_ACTUAL" -lt "$COMPRESSED_RANGE" ]; then
    echo "[!] Partial download too small: got ${P_ACTUAL} bytes, expected ${COMPRESSED_RANGE}."
    echo "    Re-run the script to resume — curl will continue from byte ${P_ACTUAL}."
    exit 1
fi
echo ""
echo "[+] Compressed slice downloaded: ${P_ACTUAL} bytes."

# ── Base file — Step 2: local decompress + truncate ──────────────────────────
echo ""
echo "[3/3] Base set — Step 2: local decompress + truncate (no network)"
echo "      gunzip partial_base.gz | head -c ${TARGET_BYTES} > bigann_base_10M.bvecs"
echo ""

# Subshell with pipefail OFF: head -c exits after TARGET_BYTES bytes, gunzip
# receives SIGPIPE and exits 141.  That non-zero code must not abort the script.
(set +o pipefail
 gunzip -c partial_base.gz | head -c "${TARGET_BYTES}"
) > bigann_base_10M.bvecs

B_ACTUAL=$(stat -c%s bigann_base_10M.bvecs)
if [ "$B_ACTUAL" -ne "$TARGET_BYTES" ]; then
    echo "[!] Base file size mismatch: got ${B_ACTUAL}, expected ${TARGET_BYTES}."
    echo "    The compressed slice may have been too small.  Try increasing COMPRESSED_RANGE."
    exit 1
fi
echo "[+] Base OK: ${B_ACTUAL} bytes (10,000,000 vectors × 132 bytes)."

# ── Cleanup ──────────────────────────────────────────────────────────────────
echo ""
echo "[*] Removing partial_base.gz (no longer needed)..."
rm -f partial_base.gz

echo ""
echo "[+] Done. Files in ${RAW_DIR}:"
ls -lh "${RAW_DIR}"
