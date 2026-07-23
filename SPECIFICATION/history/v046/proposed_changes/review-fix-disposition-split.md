---
topic: review-fix-disposition-split
author: claude-fable-5
created_at: 2026-07-23T17:59:38Z
---

## Proposal: split finding-disposition out of the review fix stage (Scenario 20)

### Target specification files

- SPECIFICATION/scenarios.md
- SPECIFICATION/contracts.md

No `tests/heading-coverage.json` co-edit: this proposal adds, changes,
and removes NO `## ` H2 heading — the Scenario 20 heading stays
byte-identical and both Gherkin edits happen inside its existing fence.

### Summary

Amend Scenario 20 so the review gate's rework round is modeled as two
separate steps — a DISPOSITION stage that adjudicates each blocking
finding (accept, or reject with a one-line rationale) and a FIX stage
that implements only the accepted findings — replacing the ratified
single-step language in which the implementer both adjudicates and
fixes. Add one Gherkin scenario in the same fence for the round whose
blocking findings are ALL rejected: it routes directly back to review,
the janitor does not re-run (no code changed), and the rejection
record is carried to the re-review. Add the design-record citation for
the split to the `dispatcher.review_fix_cap` policy bullet in
contracts.md per §"Intent preservation". Cap semantics, the blocking
default, `merge_on_review_cap`, and the Scenario 20 telemetry scenario
are unchanged.

### Motivation

The maintainer directed (2026-07-23, relayed via the thread
supervisor) that the `review_fix` node's conflation of
finding-disposition with fix implementation be restructured by
splitting the two into cohesive separate steps — each independently
controllable, independently promptable, able to run a different model.
The design record is
`plan/factory-success-rate-remediation/research/review-fix-split-design.md`
(ledger `bd-ib-o35rcx`, child of epic `bd-ib-cvgjop`), adversarially
reviewed 2026-07-23 (verdict SOUND-WITH-CHANGES; both blocking
findings incorporated). Ratified Scenario 20 currently codifies the
conflation ("When the implementer addresses or rejects each blocking
finding with a rationale"), so the spec must move first — the
implementation slice (`bd-ib-fe574e`) lands only after this proposal
ratifies. The all-rejected scenario asserts "the janitor does not
re-run" explicitly per the adversarial review's finding #9: that skip
is the design's rationale for the direct route and must be falsifiable
the way the capped-review scenarios are.

### Proposed Changes

**(a) `scenarios.md` — Scenario 20, second Gherkin scenario, REPLACE
(verbatim; the single replacement emits BOTH scenarios below, so the
addition carries no positional dependence):**

```
  Scenario: A blocking finding routes back to the implementer and re-validates
    Given the review gate raised at least one blocking finding
    And the review fix-round budget (dispatcher.review_fix_cap) is not yet exhausted
    When the implementer addresses or rejects each blocking finding with a rationale
    Then the change is re-validated by the janitor and reviewed again
```

**WITH:**

```
  Scenario: A blocking finding is adjudicated, and accepted findings are fixed and re-validated
    Given the review gate raised at least one blocking finding
    And the review fix-round budget (dispatcher.review_fix_cap) is not yet exhausted
    When the disposition stage adjudicates each blocking finding — accepting it, or rejecting it with a one-line rationale
    And at least one blocking finding is accepted
    And the fix stage implements each accepted finding and no rejected one
    Then the change is re-validated by the janitor and reviewed again
    And the disposition record is carried to the re-review, which honors each rejection unless it re-confirms a genuine correctness or security defect

  Scenario: A round whose blocking findings are all rejected re-reviews without a fix pass
    Given the review gate raised at least one blocking finding
    And the review fix-round budget (dispatcher.review_fix_cap) is not yet exhausted
    When the disposition stage rejects every blocking finding, each with a rationale
    Then the run routes directly back to review
    And the janitor does not re-run (no code changed)
    And the rejection record is carried to the re-review, which honors it unless it re-confirms a genuine correctness or security defect
```

**(b) `contracts.md` — §"The two rework caps", the
`dispatcher.review_fix_cap` bullet, REPLACE (verbatim):**

```
- **`dispatcher.review_fix_cap`** (integer, default **`3`**) — the INNER,
  pre-merge review fix-round budget. At the cap, a still-blocking review is
  disposed by the item's effective `merge_on_review_cap`.
```

**WITH:**

```
- **`dispatcher.review_fix_cap`** (integer, default **`3`**) — the INNER,
  pre-merge review fix-round budget. At the cap, a still-blocking review is
  disposed by the item's effective `merge_on_review_cap`. A fix round has
  two separate steps — a disposition stage adjudicates each blocking
  finding (accept, or reject with rationale) and a fix stage implements
  only the accepted findings (Scenario 20); a round whose findings are all
  rejected re-reviews directly, and every reviewer-granted round consumes
  this budget either way. Design record for the split:
  `plan/factory-success-rate-remediation/research/review-fix-split-design.md`
  (ledger `bd-ib-o35rcx`, maintainer directive 2026-07-23).
```

**(c) Deliberately NOT touched.** Scenario 20's Feature narrative, its
approve/capped/telemetry scenarios, the `## Scenario 20` heading text,
`merge_on_review_cap` semantics, and Scenario 48 are all unchanged.
The workflow-file node names (`disposition`, `review_fix`) are
implementation surface and deliberately do not appear in the Gherkin —
the scenarios speak of the disposition STAGE and fix STAGE.
