---
topic: workflow-edit-approval-tiers
author: claude-opus-5-5
created_at: 2026-11-02T22:57:58Z
---

## Proposal: Workflow-edit approval hygiene covers both authorization tiers

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The needs-attention `hygiene:workflow-edit-approval:<work-item-id>` fact surfaces every open item carrying either workflow-edit authorization label — the maintainer-only `approval:workflow-edit` or the delegable `approval:workflow-edit-additive` — and names which tier the label admits.

### Motivation

Maintainer ruling 2026-11-02 split the fleet workflow-edit guard (livespec-dev-tooling `check-no-workflow-edits.sh`) into two tiers. An ADDITIVE edit — a workflow diff that adds lines only, measured against the merge base, with an exemption attesting `change=additive` and `ci_runtime=no-significant-increase` — is admitted under `approval:workflow-edit-additive`, which a coordinator agent may set under delegated maintainer authority. Every edit that deletes or modifies workflow lines, removes or reduces test coverage or quality gates, or significantly increases CI runtime still needs `approval:workflow-edit`, set by the maintainer directly. The contracts.md clause names only the maintainer label, so a delegated additive authorization would be invisible to the maintainer. The label is the maintainer's notification surface for an advisory control, so the delegated tier needs the same visibility.

### Proposed Changes

In `contracts.md`, replace the paragraph headed **Workflow-edit approval (`hygiene:workflow-edit-approval:<work-item-id>`).** with:

**Workflow-edit approval (`hygiene:workflow-edit-approval:<work-item-id>`).** For every work-item of this repository that is not `closed` and carries the `approval:workflow-edit` label or the `approval:workflow-edit-additive` label, the snapshot MUST carry one attention item. The item names the work-item id, its lifecycle status, its title, and the tier the label admits: `maintainer` for `approval:workflow-edit`, `additive` for `approval:workflow-edit-additive`. When both labels are present, the tier is `maintainer`. Its handoff opens the item for the maintainer's review (the `discuss-work-item` operation). The maintainer sets `approval:workflow-edit` directly; a coordinator agent may set `approval:workflow-edit-additive` under delegated maintainer authority for an attested add-only edit with no significant CI-runtime increase. Either label is the maintainer's notification mechanism for the advisory workflow-edit control, so the fact MUST NOT be suppressed by any other fact about the same item, and it clears only when the item closes or both labels are removed. A store read that fails MUST surface as a visible failure rather than as an absence of these items. Scenario 232 in `scenarios.md` exercises this paragraph.

In `scenarios.md`, retitle Scenario 232 to `## Scenario 232 — needs-attention surfaces an item labelled with a workflow-edit authorization` (and update the matching `tests/heading-coverage.json` row in the revise commit), and replace its gherkin block with:

```gherkin
Feature: The workflow-edit authorization labels are the maintainer's notice
  As the maintainer authorizing an edit to .github/workflows/
  I want every open item carrying a workflow-edit authorization label to appear in needs-attention
  So that the advisory workflow-edit control, including delegated additive authorizations, has a surface where it is noticed

  Scenario: An open item labelled approval:workflow-edit is surfaced at the maintainer tier
    Given an open work-item carrying the approval:workflow-edit label
    When the needs-attention snapshot is composed
    Then it carries hygiene:workflow-edit-approval:<work-item-id> naming the item, its status, its title and the tier maintainer
    And its handoff opens the item for review

  Scenario: An open item labelled approval:workflow-edit-additive is surfaced at the additive tier
    Given an open work-item carrying only the approval:workflow-edit-additive label
    When the needs-attention snapshot is composed
    Then it carries hygiene:workflow-edit-approval:<work-item-id> naming the item, its status, its title and the tier additive

  Scenario: A closed or unlabelled item is not surfaced
    Given a closed work-item carrying either label and an open work-item carrying neither
    When the needs-attention snapshot is composed
    Then neither item yields a workflow-edit-approval fact
```
