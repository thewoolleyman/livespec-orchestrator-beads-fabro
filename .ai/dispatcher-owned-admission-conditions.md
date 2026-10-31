# Dispatcher-owned dispatch-admission conditions

Moved word for word from `AGENTS.md` §"The Dispatcher owns three dispatch-admission conditions — a caller adds none of them" on 2026-10-30, when the maintainer
directed AGENTS.md split into a short core plus read-on-demand `.ai/` files
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Words such as "above" and "below" point into the AGENTS.md this text came from;
the sections they name now live in the `.ai/` files AGENTS.md routes to.

## The Dispatcher owns three dispatch-admission conditions — a caller adds none of them

**Do NOT put a master-CI pre-check in front of `drive` or `dispatcher.py`.** The
governing rule is `SPECIFICATION/contracts.md` §"A caller does not gate a dispatch
on the default branch's CI", and it binds every caller alike — an operator, a launch
loop, a supervising session, a coordinator. A caller MUST NOT read the default
branch's latest CI run to decide whether to invoke a dispatch, and MUST NOT hold,
defer or skip a dispatch because that run is pending.

Why this is worth its own section rather than a line in a gate list: this repository
releases often, so the latest default-branch run is PENDING for much of any working
day, and a hand-rolled pre-check reads that pending run's EMPTY CONCLUSION as a
refusal — a confident wrong answer with no error, in front of the one mechanism
built for exactly that state. Measured 2026-10-18: nine launching sessions each held
launches that way, every one of them past a preflight that would have waited the
pending run out. The 2026-10-13 measurement that produced the bounded wait recorded
the same shape — a pending run read as a refusal pushed a retry loop onto every
caller, and those loops then raced the newer runs their own merges started (design
record: ledger epic `bd-ib-jnpvh4`; the 2026-10-18 instance is work-item
`bd-ib-zygea5`).

**These are the three admission conditions the Dispatcher owns, and a caller MUST
NOT duplicate any of them:**

1. **The bounded master-CI preflight wait.** It waits on a pending run for its
   bounded window — `WAIT_BOUND_SECONDS = 1800` at `POLL_INTERVAL_SECONDS = 60`, in
   `commands/_dispatcher_ci_preflight_wait.py`, measured from the START of the
   preflight — refuses on a run that concludes red or on an unprovable condition,
   and, when the window expires with the run still pending, returns a distinct
   PENDING outcome journaled as `status: deferred` with reason `master-ci-pending`,
   claiming no work item. A run that has not concluded has not failed, so a pending
   reading is deliberately not an outcome at all.
2. **The admission session-headroom assessment** of §"Provider spend containment" →
   "Admission filters candidates by projected Claude session headroom". Under that
   clause's enabling conditions and exceptions its skips are candidate-local: the
   dispatch proceeds while every admission-required node retains an eligible
   candidate, and otherwise a `ready` item stays `ready` and a parked rework item
   stays parked, with no new claim, until the scheduled reevaluation.
3. **Plugin build currency** per §"Self-contained plugin dispatch" → "The
   dispatch-admission path MUST NOT block on ambient release-staleness". A build
   lagging the latest release is **surfaced as a warning** — the
   `dispatcher-registered-install-lag` line the dispatcher journals and prints on
   stderr — and refused only below a committed `dispatcher.minimum_release` floor,
   which is the only blocking currency form there is. Keeping a long-lived session
   bound to the registered build is the operator's duty (§"Stop the line for
   breakages"), not an admission condition.

**What a launch loop MAY add on its own**, because the Dispatcher does not own it:
capacity on the factory host (its measured idle CPU, for instance), the availability
of a launch slot the loop schedules itself, and the spacing between launches. Such a
gate decides only WHEN the loop invokes a dispatch, and it MUST NOT re-implement,
pre-empt or stand in for any of the three conditions above. Note also that a
loop-scheduled launch slot is not a second repository-capacity authority: any
repository-capacity observation a caller makes consumes the authoritative projection
of §"Orchestrator-owned attention facts" → "Capacity single authority".

Read `.ai/master-ci-green-preflight.md` for what the master-CI surfaces actually say
and the three ways a hand-rolled watcher of them gets a confident wrong answer — to
understand a refusal you have already been given, never to pre-empt one.
