---
topic: factory-run-wall-budget
author: claude-opus-5-5:factory-run-wall-budget-plan
created_at: 2026-10-14T00:32:05Z
---

## Proposal: A whole-run wall budget bounds how long one factory run holds a slot

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add a configured whole-run wall budget, `dispatcher.run_wall_budget_seconds`, beside the node timeouts. The Dispatcher's progress watchdog enforces it. A run whose slot-holding time exceeds the budget is exported, then cancelled, which releases its factory slot. The Dispatcher journals a distinct `run-wall-budget-exceeded` record and rests the item at `blocked` / `needs-human` with that reason and the run's work preserved by reference. A budget cancel is never non-convergence. A budget smaller than any node timeout resolved for the dispatch is refused before any run exists. A budget cancel whose export cannot be read back is held and journaled, never forced.

### Motivation

Measured on hp's fleet Fabro server. On 2026-10-13 (07:12Z to 23:45Z, fleet cap 10; measurement on bd-ib-sdxfsn), runs that parked at needs_human after implement, pr, proof_capture or fix held a slot 200 to 390 minutes each, while the successful-run median was 99 minutes. Runs ending at needs_human used 92.2 of about 120 slot-hours. On 2026-10-14, plan factory-run-wall-budget (epic bd-ib-hqt3s5, research `plan/factory-run-wall-budget/research/001-origin-measurements-and-direction-2026-10-14.md`) read `fabro ps -a --server hp --json` for 2026-09-30 to 2026-10-14. Over that window, 94 ImplementWorkItem runs succeeded from 2026-10-07 on: p50 85 minutes, p90 172, max 348. 245 runs failed: p50 65, p90 254, max 548. Nothing bounds a whole run today. Per-node timeouts and the stall window are bounds on one node and on one quiet stretch. The `fabro run` subprocess ceiling of §"ACP node timeouts" is derived from the graph's worst case; on this repository it is 145800 seconds (40.5 hours). `_dispatcher_execution_budget` explicitly says a sum of separately bounded operations is not a deadline anything enforces.

The same measurement fixes the default. A budget near twice the median would have cut off 7 of the 60 successes since 2026-10-11, so it would be a false kill of healthy runs. The proposed default of 21600 seconds cuts off 0 of the 94 successes since 2026-10-07. It would have returned about 7 slot-hours a week from the failed runs. A repository that wants a tighter trade sets the key.

The cancel reuses rails that are already ratified. It uses the export-then-terminate precondition of §"A factory run never awaits a human". It uses the cancel record of the Dispatcher progress watchdog. It uses the needs-human rest and the not-non-convergence rule of that subsection. So a budget cancel adds a reason and a bound, not a new pipeline.

### Proposed Changes

### contracts.md

In `## ACP node timeouts`, under **Keys.**, after the sentence ending "is a positive integer of seconds for the run-level stall watchdog.", insert:

```markdown
`dispatcher.run_wall_budget_seconds` is a positive integer of seconds for
the whole-run wall budget of the Dispatcher progress watchdog; with no
configured value it MUST resolve to **21600** seconds. It resolves through
the same layers as the node timeouts, and the dispatch record MUST name the
layer that supplied it. A resolved budget smaller than any node timeout
resolved for the same dispatch MUST be rejected before any run exists,
naming both keys and both values, because such a budget would cancel that
node's legitimate turn.
```

In `### Dispatcher progress watchdog`, insert a new paragraph immediately after the paragraph that begins **The cancel record.**:

```markdown
**The whole-run wall budget.** The watchdog MUST also bound how long one
run holds a factory slot, by the resolved `dispatcher.run_wall_budget_seconds`
(§"ACP node timeouts"). The budget clock MUST start at the instant the
factory first reports the run `running`. That instant is read from the
run's own record when the record carries it. Otherwise it is the first
watchdog poll that observes the run `running`. Time a run spends queued
before that instant, including `runnable`, MUST NOT count, because a queued
run holds no slot. The budget is independent of progress. A run making
progress MUST still be cancelled once its elapsed slot-holding time exceeds
the budget, and an open command node does not defer it. When the budget is
exceeded, the Dispatcher MUST first export the run's record under the
export-then-terminate precondition of §"A factory run never awaits a human".
That means writing and reading back the preserve-by-reference pointer. Only
then MUST it cancel the run, and cancelling the run is what releases its
slot. It MUST journal one `run-wall-budget-exceeded` record carrying every
field of the cancel record above, plus the elapsed slot-holding seconds,
the budget, and the layer that supplied the budget. It MUST then rest the
item at `blocked` with `blocked_reason` `needs-human`, and its ledger
comment MUST name the run id, the factory, the stage, the elapsed seconds,
the budget, the preserve-by-reference pointer, and, when the record names
them, the pull request and the published head. That comment MUST also name
the remedy `resolve-blocked:<id>:ready`. A budget cancel is not
non-convergence, under the same rule as a `stalled-no-progress` outcome
above. It is not released to `ready` automatically, and it neither
increments nor resets the item's count under §"Across-dispatch
required-result progress". When the export cannot be read back, the
Dispatcher MUST NOT cancel the run. It MUST journal one
`run-wall-budget-held` record naming the run, the elapsed seconds, the
budget and the failed measurement, and it retries on the next poll. When
the run's `running` instant cannot be read and no poll has yet observed it
`running`, the budget is unmeasured, and the watchdog MUST NOT cancel on
it. Scenario 175 in `scenarios.md` exercises this paragraph.
```

### scenarios.md

Append a new scenario after Scenario 174:

```markdown
## Scenario 175 — A run past the whole-run wall budget is exported, cancelled and rested for a human

```gherkin
Feature: One factory run holds a slot no longer than the whole-run wall budget
  Scenario: A run past the budget parks at needs-human with its work preserved
    Given a dispatch whose resolved dispatcher.run_wall_budget_seconds is 21600
    And its run has been running for longer than 21600 seconds since the factory first reported it running
    When the watchdog samples the run
    Then the Dispatcher writes and reads back the run's preserve-by-reference pointer before it cancels the run
    And the run is cancelled and no longer holds a factory slot
    And the journal carries one run-wall-budget-exceeded record naming the run id, the factory, the stage, the elapsed seconds, the budget and the layer that supplied it
    And the item rests at blocked with blocked_reason needs-human
    And its ledger comment names the run id, the stage, the elapsed seconds, the budget, the preserve-by-reference pointer and the remedy resolve-blocked:<id>:ready
    And no non-convergence-bounce record is journaled and the item is not moved to backlog
  Scenario: Queue time does not count against the budget
    Given a run that waited as runnable before the factory first reported it running
    And the time since it first ran is less than the budget while the time since it was submitted is more
    When the watchdog samples the run
    Then it does not cancel the run
  Scenario: A progressing run is still bounded
    Given a run whose event stream shows a command node started and not completed
    And its slot-holding time exceeds the budget
    When the watchdog samples the run
    Then it exports and cancels the run as run-wall-budget-exceeded
  Scenario: A published run names its pull request and head
    Given a run past the budget whose event stream records a completed publish_draft
    When the Dispatcher journals run-wall-budget-exceeded
    Then the record and the ledger comment name the pull request and the head the run's last completed publish_draft pushed
  Scenario: An export that cannot be read back holds the cancel
    Given a run past the budget whose preserve-by-reference pointer cannot be read back
    When the watchdog samples the run
    Then it does not cancel the run
    And the journal carries a run-wall-budget-held record naming the run, the elapsed seconds, the budget and the failed measurement
  Scenario: An unmeasured start is not a cancel
    Given a run whose record carries no running instant and which no watchdog poll has yet observed running
    When the watchdog samples the run
    Then it does not cancel the run on the budget
  Scenario: A budget below a node timeout is refused before any run exists
    Given a dispatch target whose resolved dispatcher.run_wall_budget_seconds is smaller than its resolved implement node timeout
    When the Dispatcher prepares the dispatch
    Then it refuses before any run exists, naming dispatcher.run_wall_budget_seconds, dispatcher.node_timeouts.implement and both values
  Scenario: The default budget
    Given a dispatch target that configures no dispatcher.run_wall_budget_seconds
    When the Dispatcher prepares the dispatch
    Then the resolved budget is 21600 seconds and the dispatch record names the default layer
```
```

### tests/heading-coverage.json

Add one entry for the new scenarios.md heading `## Scenario 175 — A run past the whole-run wall budget is exported, cancelled and rested for a human`, with `test` set to `"TODO"` and `reason` set to `"implemented by bd-ib-sdxfsn (plan factory-run-wall-budget, epic bd-ib-hqt3s5)"`. The contracts.md edits add no `## ` heading.
