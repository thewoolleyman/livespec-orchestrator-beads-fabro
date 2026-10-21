---
topic: non-record-capture-is-a-proof-record-finding
author: claude:fabro-currency
created_at: 2026-10-21T22:03:39Z
---

## Proposal: A captured comment that does not parse as a record is a proof-record finding

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a fifth member to the closed enumeration of proof-record findings in contracts.md (Self-contained plugin dispatch, Definition-of-Done and Proof-of-Done stages): a newest captured Proof of Done comment that does not parse as a record, such as one whose header carries an empty run id. A verdict whose only blocking finding is such a capture is then a recapture verdict, routes to proof_capture under the existing two-lap bound, and does not reach publication-head. Add Scenario 235 stating both the recapture route and the third-verdict bound.

### Motivation

Measured on livespec-dev-tooling-r6kagr, run 01M5E8H65Z04 on hp (build v0.229.3): proof_capture posted a captured comment on PR #2712 whose header read 'Proof of Done — captured — run  — 2026-10-21T04:34:04Z', with an EMPTY run id. review approved and proof_verify verified, then publication-head failed closed with LIVESPEC_PR_PROOF_IDENTITY_UNESTABLISHED and the run ended at needs_human. A resume restarts at the failed stage and never re-runs proof_capture, so the only recovery is a fresh dispatch. bd-ib-oa67lv fixed the capture prompt and closed the proof-grade and publication-head false greens, and coordinator R386 assigned the route back to proof_capture to bd-ib-2oxr6v. That item's R265 dod-preflight (gate 20261021T214506Z-193381, both legs) refused the assertion: the enumeration of proof-record findings is CLOSED and names no unparseable record, so no ratified heading governs the route. This proposal supplies that heading; coordinator R534 directed the filing.

### Proposed Changes

In SPECIFICATION/contracts.md, section 'Self-contained plugin dispatch', subsection 'Definition-of-Done and Proof-of-Done stages', replace the paragraph opening

```
A blocking review finding whose subject is the latest captured record
rather than the tree is a PROOF-RECORD finding. Each of these is one: a
record that is not current for the head under review; a behavioural
assertion whose proof is test-suite output alone; a step that runs a
program the rule above requires the record to contain and that the record
does not contain; and an assertion whose proof is a printed conclusion
rather than the observed output.
```

with

```
A blocking review finding whose subject is the latest captured record
rather than the tree is a PROOF-RECORD finding. Each of these is one: a
record that is not current for the head under review; a behavioural
assertion whose proof is test-suite output alone; a step that runs a
program the rule above requires the record to contain and that the record
does not contain; an assertion whose proof is a printed conclusion
rather than the observed output; and a newest captured Proof of Done
comment on the pull request that does not parse as a record, such as one
whose header carries an empty run id. `review` MUST treat that last case
as a blocking proof-record finding naming the comment and the field that
failed to parse, so a verdict whose only blocking finding is a non-record
capture is a recapture verdict, routes to `proof_capture` under the same
two-lap bound, and MUST NOT reach `publication-head` on a capture that
names no run.
```

The rest of that paragraph (the recapture verdict definition, its routing, the two-lap bound, and the third-verdict route to `non_converged`) is unchanged and applies to the new member exactly as to the other four. No new graph node or edge is introduced: the route is the existing `recapture` route, so the derived credential-use allowance that v177 bounds is unchanged.

In SPECIFICATION/scenarios.md, append the following scenario. The revise pass MUST add a matching entry to tests/heading-coverage.json in the same change, with test 'TODO' and reason 'An integration-tier test is owed for this heading; the owning work-item is filed after ratification.'

## Scenario 235 — A captured comment that does not parse as a record is a proof-record finding

```gherkin
Feature: A capture that names no run is re-captured instead of stranding the run
  As the maintainer of a repository dispatched to the factory
  I want a captured comment that does not parse as a record to be re-captured within the bounded cycle
  So that a run whose proof was replayed and verified does not end at needs_human on the capture's malformed header

  Scenario: A non-record capture routes to proof_capture
    Given a pull request whose newest captured Proof of Done comment has a header whose run id is empty
    And that defect is the review verdict's only blocking finding
    And the run has issued fewer than two recapture verdicts
    When the review node ends
    Then the review record names that comment and states that its header carries no run id
    And the run routes to proof_capture with preferred_label recapture
    And no disposition visit, no review_fix visit and no review-fix round is consumed
    And proof_capture publishes a new captured record that parses as a record and is current for the publish head

  Scenario: A non-record capture on the third recapture verdict does not re-enter proof_capture
    Given a pull request whose newest captured Proof of Done comment does not parse as a record
    And the run has already issued two recapture verdicts
    When the review node ends with that defect as its only blocking finding
    Then the run routes to non_converged without entering proof_capture
```

