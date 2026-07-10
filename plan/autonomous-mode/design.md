# Autonomous-mode MVP — orchestrator decision-engine plan

**Repo:** `thewoolleyman/livespec-orchestrator-beads-fabro` · **Thread:**
`plan/autonomous-mode/` · **Role:** the Orchestrator-Plane decision engine — the
LLM that stands in for the operator to resolve the human gates the Dispatcher
otherwise parks, so the console's autonomous-mode toggle has something to honor.

> **Coordinated by** `livespec/plan/autonomous-mode/design.md` (the overall plan).
> **This repo publishes** the arming/audit contract the console
> (`livespec-console-beads-fabro/plan/autonomous-mode/design.md`) builds against.

---

## 1. Goal (orchestrator's half)

Build the orchestrator-side **full autonomous mode engine**: an invocation-scoped
mode that (1) collapses the two human-delegable valves to their autonomous legs
(effective `admission_policy` → `auto`, effective `acceptance_policy` → `ai-only`),
(2) adds a NEW LLM decision stage that RESOLVES `blocked_reason: needs-human` items
instead of parking them — routing a resolved item back onto its normal path — while
(3) still ESCALATING the truly-unresolvable, and (4) writing a per-decision audit
journal. It COMPOSES the already-shipped valve, escalation, cost-gate, reflection,
and consent machinery; it never bypasses it.

## 2. Current state (2026-07-10 survey)

**The spec is already a COMPLETE normative definition of this engine** (current
version v032; zero pending proposals):
- `SPECIFICATION/spec.md` §"Full autonomous mode" (lines ~145-178): a global,
  DANGEROUS, DEFAULT-OFF override of the human-delegable gates that "COMPOSES the
  existing gate, valve, and consent model" — treats every effective
  `admission_policy` as `auto`, every effective `acceptance_policy` as `ai-only`,
  and **"LLM-resolves `blocked_reason: needs-human` items … instead of parking
  them."** Guardrail: it MUST NOT auto-resolve a truly-unresolvable decision —
  "MUST still be escalated and surfaced to a human, never guessed." Arming: the
  `dispatcher.autonomous_mode` config key + `drive --mode autonomous` opt-in + a
  per-decision audit record.
- `SPECIFICATION/contracts.md` §"Full autonomous mode" (~1331-1404): MUST
  auto-approve manual items; MUST accept `ai-then-human` on a passing AI pass; MUST
  LLM-resolve `needs-human` blocks rather than surface them, routing the resolved
  item back onto its normal path; MUST still escalate truly-unresolvable. Arming
  config key defaults `false`; explicit `drive --mode autonomous` opt-in; **MUST NOT
  persist beyond the invocation.** Every auto-resolution journaled with work-item id
  + which gate collapsed (`approve`/`acceptance`/`needs-human`) + what the LLM
  decided; no auto-resolution may be silent.
- `SPECIFICATION/constraints.md` §"Full autonomous mode constraints" (~143-165): no
  silent or unbounded autonomous mode; MUST NOT be enabled by default.
- `SPECIFICATION/scenarios.md` Scenarios 33-37: auto-approve a manual item;
  auto-accept an `ai-then-human` item; resolve a `needs-human` block; still escalate
  the truly-unresolvable; default-off / explicitly-armed.

**The engine is unbuilt.** The single tracking item `bd-ib-82a` ("Implement full
autonomous mode engine", feature, backlog, `depends_on: []`, no slices;
"Consolidates 38 over-granular per-clause gap items filed in error") sits ready.
Confirmed gaps (file:line under
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/`):
- `--mode autonomous` is only a queue-drain SCOPE switch (`dispatcher.py:1365-1367`,
  header `:84-86`): `shadow` dispatches only `--item`-named items; `autonomous` takes
  the whole ready queue. It does NOT collapse any gate.
- The admission valve still HOLDS `manual`/unresolvable items
  (`_dispatcher_valves.py:190-232`); the acceptance valve still PARKS
  `ai-then-human`/`human-only` (`:235-242`, runtime park `dispatcher.py:1864-1883`);
  a `blocked` in-loop gate never auto-resumes (`dispatcher.py:100-102`); cost is
  fail-closed on unobservable (`_dispatcher_cost.py:191-230`).
- The only LLM anywhere is the out-of-band reflector `_dispatcher_reflector_oob.py` —
  a post-verdict, fail-open, default-OFF OBSERVER that files dedup issues and proposes
  human-ratified lessons and PROVABLY never changes a verdict, admits/accepts an item,
  or resumes a run. **It is an auditor, not a gate-resolution engine.**
- No `dispatcher.autonomous_mode` config key exists in code (grep finds only the
  cost-module label constant `_AUTONOMOUS_MODE = "autonomous"`).

**Machinery the engine COMPOSES (already shipped, closed):** the 7-state lifecycle +
admission valve + WIP cap + post-merge acceptance valve (`bd-ib-vvrxcb`/`dnw2ei`);
the approve/accept/reject valve actions + set-admission/set-acceptance policy edits
(`bd-ib-ew7bdv`, `q3x6va`/`7cpgeh`); in-loop human escalation + blocked-aware
dispatcher + park-at-needs-human (`livespec-impl-beads-4zl`/`bn4`); the reflection
gate + out-of-band reflector (`livespec-impl-beads-29f`); cost-observability +
fail-closed spend cap (`5v9`/`y0m`).

## 3. Steps

### O1 — spec currency + publish the arming/audit contract
The engine is fully spec'd, so this step publishes the integration contract and
executes the spec fixes Step 0 found; it does not author the engine design.
(Step 0 — the independent Fable validation, 2026-07-10, NO-BLOCKERS — already
performed the currency validation; its findings are baked into the bullets
below and recorded in
`livespec/plan/autonomous-mode/research/step0-fable-verdict.md`.)
- **Confirm internal consistency** of the v032 Full-autonomous-mode spec (spec /
  contracts / constraints / scenarios 33-37 agree).
- **File the REQUIRED irreducible-touchpoints propose-change** (Step-0 verified:
  the v032 spec does NOT say this, and in one place says the opposite). The
  truly-unresolvable definition (`spec.md` §"Terminology") is only the general
  three-pronged test (LLM confidence / unobtainable information / policy marks
  it human-only) and never names the design-human-gated decisions. Worse, the
  collapse clause auto-approves "even items whose stored `admission_policy` is
  `manual`" while §"Dispatcher grooming behavior" names `manual` admission "the
  first-class realization of the prior `human-gated` spec-change marker" — as
  written, an autonomous run would auto-admit a spec-change slice. The
  propose-change MUST:
  (a) name the design-human-gated set — drift acceptance, spec-change slices,
  and the regroom/backlog-bounce disposition (grooming stays human; a
  non-convergence bounce lands in `backlog` and escalates, never auto-groomed —
  bounces are structurally safe today because `backlog` is outside the
  collapse's reach);
  (b) define how the engine distinguishes design-gated `manual` (a spec-change
  slice) from routine `manual` admission, so the collapse never bypasses a
  by-design human gate; and
  (c) reconcile the blanket "treat every item's effective `acceptance_policy`
  as `ai-only`" with Scenario 36's `human-only` carve-out (a `human-only`
  policy is truly-unresolvable and MUST still park).
  Attribution note for the proposal rationale: only drift acceptance is
  normative livespec-core law ("the irreducible human touchpoint that survives
  even a fully autonomous orchestrator"); spec-change gating and
  regroom-stays-human are core NON-normative guidance promoted into THIS spec
  by maintainer declaration (2026-07-10) — cite them as such, never as existing
  core contract.
- **Publish the arming/audit contract (the contract-first deliverable, overall plan
  I1).** Pin exactly: the published command surface the console calls to arm/disarm
  autonomous mode, and how the console reads the per-decision audit journal.
  Step 0 sharpened the persistence-model seam (overall plan §6.1) into three
  REQUIRED pins — note the seam is NOT "the orchestrator persists nothing":
  v032 already defines a PERSISTENT permission key
  (`livespec-orchestrator-beads-fabro.dispatcher.autonomous_mode` in the
  governed repo's `.livespec.jsonc`, default `false`) ALONGSIDE the required
  per-invocation `drive --mode autonomous` flag; "MUST NOT persist beyond the
  current invocation" governs the armed MODE, not the key.
  (a) **The config key's disposition.** The console spec ALSO persists its own
  namespaced `autonomous_mode.enabled` block — two persistent booleans in the
  same `.livespec.jsonc`. Recommended: the console's
  `factory.autonomous_mode_enable/disable_requested` commands map to setting
  the ORCHESTRATOR's key (the single persistent permission), and the console's
  own block is dropped or defined as derived (console C1 owns that side).
  (b) **The loop launcher's identity.** Pin WHO reads the persistent permission
  and passes `--mode autonomous` per run. Recommended: the console's existing
  factory-drain path, extended to pass the mode while the permission is
  enabled.
  (c) **Which surface carries `--mode autonomous`.** v032 attaches it to
  `drive` (the one-action executor), but the shipped mode-bearing entry point
  is the dispatcher `loop` subcommand (`dispatcher.py:2594`); pin the surface,
  folding any wording fix into the same propose-change.
- **Route:** any real change via `/livespec:propose-change` → independent Fable
  review → `/livespec:revise`, co-editing `tests/heading-coverage.json` for any H2
  change. **Gate:** overall Step 0. **Done:** the arming/audit contract is frozen and
  cross-referenced by the console plan (unblocks console C3).

### O2 — implement the engine (`bd-ib-82a`)
- **Groom `bd-ib-82a`** into dependency-layered slices (recommend: (a) the
  `dispatcher.autonomous_mode` config key + `drive --mode autonomous` gate-collapse
  of the two valves; (b) the NEW LLM `needs-human` resolution stage +
  route-resolved-back-onto-path; (c) the truly-unresolvable escalation boundary;
  (d) the per-decision audit journal; (e) scenarios 33-37 as executable acceptance).
- **Build**, composing the shipped valve/escalation/cost-gate/reflection machinery —
  never bypassing a gate, always journaling. Respect the fail-closed cost gate
  (autonomous + unobservable cost ⇒ refuse) as an existing invariant the engine
  inherits.
- TDD Red-Green-Replay per the repo's Python ritual; worktree → PR → merge per slice.
- **Gate:** O1. **Done:** scenarios 33-37 pass with live evidence; merged slices;
  a real `drive --mode autonomous` run auto-resolves at least one manual admission,
  one `ai-then-human` acceptance, and one `needs-human` block, and escalates a
  planted truly-unresolvable item — every decision journaled.

## 4. Integration seam this repo owns half of

The console persists a durable `autonomous_mode.enabled` preference; this plane's
autonomous mode is per-invocation and MUST NOT persist. The reconciliation
(finalized in O1) keeps both invariants: the console owns the durable INTENT; this
plane owns the per-run ARMING and the DECISION + AUDIT. The published contract from
O1 is the single source of truth for how the console's toggle reaches a
`drive --mode autonomous` launch and how the console reads the audit journal.

## 5. Items to fold / track
- `bd-ib-82a` (feature, backlog) — THE engine; the whole O-track. Refresh its stale
  spec pointer (cites orchestrator v025; spec is v032).
- `plan/fabro-token-refresh/` (active, infra) — the Fabro GitHub-App installation
  token 60-minute TTL kills long factory runs at the publish/PR node. A long
  autonomous run must be able to publish. No shared code surface with gate-resolution;
  TRACK as a robustness precondition for the overall plan's I2 live exercise, do not
  fold into O2.
- Related open robustness bugs to sequence around (not part of O2's design):
  `bd-ib-18r` (blocked must be first-class outcome, not failed-and-exit), `bd-ib-6vu`
  (parked-run resume must re-project credentials) — both matter for unattended runs.
  Step-0 note on `bd-ib-18r`: an in-loop park today gets NO ledger write-back,
  so the overall plan's I2 truly-unresolvable plant MUST be ledger-level (O2's
  new escalation path serves this) — or `bd-ib-18r` triaged first — for the
  escalation leg to surface in the console.

## 6. Definition of done (orchestrator's contribution to the MVP)
O2 merged and live-exercised (§3 O2 Done). Final MVP acceptance is the overall
plan's I2 end-to-end exercise, driven from the console TUI, which this engine powers.

## 7. Discipline
Worktree → PR → merge → cleanup from the orchestrator primary checkout on
`origin/master` (note: a maintainer-owned dirty file may exist on the primary —
branch from `origin/master` and do not touch it); `mise exec -- git …`; never
`--no-verify`. Product Python changes use Red-Green-Replay; spec H2 changes co-edit
`tests/heading-coverage.json`; plan docs are `docs(plan):`. End on `master`, clean.
