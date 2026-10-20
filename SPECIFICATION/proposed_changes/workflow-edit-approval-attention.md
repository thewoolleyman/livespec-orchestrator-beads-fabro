---
topic: workflow-edit-approval-attention
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T23:21:28Z
---

## Proposal: needs-attention surfaces every open work-item labelled approval:workflow-edit

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The fleet's advisory workflow-edit control is notified through a LABEL, not through push automation. A maintainer authorizes an edit to `.github/workflows/` by labelling the item `approval:workflow-edit`, and that label is meant to be noticed in needs-attention. No needs-attention fact reads the label today, so an authorized item is surfaced nowhere. This proposal adds an orchestrator-owned attention fact, `hygiene:workflow-edit-approval:<work-item-id>`, composed as its own item for each open work-item carrying the label. Each item names the work-item, its status and its title, and carries a handoff that opens it for review.

### Motivation

Work-item bd-ib-qr4c7h records the maintainer's ruling of 2026-09-10 on livespec-dev-tooling-9ptz: the notification mechanism for the advisory workflow-edit control is the `approval:workflow-edit` label surfaced in needs-attention; the label is the notice, and there is no push-style automation. The dev-tooling half landed in livespec-dev-tooling PR #2246. Measured 2026-09-11 on orchestrator build 5fe72a98e59e, no needs-attention gather references the label. Plan spec-implementation-lockstep R1 batch 10 routes the item here.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Orchestrator-owned attention facts", add a new paragraph after the "**Ready-work aging (`hygiene:ready-aging:<repo>`).**" paragraph:

> **Workflow-edit approval (`hygiene:workflow-edit-approval:<work-item-id>`).** For every work-item of this repository that is not `closed` and carries the `approval:workflow-edit` label, the snapshot MUST carry one attention item naming the work-item id, its lifecycle status and its title, with a handoff that opens the item for the maintainer's review (the `discuss-work-item` operation). The label is the maintainer's notification mechanism for the advisory workflow-edit control, so the fact MUST NOT be suppressed by any other fact about the same item, and it clears only when the item closes or the label is removed. A store read that fails MUST surface as a visible failure rather than as an absence of these items. Scenario 229 in `scenarios.md` exercises this paragraph.

In SPECIFICATION/scenarios.md, add at the end of the file (tests/heading-coverage.json MUST gain an entry in the same revise):

## Scenario 229 — needs-attention surfaces an item labelled approval:workflow-edit

```gherkin
Feature: The workflow-edit approval label is the maintainer's notice
  As the maintainer authorizing an edit to .github/workflows/
  I want every open item carrying approval:workflow-edit to appear in needs-attention
  So that the advisory workflow-edit control has a surface where it is noticed

  Scenario: An open labelled item is surfaced
    Given an open work-item carrying the approval:workflow-edit label
    When the needs-attention snapshot is composed
    Then it carries hygiene:workflow-edit-approval:<work-item-id> naming the item, its status and its title
    And its handoff opens the item for review

  Scenario: A closed or unlabelled item is not surfaced
    Given a closed work-item carrying the label and an open work-item without it
    When the needs-attention snapshot is composed
    Then neither item yields a workflow-edit-approval fact
```
