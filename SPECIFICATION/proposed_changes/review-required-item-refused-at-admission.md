---
topic: review-required-item-refused-at-admission
author: claude-opus-5-5
created_at: 2026-11-01T01:58:52Z
---

## Proposal: An item declaring a human review requirement is refused at admission before any sandbox launch

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add the `review_requirement` field to "## Work-item beads-issue mapping" as the beads label `review-requirement:human-before-merge` (absent reads back `None`, meaning no requirement), and add a **Review-free** condition to "### Admission valve (`ready → active`)": the Dispatcher MUST refuse to admit an item whose `review_requirement` is non-null, BEFORE launching any sandbox run, with a distinct named refusal reason surfaced on the journal and the needs-attention surface, without marking the item `blocked` and without retrying it into a sandbox. An item without the field dispatches exactly as before. Scenario 48 is amended with the refusal and its negative case; no heading is added.

### Motivation

Item bd-ib-qrth ("Dispatcher REFUSES AT ADMISSION for items declaring a human review requirement"), slice 2 of 3 of the livespec core arc livespec-4rq4 ("Item-level 'needs dual review' is structurally unenforceable"), which owns this item; it has no parent edge here because the arc lives in another tenant. Filed as the linked proposal plan bd-ib-ax3rds (spec-implementation-lockstep) assertion 7 requires, as part of the R1 bd-ib-j6uvkj residual batch under the coordinator ruling of 2026-11-01T00:21:09Z. Judged a FEATURE: no ratified clause of this repository states refusing an item that declares a review requirement, and the field is not in this repository's beads mapping. The batch-10 routing note held this proposal until slice 1 ratified the field's meaning in livespec-runtime; that precondition is now met: livespec-runtime-jo9 is closed, `ReviewRequirement = Literal["human-before-merge"]` and `WorkItem.review_requirement` exist in livespec-runtime's `work_items/types.py` and its SPECIFICATION/spec.md, and the vendored copy here already carries the field. The design is the 2026-07-21 supervisor ruling and maintainer decision recorded on the item: refuse at admission, NOT a `do-not-merge` label on the dispatched path (that label is inert because the pr stage arms auto-merge directly), and NOT GitHub branch protection (declined by the maintainer). Because the maintainer accepted that the guarantee rests entirely on this repository's own code, the amended scenario proves the refusal FIRES and no sandbox launches, and pairs it with the non-declaring negative case. The hand-built-path label is slice 3 of livespec-4rq4 and is out of scope here. The item's 2026-07-21 comments still bind: it stays in backlog, not routed through intake, until this proposal ratifies, because a cross-tenant dependency edge does not hold it at dispatch time.

### Proposed Changes

### contracts.md — "## Work-item beads-issue mapping"

In the opening paragraph's field list, replace "the `factory_safety` runnability field, the `awaits_scope_override` refusal-remedy signal," with "the `factory_safety` runnability field, the `review_requirement` merge-review field, the `awaits_scope_override` refusal-remedy signal,".

In the invariants block, replace "the admission valve checks capacity, dependencies, assignee, and factory-safety;" with "the admission valve checks capacity, dependencies, assignee, factory-safety, and review requirement;".

Insert, immediately after the `factory_safety` bullet and before the `awaits_scope_override` bullet:

- `review_requirement` — beads label `review-requirement:human-before-merge`, the one value of livespec-runtime's `ReviewRequirement`. An absent label reads back `None`, meaning the item declares no review requirement and dispatches as any other item. A present label declares that the item's change MUST NOT merge without a human review, and the admission valve refuses such an item (§"Admission valve (`ready → active`)" → **Review-free**). An unrecognized `review-requirement:` value MUST be read as declaring the requirement, never as `None`, so a malformed declaration fails toward refusal.

### contracts.md — "### Admission valve (`ready → active`)"

In the opening paragraph, replace "capacity, dependencies, a resolvable assignee, and factory-safety:" with "capacity, dependencies, a resolvable assignee, factory-safety, and review requirement:".

Insert, immediately after the **Factory-safe:** bullet:

- **Review-free:** an item whose `review_requirement` is non-null declares that its change MUST NOT merge without a human review, which the unattended factory path — whose pr stage arms auto-merge — cannot honour. The Dispatcher MUST refuse to admit it, BEFORE launching any sandbox run, and MUST journal and surface on the needs-attention awareness surface a refusal whose reason names the review requirement, distinct from the host-route refusal, so an operator sees why the item is not picked rather than an item that is silently ranked out. The item is NOT marked `blocked` and MUST NOT be retried into a sandbox. An item whose `review_requirement` is `None` MUST be admitted or refused exactly as it would be without this condition.

### scenarios.md — "## Scenario 48 — Dispatcher refuses a not-factory-safe item at admission"

Append, inside the scenario's gherkin block after its last scenario:

```gherkin
  Scenario: A ready item declaring a human review requirement is refused before any sandbox launch
    Given a `ready` work-item whose `review_requirement` is `human-before-merge` and whose `factory_safety` is null
    And a free WIP slot, cleared dependencies, and a resolvable assignee
    When the Dispatcher's admission valve evaluates it
    Then the item is not admitted to `active`
    And no Fabro sandbox run is launched for it
    And the journal and the needs-attention surface carry a refusal naming the review requirement
    And the item stays `ready` (it is not marked `blocked`)

  Scenario: A ready item declaring no review requirement is admitted as before
    Given a `ready` work-item carrying no `review-requirement:` label, so its `review_requirement` reads back `None`
    And a free WIP slot, cleared dependencies, a resolvable assignee, and a null `factory_safety`
    When the Dispatcher's admission valve evaluates it
    Then the item is admitted to `active` and its sandbox run is launched
```

No `## ` heading is added, renamed or removed, so tests/heading-coverage.json is unchanged. Scenario numbers 288-289 reserved for this batch are not used.
