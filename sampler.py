#!/usr/bin/env python3
"""Continuous resource sampler for macOS (stdlib only, no root needed).

Runs as a launchd KeepAlive daemon. Every INTERVAL seconds it logs:
  - system CPU% computed from per-process cputime deltas between ticks,
    so all CPU consumed between samples is accounted for (no blind window)
  - RAM breakdown (vm_stat) and swap usage
  - top 5 process names by CPU over the interval and by resident memory

Known limits: a process that both starts and exits within a single interval
leaves no trace (needs root process accounting); sleep periods appear as
timestamp gaps, and the tick after a gap >3x INTERVAL is skipped to avoid
averaging across the sleep.
"""
import csv
import os
import re
import subprocess
import sys
import time
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.environ.get("RESMON_LOG_DIR") or os.path.join(BASE, "logs")
INTERVAL = float(os.environ.get("RESMON_INTERVAL", "10"))
RETENTION_DAYS = int(os.environ.get("RESMON_RETENTION_DAYS", "90"))
NCPU = int(subprocess.check_output(["sysctl", "-n", "hw.ncpu"]).strip())
PAGESIZE = int(subprocess.check_output(["sysctl", "-n", "hw.pagesize"]).strip())
MB = 1048576

SYS_HEADER = ["timestamp", "cpu_pct", "load_1m", "mem_used_mb", "mem_wired_mb",
              "mem_compressed_mb", "mem_free_mb", "swap_used_mb"]
PROC_HEADER = ["timestamp", "metric", "rank", "value", "command"]


def sh(args):
    return subprocess.check_output(args, text=True)


def parse_cputime(s):
    """ps cputime: [dd-]hh:mm:ss.cc or mm:ss.cc -> seconds."""
    days = 0
    if "-" in s:
        d, s = s.split("-", 1)
        days = int(d)
    sec = 0.0
    for part in s.split(":"):
        sec = sec * 60 + float(part)
    return days * 86400 + sec


def read_procs():
    """pid -> (cputime_sec, rss_kb, command_name)"""
    procs = {}
    for line in sh(["ps", "-Aceo", "pid=,cputime=,rss=,comm="]).splitlines():
        m = re.match(r"\s*(\d+)\s+([\d:.\-]+)\s+(\d+)\s+(.*)$", line)
        if not m:
            continue
        pid, ct, rss, comm = m.groups()
        try:
            procs[int(pid)] = (parse_cputime(ct), int(rss), comm.strip())
        except ValueError:
            continue
    return procs


def read_memory():
    pages = {}
    for line in sh(["vm_stat"]).splitlines():
        m = re.match(r"(.+?):\s+(\d+)\.", line)
        if m:
            pages[m.group(1)] = int(m.group(2))
    used = (pages.get("Pages active", 0) + pages.get("Pages wired down", 0)
            + pages.get("Pages occupied by compressor", 0)) * PAGESIZE / MB
    wired = pages.get("Pages wired down", 0) * PAGESIZE / MB
    comp = pages.get("Pages occupied by compressor", 0) * PAGESIZE / MB
    free = (pages.get("Pages free", 0) + pages.get("Pages inactive", 0)
            + pages.get("Pages speculative", 0)) * PAGESIZE / MB
    m = re.search(r"used = ([\d.]+)M", sh(["sysctl", "-n", "vm.swapusage"]))
    swap_used = float(m.group(1)) if m else 0.0
    return used, wired, comp, free, swap_used


def append(path, header, rows):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        w.writerows(rows)


def tick(prev, prev_t, procs, now):
    dt = now - prev_t
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    day = datetime.now().strftime("%Y-%m-%d")

    # CPU seconds consumed per process since last tick. A pid unseen before,
    # or whose counter went backwards (pid reuse), counts its full cputime —
    # it started within this interval.
    by_cmd = {}
    total = 0.0
    for pid, (ct, rss, comm) in procs.items():
        p = prev.get(pid)
        d = ct - p[0] if (p and ct >= p[0]) else ct
        if d > 0:
            by_cmd[comm] = by_cmd.get(comm, 0.0) + d
            total += d

    cpu_pct = min(100.0, total / (dt * NCPU) * 100.0)
    load1 = sh(["sysctl", "-n", "vm.loadavg"]).split()[1]
    used, wired, comp, free, swap_used = read_memory()
    append(os.path.join(LOG_DIR, f"sys-{day}.csv"), SYS_HEADER,
           [[ts, f"{cpu_pct:.1f}", load1, f"{used:.0f}", f"{wired:.0f}",
             f"{comp:.0f}", f"{free:.0f}", f"{swap_used:.1f}"]])

    top_cpu = sorted(by_cmd.items(), key=lambda kv: kv[1], reverse=True)[:5]
    rows = [[ts, "cpu", i + 1, f"{d / (dt * NCPU) * 100:.1f}", comm]
            for i, (comm, d) in enumerate(top_cpu)]

    mem_cmd = {}
    for _, (_, rss, comm) in procs.items():
        mem_cmd[comm] = mem_cmd.get(comm, 0) + rss
    top_mem = sorted(mem_cmd.items(), key=lambda kv: kv[1], reverse=True)[:5]
    rows += [[ts, "mem", i + 1, f"{rss / 1024:.1f}", comm]
             for i, (comm, rss) in enumerate(top_mem)]
    append(os.path.join(LOG_DIR, f"proc-{day}.csv"), PROC_HEADER, rows)


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    print(f"resmon sampler started, interval={INTERVAL}s", flush=True)
    prev, prev_t = None, None
    last_cleanup = 0.0
    while True:
        started = time.time()
        try:
            procs = read_procs()
            now = time.time()
            if prev is not None and now - prev_t <= INTERVAL * 3:
                tick(prev, prev_t, procs, now)
            prev, prev_t = procs, now
            if now - last_cleanup > 3600:
                subprocess.run(["find", LOG_DIR, "-name", "*.csv",
                                "-mtime", f"+{RETENTION_DAYS}", "-delete"], check=False)
                last_cleanup = now
        except Exception as e:
            print(f"tick error: {e}", file=sys.stderr, flush=True)
        time.sleep(max(1.0, INTERVAL - (time.time() - started)))


if __name__ == "__main__":
    main()
