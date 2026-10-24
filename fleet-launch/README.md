# `fleet-launch/` — PROVISIONAL and EXPERIMENTAL fleet launch scripts (stopgap)

**This directory is a provisional, experimental stopgap.** It captures a dispatch
pattern that emerged during one plan, petri-factory-on-gmktec (epic `bd-ib-fyozyd`),
so that the scripts the factory seats run are committed, reviewed and tested instead
of living uncommitted under `tmp/`. It is not the design the fleet should keep.

**The preferred means is first-class, not this directory.** Fleet launch should be
driven through the livespec console application, whose track is on hold, or through a
committed, tested launch-loop tool: work-item `bd-ib-jr6w7v`. This directory points at
both. New capability belongs there, not here.

**Retirement condition.** Delete this directory once every factory launch on the
operator host is made by the console application or by the `bd-ib-jr6w7v` launch-loop
tool, and no seat runs a script from here. The plan that committed it is
provisional-fleet-launch (epic `bd-ib-klkbxp`).

## Why it is caller-side, and the Dispatcher is untouched

`SPECIFICATION/contracts.md` §"Host concurrency belongs to the Fabro scheduler" (spec
v053) gives the Dispatcher no host-level concurrency limit, admission gauge or lock;
`wip_cap` is its only concurrency control. The admission section (§"Dispatcher
admission, WIP cap, and post-merge acceptance") lets a caller add gates of its own for
conditions the Dispatcher does not own: host capacity, a launch slot the caller
schedules, and launch spacing. Everything here is such a caller-side gate. These
scripts decide only WHEN to invoke `drive --action impl:<item>`; they never stand in
for the Dispatcher's own admission conditions.

## What is here

| File | What it does |
| --- | --- |
| `config.sh` | The one place a host-specific value is set: factory server URLs, the fabro client path, the fleet-cap and hold files, the queue, lock and in-flight directories, the plugin registry and cache, the wrappers and the timings. Every value can be overridden from the environment. |
| `dispatch-dual.sh` | Launches one work-item. Gates, in order: the Dispatcher's ready set, the shared fleet cap, the launch-time Definition-of-Done preflight, the hold file, gmktec's own ceiling and idle CPU, a per-factory FIFO ticket and mutex, a binding re-count including this launch's in-flight marker, and a usable-credential probe. |
| `ready-set-check.py` | Asks the installed plugin build's own `ready_items()` whether an item is dispatchable, so the answer cannot diverge from the Dispatcher's selection. |
| `release-hold-on-caam-rotation.sh` | Keeps the hold file in place until caam's active Claude profile changes, then removes it. |
| `resolve-default-factory.sh` | Prints a repository's committed `dispatcher.default_factory` from its origin default branch. |
| `host-capture-payload.py` | Builds a `host_recorded` Proof-of-Done payload from a registry-resolved capture dispatch; refuses, writing nothing, when any evidence is missing. |
| `wrappers/` | PATH-keeping shims around each independent tenant's committed credential wrapper, passed as `WRAPPER=` to `dispatch-dual.sh`. `homelab-wrapper.argv` holds parameter-store PATHS, never secret values. |

## Running a launch

Run it from a checkout of this repository's `master`, never from a copy under
`tmp/`, and through the detached gate runner so it outlives the calling session:

```bash
mise exec -- just gate-start -- bash -c 'env ONLY_GMK=1 fleet-launch/dispatch-dual.sh <item-id> >> <state-dir>/seq-<item-id>.log 2>&1'
```

For an independent tenant, add `REPO_OVERRIDE=/data/projects/<repo>` and
`WRAPPER=<path>/fleet-launch/wrappers/with-<repo>-env-keep-path.sh`. For a
registry-resolved capture dispatch, add `CAPTURE_NULL=1 CAPTURE_EXPECT=petri`. To keep
a queue position across a restart, pass the old ticket's number as `TICKET_NS`.

The state directory (`FLEET_LAUNCH_STATE_DIR`) holds data only: logs, verdicts, the
shared `fleet-cap` file and the `hold-gmktec` file. It never holds a script.

## Behaviour recorded at commit time

Ported from the seat launcher `dispatch-dual-r681b.sh` as it ran on 2026-10-24, with
three deliberate differences:

- The retired factories (hp-xubuntu and vps) are no longer read at all; the fleet
  count is gmktec plus mi-homelab plus launches not yet listed.
- The hold file pauses every launch, mi-homelab included; the seat version paused
  only gmktec launches.
- A capture dispatch locates its run only by process ancestry from the drive process,
  and the final `drive rc=` log line carries a timestamp.

Known defects that shaped it, each fixed here: a launcher reading a stopped factory's
board saw the fleet as unknown and never launched (2026-10-24, 13:07Z to 14:37Z); an
early FIFO ticket was dropped when a binding count failed, losing its queue place; and
an edit that appended a trailing comment to a multi-statement line silently dropped
the mi-homelab board read, which `bash -n` could not catch. The last is why this
directory's check target runs a hermetic harness, not only a syntax check.
