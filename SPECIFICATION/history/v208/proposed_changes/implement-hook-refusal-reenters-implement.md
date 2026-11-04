---
topic: implement-hook-refusal-reenters-implement
author: claude-opus-5-5
created_at: 2026-10-24T22:45:02Z
---

## Proposal: A hook-refused incomplete implement turn re-enters implement

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

An implement turn that ends incomplete after the repository's commit hook refused its latest commit, naming failed targets, re-enters implement with the hook's failed targets and error lines in its brief while the implement node's retry budget remains, instead of failing at needs_human. An exhausted budget fails naming the failed targets; an incomplete turn with no refused commit fails as partial progress, as before.

### Motivation

Work-item bd-ib-y7372n (plan livespec-dev-tooling-dfixhe, assertion 13). Runs quit on fixable gate failures with hours of turn allowance left: bd-ib-8zyan run 01M5QNH88NHN68ST28Y80CZJ48 ended ~30 s after its Green amend was refused by check-types (3 pyright errors), with ~196 minutes left, and its needs-human cause carried only the agent's own wrong account of the hook; bd-ib-idpr32 (coverage) and bd-ib-3kqdln ended the same way. The v165 paragraph routes every incomplete turn straight to failure, so a fixable refusal costs a human round-trip and a full re-dispatch.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Self-contained plugin dispatch", paragraph "An implement turn that ends incomplete does not succeed", replace the sentence:

> When the field reports the work incomplete, the stage MUST end with a failed outcome whose cause names partial progress, so the run takes the same failure edge as any other `implement` failure, and the dispatch outcome detail MUST carry that cause.

with:

> When the field reports the work incomplete and the turn left no refused commit attempt, the stage MUST end with a failed outcome whose cause names partial progress, so the run takes the same failure edge as any other `implement` failure, and the dispatch outcome detail MUST carry that cause. When the field reports the work incomplete, the turn's latest commit attempt was refused by the repository's commit hook naming failed targets, and the `implement` node's retry budget is not exhausted, the run MUST re-enter the `implement` stage instead of failing it. The re-entered turn's brief MUST carry the refused commit's failed target names and the hook's own error lines, taken from the hook's recorded output rather than from the previous turn's reply; the run MAY establish the refusal by running the repository's commit hook itself over the changes the turn left staged. When that budget is exhausted after a hook-refused commit, the stage MUST end with a failed outcome whose cause names the hook's failed targets, and the dispatch outcome detail MUST carry that cause.

In SPECIFICATION/scenarios.md, "## Scenario 204 — An implement turn that reports its work incomplete fails the implement stage", replace the first scenario block:

```gherkin
  Scenario: A turn that reports partial progress fails the stage
    Given an implement turn whose final output's completion field reports the Definition of Done incomplete
    When the implement stage ends
    Then the stage outcome is failed with a cause naming partial progress
    And the run takes the implement stage's failure edge, and the dispatch outcome detail carries that cause
```

with:

```gherkin
  Scenario: A turn that reports partial progress fails the stage
    Given an implement turn whose final output's completion field reports the Definition of Done incomplete
    And the turn left no refused commit attempt
    When the implement stage ends
    Then the stage outcome is failed with a cause naming partial progress
    And the run takes the implement stage's failure edge, and the dispatch outcome detail carries that cause

  Scenario: A turn whose commit the hook refused re-enters implement while its retry budget remains
    Given an implement turn whose final output's completion field reports the Definition of Done incomplete
    And the turn's latest commit attempt was refused by the repository's commit hook naming failed targets
    And the implement node's retry budget is not exhausted
    When the implement stage ends
    Then the run re-enters the implement stage instead of failing it
    And the re-entered turn's brief carries the refused commit's failed target names and the hook's own error lines, taken from the hook's recorded output

  Scenario: A hook-refused turn with its retry budget exhausted fails naming the failed targets
    Given an implement turn whose final output's completion field reports the Definition of Done incomplete
    And the turn's latest commit attempt was refused by the repository's commit hook naming failed targets
    And the implement node's retry budget is exhausted
    When the implement stage ends
    Then the stage outcome is failed with a cause naming the hook's failed targets
```

The other two scenarios of Scenario 204 (no completion field; reported complete) are unchanged.
