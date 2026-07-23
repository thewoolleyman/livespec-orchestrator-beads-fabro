# Handoff — factory-success-rate-remediation

Thread goal: raise the dark-factory merge success rate (78% fleet-wide,
94% on this repo over 2026-06-11..2026-07-23) by remediating the
failure causes the 2026-07-23 telemetry investigation actually
measured — NOT by scaling the review stage, which the data cleared
(83% first-pass approve, ~2% terminal cause, zero detected misses).

Ledger epic anchor: `bd-ib-cvgjop` (this thread's status anchor).
Status is always READ from the ledger — compose it via the
`/livespec-orchestrator-beads-fabro:list-work-items` and
`/livespec-orchestrator-beads-fabro:next` operations; this file
deliberately carries no work queue of its own.

## Read first (in this order)

1. `research/synthesis.md` — the cross-track conclusion and the
   priority ordering of the remediation targets.
2. `research/failure-telemetry-2026-07-23.md` — the failure
   distribution the priorities rest on (raw evidence: `research/data/`,
   documented in `research/data/README.md`).
3. `research/review-fix-conflation.md` — the design-record finding
   behind child item `bd-ib-o35rcx`.
4. `research/parallel-review-support.md` and
   `research/supervisor-pattern-feasibility.md` — capability research
   consulted only if the maintainer revisits reviewer scaling or a
   watch-and-steer supervisor.

## Ledger items this thread tracks (cited read-only)

- Epic: `bd-ib-cvgjop`.
- Child filed by this thread: `bd-ib-o35rcx` (review_fix
  disposition-conflation design record; `blocked` needs-human — the
  maintainer decision and its options are in
  `research/review-fix-conflation.md` §"Options recorded for the
  maintainer decision").
- Pre-existing items the epic prioritizes (already filed before this
  thread; listed inside the epic's description): `bd-ib-nga9`,
  `bd-ib-lgv`, `bd-ib-2nq`, `bd-ib-6ka`, `bd-ib-18r`, `bd-ib-6vu`,
  `bd-ib-4sy`, `bd-ib-qq7f`, `bd-ib-sd8o`.
- Related but OUTSIDE this epic: `bd-ib-elvxv2` (Honeycomb access-path
  documentation chore; `ready`; targets the livespec repo with an
  optional vps-info pointer — do NOT drain it against this repo's
  checkout).

## Next action

1. Maintainer answers `bd-ib-o35rcx` (status-quo-with-rationale vs
   restructure; options in `research/review-fix-conflation.md`). If the
   answer is a restructure, file the resulting implementation slice(s)
   via `/livespec-orchestrator-beads-fabro:capture-work-item` as
   children of `bd-ib-cvgjop`.
2. Implementation of every ready, factory-safe item above goes through
   the FACTORY path: `/livespec-orchestrator-beads-fabro:drive --action
   impl:<id>` for a single item, or the Dispatcher drain — from this
   repo's root:
   `/data/projects/1password-env-wrapper/with-livespec-env.sh python3
   .claude-plugin/scripts/bin/dispatcher.py loop` — never the
   in-session Red→Green driver. Check readiness first via
   `/livespec-orchestrator-beads-fabro:next`. "Factory-safe" means
   in-repo, dispatchable Python/config work; outward-facing work (an
   upstream/fork fabro change, a host-production rollout such as parts
   of `bd-ib-2nq`) is not, and is hand-built instead — assess per item
   at dispatch time.
3. When the epic's tracked items are closed and the merge-rate question
   is considered answered, close `bd-ib-cvgjop` and archive this thread
   (`git mv plan/factory-success-rate-remediation/
   plan/archive/factory-success-rate-remediation/`).
