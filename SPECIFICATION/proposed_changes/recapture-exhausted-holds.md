---
topic: recapture-exhausted-holds
author: claude-opus-5-5
created_at: 2026-11-11T02:35:36Z
---

## Proposal: A run that exhausted its recapture bound is held by recovery routing with a record naming the explicit resume route, never routed fresh or resumed automatically

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend the recovery-release clause in contracts.md. An item whose latest run ended at the non_converged terminal because its recapture bound was reached (LIVESPEC_RECAPTURE_EXHAUSTED) is routed held, never fresh, and never resume or seeded automatically. Its recovery-held record names the refusal recapture-exhausted, the preserved implementation (open pull request and head, else the needs-human ref, else none) and the explicit `resume --item <id>` at proof_capture with a proof rider. Two scenarios are added: one for the hold, one for the record's text.

### Motivation

On 2026-11-11, bd-ib-qshcwc's run 01M73ZK6Z090 ended LIVESPEC_RECAPTURE_EXHAUSTED: review returned a recapture verdict three times on one proof-record finding. Its implementation was finished and settled on open draft #4841. Recovery routing nonetheless read route='fresh', which would re-implement finished work. The cause is commit adadc0c42 (2026-11-03): _dispatcher_recovery_release._is_recovery_terminal excludes LIVESPEC_RECAPTURE_EXHAUSTED endings from the recovery release, so the item is never 'released' and falls through to fresh. The ratified clause states no such exclusion: it releases every non_converged ending. legacy-coordinator-agent decided (2026-11-11, duties §1: cut the tokens that failures and rework throw away) that such an item must be HELD with a routing record naming the explicit route, and must not be auto-resumed, because a proof that exhausted its recapture budget can loop if resumed blindly. Filed in plan publish-draft-green-work-loss (epic bd-ib-acrr56).

### Proposed Changes

In SPECIFICATION/contracts.md, in the recovery-release clause (the paragraph that begins "... An item is also released for recovery when its latest journaled dispatch ended at the workflow's `needs_human` terminal or at a `non_converged` terminal ..."), a new sentence MUST be added immediately after that first release sentence:

"An item whose latest journaled dispatch ended at the `non_converged` terminal because the run's recapture bound was reached, that is, the third recapture verdict of §"Self-contained plugin dispatch" routed to `non_converged` and the ending carries `LIVESPEC_RECAPTURE_EXHAUSTED`, is released for recovery by that sentence. Recovery routing MUST route such an item `held`. It MUST NOT route it `fresh`, and it MUST NOT route it `resume` or `seeded` automatically, even when every resume precondition passes. A proof that exhausted its recapture bound is not re-captured until a person or an owning seat supplies a proof rider and resumes it explicitly through §"Resume from a published pull request (`resume --item`)". The `recovery-held` record of such an item MUST name the refusal `recapture-exhausted`. Its detail MUST read `recapture-exhausted: implementation preserved on <preserved> ; resume --item <work-item-id> at proof_capture with a proof rider`. `<preserved>` names pull request `#<number>` at head `<sha>` when the item's pull request is open. Otherwise it names the needs-human ref and commit preserved at that run's ending. Otherwise it names `no preserved work observed`. This hold is a non-fallback refusal: no other fallback-permitting refusal can turn it into a `seeded` or `fresh` route. It is graded after the pre-claim refusal of §"Across-dispatch required-result progress", exactly as every released candidate is."

The sentence that the release "consumes no budget of §"The three rework caps"" MUST continue to hold for such an item. An explicit `resume --item` of it is governed by that command's own preconditions, including its two-resume chain bound, and this hold MUST NOT add a precondition to that command.

In SPECIFICATION/scenarios.md two new scenarios MUST be added. The revise pass MAY renumber them to the next free numbers:

## Scenario 342 — A run that exhausted its recapture bound is held by recovery routing, never routed fresh or resumed automatically

```gherkin
Feature: A recapture-exhausted run's finished implementation is never thrown away by recovery routing
  Scenario: The item is held, not routed fresh
    Given an item whose latest journaled dispatch ended at the non_converged terminal with LIVESPEC_RECAPTURE_EXHAUSTED
    And its draft pull request is open and every resume precondition passes
    And the item has been returned to ready
    When recovery routing grades the item
    Then the route is held
    And no run is launched for the item
    And the route is neither fresh nor resume nor seeded
  Scenario: No preserved work still holds
    Given an item whose latest journaled dispatch ended with LIVESPEC_RECAPTURE_EXHAUSTED and that holds no open pull request and no needs-human ref
    When recovery routing grades the item
    Then the route is held, not fresh
```

## Scenario 343 — A recapture-exhausted hold names the preserved implementation and the explicit resume route

```gherkin
Feature: The recovery-held record tells the next seat how to resume a recapture-exhausted item
  Scenario: Open pull request
    Given an item held because its latest run exhausted its recapture bound, and whose pull request 4841 is open at head 8a902ed46
    When its recovery-held record is written
    Then the record names the refusal recapture-exhausted
    And its detail reads "recapture-exhausted: implementation preserved on #4841 at 8a902ed46 ; resume --item <work-item-id> at proof_capture with a proof rider"
  Scenario: No open pull request
    Given such an item with no open pull request and a needs-human ref preserved at that run's ending
    When its recovery-held record is written
    Then the detail names that needs-human ref and its commit in place of the pull request
```

Per this repository's revise co-edit discipline, the revise pass MUST add tests/heading-coverage.json rows and tests/heading-coverage-debt.json rows for both new headings through resulting_files[]. Their test MAY be "TODO", with a reason naming the implementing work-item filed beside this proposal.
