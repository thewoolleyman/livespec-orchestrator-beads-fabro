---
topic: full-autonomous-mode
author: claude-opus-4-8
created_at: 2026-07-03T00:28:08Z
spec_commitments:
  impl_followups:
    - id_hint: orchestrator-full-autonomous-mode
      description: |
        Implement full autonomous mode in the beads-fabro Dispatcher: the dispatcher.autonomous_mode config key (default false), the orchestrate run --mode autonomous explicit opt-in, the effective-policy collapse (admission->auto, acceptance->ai-only) and LLM-resolution of blocked_reason:needs-human items, the still-escalate path for truly-unresolvable decisions, and the per-decision Dispatcher-journal audit records — each behavior linked clause->scenario->test.
---

## Proposal: Full autonomous mode (dangerous, default-off Dispatcher override)

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Add a global, dangerous, default-off full autonomous mode that, for a single explicit `orchestrate run --mode autonomous` invocation, collapses the admission and acceptance human valves to their AI/auto leg, waives store-write consent for the run, and LLM-resolves blocked_reason:needs-human items — while MUST-still-escalating any truly-unresolvable decision and journaling every auto-resolution. Governed by a dispatcher.autonomous_mode config key (default false) and specified across spec.md (intent + terminology), contracts.md (wire/config/audit), constraints.md (safety), and scenarios.md (Gherkin), composing rather than bypassing the existing valve/consent model.

### Motivation

Operator request for a 'full autonomous mode' toggle in the orchestrator so an LLM handles all possible human decisions, blocking only on the truly unresolvable; labelled dangerous / use-with-caution. This is the orchestrator-plane engine half of the cross-repo request; the console-surface half is filed in livespec-console-beads-fabro and the lean-plugin half in livespec-orchestrator-git-jsonl.

### Proposed Changes

Add **full autonomous mode** to the beads-fabro orchestrator as a global,
DANGEROUS, DEFAULT-OFF override that composes — never bypasses — the
existing valve and consent model. Touches four spec files atomically
(a behavior clause with no scenario is malformed).

### `SPECIFICATION/spec.md`
- Add a `## Terminology` entry defining **"Truly-unresolvable decision"**
  (currently unused): the residual escalation class the mode MUST still
  surface to a human.
- Add a `## Full autonomous mode` section (after §"Substrate properties",
  before §"What this spec is not"): for the current invocation the mode
  MUST treat every item's effective `admission_policy` as `auto` and
  `acceptance_policy` as `ai-only`, MUST blanket-waive store-write consent
  for the run (an invocation-scoped extension of §"Operation-class waiver"
  / §"Machine-path exemption — the Dispatcher", still creating no net-new
  work-items), and MUST LLM-resolve `blocked_reason: needs-human` items —
  EXCEPT a truly-unresolvable decision, which it MUST still escalate. The
  "no release with zero verification" floor MUST hold.

### `SPECIFICATION/contracts.md`
- Add a `## Full autonomous mode` section (after §"Dispatcher admission,
  WIP cap, and post-merge acceptance", before §"Beads connection model")
  specifying: the override semantics above; a new config key
  `livespec-orchestrator-beads-fabro.dispatcher.autonomous_mode` (MUST default
  `false`) sibling to `dispatcher.wip_cap`; a required explicit opt-in
  `orchestrate run --mode autonomous`; a Dispatcher-journal audit record
  for EACH auto-resolved decision (item id, collapsed valve, LLM decision)
  that MUST NOT be silent; a note that autonomous-mode auto-resolutions are
  a BOUNDED extension of the Machine-path exemption (no net-new
  work-items); and a gap-detectable MUST-clause block.

### `SPECIFICATION/constraints.md`
- Add a `## Full autonomous mode constraints` section (after §"Skill
  orchestration constraints", before §"Persistent Agent Knowledge
  constraints") plus a `## Forbidden patterns` bullet: default-off /
  explicit / invocation-scoped / non-inferred / non-persistent; explicit
  dangerous-mode confirmation; audit-every-resolution; MUST still escalate
  the truly-unresolvable and MUST NOT weaken the zero-verification floor.

### `SPECIFICATION/scenarios.md`
- Append Gherkin scenarios (house style) covering: auto-admit a `manual`
  item; auto-accept an `ai-then-human` item; LLM-resolve a needs-human
  block; the SAFETY scenario (truly-unresolvable still escalates); and the
  default-off / explicit-arm guard.

Every new H2 heading MUST get a `tests/heading-coverage.json` entry.
