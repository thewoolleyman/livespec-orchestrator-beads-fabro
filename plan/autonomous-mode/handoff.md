# Autonomous-mode MVP — orchestrator plan handoff

**Status:** round 1 of the overall plan's fable-review LOOP is done (2026-07-10:
Step-0 validation NO-BLOCKERS, then this plan REVISED per its findings — full
verdict: `livespec/plan/autonomous-mode/research/step0-fable-verdict.md`). The
loop is still OPEN: O1 MUST NOT start until the overall plan's Step-0 gate is
met — a FRESH Fable session review finds nothing blocking AND the MAINTAINER
certifies (loop state: `livespec/plan/autonomous-mode/handoff.md`).
First-drafted 2026-07-10 from a repo survey.

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
- **O1** publish the arming/audit contract + execute the Step-0 spec fixes (the
  contract-first deliverable that unblocks console C3). Two REQUIRED deliverables
  (design.md §3 has the full text): (1) the irreducible-touchpoints
  propose-change — Step 0 verified the v032 spec does NOT protect the
  design-human-gated decisions and its `manual`-admission collapse would
  auto-admit a spec-change slice; the change names the set (drift-accept /
  spec-change / regroom), splits design-gated `manual` from routine `manual`,
  and reconciles the `human-only`-acceptance carve-out; (2) the arming contract
  pinning the `dispatcher.autonomous_mode` key's disposition versus the
  console's intent block, the loop launcher's identity, and whether `drive` or
  the dispatcher `loop` carries `--mode autonomous`. Route via propose-change →
  independent Fable review → revise.
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
WAIT for the overall plan's fable-review loop to exit — a FRESH Fable session
finds nothing blocking AND the maintainer certifies
(`livespec/plan/autonomous-mode/handoff.md` records the loop state). Only then
start O1: file the two required deliverables above, then groom `bd-ib-82a`
into slices for O2. Refresh `bd-ib-82a`'s stale spec pointer (cites v025; spec
is v032).

## Pointers
- Ledger read: `bd list --json` from inside this repo (tenant database
  `livespec-orchestrator-beads-fabro`; `bd-ib-*` / `livespec-impl-beads-*` ids).
- Discipline: worktree → PR → merge → cleanup; branch from `origin/master` (do not
  touch any maintainer-owned dirty file on the primary); `mise exec -- git …`; never
  `--no-verify`; Python product changes use Red-Green-Replay; spec H2 changes co-edit
  `tests/heading-coverage.json`; plan docs are `docs(plan):`.
