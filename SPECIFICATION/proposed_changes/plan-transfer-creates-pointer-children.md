---
topic: plan-transfer-creates-pointer-children
author: claude-opus-5-5
created_at: 2026-11-01T01:58:51Z
---

## Proposal: A transferred work item stays under the plan as an open pointer child until its downstream item is observed closed

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Today an archive-time transfer of remaining WORK lets a plan archive as soon as the follow-up work-items are named, even though that work is undelivered. This change keeps the transfer (execution ownership moves) but makes it non-completing: each transferred work item MUST be represented under the plan epic by one pointer child whose metadata names the downstream repository, work-item id and URL. The pointer child is an ordinary undisposed child, so the existing mechanical leg keeps the plan live; it MAY be closed only when the shared result reader observes the downstream item closed (`satisfied`). The completeness review attests requirement-carrier coverage as today and, separately, reports each pointer child's delivery state. It amends the two existing transfer sentences of "### Archive on completion" rather than adding a new clause, and adds Scenario 282.

### Motivation

Item bd-ib-e26omv ("Make plan archival proof-carrying; transfers create open pointer children"), owned by plan plan-transfer-pointer-children (epic bd-ib-7ku3pi), filed as this R1 bd-ib-j6uvkj residual under plan spec-implementation-lockstep (epic bd-ib-ax3rds), coordinator ruling 2026-11-01T00:21:09Z. Judged a FEATURE, not a bug: the item calls itself a bug, but the R290 triage (2026-10-20) found that its ask CONTRADICTS ratified text, which sanctions archiving once remaining WORK is transferred to named follow-ups, and no clause states pointer children; a change that contradicts a ratified clause is new behaviour and needs ratification. Regression provenance: livespec plan create-agent-cockpit-repo (epic livespec-livyxu) archived while agent-cockpit-info issues 2-12 carried undelivered work. Part of that regression is already governed: since the proof leg, an unproved plan ASSERTION is not transferable (Scenario 135, 'An unproved plan assertion is not transferable'), so outcomes stated as plan assertions now keep the plan live. What remains unstated is transferred WORK that no plan assertion names. The revise reviewer for plan bd-ib-7ku3pi MUST decide the design question this raises: this proposal reverses 'after which the plan is archived whole' for work-item transfers. If the reviewer prefers to keep the ratified transfer disposition, the alternative is to reject this proposal and dispose bd-ib-e26omv as governed by '### Archive on completion' plus the proof leg. Plan bd-ib-7ku3pi's own Definition of Done assertions are session-derived and unconfirmed by the maintainer (its research note 001). Transfers INTO another plan (a plan-store edit) are deliberately left unchanged.

### Proposed Changes

In SPECIFICATION/contracts.md, under "### Archive on completion", first paragraph, replace the sentence

> The one exception is an explicit handoff at archive time: every remaining piece of work MUST be transferred to named follow-up plan(s) or work-item(s), and the archive record MUST state those names exactly.

with:

> The one exception is an explicit handoff at archive time: every remaining piece of work MUST be transferred to named follow-up plan(s) or work-item(s), and the archive record MUST state those names exactly. A transfer to a work-item changes who executes the work, not whether it is done: each transferred work-item MUST be represented under the plan epic by one POINTER CHILD, a child work-item whose metadata carries `transfer_target_repository`, `transfer_target_item` and `transfer_target_url` naming the downstream repository, its work-item id and its URL. A pointer child is undisposed, and so holds the mechanical leg below, until the shared result reader of §"Shared authoritative result reader" observes its downstream item `closed` as `satisfied`; `close_plan_child` MUST refuse to close a pointer child on any other reading, naming the downstream item and the reading, and an `unobservable` reading MUST NOT close it.

In the same section, in the paragraph beginning "When a plan would close with anything unresolved", replace

> or ALL of its remaining WORK blockers are TRANSFERRED to a different or new NON-ARCHIVED plan and/or work-item, after which the plan is archived whole.

with:

> or ALL of its remaining WORK blockers are TRANSFERRED to a different or new NON-ARCHIVED plan and/or work-item, after which the plan is archived whole once every pointer child that a work-item transfer created is disposed.

In the same section, in the paragraph beginning "When a plan operation resumes or drives an archive attempt", after the sentence ending "MUST record its result durably.", insert:

> The review MUST report each pointer child's downstream item and its observed state separately from its requirement-carrier attestation; a pointer child counts as a carrier of the work it names but is not delivery evidence for it.

In SPECIFICATION/scenarios.md, append:

## Scenario 282 — A work-item transfer keeps the plan live through an open pointer child until the downstream item closes

```gherkin
Feature: A transfer moves execution ownership without completing the plan
  Scenario: A transfer creates a pointer child and the plan stays live
    Given a plan whose only remaining work is transferred to a work-item in another repository
    When the transfer is recorded at archive time
    Then the plan epic carries one pointer child naming the downstream repository, work-item id and URL
    And archive_thread refuses because that child is undisposed
  Scenario: A pointer child cannot be closed while its downstream item is open
    Given a pointer child whose downstream item reads open
    When close_plan_child is called for it
    Then it refuses naming the downstream item and the reading
  Scenario: An unobservable downstream item does not dispose the pointer
    Given a pointer child whose downstream repository cannot be read
    When close_plan_child is called for it
    Then it refuses and the pointer child stays open
  Scenario: The pointer is disposed once the downstream item closes
    Given a pointer child whose downstream item is observed closed
    When close_plan_child is called for it
    Then the pointer child is closed and the mechanical leg no longer counts it
```

Spec size: this amends two existing sentences and one paragraph of "### Archive on completion" and adds one scenario; no new section. At revise, `tests/heading-coverage.json` gains an entry for the Scenario 282 heading.
