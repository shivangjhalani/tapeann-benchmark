"""
Shared runner utilities:
  - drop_caches (via sudo)
  - /usr/bin/time -v wrapping + parsing
  - /proc/{pid}/io polling for bytes_read_total, ios_total
  - systemd-run --scope -p MemoryMax=... wrapper for ram-capped modes
  - CSV append with unified RUNS_COLS schema
  - resume-key helpers
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configs.grid import RUNS_CSV, RUNS_COLS, LOGS_DIR, ensure_dirs

# ─── /usr/bin/time -v parsing ───────────────────────────────────────────────

_RE_RSS = re.compile(r"Maximum resident set size \(kbytes\):\s*(\d+)")
_RE_USR = re.compile(r"User time \(seconds\):\s*([\d.]+)")
_RE_SYS = re.compile(r"System time \(seconds\):\s*([\d.]+)")


def parse_time_stderr(err: str) -> dict:
    def g(rx, default=0.0):
        m = rx.search(err or "")
        return float(m.group(1)) if m else default
    return {
        "peak_rss_mb": round(g(_RE_RSS) / 1024, 1) if _RE_RSS.search(err or "") else 0.0,
        "cpu_user_s":  g(_RE_USR),
        "cpu_sys_s":   g(_RE_SYS),
    }


def wrap_time(cmd):
    """Prepend /usr/bin/time -v to capture RSS and CPU."""
    if os.path.exists("/usr/bin/time"):
        return ["/usr/bin/time", "-v"] + list(cmd)
    return list(cmd)


# ─── drop_caches ────────────────────────────────────────────────────────────

def drop_caches():
    """Run `sync; echo 3 > /proc/sys/vm/drop_caches` via sudo. Warns on failure."""
    try:
        subprocess.run(["sudo", "-n", "sh", "-c",
                        "sync && echo 3 > /proc/sys/vm/drop_caches"],
                       check=True, capture_output=True, text=True, timeout=30)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  [warn] drop_caches failed: {e}. Results will not be truly cold.")


# ─── systemd-run wrapper ────────────────────────────────────────────────────

def wrap_ram_cap(cmd, ram_cap_bytes: int | None):
    """If ram_cap_bytes is set, wrap the command in a systemd-run scope with
    the given MemoryMax. Requires passwordless sudo + systemd.

    Returns the wrapped command list."""
    if not ram_cap_bytes:
        return cmd
    if not shutil.which("systemd-run"):
        print("  [warn] systemd-run not found; ram_cap ignored.")
        return cmd
    scope_name = f"tape-bench-{os.getpid()}-{int(time.time()*1000)%100000}"
    return [
        "sudo", "-n", "systemd-run",
        "--scope",
        f"--unit={scope_name}",
        f"--property=MemoryMax={ram_cap_bytes}",
        f"--property=MemorySwapMax=0",
        "--quiet",
        "--",
    ] + list(cmd)


# ─── /proc/{pid}/io polling ─────────────────────────────────────────────────

class ProcIOPoller(threading.Thread):
    """Polls /proc/{pid}/io in a background thread and keeps the last valid
    sample. Exits when the target process does (file disappears).

    Fields we care about:
      read_bytes   — bytes actually pulled from block devices (disk I/O)
      syscr        — read syscalls count
    """

    def __init__(self, pid: int, interval_s: float = 0.1):
        super().__init__(daemon=True)
        self.pid = pid
        self.interval_s = interval_s
        self.last = {"read_bytes": 0, "syscr": 0, "rchar": 0}
        self._stop_event = threading.Event()

    def run(self):
        path = f"/proc/{self.pid}/io"
        while not self._stop_event.is_set():
            try:
                with open(path) as f:
                    for line in f:
                        k, _, v = line.partition(":")
                        k = k.strip()
                        if k in self.last:
                            self.last[k] = int(v.strip())
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                return
            self._stop_event.wait(self.interval_s)

    def stop(self):
        self._stop_event.set()


class ProcTreeIOPoller(threading.Thread):
    """Polls /proc/{pid}/io for the root PID and every descendant.

    Each tick we:
      1. Walk /proc/*/stat to find current descendants (by PPID chain).
      2. Read /proc/{pid}/io for each. Track the max per-pid sample so we
         don't lose counters when a pid exits between ticks.
    Total = sum of max-per-pid at the end.
    """

    def __init__(self, root_pid: int, interval_s: float = 0.05):
        super().__init__(daemon=True)
        self.root_pid = root_pid
        self.interval_s = interval_s
        self._stop_event = threading.Event()
        # pid -> {"read_bytes": int, "syscr": int}
        self._max = {}

    @staticmethod
    def _read_ppid_map():
        m = {}
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                with open(f"/proc/{name}/stat") as f:
                    line = f.read()
                # stat fields: pid (comm) state ppid ...
                rp = line.rfind(")")
                tail = line[rp + 2:].split()
                ppid = int(tail[1])
                m[int(name)] = ppid
            except (OSError, ValueError):
                continue
        return m

    def _descendants(self, ppids):
        """Walk PPID map, return set of pids whose ancestor chain hits root."""
        out = {self.root_pid}
        frontier = {self.root_pid}
        while frontier:
            nxt = set()
            for pid, pp in ppids.items():
                if pp in frontier and pid not in out:
                    out.add(pid); nxt.add(pid)
            frontier = nxt
        return out

    def run(self):
        while not self._stop_event.is_set():
            try:
                ppids = self._read_ppid_map()
                for pid in self._descendants(ppids):
                    try:
                        with open(f"/proc/{pid}/io") as f:
                            sample = {"read_bytes": 0, "syscr": 0}
                            for line in f:
                                k, _, v = line.partition(":")
                                k = k.strip()
                                if k in sample:
                                    sample[k] = int(v.strip())
                    except (FileNotFoundError, ProcessLookupError, PermissionError):
                        continue
                    prev = self._max.get(pid, {"read_bytes": 0, "syscr": 0})
                    self._max[pid] = {
                        "read_bytes": max(prev["read_bytes"], sample["read_bytes"]),
                        "syscr":      max(prev["syscr"],      sample["syscr"]),
                    }
            except FileNotFoundError:
                pass
            self._stop_event.wait(self.interval_s)

    def stop(self):
        self._stop_event.set()

    @property
    def total_read_bytes(self):
        return sum(v["read_bytes"] for v in self._max.values())

    @property
    def total_syscr(self):
        return sum(v["syscr"] for v in self._max.values())


# ─── Run a subprocess with time + io polling ────────────────────────────────

def run_measured(cmd, cwd=None, log_path=None):
    """Launch cmd, poll /proc/{pid}/io, wait, return a dict with:
       rc, stdout, stderr, wall_s, bytes_read_total, ios_total,
       cpu_user_s, cpu_sys_s, peak_rss_mb
    Writes full stdout/stderr to log_path if provided."""
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=cwd,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, bufsize=1)
    # Poller attaches to the outermost process. When wrapped in
    # /usr/bin/time or sudo/systemd-run, that's the wrapper PID — its
    # read_bytes does NOT include children's. We therefore also read
    # the recursive sum via /proc/{pid}/task/{tid}/io if available;
    # simplest: also accumulate from child via `--children=yes`-style
    # polling of the process tree. Pragmatic approach: poll the child
    # of the root and take the last non-zero reading.
    # Poll the whole process tree: sudo/systemd-run/time wrap the real binary,
    # and /proc/{root}/io doesn't include descendants. We walk /proc/*/stat
    # every tick looking for PIDs whose PPID is in our known set, growing the
    # set as we discover them.
    tree_poll = ProcTreeIOPoller(proc.pid)
    tree_poll.start()
    stdout, stderr = proc.communicate()
    wall_s = time.time() - t0
    tree_poll.stop()
    tree_poll.join(timeout=0.5)

    bytes_read = tree_poll.total_read_bytes
    ios_total  = tree_poll.total_syscr

    if log_path:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w") as f:
            f.write("CMD: " + " ".join(map(str, cmd)) + "\n")
            f.write("STDOUT:\n" + (stdout or "") + "\nSTDERR:\n" + (stderr or ""))

    parsed = parse_time_stderr(stderr or "")
    return {
        "rc":               proc.returncode,
        "stdout":           stdout or "",
        "stderr":           stderr or "",
        "wall_s":           round(wall_s, 3),
        "bytes_read_total": bytes_read,
        "ios_total":        ios_total,
        **parsed,
    }


# ─── runs.csv helpers ───────────────────────────────────────────────────────

RESUME_KEY_COLS = ("algo", "dataset", "variant", "mode", "ram_cap_bytes",
                   "params_json", "threads", "trial")


def load_done_keys():
    if not os.path.exists(RUNS_CSV):
        return set()
    done = set()
    with open(RUNS_CSV) as f:
        for r in csv.DictReader(f):
            done.add(tuple(str(r.get(c, "")) for c in RESUME_KEY_COLS))
    return done


def make_resume_key(row: dict):
    return tuple(str(row.get(c, "")) for c in RESUME_KEY_COLS)


def append_run_row(row: dict):
    ensure_dirs()
    os.makedirs(os.path.dirname(RUNS_CSV), exist_ok=True)
    write_header = not os.path.exists(RUNS_CSV)
    with open(RUNS_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RUNS_COLS)
        if write_header:
            w.writeheader()
        # Fill missing columns with empty string so DictWriter doesn't error.
        full = {c: row.get(c, "") for c in RUNS_COLS}
        w.writerow(full)


# ─── Commit SHA + index-size helpers ────────────────────────────────────────

_CACHED_SHA = None


def commit_sha():
    global _CACHED_SHA
    if _CACHED_SHA is not None:
        return _CACHED_SHA
    try:
        _CACHED_SHA = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        _CACHED_SHA = "unknown"
    return _CACHED_SHA


def dir_size_bytes(path):
    total = 0
    for r, _, fs in os.walk(path):
        for fn in fs:
            try: total += os.path.getsize(os.path.join(r, fn))
            except OSError: pass
    return total


def largest_file_bytes(path):
    """Biggest single file in dir — proxy for 'disk-resident index' size."""
    best = 0
    for r, _, fs in os.walk(path):
        for fn in fs:
            try: best = max(best, os.path.getsize(os.path.join(r, fn)))
            except OSError: pass
    return best
