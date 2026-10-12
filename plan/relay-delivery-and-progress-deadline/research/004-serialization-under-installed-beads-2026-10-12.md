# Per-epic write serialization under the installed Beads surface

> **WITHDRAWN RECOMMENDATION (2026-10-12).** The maintainer ruled the
> single-host writer assumption invalid: writes may come from several hosts,
> containers or cloud instances that share no state except the Beads server.
> Option A below, the host-root kernel fence, and the "Measurement 3"
> topology argument therefore do not hold. Measurements 1 and 2 stand. Read
> `005-cross-host-serialization-by-conditional-close-2026-10-12.md` for the
> current analysis.

Written 2026-10-12 by the restarted relay session (Claude Code, session
`relay-delivery-and-progress-deadline`). It consumes the Beads PR 1 closure
and the stall plan's local-alternatives investigation, adds two measurements
that investigation did not take, and recommends the design route for
`bd-ib-zi5ygh`.

## What was reconciled

- [Beads PR 1](https://github.com/thewoolleyman/beads/pull/1) is CLOSED, not
  merged, at 2026-10-12T06:23:43Z, head `e82e0f4e`, no reviews. The closure
  comment, made at the maintainer's direction, withholds any Beads change
  until a local alternative is shown to fail the requirement or to be
  substantially inferior or more complex.
- The `bd-ib-vvf45c` comment of 2026-10-12T06:25:25Z assigns that
  local-alternatives investigation to the stall plan owner (session
  `agent-session-stall-prevention`, plan epic `bd-ib-jnpvh4`).
- That investigation exists. It is research note
  `plan/agent-session-stall-prevention/research/004-local-serialization-before-beads-change-2026-10-12.md`,
  committed as `759f5925` on branch `docs/stall-local-recovery-alternatives`.
  At the time of writing that branch was not yet pushed and had no pull
  request, so this note cites it as that session's work in progress. Its
  finding is that necessity of changing Beads has NOT been established. A
  per-epic kernel ownership descriptor under one declared host root, plus one
  metadata update carrying the new authority and its operation receipt, passed
  eleven real-process controls against the installed `bd 1.2.2 (6c124203e)`.
  It names two limits. That form conflicts with
  `SPECIFICATION/constraints.md` §"Process boundaries". And it protects only
  writers that share one host and one root.

## The governing conflict

`contracts.md` §"Required result, budget and progress epoch" requires:
"Writes MUST serialize per epic and detect a stale prior epoch before
mutation." `constraints.md` §"Process boundaries" says that concurrency on the
tenant database "is owned by the shared `dolt sql-server`'s transaction
lifecycle (auto-commit OFF; the server serializes writes). The plugin adds no
lockfile and no advisory lock".

The constraint is correct only if the server's serialization covers the
plugin's read, validate and write sequence. The measurement below shows that
it does not, even for a single `bd update`.

## Measurement 1: concurrent distinct top-level metadata keys lose updates

The question was whether an append-only event store could be built from
metadata by giving each writer its own top-level key. `AGENTS.md` records that
`bd update --metadata` merges at the top level. If that merge happened inside
one server transaction, two concurrent writers of different keys would both
survive.

Method. The probe used one owned disposable record,
`bd-ib-relay-probe-583fa5101e`, created with `--no-history` and deleted
afterwards (`bd show` exit 1 after deletion). All calls went through the public
`/usr/local/bin/bd`, run from the tenant root under `with-livespec-env.sh`. A
sequential control wrote `seq_a`, then `seq_b`. Both survived beside the
original `base` key, which proves that the probe can see a surviving key. Then
there were twelve trials. In each, two separate processes released at the same
wall-clock instant each wrote one distinct top-level key with `bd update
<id> --metadata '{"<key>":1}'`.

Result: in **3 of 12** trials, **both processes exited 0 and one key was
absent** on read-back (trials 3, 10 and 11; two lost the second writer's key,
one lost the first's). No process exited non-zero, and the untouched `base`
key survived every trial.

Reading. The public metadata merge is a client-side read-modify-write, not a
merge inside the server's transaction. A concurrent writer's committed key is
silently overwritten, with success reported to both callers. So the server
does NOT serialize the plugin's logical writes, even when no two writers touch
the same key. A metadata-keyed event log is not a safe lock-free design.
Probe source SHA256:
`407cfb8ff541da31d38a389cb560f7e25485defebc052328d91cc94b63fba0cd`.

## Measurement 2: concurrent native comment appends all survive

Method. The probe used one owned disposable record,
`bd-ib-relay-probe-20c9f4550c`, set up and cleaned up in the same way. There
were ten trials. In each, three separate processes released at the same
instant each ran `bd comments add <id> <unique marker>`.

Result: **30 of 30** appends survived, and all exits were 0. `bd comments
--json` returns rows sorted by `created_at`. That field has one-second
resolution, and 15 of the 30 rows shared a timestamp with another row. Comment
ids are UUIDv7 values such as `01a12f02-2e6b-7b7f-...`, which are
time-ordered at millisecond resolution with a random tail. Probe source
SHA256: `12f3676e62b523189ec863075572103035883affbb1f2a8b79a00a1f6f5e972f`.

Reading. Comments are a durable append-only log under concurrency. But the
probe does not establish that the id order equals commit order. An append
whose id was generated earlier can become visible after a reader has already
reduced the log. A comment-log design therefore needs a settle rule before a
reduction may treat a winner as final. That is the gap the stall note
describes as "no exclusive execution ownership".

## Measurement 3: the actual writer topology is one host

The tenant's Dolt server listens on `127.0.0.1:3307` only (`ss -ltnp`: owned
by `dolt`, bound to loopback). `tailscale serve status` shows no proxy for
port 3307, and `.beads/config.yaml` pins `dolt.server-host: 127.0.0.1`. Every
sanctioned writer of this tenant therefore runs on this host. Factory
sandboxes on `hp` cannot write it (measured in prerequisite run
`01M4FC8VTGGRS5F537NAA7ZYP7`, as recorded on `bd-ib-zi5ygh`). The stall note
named the topology as "the key choice". A single-host owner with one declared
root is the topology that actually exists, not an assumption made for
convenience.

## Options and recommendation

| Option | Meets "serialize per epic, detect stale epoch before mutation"? | Cost |
| --- | --- | --- |
| A. Narrow amendment to §"Process boundaries": plan-authority writers take a per-epic kernel ownership descriptor under one declared host root, held across the read, validate and metadata write, with no lease expiry and never unlinked | Yes. The stall note measured it with eleven controls, including crash before and after the write, a live owner not stolen, a dead parent with a live write child, and stale refusal. | One spec amendment through the normal propose-change and revise path. It protects only same-host writers, which is the measured topology. |
| B. Lock-free comment-log reduction | Only with a settle rule, because append order is not commit order. Stale detection happens after the append, not before mutation. | Every reader of `next_action` becomes a reduction over the log, receipts grow without a bound, and it still needs the stall plan's fenced ownership for recovery execution. That is substantially more complex. |
| C. Beads conditional transition (PR 1) | Yes, across hosts. | Closed by the maintainer. A cross-host requirement does not exist (Measurement 3), so necessity is not established. |
| D. Keep §"Process boundaries" unchanged and rely on Dolt | No. Measurement 1 shows silent lost updates with exit 0. | None, and it is wrong. |

**Recommendation: Option A.** Measurement 1 shows the constraint's stated
premise is false for the plugin's actual write path, so a narrow amendment
corrects the specification to match a measured fact rather than waiving a
rule. It is the local solution the maintainer's ruling asks to exhaust before
any Beads change. On the measured topology it is not inferior to C. The
amendment should be one clause, scoped to plan-authority and obligation
writers. It names the declared root, forbids unlinking and timed lease steal,
requires that a write child inherit the descriptor, and keeps the existing
bans on per-write `DOLT_COMMIT`, direct plugin SQL, daemons and a second
canonical ledger. The stall plan's recovery-execution fence
(`contracts.md`: "serialized generation-fenced ownership") would rest on the
same clause, so one amendment serves both plans.

## Consequence for `bd-ib-zi5ygh`

The latest review of the zi5ygh terminal artifact flagged the worker's
abstract-socket plugin lock as prohibited. Under Option A, a kernel-scoped
per-epic fence becomes the sanctioned mechanism. Whether the preserved
artifact's fence meets the amendment's specific terms is a review question
and is not claimed here. The terms are the declared root, no steal, child
inheritance and the stale-epoch check before the write. Its separately
recorded defects remain owed regardless: the missing or legacy
`next_action` crash in the diagnosis handler, and the unproved causal host
recovery path. Retrieve it with `fabro dump 01M4HQQZJCNP5HZ89M80PYCHXK
--server https://hp-xubuntu.perch-rudd.ts.net:32276`, then verify
`stages/003-implement@1/diff.patch` against SHA256 `912547bd…dea9`.

## Probe sources

Both probes ran as `with-livespec-env.sh -- python3 -I <probe> <out-dir>
<trials> [<width>]` from the tenant root. Each probe deletes only the one
record it created.

```python
# distinct_keys.py — trials of two concurrent distinct-key metadata writes
import json, subprocess, sys, time, uuid
from pathlib import Path
ROOT = "/data/projects/livespec-orchestrator-beads-fabro"
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
TRIALS = int(sys.argv[2])
def bd(*a, check=True):
    r = subprocess.run(["/usr/local/bin/bd", *a], cwd=ROOT, capture_output=True, text=True, timeout=60)
    if check and r.returncode: raise RuntimeError(f"bd {a[:2]} exit {r.returncode}: {r.stderr[:400]}")
    return r
def meta(item):
    return json.loads(bd("show", item, "--json").stdout)[0].get("metadata") or {}
item = "bd-ib-relay-probe-" + uuid.uuid4().hex[:10]
results = []
try:
    bd("create", "--id", item, "--type", "task", "--title", "Disposable relay distinct-key concurrency probe",
       "--description", "Owned finite experiment; not a work item.", "--no-history",
       "--metadata", json.dumps({"base": {"v": 0}}), "--json")
    bd("update", item, "--metadata", json.dumps({"seq_a": 1}), "--json")
    bd("update", item, "--metadata", json.dumps({"seq_b": 1}), "--json")
    m = meta(item); assert {"base", "seq_a", "seq_b"} <= m.keys(), m
    results.append({"case": "sequential_control", "keys": sorted(m)})
    for t in range(TRIALS):
        ka, kb = f"t{t}_a", f"t{t}_b"
        go = time.time() + 1.0
        procs = []
        for k in (ka, kb):
            script = (f"import time,subprocess,json;time.sleep(max(0,{go}-time.time()));"
                      f"r=subprocess.run(['/usr/local/bin/bd','update','{item}','--metadata',json.dumps({{'{k}':1}}),'--json'],"
                      f"cwd='{ROOT}',capture_output=True,text=True);print(json.dumps({{'exit':r.returncode,'err':r.stderr[-300:]}}))")
            procs.append(subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True))
        outs = [json.loads(p.communicate(timeout=90)[0]) for p in procs]
        m = meta(item)
        results.append({"trial": t, "exits": [o["exit"] for o in outs], "errs": [o["err"] for o in outs if o["exit"]],
                        "a_present": ka in m, "b_present": kb in m, "base_intact": m.get("base") == {"v": 0}})
finally:
    bd("delete", item, "--force", check=False)
    gone = bd("show", item, "--json", check=False).returncode
    (OUT / "receipt.json").write_text(json.dumps({"item": item, "results": results, "cleanup_show_exit": gone}, indent=1))
```

The comment probe has the same shape. It creates the record without
metadata, and each trial releases WIDTH processes, each running
`bd comments add <item> probe-t<trial>-w<n>`. It then counts which markers
appear in `bd comments <item> --json` (field `text`) and records `(created_at,
id)` order and timestamp ties.
