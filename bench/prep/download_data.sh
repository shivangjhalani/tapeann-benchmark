#!/usr/bin/env bash
# Download a SIFT/BIGANN subset (1M, 10M, or 100M) from INRIA TEXMEX.
#
# Usage:  download_data.sh [sift1m|sift10m|sift100m]     (default: sift10m)
#
# Strategy:
#   1. Byte-range FTP fetch of a compressed prefix sized for NVECS × 132 B
#      × 25% safety margin, divided by the measured 1.353× compression ratio.
#   2. Local gunzip | head -c truncates to exactly NVECS × 132 B.
#   3. Idempotent: if the final base/query file already exists at the
#      correct size, the download step is skipped.
#
# Each bvec record: [int32 dim=128][128 × uint8] = 132 bytes.

set -euo pipefail

PROFILE="${1:-sift10m}"

case "$PROFILE" in
    sift1m)    NVECS=1000000;   COMPRESSED_RANGE=128000000 ;;     # ~122 MB compressed  → ~165 MB decompressed
    sift10m)   NVECS=10000000;  COMPRESSED_RANGE=1219784162 ;;    # ~1.22 GB compressed → ~1.65 GB decompressed
    sift100m)  NVECS=100000000; COMPRESSED_RANGE=12197841620 ;;   # ~12.2 GB compressed → ~16.5 GB decompressed
    *)  echo "[!] Unknown profile: $PROFILE  (expected sift1m | sift10m | sift100m)"; exit 1 ;;
esac

RECORD_SIZE=132
TARGET_BYTES=$(( NVECS * RECORD_SIZE ))

RAW_DIR="$(cd "$(dirname "$0")/../../data/raw" && pwd)"
cd "$RAW_DIR"

BASE_OUT="bigann_base_${PROFILE}.bvecs"
QUERY_OUT="bigann_query.bvecs"
FTP_BASE="ftp://ftp.irisa.fr/local/texmex/corpus"

echo "[cfg] profile=${PROFILE}  nvecs=${NVECS}  target_bytes=${TARGET_BYTES}"
echo "[cfg] raw_dir=${RAW_DIR}"
echo ""

# ── Query file ────────────────────────────────────────────────────────────────
Q_EXPECTED=$(( 10000 * RECORD_SIZE ))  # 10k queries, shared across all profiles

if [ -f "$QUERY_OUT" ] && [ "$(stat -c%s "$QUERY_OUT")" = "$Q_EXPECTED" ]; then
    echo "[1/3] Query set already present ($QUERY_OUT, ${Q_EXPECTED} B) — skipping."
else
    echo "[1/3] Query set  (bigann_query.bvecs.gz → $QUERY_OUT, ~1 MB)."
    curl --progress-bar --retry 5 --retry-delay 5 \
         "${FTP_BASE}/bigann_query.bvecs.gz" \
        | gunzip -c > "$QUERY_OUT"
    Q_ACTUAL=$(stat -c%s "$QUERY_OUT")
    if [ "$Q_ACTUAL" -ne "$Q_EXPECTED" ]; then
        echo "[!] Query file size mismatch: got ${Q_ACTUAL}, expected ${Q_EXPECTED}."
        exit 1
    fi
    echo "[+] Query OK: ${Q_ACTUAL} bytes."
fi
echo ""

# ── Base file — check idempotency ────────────────────────────────────────────
if [ -f "$BASE_OUT" ] && [ "$(stat -c%s "$BASE_OUT")" = "$TARGET_BYTES" ]; then
    echo "[2-3/3] Base set already present ($BASE_OUT, ${TARGET_BYTES} B) — skipping."
    echo ""
    echo "[+] Done. Files in ${RAW_DIR}:"
    ls -lh "$RAW_DIR"
    exit 0
fi

# ── Base file — Step 1: byte-range download ──────────────────────────────────
echo "[2/3] Base set — byte-range download"
echo "      Fetching first ${COMPRESSED_RANGE} B of bigann_base.bvecs.gz"
echo "      Resumable via 'curl -C -'."
echo ""

PARTIAL="partial_base_${PROFILE}.gz"
curl --progress-bar --retry 5 --retry-delay 10 --retry-max-time 14400 \
     -C - \
     -r "0-${COMPRESSED_RANGE}" \
     -o "$PARTIAL" \
     "${FTP_BASE}/bigann_base.bvecs.gz"

P_ACTUAL=$(stat -c%s "$PARTIAL")
if [ "$P_ACTUAL" -lt "$COMPRESSED_RANGE" ]; then
    echo "[!] Partial download too small: got ${P_ACTUAL}, expected ${COMPRESSED_RANGE}."
    echo "    Re-run to resume."
    exit 1
fi
echo "[+] Compressed slice downloaded: ${P_ACTUAL} bytes."
echo ""

# ── Base file — Step 2: decompress + truncate ───────────────────────────────
echo "[3/3] Decompress + truncate → ${BASE_OUT} (${TARGET_BYTES} B)"
echo ""
# pipefail OFF: head -c exits early, gunzip receives SIGPIPE (exit 141).
(set +o pipefail
 gunzip -c "$PARTIAL" | head -c "$TARGET_BYTES"
) > "$BASE_OUT"

B_ACTUAL=$(stat -c%s "$BASE_OUT")
if [ "$B_ACTUAL" -ne "$TARGET_BYTES" ]; then
    echo "[!] Base size mismatch: got ${B_ACTUAL}, expected ${TARGET_BYTES}."
    echo "    Compressed slice was too small — increase the COMPRESSED_RANGE for this profile."
    exit 1
fi
echo "[+] Base OK: ${B_ACTUAL} bytes."

rm -f "$PARTIAL"

echo ""
echo "[+] Done. Files in ${RAW_DIR}:"
ls -lh "$RAW_DIR"
