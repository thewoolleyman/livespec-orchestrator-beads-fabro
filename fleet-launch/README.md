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
| `board-snapshot.sh` | The shared factory-board reader both launchers source. Every launcher on the host reads a factory's board through one snapshot file refreshed at most once per `FLEET_LAUNCH_BOARD_TTL_S`, because one run listing costs the petri server 25-40 s; an unreadable refresh is an unknown count, never zero, and the binding count under the launch mutex reads the factory directly. |
| `dispatch-dual.sh` | Launches one work-item. Gates, in order: the Dispatcher's ready set, the repository hold file, the repository WIP gate (counted claims against `wip_cap`, one above for an item in `breakage-exception`; an unreadable count never holds), the shared fleet cap, a fast-forward of the checkout to origin's default branch and then the launch-time Definition-of-Done preflight, the gmktec hold file, the gmktec target setting (default or candidate instance, the candidate only below `FLEET_LAUNCH_GMK_CANDIDATE_CAP`), gmktec's own ceiling and idle CPU, a per-factory FIFO ticket and mutex, a binding re-count including this launch's in-flight marker, and a second checkout fast-forward and a usable-credential probe. A drive that exits non-zero before its run lists re-takes a ticket at the same ticket number after the delay its consecutive early-exit count selects, except a failed `goal-minijinja-preflight` stage or an exit `5`, which end the launcher with a terminal line and one ledger comment. After it invokes the drive it re-reads every applicable hold on each poll until the item reads `active`, the run lists or the drive exits; a hold set while the item still reads `ready` stops the drive with TERM, keeps the FIFO ticket at its number and logs the hold, and a stop that finds the item `active` makes a `stopped-after-admission` non-run exit with one ledger comment (Scenario 330). |
| `ledger-item.py` | Reads a work-item's ledger status or appends one ledger comment to it through the installed plugin build's own store seam; the launcher uses it to tell `ready` from `active` after a stop. |
| `launcher-versions.sh` | Read-only readback: lists every running `dispatch-dual*.sh` and `resume-capped*.sh` launcher with the version (first 12 hex digits of the sha256) of the script content it is executing, read from bash's open file descriptor, and the version of the script file on disk, and marks each launcher whose two differ `STALE`. |
| `ready-set-check.py` | Asks the installed plugin build's own `ready_items()` whether an item is dispatchable, so the answer cannot diverge from the Dispatcher's selection. |
| `release-hold-on-caam-rotation.sh` | Keeps the hold file in place until caam's active Claude profile changes, then removes it. |
| `resolve-default-factory.sh` | Prints a repository's committed `dispatcher.default_factory` from its origin default branch. |
| `host-capture-payload.py` | Builds a `host_recorded` Proof-of-Done payload from a registry-resolved capture dispatch; refuses, writing nothing, when any evidence is missing. |
| `wrappers/` | PATH-keeping shims around each independent tenant's committed credential wrapper, passed as `WRAPPER=` to `dispatch-dual.sh`. `homelab-wrapper.argv` holds parameter-store PATHS, never secret values. |
| `test/run-tests.sh` | The hermetic harness run by `just check-fleet-launch`; it uses stub boards, credentials, preflights, queue, lock, in-flight and state directories, never a live factory. |

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

A running bash launcher executes the script content it started with, so a hold check added
to the script later never reached it (bd-ib-5ycmsm). Both launchers therefore compare their
script on disk with the content they started on at the top of every wait loop and again
after they bind at the launch point, and re-execute themselves when it differs, keeping
their pid, FIFO ticket and give-up deadline. Replace a launcher script atomically (write
beside it, then `mv`); an in-place edit corrupts a running bash. A launcher started before
this change cannot re-execute itself, so after any change to a hold or guard, run
`fleet-launch/launcher-versions.sh` and restart each launcher it marks `STALE` (pass its old
ticket number as `TICKET_NS` to keep its place) before relying on the change. `config.sh` and
`board-snapshot.sh` are read when a launcher starts and are not part of the version.

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
