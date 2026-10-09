---
topic: dispatcher-successful-terminal-evidence
author: codex
created_at: 2026-10-09T14:55:22Z
---

## Proposal: Reconcile authenticated terminal success separately from engine event persistence

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Define the bounded Dispatcher evidence rule required by plan run-lifecycle-false-verdicts assertion 3 and existing implementation child bd-ib-l55d7e.

### Motivation

The user instructed autonomous completion, full Definition of Done, proof and archive of run-lifecycle-false-verdicts. Factory run 01M4GJ5KMVGH4VJEKQBBC4DQ9F correctly refused the existing child because its Fabro runtime reference did not govern terminal-result reconciliation. The observed incident completed verify_pr but the engine lost its terminal-event storage; the Dispatcher reported failure despite matching publication. This proposal supplies the missing normative rule and negative controls without expanding into engine storage repair.

### Proposed Changes

Insert the following H2 before Dispatcher policy settings in contracts.md and append the scenario to scenarios.md. Link Scenario 166 in tests/heading-coverage.json to existing child bd-ib-l55d7e until its real integration proof lands. No new duplicate child is required.

## Dispatcher successful terminal evidence

The Dispatcher MUST distinguish successful workflow completion from an engine's
failure to persist its terminal run event. A worker-exit conclusion that reports
exit status zero before emitting a terminal event MUST NOT by itself turn a
completed successful workflow into a failed implementation. Reconciliation of
this conflict MUST use the latest available structured checkpoint for the current
run and matching forge publication evidence; free-form assistant prose, a process
exit code alone, or a successful earlier attempt MUST NOT establish completion.

The checkpoint MUST identify the current run, establish that its configured
successful terminal route has completed all required preceding stages, and carry
successful outcomes for those stages. A checkpoint at the final successful stage
whose next node is the configured successful exit qualifies; requiring a separate
completed exit-node entry MUST NOT exclude that engine representation. A merely
intermediate checkpoint, a failed required stage, cancellation, non-convergence,
or a needs-human route MUST NOT qualify. Publication MUST be observed on the
expected repository and publish branch at the checkpoint's successful published
head; a stale or unrelated pull request, a closed unmerged pull request, a head
mismatch, or unavailable evidence MUST NOT establish successful completion.

When both evidence legs qualify, the Dispatcher MUST continue its ordinary
pull-request and merge reconciliation and report the matching pull request and
its observed publication or merge state. This classification MUST NOT bypass
merge holds, required checks, proof verification, post-merge janitor, acceptance,
or any other ordinary disposition guard. A pending merge remains pending and a
later reconciliation failure retains its normal non-green outcome. Without both
evidence legs, the conflict MUST retain the ordinary non-green disposition.

The dispatch journal MUST identify the run, the structured completion and
publication evidence used, and the conflicting engine conclusion separately from
the successful-workflow classification. It MUST retain the conflict actually
observed through supported engine surfaces, without fabricating server-log
access, timestamps or events. This rule changes Dispatcher evidence reconciliation
only; it makes no claim to repair the engine's run store.


## Scenario 166 — Successful terminal evidence survives an engine terminal-event persistence failure

Governing clause: `contracts.md` §"Dispatcher successful terminal evidence".

```gherkin
Feature: reconcile successful completion separately from run-store loss
  Scenario Outline: authenticated successful completion reaches normal publication reconciliation
    Given the latest structured checkpoint identifies the current run and its successful published head
      And every required stage on its configured successful terminal route succeeded
      And the checkpoint <terminal_shape>
      And the expected repository and publish branch have a matching pull request at that head
      And the engine reports a zero-status worker exit before a terminal run event was persisted
    When the Dispatcher classifies the run through its ordinary dispatch path
    Then it continues normal pull-request and merge reconciliation for that pull request
      And it reports the observed publication or merge state without a false implementation failure
      And the journal identifies the run and both evidence legs separately from the conflicting engine conclusion
      And ordinary merge, proof, janitor and acceptance guards still apply
    Examples:
      | terminal_shape                                           |
      | records the successful exit completed                    |
      | records the final successful stage with next node at exit |

  Scenario Outline: insufficient or contrary evidence cannot establish successful completion
    Given an engine conclusion reports failure for the current run
      And <defect>
    When the Dispatcher evaluates the terminal evidence conflict
    Then the ordinary non-green disposition remains
      And no stale or unavailable evidence is reported as successful completion
    Examples:
      | defect                                                       |
      | the latest checkpoint is unavailable                         |
      | the checkpoint belongs to another run                        |
      | only an earlier attempt has a successful checkpoint          |
      | the latest checkpoint is intermediate                        |
      | a required stage failed                                      |
      | the run was cancelled                                        |
      | the terminal route is needs-human or non-converged            |
      | the matching pull request is absent or cannot be observed     |
      | the pull request has a different head, branch or repository   |
      | the pull request is closed without merging                   |
      | the worker exited nonzero                                    |

  Scenario: successful classification does not grant merge or acceptance
    Given both successful terminal evidence legs qualify despite the engine conclusion
      And the pull request is held from merging or a later ordinary check fails
    When the Dispatcher continues reconciliation
    Then the hold or failure has its ordinary disposition
      And successful workflow classification does not force a green dispatch or close the item
```

