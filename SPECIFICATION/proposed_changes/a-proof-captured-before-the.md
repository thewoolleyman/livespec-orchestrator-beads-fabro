---
topic: a-proof-captured-before-the
author: claude-opus-5-5:publish-draft-green-work-loss
created_at: 2026-11-12T11:10:00Z
---

## Proposal: The workflow, not the reviewer, selects the latest captured record and decides its currency, so a proof re-captured after a refresh is not reported stale

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

contracts.md says `review` MUST review "the latest captured record" alongside the code, and that a record not current for the head under review is a proof-record finding. It leaves both the selection of that record and the currency decision to the reviewer. The reviewer reads the pull request's whole comment stream and picks the record itself.

After a refresh re-proves, the pull request carries several captured records. A reviewer that does not see the newest record whole can grade an older one, report it not current, and send a correct proof back for recapture until the bound is spent.

This proposal adds one paragraph under the same H2, covering three things:

- The workflow MUST select the latest captured record deterministically and hand `review` that record whole, with its comment URL and declared head.
- The workflow MUST decide the record's currency itself, by tree comparison, before `review` is entered. A record that is not current goes back to `proof_capture` without a review visit. A record that is current cannot draw a currency finding.
- A run that exhausts its recapture bound on currency names both heads in its cause.

One sentence of the existing paragraph is amended to point at the new one, and Scenario 355 exercises it.

### Motivation

Measured 2026-11-12 by the publish-draft-green-work-loss seat on livespec-dev-tooling-s4gx7a, run 01M77BM3M4MT6KVEFSVWDT6733 (petri, orchestrator v0.321.0), read through `dispatcher.py inspect --factory petri` and the pull request's comments. The run ended `non_converged` with LIVESPEC_RECAPTURE_EXHAUSTED after 127m44s. The filing item bd-ib-rriwjr attributed the loss to capture declaring a stale head. The run's record shows the capture was correct and the selection was wrong:

- `proof_capture@1` posted a captured record declaring head 9d36625e3 (comment 6819804969, 09:24:56Z).
- `pr_refresh@1` rebased onto 0560e8af8 and republished at 448a612cb, and its carry-forward decision was `reproof_required` (09:48:01Z).
- `proof_capture@2` (09:48:40Z) and `proof_capture@4` (09:53:33Z) each posted a captured record declaring 448a612cb. `proof_capture@3` posted nothing, stating correctly that a current record was already on the pull request. Each capture confirmed `git diff --quiet FETCH_HEAD HEAD`.
- `review@2`, `review@3` and `review@4` each reported "its declared publish-branch head 9d36625e3... has a different tree from origin/feat/livespec-dev-tooling-s4gx7a at 448a612cb..." and ended `recapture`. Each then ran `git diff --quiet 9d36625e3... origin/<publish branch>`, the oldest record's head.
- `review@2`'s record read was `gh pr view 4291 --json comments`. Its tool result is 149 469 characters holding four Proof of Done records of about 47 000 characters each. The oldest record's header is at the start of that result, and the newest record's `Publish-branch head:` line is about 100 000 characters in. The engine's event store holds the result whole. The verdict named only the oldest record's head, which is consistent with the review adapter (codex-acp) showing its model only the head and tail of a long result. That elision is inferred from the verdict, not observed in the model's input.

bd-ib-qshcwc run 01M74BY38TBC (2026-11-11, before v0.321.0) ended the same way, so the class predates v0.321.0. Over 72 hours, 2 of the 7 recapture-exhausted runs fleet-wide (about 2.3 run-hours) were currency-only. livespec-dev-tooling-s4gx7a is held blocked until this has a fix or a measured workaround.

Whatever an adapter does to a long tool result, the selection of the record `review` grades and the comparison of two trees are deterministic facts. Leaving them to a language model reading an unbounded comment stream is what let a correct proof be judged stale three times.

Fleet scope: the `implement-work-item` workflow ships in this plugin's payload and runs for every tenant the Dispatcher admits. Every repository whose refresh round re-proves can carry several captured records on one pull request.

Owning work item: bd-ib-rriwjr, plan publish-draft-green-work-loss (epic bd-ib-acrr56). Its Definition of Done will be restated against this paragraph once the proposal is ratified, because its first assertion names behaviour the run shows is already delivered.

Co-edit owed at revise, outside this spec target: `tests/heading-coverage.json` gains one row for the new `## Scenario 355` heading (test TODO, reason naming bd-ib-rriwjr). The revise MUST confirm that Scenario 355 is still free when it cuts, because Scenarios 345 to 354 are claimed by open proposals. If 355 is taken, the revise MUST renumber.

### Proposed Changes

1. contracts.md: insert this new paragraph IMMEDIATELY BEFORE the paragraph that begins "**`proof_verify`.** The node MUST run on an adapter distinct from the implementer's", that is, after the paragraph that begins "A blocking review finding whose subject is the latest captured record":

**Review grades the latest captured record, which the workflow selects and checks for currency.** Which captured record `review` grades, and whether that record is current, MUST be decided by the workflow before the `review` turn starts, by a deterministic rule computed from the pull request and repository state alone. No language-model judgement MAY take part in either decision.

- The latest captured record is the comment on the run's pull request with the newest creation time whose first line begins `Proof of Done — captured — run ` followed by this run's id or an id a resume links to it, and that parses as a record. The workflow MUST hand `review` that record's full text, its comment URL and its declared publish-branch head as one bounded input in the sandbox, and `review` MUST grade that record and no other. The `review` turn MUST NOT be the means by which the record is selected, and the selection MUST NOT depend on the turn reading the pull request's whole comment stream.
- Before `review` is entered, the workflow MUST compare the tree of the selected record's declared head with the tree of origin's publish-branch head, fetched at that moment. When the trees differ, the run MUST route to `proof_capture` with that comparison as its finding, giving both heads, and MUST NOT enter `review`. That route counts against the existing two-lap recapture bound, so the third such route in one run, or the third recapture from any source, MUST reach the existing `non_converged` terminal. When the trees are equal, the record is current, `review` MUST NOT raise a finding that it is not current, and the workflow MUST discard any such finding a verdict carries before it classifies the verdict.
- When a run reaches `non_converged` because its recapture bound is spent and the last recapture was routed because a record was not current, the terminal cause MUST name the selected record's declared head, its comment URL and origin's publish-branch head, in addition to LIVESPEC_RECAPTURE_EXHAUSTED.
- When no captured record parses for this run, the existing rule for a non-record capture applies unchanged.

Scenario 355 in `scenarios.md` exercises this paragraph.

1b. contracts.md: in the paragraph that begins "**`proof_capture`.**" (the one containing "`review` MUST review the latest captured record alongside the code"), change the sentence "`review` MUST review the latest captured record alongside the code; because `review_fix` re-enters `janitor`, every accepted fix round re-enters `publish_draft` and `proof_capture` before `review`, so the record `review` reads is normally current." to: "`review` MUST review the latest captured record alongside the code, as the paragraph \"Review grades the latest captured record, which the workflow selects and checks for currency\" selects it; because `review_fix` re-enters `janitor`, every accepted fix round re-enters `publish_draft` and `proof_capture` before `review`, so the record `review` reads is normally current." No other sentence of that paragraph changes.

2. scenarios.md: append this new H2 section after the last ratified scenario:

## Scenario 355 — Review grades the latest captured record the workflow selected, and the workflow decides its currency

```gherkin
Feature: A proof re-captured after a refresh is graded as the current proof
  Scenario: The workflow hands review the newest captured record whole
    Given a run whose pull request carries a captured record R1 declaring head H1, then a verified record and a reproof_required record, then a captured record R2 declaring head H2
    And the four records together exceed 100 000 characters
    When the run enters review
    Then review's input names R2's comment URL and head H2 and carries R2's full text
    And review grades R2

  Scenario: A current record draws no currency finding
    Given that run, whose publish branch on origin is at H2
    When review ends with a verdict whose only blocking finding is that the record is not current
    Then the workflow discards that finding before classifying the verdict
    And the verdict is not a recapture verdict

  Scenario: A record that is not current goes back to proof_capture without a review visit
    Given a run whose latest captured record declares head H1 while origin's publish branch is at H2 with a different tree
    And the run has issued fewer than two recapture verdicts
    When the workflow checks the record's currency
    Then the run routes to proof_capture with a finding giving H1 and H2
    And no review visit is consumed

  Scenario: A commit that changes no tree does not make the record stale
    Given a run whose latest captured record declares head H2 while origin's publish branch is at H3, whose tree equals H2's
    When the workflow checks the record's currency
    Then the record is current and the run enters review

  Scenario: Exhaustion on currency names both heads
    Given a run that has issued two recapture verdicts
    And its latest captured record declares head H1 while origin's publish branch is at H2 with a different tree
    When the workflow checks the record's currency
    Then the run ends at non_converged
    And the cause names LIVESPEC_RECAPTURE_EXHAUSTED, head H1, the record's comment URL and head H2
```

No existing H2 heading is renamed or removed.

3. **Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading. The row is carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit. It carries `test: "TODO"`, `work_item: "bd-ib-rriwjr"` and a non-empty `reason` naming the tier the owed test runs at, which is integration or above. The same commit MUST add one matching `tests/heading-coverage-debt.json` entry carrying the key three (`spec_root`, `spec_file`, `heading`), `work_item: "bd-ib-rriwjr"` and `first_seen` set to the revise date. If the revise renumbers Scenario 355, the row and the entry MUST carry the renumbered heading text.
