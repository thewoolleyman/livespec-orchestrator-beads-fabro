---
topic: stall-watchdog-cancel-recovery
author: claude-opus-5-5:stall-watchdog-false-kills-plan
created_at: 2026-10-12T17:23:04Z
---

## Proposal: Dispatcher progress watchdog: what counts as progress, and how a cancel is routed

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Ratify the Dispatcher's wall-clock progress watchdog, which no clause governs today. The ratified behaviour: progress is the newest of the agent heartbeat and the run's own event stream. An open command node is bounded by its resolved node timeout rather than by the stall window. A stall-watchdog cancel is never non-convergence. It journals the cancelled run's stage and any published head. A run that had already published is released and resumed by the Dispatcher; any other cancel rests its item at blocked with blocked_reason needs-human, with a ledger comment naming the run.

### Motivation

Measured 2026-10-12 by plan stall-watchdog-false-kills (epic bd-ib-laf735, research plan/stall-watchdog-false-kills/research/001-measured-false-kills-2026-10-12.md). Three of the six stall cancels on hp since 2026-10-08 killed healthy runs inside the janitor and publish_draft command nodes, because the heartbeat only beats while an agent runs and was preferred over a fresher event stream. All six were then journaled as a non-convergence-bounce, sending each item to backlog and feeding calibration a false 'too big' signal. Scenario 11 defines non-convergence as repeated janitor-gate failure within the fix-loop cap, which neither a hang nor a false kill is. Two of the cancelled runs had already published; their next dispatch reclaimed the publish branch and rebuilt the work from implement (bd-ib-kawo6a took five more hours to merge). No clause covers any of this, so the plan's children bd-ib-nfbyot and bd-ib-3snvbf cannot carry gradeable Definitions of Done: the factory dod_gate refused bd-ib-nfbyot on run 01M4RH31376XYRDRARCFTKMWWK because no heading governs where a stall-cancelled item rests. Routing a published cancel to a Dispatcher-invoked resume follows the precedent v127 set for provider-limit failures: release and resume rather than blocked/needs-human. The second-consecutive-cancel rest keeps a genuine hang from looping.

### Proposed Changes

### contracts.md

Insert a new subsection immediately after `### Dispatcher grooming behavior`:

```markdown
### Dispatcher progress watchdog

The Dispatcher's wall-clock progress watchdog cancels a run that makes no
progress for the configured stall window and reports the distinct
`stalled-no-progress` outcome. This subsection governs what counts as
progress and how a cancel is routed. It does not govern the Fabro engine's
own run-level `stall_timeout` of §"ACP node timeouts".

**Progress.** A liveness sample MUST report the NEWEST progress instant
among every source it reads: the agent heartbeat keyed on the dispatch, and
the run's own Fabro event stream. A source that carries an older instant
MUST NOT mask a source that carries a newer one. While the run's event
stream shows a command node started and not completed, the watchdog MUST
NOT cancel the run before that node's resolved timeout (§"ACP node
timeouts") has elapsed since the node started. A command node emits only
its start and completion events, so the stall window alone cannot bound it.
A run whose every source stays unchanged for the full stall window, with no
command node open, MUST still be cancelled as `stalled-no-progress`.

**The cancel record.** On a cancel the Dispatcher MUST journal one
`watchdog-stall-cancel` record naming the run id, the factory, and the
stage the run was executing. That stage is the node whose start event has
no completion event or, between nodes, the target of the edge its last
succeeded node's outcome selected. When the run's event stream records a
completed `publish_draft`, the record MUST also name the open pull request
and the head the publish branch carries on origin at cancel time. When the
head cannot be observed, the record MUST say so rather than omit it.

**Not non-convergence.** A `stalled-no-progress` outcome is NOT factory
non-convergence (§"Dispatcher grooming behavior"). The Dispatcher MUST NOT
bounce the item to `backlog` for it and MUST NOT journal a
`non-convergence-bounce` record for it. The calibration analysis pass MUST
NOT count it as a non-convergence observation, while a fix-loop-cap
non-convergence still counts.

**Routing.** When the cancel record names a published head, the head equals
the pull request's current head, and the item's immediately preceding
dispatch did not also end `stalled-no-progress`, the Dispatcher MUST release
the item to `ready` and itself invoke `resume --item` under its own invoker
identity, as §"Factory-configurable ACP fallback priority" →
"Provider-limit release and re-dispatch" does. Every other cancel, and every
such resume that refuses, MUST rest the item at `blocked` with
`blocked_reason` `needs-human`. A ledger comment on the item MUST name the
cancelled run id, its factory and its stage. When the run had published, the
comment MUST also name the pull request and the head, and state that
`resolve-blocked:<id>:ready` followed by `resume --item` finishes the work.
A second consecutive stall cancel names both cancelled runs and invokes no
further resume automatically. Scenario 170 in `scenarios.md` exercises this
subsection.
```

### scenarios.md

Append:

```markdown
## Scenario 170 — A stall-watchdog cancel is never non-convergence: a published run is resumed, an unpublished one rests for a human

```gherkin
Feature: A stall-watchdog cancel keeps the work it can and asks a human about the rest
  Scenario: The watchdog does not cancel a run inside an open command node
    Given a dispatched run whose last agent stage completed and whose event stream shows the janitor command node started and not completed
    And the heartbeat has not advanced for longer than the stall window
    When the watchdog samples the run before the janitor node's resolved timeout has elapsed
    Then it does not cancel the run
  Scenario: A newer event masks an older heartbeat
    Given a dispatched run whose heartbeat's newest beat is older than the newest event in its event stream
    When the watchdog samples the run
    Then the sample reports the newer event's instant as the run's progress
  Scenario: A run with no progress and no open command node is still cancelled
    Given a dispatched run whose heartbeat and event stream both stay unchanged for the full stall window with no command node open
    When the watchdog samples it
    Then it cancels the run as stalled-no-progress
  Scenario: A run cancelled after publishing is released and resumed
    Given a dispatched item whose run completed publish_draft, opening a draft pull request at a head
    And the watchdog cancels the run as stalled-no-progress while it executes proof_capture
    When the Dispatcher records the outcome
    Then the journal carries a watchdog-stall-cancel record naming the run id, the factory, proof_capture as the stage, the pull request and that head
    And the item is not moved to backlog and no non-convergence-bounce record is journaled
    And the item is released to ready and the Dispatcher invokes resume for it under its own invoker identity
    And the resumed run enters the workflow at proof_capture on that head and its record shows no visit to dod_gate, implement or janitor
  Scenario: A run cancelled before publishing rests for a human
    Given a dispatched item whose run the watchdog cancels as stalled-no-progress while it executes implement
    When the Dispatcher records the outcome
    Then the item rests at blocked with blocked_reason needs-human
    And a ledger comment on the item names the cancelled run id, its factory and implement as the stage
    And the item is not moved to backlog and no non-convergence-bounce record is journaled
  Scenario: A second consecutive stall cancel rests for a human even after publishing
    Given an item whose resumed run is itself cancelled by the watchdog as stalled-no-progress
    When the Dispatcher records the outcome
    Then the item rests at blocked with blocked_reason needs-human and its ledger comment names both cancelled runs
    And no further resume is invoked automatically
  Scenario: Calibration does not read a stall cancel as non-convergence
    Given a journal holding a stall-cancelled dispatch and a fix-loop-cap non-convergence
    When the calibration analysis pass runs
    Then it counts the fix-loop-cap dispatch as a non-convergence observation
    And it does not count the stall-cancelled dispatch as one
```
```

### tests/heading-coverage.json

Add an entry for `## Scenario 170 — A stall-watchdog cancel is never non-convergence: a published run is resumed, an unpublished one rests for a human` with `test: "TODO"` and a reason naming bd-ib-qsk4o5, bd-ib-nfbyot and bd-ib-3snvbf as the implementing items.

## Proposal: Resume anchored on a stall-cancel record when no proof record exists yet

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Let `resume --item` anchor on the `watchdog-stall-cancel` record when the pull request carries no proof record of the earlier run yet. That is the state every measured stall cancel left, because each struck before or at the start of proof_capture. Narrow the 'nothing to resume from' refusal to match.

### Motivation

Today a resume anchors only on the latest proof record naming a head, and refuses when none exists (Scenario 143, 'Nothing to resume from'). A run that published and was cancelled before proof_capture finished has a reviewed, janitor-green head on an open pull request, but no record. So the only route left is a plain dispatch, which reclaims the branch and rebuilds from implement. That is what happened to bd-ib-z6fmp and bd-ib-kawo6a on 2026-10-11 and 2026-10-12. The cancel record of the companion proposal names the run, the stage and the published head, which is everything the resume needs. The head-equality, Definition-of-Done-snapshot, liveness and two-resume refusals still bind unchanged.

### Proposed Changes

### contracts.md, §"Resume from a published pull request (`resume --item`)"

In **What it resumes**, after the sentence defining the *published head*, add:

```markdown
When no proof record on the pull request carries an identifier of the
earlier run, the earlier run's `watchdog-stall-cancel` record (§"Dispatcher
progress watchdog") anchors the resume instead, provided it names a
published head. The earlier run is that record's dispatch, the published
head is the head it names, and the resumed-at stage is the stage it names,
where a recorded `publish_draft` normalizes to `proof_capture`. The resume
record MUST name the cancel record as the source that decided the stage.
```

In **Refusals**, replace the bullet

```markdown
- the item's publish branch carries no open pull request, or no proof
  record on it names a head (remedy: a plain dispatch);
```

with

```markdown
- the item's publish branch carries no open pull request, or no proof
  record on it names a head and no `watchdog-stall-cancel` record of the
  earlier run anchors one (remedy: a plain dispatch);
```

### scenarios.md

In Scenario 142, add after `Scenario: A run that terminated inside a fix loop resumes at fix`:

```gherkin
  Scenario: A stall-cancelled run with no proof record resumes from its cancel record
    Given a ready item whose earlier run completed publish_draft and was cancelled by the watchdog while executing proof_capture, leaving no proof record on its pull request
    And the earlier run's watchdog-stall-cancel record names a head equal to the pull request's current head
    When resume runs for the item
    Then the new run enters the workflow at proof_capture on that head and no dod_gate, implement or janitor stage runs
    And the resume record names the cancel record as the source that decided the stage
    And the dispatch journal carries neither a publish-branch-reclaim record nor a publish-branch-reclaim-held record for the resume
```

In Scenario 143, replace the `Nothing to resume from` Given with:

```gherkin
    Given a ready item whose publish branch carries no open pull request, or whose pull request carries no proof record naming a head and whose earlier run left no watchdog-stall-cancel record naming one
```
