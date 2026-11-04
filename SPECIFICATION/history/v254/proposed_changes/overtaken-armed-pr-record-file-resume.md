---
topic: overtaken-armed-pr-record-file-resume
author: claude-opus-5-5:sandbox-commit-gate-ceiling
created_at: 2026-10-29T10:00:57Z
---

## Proposal: An armed pull request overtaken only in declared record files is resumed by the Dispatcher without a human step

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Give contracts.md "Armed pull request overtaken by the default branch" a record-file arm. When the two conflicting merge-wait polls that end the wait today are followed by a measurement showing that every path in conflict between the pull request head and the default branch's tip is a declared `dispatcher.record_files` entry, the Dispatcher MUST resolve the item to `ready` and resume it in the same invocation instead of resting it at `needs-human`. Any other conflict, an unmeasurable conflict set, or a refused resume rests the item exactly as today, with the refusal or the measurement failure named. Remove the sentence in "Declared record files merge without a repair round" that says that paragraph changes no ratified behaviour of the merge wait, and replace it with a pointer to the new arm. Extend Scenario 184 with the three resulting sub-scenarios.

### Motivation

Since spec revision v162 (Scenario 200), a `pr_refresh` whose conflicts lie only in declared record files merges them entry by entry with no repair round, so the resumed run's refresh already absorbs exactly this class of conflict. What remains is the human step in front of it: an armed pull request overtaken by a record-file-only default-branch commit rests at `blocked / needs-human`, and the recovery is the fixed chain `resolve-blocked:<id>:ready` then `resume --item <id>`. That chain takes no human judgement. On this repository, which declares record files that almost every change extends (`tests/heading-coverage.json` and its siblings), it fires on ordinary concurrent merges. Work item bd-ib-nonaor (plan bd-ib-qy5wol, follow-up to bd-ib-davaxq requested by the gitops-fleet-capacity-monitoring driver on 2026-10-19) carries the implementation. It is held because it changes the ratified outcome of this paragraph and of Scenario 184, and the 2026-10-20 governance-routing note on that item (R1 bd-ib-j6uvkj, batch 6) records that its disposition is a linked proposal amending this paragraph, filed by the plan that owns it. The amendment does not conflict with the merge-poll-budget-exhaustion sentence already in the paragraph: that sentence fills the non-conflicting case, and this one adds an arm to the conflicting case.

### Proposed Changes

1. contracts.md, "Armed pull request overtaken by the default branch": after the sentence that ends the wait on two consecutive OPEN-and-conflicting polls, and before the sentences that rest the item at `blocked`, insert the record-file arm:

"Before it rests the item, the Dispatcher MUST compute the set of paths that conflict between the pull request's head and the default branch's tip, by a merge computation that changes no ref, no working tree of the primary checkout and nothing on the forge. When that set is non-empty and every path in it is a `path` declared in the committed `dispatcher.record_files` of the repository, the Dispatcher MUST resolve the item to `ready` through the same transition `resolve-blocked:<work-item-id>:ready` performs, and MUST then resume it in the same invocation through the same path `resume --item <work-item-id>` takes. The automatic resume MUST be subject to every refusal and bound of "Resume from a published pull request (`resume --item`)", including its two-resume limit, and the Dispatcher MUST attempt it at most once per invocation. The claim and the ownership lock that the invocation itself holds for the item MUST be released or carried into the resume, and MUST NOT count as a live ownership lock or a live earlier run for that resume's refusals. Before it resolves the item, the Dispatcher MUST journal one `base-advanced-record-files-resume` row naming the run id, the pull request number, its head, the default branch's tip and every conflicted path. When the resume is admitted, the invocation's outcome and exit code are those of the resumed dispatch. When the resume refuses, the item MUST rest at `blocked` with `blocked_reason: needs-human` exactly as below, with the cause `base-advanced-after-arming`, and the ledger comment and the outcome detail MUST name the refusal. When any conflicted path is not a declared record file, when the repository declares no record files, or when the conflict set cannot be computed, the item MUST rest exactly as below, and in the last case the ledger comment MUST name the measurement that failed. The automatic resume MUST NOT disarm, close or rewrite the pull request; the resumed run's `pr_refresh` disarms it before refreshing, as for a hand-driven resume."

The existing sentence "The Dispatcher MUST NOT disarm, close or rewrite the pull request itself" MUST remain. The final sentence of the paragraph MUST become: "Scenario 184 in `scenarios.md` exercises this paragraph, including its record-file arm, the `pr` routing above, and the disarm in \"Scripted publication and proof-head integrity\"."

2. contracts.md, "Declared record files merge without a repair round": the sentence "This paragraph changes no ratified behaviour of the Dispatcher's merge wait, including \"Armed pull request overtaken by the default branch\"." MUST be replaced with: "The Dispatcher's merge wait reads `dispatcher.record_files` only through the record-file arm of \"Armed pull request overtaken by the default branch\"; this paragraph changes no other behaviour of the merge wait."

3. scenarios.md, Scenario 184: the heading MUST remain unchanged. The existing sub-scenario "An armed pull request overtaken by a conflicting commit rests at needs-human with a named cause" MUST gain the Given line "And at least one conflicted path is not a declared record file". Three sub-scenarios MUST be added after it:

```gherkin
  Scenario: An armed pull request overtaken only in declared record files is resumed without a human step
    Given a run that armed auto-merge for head H and terminated through exit
    And a later default-branch commit conflicts with the pull request only in paths declared in dispatcher.record_files
    When two consecutive merge-wait polls report the pull request OPEN and conflicting with the default branch
    Then the Dispatcher journals one base-advanced-record-files-resume row naming every conflicted path
    And the item is resolved to ready and resumed in the same invocation, whose outcome and exit code are those of the resumed dispatch
    And the Dispatcher does not disarm, close or rewrite the pull request

  Scenario: A refused automatic resume rests the overtaken pull request at needs-human naming the refusal
    Given an armed pull request overtaken only in declared record files
    And the item's pull request has already taken its two resumes
    When the merge wait attempts the automatic resume
    Then the item rests at blocked with blocked_reason needs-human and the cause base-advanced-after-arming
    And the livespec-base-advanced-after-arming comment and the outcome detail name the resume's refusal

  Scenario: An unmeasurable conflict set rests the overtaken pull request at needs-human
    Given an armed pull request reported OPEN and conflicting on two consecutive merge-wait polls
    And the Dispatcher cannot compute the conflicted paths
    When the merge wait ends
    Then the item rests at blocked with blocked_reason needs-human and the cause base-advanced-after-arming
    And the livespec-base-advanced-after-arming comment names the measurement that failed, and no resume is attempted
```

The `tests/heading-coverage.json` entry for Scenario 184 MUST be kept, because the heading does not change; no heading is added or removed.
