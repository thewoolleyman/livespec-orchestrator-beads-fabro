---
topic: run-wall-budget-continues-while-progressing
author: claude-opus-5-5
created_at: 2026-11-10T21:01:45Z
---

## Proposal: A run past the whole-run wall budget continues while it progresses

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The whole-run wall budget stops being progress-independent. When a run's slot-holding time passes `dispatcher.run_wall_budget_seconds`, the watchdog grades the run's recent progress instead of cancelling it outright. A run that has made progress within its progress window keeps running. A run that has not is exported, cancelled and rested for a human exactly as today. A new committed hard ceiling, `dispatcher.run_wall_ceiling_seconds` (default three times the budget), bounds every run whatever its progress. Progress means committed work, not liveness: a new work-in-progress capture, or the first completion in the run of a workflow node. The credential-use window is re-based on the ceiling, so a run allowed to continue is not stopped by its own credential deadline.

### Motivation

Maintainer ruling 2026-11-10, recorded on plan epic bd-ib-nckst7 as scope event frwp-maintainer-ruling-wall-budget-principle-2026-11-10, verbatim: "On decision 1, the correct behavior is that if there is autonomous progress that can be made, and the item isn't thrashing or wasting tokens/infra resources, then it should be allowd to continue.  And any items waiting on a human should not block other things from entering the factory." Measured from the dispatch journals, 2026-11-03 to 2026-11-10: 15 whole-run wall-budget cancels landed after the run had published its pull request, 12 in this repository and 3 in livespec-dev-tooling. All 15 were in post-publish stages (fix_commit_settle, janitor, pr_refresh), none in implement. legacy-coordinator-agent counted 4 more on 2026-11-10, among them bd-ib-rfhnqf (PR 4818: Proof of Done captured and verified 09:23-09:27Z, then killed in pr_refresh at 21641 of 21600 s). Each one rested for a person and was hand-landed, although no work was lost. The current clause cancels a run that is making progress (contracts.md §"Dispatcher progress watchdog" → "The whole-run wall budget": "The budget is independent of progress"), so it fails the first half of the ruling. The second half already holds and is kept. A budget cancel releases the slot. A run whose item rests `blocked` holds no slot and is not a counted claim under §"Per-repo WIP cap". So a run waiting on a human blocks no admission. The alternatives offered on 2026-11-10 (release-to-resume, bounded-extension, exempt, unchanged) are superseded by the ruling. Release-to-resume would still cancel progressing runs and only rescue published ones. Exempt would let a non-converging loop hold a slot without bound. Progress is graded on committed work, not on liveness, because plan stall-watchdog-false-kills measured liveness signals cancelling healthy runs, and a refresh that only rebases creates no capture.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Dispatcher progress watchdog", replace the paragraph "**The whole-run wall budget.**" from the sentence "The budget is independent of progress:" through "... including while a budget export is held pending its read-back." with the following text, and keep its preceding sentences (the budget clock, queue time, strict excess, the unmeasured budget) unchanged:

> **Progress past the budget.** Once a run's measured slot-holding time exceeds the budget, the watchdog MUST grade the run's progress at that poll and at every later poll, and MUST NOT cancel the run on the budget while the run is *progressing*. A run is progressing when, within its *progress window* ending at the poll, either (a) the run created a new work-in-progress capture (§"Dispatcher admission, WIP cap, and post-merge acceptance" → "Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref"), or (b) the run's own event stream records the completion of a workflow node that had not completed earlier in the same run. The progress window is the largest node timeout resolved for the dispatch (§"ACP node timeouts"), so every legitimately running node can complete within it. Liveness signals (an agent heartbeat, a command node being open, events of nodes that already completed earlier in the run) MUST NOT count as progress for this grading. A grading whose inputs cannot be read MUST be treated as not progressing; it MUST NOT be read as progress. When a grading finds the run not progressing, the run takes the budget disposition below. When a run's measured budget is exceeded, it is not progressing, and it also meets the stalled-no-progress rule, the budget takes precedence: the run takes the budget disposition below and never the stall disposition, including while a budget export is held pending its read-back.
>
> On the first poll at which a run continues past its budget, the Dispatcher MUST journal one `run-wall-budget-continued` record naming the work-item, the dispatch id, the run id, the factory, the stage, the elapsed seconds, the budget, the progress window and the progress evidence (the capture ref and its commit, or the node that completed and its completion instant). It MUST add one ledger comment to the item naming the same. Each later grading that continues the run MUST journal a `run-wall-budget-continued` record carrying the same fields and MUST NOT add a further ledger comment. A `run-wall-budget-continued` record is not a hold under "Journal-recorded holds" and does not retire one.
>
> **The hard ceiling.** Whatever its progress, a run whose slot-holding time is strictly greater than the resolved `dispatcher.run_wall_ceiling_seconds` MUST take the budget disposition below, journaling `run-wall-budget-exceeded` with the ceiling named as the bound that was exceeded. A run that continues past its budget is therefore bounded by the ceiling. A loop inside the run that keeps committing different trees is also bounded by the workflow's own visit and rework limits, which this paragraph does not change.

In the next paragraph ("When the budget is exceeded, the Dispatcher MUST first export ..."), replace "When the budget is exceeded" with "When a run takes the budget disposition (its budget is exceeded and it is not progressing, or its ceiling is exceeded)". In the `run-wall-budget-exceeded` record's required fields, add "the bound exceeded (`budget` or `ceiling`) and, for a `budget` bound, the progress window and the statement that no progress was observed within it". The rest of the budget disposition, including the rest at `blocked` with `blocked_reason` `needs-human`, the not-non-convergence rule, the held-export path and Scenario 175's held-export cases, MUST stay as it is. A run waiting on a human after a budget cancel MUST continue to hold no factory slot and MUST NOT count against `wip_cap`.

In §"ACP node timeouts", after the paragraph "**Whole-run wall budget key.**", add:

> **Whole-run wall ceiling key.** `dispatcher.run_wall_ceiling_seconds` is a positive integer of seconds for the hard ceiling of §"Dispatcher progress watchdog" → "The hard ceiling". It resolves through the same three layers as the budget key, with a per-dispatch `--run-wall-ceiling-seconds <seconds>` argument as the most specific layer. Its built-in default is three times the resolved budget. The dispatch record MUST journal the resolved ceiling and name the layer that supplied it. A non-positive or non-integer value MUST be rejected before any run exists, naming the key or argument. A resolved ceiling smaller than the resolved budget MUST be rejected before any run exists, naming both keys and both values. It is committed-configuration-only and does not trigger the console Settings lockstep.

In the paragraph on the worker's maximum run budget ("The worker's maximum run budget is the smaller of two figures."), the bounded credential-use window MUST be the resolved `dispatcher.credential_queue_allowance_seconds` plus the whole-run wall CEILING resolved for the same dispatch, in place of the whole-run wall budget. The freshness gate's required figure and the status and manual-renewal surfaces follow that change. The in-sandbox start check's queue-exceeded refusal MUST keep comparing the remaining time against the resolved whole-run wall budget, so that a run that may not complete its budget's worth of running time is still refused before any coding-agent turn starts. Replace the sentence "The whole-run wall budget is not itself a hard bound:" with "Neither the whole-run wall budget nor its ceiling is itself a hard bound:", keeping the rest of that sentence.

In `SPECIFICATION/scenarios.md`, retitle `## Scenario 175 — A run past the whole-run wall budget is exported, cancelled and rested for a human` to `## Scenario 175 — A run past the whole-run wall budget continues while it progresses, and otherwise is exported, cancelled and rested for a human`. The revise that accepts this proposal MUST update that heading's entry in `tests/heading-coverage.json` in the same change. Replace its case "A progressing run is still bounded" with the cases below, and add the condition "And no work-in-progress capture and no first completion of a node was recorded within its progress window" to every existing case that cancels on the budget:

```gherkin
  Scenario: A run that committed work within its progress window continues past the budget
    Given a dispatch whose resolved budget is 21600 seconds and whose largest resolved node timeout is 14400 seconds
    And its run has held its slot for more than 21600 seconds
    And the run created a new work-in-progress capture 3000 seconds before the poll
    When the watchdog samples the run
    Then the run is not cancelled
    And the journal carries one run-wall-budget-continued record naming the capture ref and its commit
    And the item carries one ledger comment naming the continuation
  Scenario: A run that completed a new node within its progress window continues past the budget
    Given a run past its budget whose event stream records the first completion in the run of its janitor node within its progress window
    And the run created no work-in-progress capture within that window
    When the watchdog samples the run
    Then the run is not cancelled and the run-wall-budget-continued record names the janitor node and its completion instant
  Scenario: Liveness alone is not progress past the budget
    Given a run past its budget whose agent heartbeat is fresh and whose event stream shows a command node open
    And the run created no work-in-progress capture and completed no node for the first time within its progress window
    When the watchdog samples the run
    Then it exports and cancels the run as run-wall-budget-exceeded with the bound budget
    And the item rests at blocked with blocked_reason needs-human
  Scenario: A repeated visit to a completed node is not progress
    Given a run past its budget whose event stream within its progress window records only completions of the pr_refresh node, which had completed earlier in the run
    And the run created no work-in-progress capture within that window
    When the watchdog samples the run
    Then it exports and cancels the run as run-wall-budget-exceeded with the bound budget
  Scenario: An ungradable run past the budget is not treated as progressing
    Given a run past its budget whose work-in-progress refs and event stream cannot be read at the poll
    When the watchdog samples the run
    Then it takes the budget disposition and does not continue the run
  Scenario: The ceiling bounds a progressing run
    Given a dispatch whose resolved ceiling is 64800 seconds
    And its run has held its slot for more than 64800 seconds while creating a new work-in-progress capture within its progress window
    When the watchdog samples the run
    Then it exports and cancels the run as run-wall-budget-exceeded with the bound ceiling
  Scenario: A ceiling below the budget is refused before any run exists
    Given a .livespec.jsonc whose dispatcher.run_wall_ceiling_seconds is smaller than its dispatcher.run_wall_budget_seconds
    When a dispatch is requested
    Then it is rejected before any run exists, naming both keys and both values
  Scenario: A continued run's credential window covers the ceiling
    Given a dispatch whose resolved credential queue allowance is 86400 seconds, budget 21600 seconds and ceiling 64800 seconds
    When the worker's credential-use deadline is projected
    Then it is the projection instant plus 151200 seconds
    And the in-sandbox start check still refuses a first launch when less than 21600 seconds remain before that deadline
  Scenario: A run resting for a person blocks no admission
    Given an item resting at blocked with blocked_reason needs-human after a budget cancel
    When the next admission pass counts claims against wip_cap
    Then the item is not a counted claim and its run holds no factory slot
```
