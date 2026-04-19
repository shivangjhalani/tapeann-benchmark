"""
Preflight: sanity-check the host before a benchmark sweep.

Prints WARN for non-critical misconfigurations and ERROR for things that
would invalidate results. Exits non-zero only on ERRORs.

Usage:  python bench/prep/preflight.py
"""

import os
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WARN = []
ERR  = []


def _read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def check_governor():
    g = _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    if g != "performance":
        WARN.append(
            f"CPU governor is '{g}', not 'performance'. "
            "Run:  sudo cpupower frequency-set -g performance"
        )


def check_thp():
    t = _read("/sys/kernel/mm/transparent_hugepage/enabled")
    # Format: "[always] madvise never" — bracket marks current setting.
    if "[always]" in t:
        WARN.append(
            "Transparent huge pages = always. This adds latency noise. "
            "Run:  echo never | sudo tee /sys/kernel/mm/transparent_hugepage/enabled"
        )


def check_swappiness():
    try:
        s = int(_read("/proc/sys/vm/swappiness") or "60")
    except ValueError:
        s = 60
    if s > 10:
        WARN.append(
            f"vm.swappiness={s}. Prefer <=10 to keep page cache from being swapped out. "
            "Run:  sudo sysctl vm.swappiness=1"
        )


def check_disk_free(min_gb=30):
    s = shutil.disk_usage(REPO_ROOT)
    free_gb = s.free / 1024**3
    if free_gb < min_gb:
        ERR.append(f"Only {free_gb:.1f} GB free on repo filesystem (need >= {min_gb} GB).")
    else:
        print(f"[ok] disk free: {free_gb:.1f} GB")


def check_ram_free(min_gb=8):
    for line in _read("/proc/meminfo").splitlines():
        if line.startswith("MemAvailable:"):
            kb = int(line.split()[1])
            gb = kb / 1024**2
            if gb < min_gb:
                ERR.append(f"Only {gb:.1f} GB RAM available (need >= {min_gb}).")
            else:
                print(f"[ok] ram available: {gb:.1f} GB")
            return


def check_tool(name, advice):
    if shutil.which(name) is None:
        WARN.append(f"Missing tool: {name}. {advice}")


def check_can_drop_caches():
    # /proc/sys/vm/drop_caches requires root. We don't actually drop — just
    # verify we have a path to root (sudo -n).
    try:
        r = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=2)
        if r.returncode != 0:
            WARN.append("Passwordless sudo not available — cold-cache runs need it "
                        "(drop_caches + systemd-run).")
    except Exception as e:
        WARN.append(f"Could not verify sudo: {e}")


def check_systemd_run():
    if shutil.which("systemd-run") is None:
        ERR.append("systemd-run not found — needed for 'ram_capped' mode. "
                   "Install systemd or skip ram_capped in the sweep.")


def main():
    check_governor()
    check_thp()
    check_swappiness()
    check_disk_free(min_gb=30)
    check_ram_free(min_gb=8)
    check_tool("/usr/bin/time", "Needed for peak RSS capture.")
    check_tool("g++",  "Needed to compile TAPEANN benchmark_search.cpp.")
    check_tool("cargo","Needed to build DiskANN Rust binary.")
    check_can_drop_caches()
    check_systemd_run()

    print()
    for w in WARN:
        print(f"[WARN]  {w}")
    for e in ERR:
        print(f"[ERROR] {e}")

    if ERR:
        print(f"\n{len(ERR)} error(s). Fix these before running the sweep.")
        sys.exit(1)
    print(f"\nPreflight OK. ({len(WARN)} warning(s).)")


if __name__ == "__main__":
    main()
