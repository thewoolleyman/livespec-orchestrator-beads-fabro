# Autonomous-mode MVP — orchestrator plan handoff

**Status:** DRAFT — awaiting the overall Step-0 multi-model (Fable) validation pass
before implementation. First-drafted 2026-07-10 from a repo survey.

**Repo:** `thewoolleyman/livespec-orchestrator-beads-fabro` · **Role:** the
Orchestrator-Plane decision engine (the LLM gate-resolver). Driven from the delegate
session `orchestrator-autonomous-mode`.

## Read first
1. This file, then `design.md` here.
2. The overall plan: `livespec/plan/autonomous-mode/design.md`.
3. The console plan (which consumes this repo's arming contract):
   `livespec-console-beads-fabro/plan/autonomous-mode/design.md`.
Then derive live status from the ledger — it is authoritative.

## The one-line state
The engine is ALREADY fully spec'd (v032 — `spec.md`/`contracts.md`/`constraints.md`
§"Full autonomous mode", scenarios 33-37) and UNBUILT. Today `--mode autonomous` is
only a queue-drain scope switch; the valves still hold/park; the only LLM present is
a post-verdict observer, not a resolver. One backlog item tracks the whole build:
`bd-ib-82a` "Implement full autonomous mode engine" (`depends_on: []`, no slices).

## Steps (design.md §3)
- **O1** spec currency + PUBLISH the arming/audit contract (the contract-first
  deliverable that unblocks console C3): confirm v032 internal consistency, confirm
  the truly-unresolvable set includes the core irreducible touchpoints (drift-accept /
  spec-change / regroom), and pin how the console's persistent intent reaches a
  per-invocation `drive --mode autonomous` launch (the persistence-model seam). Route
  any real change via propose-change → Fable review → revise.
- **O2** implement `bd-ib-82a` in slices: `dispatcher.autonomous_mode` config key +
  `drive --mode autonomous` gate-collapse (admission→auto, acceptance→ai-only) + the
  NEW LLM `needs-human` resolution stage (route resolved back onto path) +
  truly-unresolvable escalation + per-decision audit journal. Compose the shipped
  valve/escalation/cost-gate/reflection machinery; never bypass a gate.

Gate: O1 → O2. O1's arming contract is published EARLY (overall I1) so console C3 can
build in parallel.

## Hard boundary
The engine MUST leave the irreducible human touchpoints (drift acceptance,
spec-change slices, regroom/backlog-bounce) as escalated needs-attention — they are
truly-unresolvable BY DESIGN, not by low confidence. Respect the existing fail-closed
cost gate (autonomous + unobservable cost ⇒ refuse).

## Track, don't fold
`plan/fabro-token-refresh/` (active infra: 60-min App-token TTL kills long runs) — a
robustness precondition for the overall I2 live exercise, no shared code with O2.
Open bugs to sequence around: `bd-ib-18r` (blocked as first-class outcome), `bd-ib-6vu`
(parked-run credential re-projection).

## Next action
After overall Step 0 passes NO-BLOCKERS, start O1: validate v032 currency and publish
the arming/audit contract; then groom `bd-ib-82a` into slices for O2. Refresh
`bd-ib-82a`'s stale spec pointer (cites v025; spec is v032).

## Pointers
- Ledger read: `bd list --json` from inside this repo (tenant database
  `livespec-orchestrator-beads-fabro`; `bd-ib-*` / `livespec-impl-beads-*` ids).
- Discipline: worktree → PR → merge → cleanup; branch from `origin/master` (do not
  touch any maintainer-owned dirty file on the primary); `mise exec -- git …`; never
  `--no-verify`; Python product changes use Red-Green-Replay; spec H2 changes co-edit
  `tests/heading-coverage.json`; plan docs are `docs(plan):`.
