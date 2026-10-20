---
topic: proof-record-findings
author: claude:fabro-currency (session 5c3e43cb)
created_at: 2026-10-20T17:12:42Z
---

## Proposal: A review finding against the captured proof record routes back to proof_capture, and the record carries every program it runs

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Today a review verdict whose blocking findings concern only the Proof of Done captured record travels review -> disposition -> review_fix -> janitor -> publish_draft -> proof_capture. review_fix is a code-fix node and cannot repair a record, every lap spends a review_fix and disposition visit, and proof_capture is re-entered without the findings that rejected it. This proposal defines a proof-record finding and routes a verdict made only of them straight to proof_capture with those findings, consuming no disposition or review_fix visit, bounded by its own cap. It also requires every captured record to carry every program its steps execute and to state the head its steps ran against.

### Motivation

Coordinator ruling R329 (2026-10-20), on measurements by the fallback-priority seat. Runs gmktec 01M5CE38SZJW (bd-ib-wkfwtx) and gmktec 01M5CDH2FZSE (bd-ib-22yfvh, 390 minutes) both failed with 'node 20 exceeded its firing budget of 3' at review visit 4. In both runs review_fix succeeded every round with `just check` green, so the code was fine. From review@2 on, every blocking finding was about the captured record: its steps ran untracked /tmp/proof-capture/*.py programs the record never contained, its assertions printed claimed conclusions, and its stated head and timestamp lagged the reviewed head. The ratified 'proof_capture' paragraph and Scenario 137 ('Suite-only proof is a blocking review finding') send such a finding through the review-fix route, which cannot repair it, so the loop burns the budget on correct code. Work-item bd-ib-j56cur implements the change; its pre-dispatch Definition-of-Done preflight refused it because Scenario 137 ratifies the opposite route.

### Proposed Changes

In SPECIFICATION/contracts.md, section 'Definition-of-Done and Proof-of-Done stages', paragraph '**`proof_capture`.**':

(1) After the sentence ending 'or state that no scenario governs it.', insert: 'Every program a reproduction step executes MUST be written into the record itself, inline or as an asset the record names through the proof asset store, so that each step can be replayed from the record and the repository alone; a step MUST NOT run a program that exists only in the sandbox. The record MUST state the commit sha its steps ran against, and that sha MUST equal the publish branch head at the moment of capture.'

(2) Replace the two sentences that begin 'a captured record older than the tree under review is a blocking review finding' and 'A captured record whose proof of a behavioural assertion is test-suite output alone is likewise a blocking review finding, so the run re-enters `proof_capture` through that same route rather than replaying a proof that exercised nothing.' with: 'A blocking review finding whose subject is the latest captured record rather than the tree is a PROOF-RECORD finding. Each of these is one: a record whose stated sha is not the head under review; a behavioural assertion whose proof is test-suite output alone; a step that runs a program the record does not contain; and an assertion whose proof is a printed conclusion rather than the observed output. When every blocking finding of a review verdict is a proof-record finding, `review` MUST end with `preferred_label=recapture`, which routes to `proof_capture` and MUST NOT route to `disposition` or `review_fix`, so that the verdict consumes no `disposition` or `review_fix` visit. `proof_capture` entered on that verdict MUST receive the review findings, through the engine preamble of preceding stage output and the review record on the pull request, and MUST publish a new captured record against the current publish head that addresses each of them. The third `preferred_label=recapture` from `review` in one run MUST route to the existing `non_converged` terminal. A verdict that carries at least one blocking finding about the tree routes as a `fix` verdict exactly as before, and the recapture its fix round triggers through `janitor` and `publish_draft` MUST also receive any proof-record findings of that verdict.' The backstop sentence of the '**`proof_verify`.**' paragraph is unchanged.

In SPECIFICATION/scenarios.md, '## Scenario 137 — A behavioural assertion is proved by exercising the behaviour, and a sandbox that cannot exercise it says so' (the heading MUST NOT change, so tests/heading-coverage.json needs no edit): replace the last step of the case 'Suite-only proof is a blocking review finding', 'And the run re-enters proof_capture through the review-fix route before any replay', with 'And the run re-enters proof_capture with that finding before any replay, through no disposition or review_fix visit', and append these cases inside the same gherkin block:

```gherkin
  Scenario: A proof-record-only verdict re-captures without a fix round
    Given a review verdict whose only blocking finding is that a captured step runs a program the record does not contain
    When the review node ends
    Then the run routes to proof_capture with preferred_label recapture
    And no disposition or review_fix visit is consumed
    And proof_capture publishes a new captured record against the current publish head that addresses the finding
  Scenario: A captured record is self-contained and names its head
    Given a factory-captured assertion whose reproduction step runs a helper program
    When the proof_capture node publishes the record
    Then the helper program's text is in the record or in a proof asset the record names
    And the record states the commit sha its steps ran against, equal to the publish branch head at capture time
  Scenario: A mixed verdict still fixes the tree first
    Given a review verdict with one blocking finding about the tree and one proof-record finding
    When the review node ends
    Then the run routes to disposition and review_fix as a fix verdict
    And the next proof_capture visit receives the proof-record finding
  Scenario: Re-capture is bounded
    Given a run whose review has ended with preferred_label recapture twice
    When review ends with preferred_label recapture a third time
    Then the run routes to non_converged
```
