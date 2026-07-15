# Handoff — force-factory (livespec-orchestrator-beads-fabro)

**Thread:** `plan/force-factory/` · **Ledger anchor:** epic `bd-ib-y2xro4`
(this repo's beads tenant). The thread makes invoked plan handoffs route
implementation work through the Fabro factory instead of defaulting to
in-session manual work.

> Status is **derived from the ledger**, never stored in this file:
>
> ```bash
> source /data/projects/1password-env-wrapper/with-livespec-env.sh \
>   bd -C /data/projects/livespec-orchestrator-beads-fabro show bd-ib-y2xro4
> ```
>
> Cross-repo children live in the `livespec-dev-tooling` tenant
> (livespec-dev-tooling-g5xste, livespec-dev-tooling-64x6mb) — read them with the same command against
> `/data/projects/livespec-dev-tooling`. A trailing `auto-backup failed …
> command denied` warning is correct-by-design tenant confinement, not
> an error.

## Read first (in order)

1. `plan/force-factory/findings.md` — the incident record, the
   maintainer's right-sized decision (prose-first + handoff lint +
   report-only audit counter), why the factory worker is unaffected,
   and the deferred enforcement ladder for escalation.

## Next action (one path)

Run the status-read command above. All five children were executed
2026-07-15 under explicit maintainer direction (recorded per the
exception discipline this thread itself introduces). Any child still
open that changes product code goes through the factory: dispatch it
via the `drive` operation (action `impl:<id>`) or let the Dispatcher
drain it once `ready`, then monitor to merged-PR + closure — do NOT
drive it in-session (the in-session Red→Green driver is reserved for
factory-ineligible items, factory outages, or explicit maintainer
direction, with the reason recorded). When every child is closed and
the factory-bypass audit counter has run clean for a while, propose
closing the epic and archiving this thread; if the counter shows
violations instead, escalate per the ladder in `findings.md`.

## Resume command

```
/livespec-orchestrator-beads-fabro:plan force-factory
```
