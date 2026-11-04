# 002 — The CPU sampler used for the before and after legs (2026-11-02)

Plan assertion 5 compares CPU-seconds per live run per minute before and after the change, and it requires the SAME
method both times. This is the method. Run it on the dev VPS as the user who owns the dispatcher loops:

```bash
python3 measure_dispatcher_cpu.py <seconds> <out.json>
```

## What it measures

- It finds every process whose argv is `python3 .../dispatcher.py loop ...`.
- For each loop alive for the whole window, it takes the delta of `utime+stime` (the loop's own Python) and of
  `cutime+cstime` (every child the loop reaped during the window).
- It adds the in-window CPU of the loop's children that are still alive at the window's end.
- It divides the total by the loop count and by the window in minutes.
- It also counts the distinct `fabro <subcommand>` children spawned during the window.

## Known error terms

- A child alive at the start that exits mid-window has its pre-window CPU counted, a small over-count.
- `pidstat` interval mode misses most of the short `fabro events` children. That is why this /proc accounting is the
  method of record.

## Before figure

On 2026-11-02, 19:10:37-19:11:37Z (60 s), 15 loops used 57.8 CPU-s of their own and 57.0 CPU-s in `fabro` children. That is
7.6 CPU-s per live run per minute. Spawns in the window: events 11, inspect 10, ps 1. That 60 s window is the quick figure.

The FORMAL before figure, the one the after leg compares against, is the 20-minute window 2026-11-02 19:00:34-19:20:34Z:

| Measure | Value |
| --- | --- |
| Loops alive for the whole window | 13, load 45.6/38.7/39.8 on 18 CPUs |
| Loops' own Python | 905.3 CPU-s |
| `fabro` children | 962.9 CPU-s (37.2 of it in children still alive at the end) |
| Total | 1,868 CPU-s, about 1.56 cores |
| Per live run per minute | **7.18 CPU-s**, 0.12 of a core |
| Spawns in the window | inspect 188, events 186, ps 2 |
| Per events poll | **about 10.0 CPU-s**: 1,868 / 186, parent plus children |

The two at-most-one-tenth targets are therefore 0.72 CPU-s per live run per minute (plan assertion 5) and about 1.0 CPU-s
per live run per poll (bd-ib-u6llci's host-captured assertion).

## The sampler

```python
#!/usr/bin/env python3
"""Measure CPU spent by `dispatcher.py loop` processes and their `fabro events`/`fabro *` children.

For each loop process present for the WHOLE window, CPU = delta(utime+stime+cutime+cstime) of the loop
(cutime/cstime accrue reaped children). Also samples children each second to count distinct fabro
spawns by subcommand. Prints JSON summary.
Usage: measure_dispatcher_cpu.py <seconds> <out.json>
"""
import json, os, sys, time, collections
HZ = os.sysconf("SC_CLK_TCK")
def stat(pid):
    try:
        s = open(f"/proc/{pid}/stat").read()
    except OSError:
        return None
    f = s[s.rindex(")") + 2:].split()
    # fields after ')' start at index 3 (state); utime=14,stime=15,cutime=16,cstime=17 (1-based) -> f[11..14]
    return [int(x) for x in f[11:15]], int(f[1])
def cmd(pid):
    try:
        return open(f"/proc/{pid}/cmdline","rb").read().split(b"\0")
    except OSError:
        return []
def loops():
    out = {}
    for p in os.listdir("/proc"):
        if p.isdigit():
            c = cmd(int(p))
            if len(c) > 2 and c[1].endswith(b"dispatcher.py") and c[2] == b"loop":
                a = [x.decode() for x in c if x]
                repo = a[a.index("--repo")+1] if "--repo" in a else "?"
                out[int(p)] = repo
    return out
dur = float(sys.argv[1]); outp = sys.argv[2]
start_loops = loops(); t0 = time.time()
start = {p: stat(p)[0] for p in start_loops if stat(p)}
def kids():
    k = {}
    for q in os.listdir("/proc"):
        if q.isdigit():
            st = stat(int(q))
            if st and st[1] in start_loops:
                k[int(q)] = st[0]
    return k
kids0 = kids()
preexisting = set(kids0)
spawns = {}  # pid -> (subcmd, parent, run)
while time.time() - t0 < dur:
    for p in os.listdir("/proc"):
        if not p.isdigit(): continue
        pid = int(p)
        if pid in spawns or pid in preexisting: continue
        c = cmd(pid)
        if c and c[0].endswith(b"/fabro") and len(c) > 1:
            st = stat(pid)
            if st and st[1] in start_loops:
                spawns[pid] = (c[1].decode(), st[1], c[2].decode() if len(c)>2 else "")
    time.sleep(0.5)
t1 = time.time()
end = {p: stat(p)[0] for p in start_loops if stat(p)}
kids1 = kids()
live_child_cpu = 0.0
for k, v in kids1.items():
    a = kids0.get(k, [0, 0, 0, 0])
    live_child_cpu += (v[0] + v[1] - a[0] - a[1]) / HZ
per = []
for p, repo in start_loops.items():
    if p in end and p in start:
        d = [ (b-a)/HZ for a,b in zip(start[p], end[p]) ]
        per.append({"pid": p, "repo": repo, "self_cpu_s": d[0]+d[1], "reaped_children_cpu_s": d[2]+d[3]})
by_sub = collections.Counter(v[0] for v in spawns.values())
res = {"window_s": t1-t0, "loops_full_window": len(per), "loadavg": open("/proc/loadavg").read().split()[:3],
       "total_self_cpu_s": sum(x["self_cpu_s"] for x in per), "total_children_cpu_s": sum(x["reaped_children_cpu_s"] for x in per) + live_child_cpu, "live_children_cpu_s": live_child_cpu,
       "fabro_spawns_by_subcommand": by_sub, "per_loop": per}
tot = res["total_self_cpu_s"] + res["total_children_cpu_s"]
res["cpu_s_per_live_run_per_minute"] = tot / max(len(per),1) / ((t1-t0)/60)
res["cpu_fraction_of_one_core_per_live_run"] = tot / max(len(per),1) / (t1-t0)
ev = by_sub.get("events", 0)
res["approx_cpu_s_per_events_poll"] = (res["total_children_cpu_s"] / ev) if ev else None
json.dump(res, open(outp, "w"), indent=1, default=str)
print(json.dumps({k: v for k, v in res.items() if k != "per_loop"}, default=str))
```
