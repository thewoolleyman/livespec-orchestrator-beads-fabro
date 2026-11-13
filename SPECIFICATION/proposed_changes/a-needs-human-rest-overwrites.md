---
topic: a-needs-human-rest-overwrites
author: claude-opus-5-5:dispatcher-run-watch-cost
created_at: 2026-11-12T04:38:58Z
---

## Proposal: A needs-human rest and its release leave the item's admission label as it was

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The ratified text says an admission label is not a hold mechanism and that a deliberate hold is status `blocked` with a recorded reason, but no clause says what a needs-human rest does to the label. The implementation's rest writers overwrite it with `admission:manual`, and the `resolve-blocked` release restores nothing, so an item released to `ready` carries a label the fleet's ticketing seats read as a hand-lane hold and is never ticketed. This proposal adds one requirement to the `dispatcher.auto_approve_ready` bullet of §"Dispatcher policy settings": the Dispatcher MUST NOT write, remove or change an item's admission label when it rests the item at `blocked` / `needs-human`, and `resolve-blocked:<id>:ready` MUST leave the label exactly as it was. One new un-numbered scenario exercises it across a rest and a release for an item carrying `admission:auto`, `admission:manual`, and no label.

### Motivation

Owning work item bd-ib-oz2pxq, "A needs-human rest overwrites the item's admission label with admission:manual, so an item released to ready carries a label the fleet reads as a hand-lane hold and is never ticketed". Its re-dispatch was refused at the pre-dispatch spec-tier wall at 2026-11-12T04:23:01Z on spec v357, held for this topic: the spec-stated judgement reported the asked-for behaviour unstated and named "## Dispatcher policy settings" as the heading to generalize. The refusal is right. The clause says an admission label is not a hold mechanism, and Scenario 36 already makes a `needs-human` block escalate under any combination of policy settings, so the `blocked` / `needs-human` status IS the hold; but no clause says a rest leaves the label alone, and Scenarios 172 and 175 say nothing about it.

Measured on registered build 456712f1af12 and master 8ddba27f0: the whole-run wall budget rest (`_dispatcher_run_wall_budget_disposition.py`, intent run-wall-budget-rest), the external-cancel rest (`_dispatcher_terminal_routing.py`, intent external-cancel-rest) and the second stall-cancel rest (`_dispatcher_stall_disposition.py`, intent stall-repeat-rest) each pass `admission_policy="manual"` to `update_work_item_blocked_state`. The Fabro human-gate rest in `_dispatcher_blocked.py` (intent needs-human-block) writes the same value, and the code comments justify it as making sure "no further dispatch happens without a human" because "`blocked` alone is a status the drain could still be configured to admit" — a reason the ratified text already answers, since the status is the hold and the label gates only `pending-approval` to `ready`. The release, `resolve_blocked_item` in `_drive_policy_valves.py`, clears `blocked_reason` and never touches the label. The fleet's ticketing seats mark a hand-landed item with `admission:manual` plus a reason comment and do not ticket it; a rest-written label is indistinguishable from that marker. Named cases: bd-ib-rhivsm (stuck from 2026-11-08 until cleared 2026-11-10T05:01Z), bd-ib-t3bnab, overseer-xon2cf; at filing, 22 ready items in this tenant carried `admission:manual`.

Shape decided by the dispatcher-run-watch-cost plan seat (epic bd-ib-k7ymgx), reported to legacy-coordinator-agent for objection: rests stop writing the label, and the release leaves it unchanged. Rejected: "the release clears a rest-written label by provenance", because ledger labels carry no provenance and, once rests stop writing the label, there is nothing for the release to clear. Clearing labels earlier rests already wrote is fleet residue for the ticketing seats, not part of this requirement. bd-ib-oz2pxq's Definition of Done names the three rests it measured; the requirement covers every needs-human rest, so the human-gate rest is in scope for its implementer too.

In-flight survey: open PR #4998 (attended-human-publishing-identity) and eight remote `spec/*` branches touch no admission-label or needs-human rest text. The pending in-tree proposal reconcile-runs-prints-a-bare edits a different list item of the same section (the reconciliation Holds list), and the-dispatcher-s-watch-still edits the run watch; both are compatible and aligned with.

### Proposed Changes

1. contracts.md, §"Dispatcher policy settings" → "The five policy settings", in the `dispatcher.auto_approve_ready` bullet: IMMEDIATELY AFTER the sentence "An admission label is not a hold mechanism: a deliberate per-item hold MUST be expressed as status `blocked` with its reason recorded on the item.", and BEFORE the sentence beginning "The Dispatcher MUST NOT auto-approve a **design-human-gated (spec-change-tier) item**", insert:

"The Dispatcher MUST NOT write, remove or change an item's admission label when it rests the item at `blocked` / `blocked_reason: needs-human`. This governs every needs-human rest, including the rest at the workflow's `needs_human` terminal, the whole-run wall budget rest, the rest after a cancel made outside the Dispatcher, the second stall-watchdog cancel rest, the `run-absent-repeated` rest, and the rest of a \"Live-run wall budget\" disposition. The rest's `blocked` status with its recorded reason is the hold. `resolve-blocked:<work-item-id>:ready` and `resolve-blocked:<work-item-id>:backlog` MUST leave the item's admission label exactly as it was: an item that carried `admission:auto`, `admission:manual` or no admission label before the rest carries the same after the release."

No other sentence of that bullet changes, and no other policy setting changes.

2. scenarios.md: append one new H2 section at the end of the file, after the last existing section, separated from it by one blank line:

## Scenario: a needs-human rest and its release leave the item's admission label as it was

```gherkin
Feature: a needs-human rest and its release leave the item's admission label as it was

  Scenario Outline: a needs-human rest leaves the admission label unchanged
    Given a dispatched item whose admission label is <label>
    When the Dispatcher rests the item at blocked with blocked_reason needs-human through <rest>
    Then the item is blocked with blocked_reason needs-human
    And the item's admission label is <label>

    Examples:
      | label            | rest                                                |
      | admission:auto   | the whole-run wall budget rest                      |
      | admission:auto   | the rest after a cancel made outside the Dispatcher |
      | admission:auto   | the second stall-watchdog cancel rest               |
      | admission:auto   | the rest at the workflow's needs_human terminal     |
      | admission:manual | the whole-run wall budget rest                      |
      | none             | the whole-run wall budget rest                      |

  Scenario Outline: resolve-blocked returns a rested item to ready with its admission label unchanged
    Given an item resting at blocked with blocked_reason needs-human whose admission label is <label>
    When the human runs drive --action resolve-blocked:<work-item-id>:ready
    Then the item is ready with no blocked_reason
    And the item's admission label is <label>

    Examples:
      | label            |
      | admission:auto   |
      | admission:manual |
      | none             |
```

In both outlines the label value `none` means the item carries no admission label.

3. Because item 2 adds an H2 heading, the revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for it in the same change. Its `test` MAY be `"TODO"`, and its `reason` MUST name bd-ib-oz2pxq as the work item that owns the scenario's cases.
