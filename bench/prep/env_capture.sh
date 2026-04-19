#!/usr/bin/env bash
# Capture the machine + toolchain state for reproducibility.
# Writes bench/results/env.txt — intended to be re-run whenever the
# benchmark sweep is re-run.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${REPO_ROOT}/bench/results/env.txt"
mkdir -p "$(dirname "$OUT")"

{
echo "# Environment capture  —  $(date -Iseconds)"
echo

echo "## Host"
echo "hostname: $(hostname)"
echo "kernel:   $(uname -srmo)"
echo

echo "## CPU"
lscpu | grep -E '^(Model name|Architecture|Thread|Core|Socket|CPU MHz|CPU max MHz|CPU\(s\):|L1d|L1i|L2|L3|Flags)' | sed 's/^/  /'
echo "governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo 'n/a')"
echo

echo "## Memory"
free -h | sed 's/^/  /'
echo "  THP: $(cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null || echo n/a)"
echo "  swappiness: $(cat /proc/sys/vm/swappiness 2>/dev/null || echo n/a)"
echo

echo "## Storage"
lsblk -o NAME,SIZE,TYPE,ROTA,MODEL,FSTYPE,MOUNTPOINT | sed 's/^/  /'
echo
echo "  mounts for repo path:"
df -h "$REPO_ROOT" | sed 's/^/    /'
grep -E ' /(home|nvme|data) ' /proc/mounts 2>/dev/null | sed 's/^/    /' || true
echo
if command -v nvme >/dev/null 2>&1; then
    for dev in /dev/nvme?n1; do
        [ -e "$dev" ] || continue
        echo "  nvme id-ctrl $dev (truncated):"
        sudo -n nvme id-ctrl "$dev" 2>/dev/null | grep -E '^(mn|fr|sn|ieee|cntrltype)' | sed 's/^/    /' || echo "    (need sudo)"
    done
fi
echo

echo "## Toolchain"
echo "  g++:    $(g++ --version | head -1)"
echo "  python: $(python3 --version 2>&1)"
echo "  rustc:  $(rustc --version 2>/dev/null || echo 'not installed')"
echo "  cargo:  $(cargo --version 2>/dev/null || echo 'not installed')"
python3 -c "import faiss; print(f'  faiss:  {faiss.__version__}')" 2>/dev/null || echo "  faiss:  (not importable)"
python3 -c "import numpy; print(f'  numpy:  {numpy.__version__}')" 2>/dev/null || true
echo

echo "## Git"
echo "  tape repo:    $(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo n/a)  ($(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo n/a))"
if [ -d "$REPO_ROOT/DiskANN/.git" ]; then
    echo "  DiskANN repo: $(git -C "$REPO_ROOT/DiskANN" rev-parse HEAD 2>/dev/null || echo n/a)"
fi
echo

echo "## Flags used for builds"
echo "  CXXFLAGS (tape benchmark_search): -O3 -march=native -std=c++17 -luring"
echo "  RUSTFLAGS (diskann):               -Ctarget-cpu=x86-64-v3"
} > "$OUT"

echo "[+] env captured -> $OUT"
