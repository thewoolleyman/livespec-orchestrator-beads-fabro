---
topic: a-parked-plan-child-that
author: claude-opus-5-5:delegated-gate-fleet-rollout
created_at: 2026-10-29T08:12:16Z
---

## Proposal: A dispatcher verb that classifies one work-item's spec-change tier without dispatching it

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add `dispatcher.py classify-tier --repo <path> --item <id>`, a classification-only path that records a work-item's spec-change tier through the same spec-stated judgement the pre-dispatch wall uses, and dispatches nothing. Generalize §"Terminology" so the classification stages it names include this one.

### Motivation

Plan-child disposition (constraints.md §"Not-human-gated decision constraints") admits only a child whose autonomy tier is known and not spec-change, and correctly refuses one whose tier cannot be determined. A `livespec-spec-change-tier` record is written today only at four stages: filing, groom, the pre-dispatch wall, and the release-spec-tier human valve. A child filed before the tier guard existed and parked never-dispatch (admission:manual, blocked-reason:needs-human) never passes filing or dispatch again. So it can never be classified, never be closed or re-parented, and its plan can never archive. Measured 2026-10-29: re-parenting livespec-dev-tooling-ljhi4j from plan epic livespec-dev-tooling-mvalxq to livespec-dev-tooling-dfixhe (coordinator ruling R201) was refused with nothing written. The dispatcher has no classify verb, and `loop --dry-run` is read-only by design. The disposition refusal itself is correct and is NOT relaxed by this proposal. This proposal gives the refused child a sanctioned way to acquire the datum the refusal needs. Carrier: bd-ib-sappap. Coordinator ruling: R205.

### Proposed Changes

1. spec.md §"Terminology": where the spec-change tier and its classification stages are defined, add a fifth stage, `classify`. It is a standalone classification of one work-item, requested by an operator or session through the dispatcher's `classify-tier` verb. It decides the tier through the same spec-stated judgement as the other stages. It records the result in the same `livespec-spec-change-tier` record shape, with `stage: classify`. It is never a dispatch.

2. contracts.md: add `## Dispatcher classify-tier invocation surface` beside §"Dispatcher loop invocation surface", stating:
- `dispatcher.py classify-tier --repo <path> --item <id> [--json]` MUST classify the named work-item's spec-change tier through the same spec-stated judgement the pre-dispatch wall uses.
- When the item carries no `livespec-spec-change-tier` record, it MUST append exactly one such record, with `stage: classify`.
- It MUST NOT dispatch: it creates no Fabro run, claims nothing, and leaves the item's assignee unchanged.
- When the recorded tier is not a held spec-change tier, it MUST leave the item's status and labels unchanged.
- When the recorded tier IS a held spec-change tier, the hold applies exactly as it does when filing or dispatch records that tier, and it is released only as those holds are.
- When the item already carries a `livespec-spec-change-tier` record, it MUST append nothing and MUST report the existing classification.
- It MUST exit non-zero, writing nothing, when the judgement cannot be obtained.

3. scenarios.md: add `## Scenario 259 — A parked plan child acquires its spec-change tier without being dispatched, so its disposition can proceed`.
- Given a plan child that carries no `livespec-spec-change-tier` record and is parked so that it is never dispatched, and `reparent_plan_child` refuses it as undeterminable;
- When an operator runs `dispatcher.py classify-tier --repo <repo> --item <child>`;
- Then exactly one `livespec-spec-change-tier` record with `stage: classify` is appended, no Fabro run is created, and the child's assignee is unchanged;
- And when the recorded tier is not spec-change, the child's status and labels are unchanged, and a following `reparent_plan_child` moves it and records the disposition;
- And when the recorded tier is a held spec-change tier, the disposition stays refused, exactly as the constraint requires;
- And a second `classify-tier` run appends nothing and reports the existing classification.

Revise co-edit: the two new H2s need `tests/heading-coverage.json` entries (tier-named reasons naming bd-ib-sappap as the owner) and a regenerated debt register in the revise commit.
