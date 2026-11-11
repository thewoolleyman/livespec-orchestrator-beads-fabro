---
topic: reconcile-runs-prints-a-bare
author: claude-opus-5-5:dispatcher-run-watch-cost
created_at: 2026-11-11T22:04:27Z
---

## Proposal: An attribution-pending hold's move remedy carries its press-only-when-dead precondition

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The reconciliation hold `attribution-pending` covers both a dispatch that died before its run existed and a live dispatch that has been admitted but has not yet created its run, and the two read identically. The clause requires the held entry to name the operator `move` valve as its remedy, and the implementation prints and journals that remedy bare, so a reader who presses it on a live dispatch releases a live claim. This proposal keeps the `move` valve as the named remedy and adds one requirement: the printed held line and the journaled `stranded-claim-hold` record MUST both state, beside the remedy, that the valve releases the claim and is to be pressed only after the dispatch's launcher and drive are observed dead. A new scenario inside Scenario 196 exercises it, and the one existing Scenario 196 step that names the bare remedy for this hold is brought in line.

### Motivation

Owning work item bd-ib-ajfmkw, "reconcile-runs prints a bare 'move:<id>:ready' remedy on attribution-pending holds, which releases a LIVE dispatch's claim if pressed". It was refused at admission on v0.320.0 (2026-11-11T21:58:12Z) as spec-change tier, held for this topic. The spec-stated judgement found the asked-for behaviour partial and named "## Dispatcher policy settings" as the heading to generalize: the clause requires the `move` remedy, but states no precondition. Measured instance, 2026-11-07 22:00-22:11Z: bd-ib-w5yzzt and bd-ib-7gssim were live admitted dispatches whose drive.py and dispatcher.py loop processes were alive, with no run on the petri server yet because their wave's source push sat in the pre-push gate queue. timer:reconcile-runs journaled `stranded-claim-hold` with `reason: attribution-pending` and `remedy: drive --action 'move:<work-item-id>:ready'` for both. A seat that read the row literally would have released both live claims. Today the remedy is the bare constant `ATTRIBUTION_PENDING_REMEDY` in `_dispatcher_stranded_claim_grade.py`, printed by `_dispatcher_reconcile_runs_command.py` and journaled by `_dispatcher_stranded_claim_records.py`. Routed to plan dispatcher-run-watch-cost (epic bd-ib-k7ymgx) on legacy-coordinator-agent's ruling (session b3a6daf9, 2026-11-11). In-flight survey: no open proposal or spec branch touches this clause; the open spec PRs #4977 and #4971 touch unrelated proposals.

### Proposed Changes

1. contracts.md, §"Dispatcher policy settings", in the reconciliation **Holds** list, item 2 (`attribution-pending`): the sentence "Its held entry MUST name the operator `move` valve as the remedy." MUST become:

"Its held entry MUST name the operator `move` valve as the remedy, and MUST state beside it the precondition that pressing the valve releases the claim and is to be pressed only after the dispatch's launcher and drive have been observed dead. The pass's printed held line for the claim and its journaled `stranded-claim-hold` record MUST each carry that precondition beside the remedy. A remedy printed or journaled without it MUST NOT be emitted for this reason, because a live dispatch that has been admitted but has not yet created its run reads exactly like a dispatch that died before its run existed, and pressing the bare remedy on the first releases a live claim."

No other sentence of that item changes. The other hold reasons and their remedies are unchanged.

2. scenarios.md, §"Scenario 196 — Reconciliation releases or completes a stranded dispatch claim on its owning host, and holds with a named reason every claim it cannot prove stranded": inside that section's gherkin block, insert this scenario IMMEDIATELY AFTER the `Examples:` table of `Scenario Outline: A claim that cannot be proved stranded is held with the reason of its first failing condition` (whose last row is the `effect-unobservable` row), and BEFORE `Scenario: The earliest failing condition names the hold`, separated from each by one blank line:

```gherkin
  Scenario: An attribution-pending hold names the move valve with its press-only-when-dead precondition
    Given the item carries a pending stamp with no run id
    And every condition graded before attribution-pending in the hold order passes
    When a reconcile-runs pass runs
    Then the item stays active with assignee fabro and its labels unchanged
    And the pass lists the claim in held with the reason attribution-pending
    And the printed held line names the operator move valve as the remedy together with the precondition that the valve releases the claim and is pressed only after the dispatch's launcher and drive are observed dead
    And the journaled stranded-claim-hold record for the claim carries the same remedy and the same precondition
```

3. scenarios.md, in the same Scenario 196 gherkin block, in `Scenario: A newly admitted dispatch that has not learned its run is not mistaken for the old claim`, the step "And the pass lists the claim in held with the reason attribution-pending, naming the move valve as the remedy" MUST become "And the pass lists the claim in held with the reason attribution-pending, naming the move valve as the remedy together with its press-only-when-dead precondition". No other step of that scenario changes.

No H2 heading is added, removed or renamed, so `tests/heading-coverage.json` needs no co-edit.
