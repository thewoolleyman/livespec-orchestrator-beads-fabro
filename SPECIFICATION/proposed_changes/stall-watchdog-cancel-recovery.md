---
topic: stall-watchdog-cancel-recovery
author: claude-opus-5-5:stall-watchdog-false-kills-plan
created_at: 2026-10-12T17:26:54Z
---

## Proposal: Dispatcher progress watchdog: what counts as progress, and how a cancel is routed

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Ratify the Dispatcher's wall-clock progress watchdog, which no clause governs today. Progress is the newest of the agent heartbeat and the run's own event stream, and an open command node is bounded by its resolved node timeout. A stall-watchdog cancel is never non-convergence. It is journaled with the cancelled run's stage and the head its last completed publish_draft pushed. A first stall cancel is released and recovered exactly as v127's provider-limit release is: replay-safe release to ready, resume before any reclaim, otherwise a dispatch seeded from preserved work. A second consecutive stall cancel of the same item rests it at blocked / needs-human.

### Motivation

Measured 2026-10-12 by plan stall-watchdog-false-kills (epic bd-ib-laf735, research plan/stall-watchdog-false-kills/research/001-measured-false-kills-2026-10-12.md). Three of the six stall cancels on hp since 2026-10-08 killed healthy runs inside the janitor and publish_draft command nodes, because the heartbeat only beats while an agent runs and was preferred over a fresher event stream. All six were then journaled as a non-convergence-bounce, sending each item to backlog and feeding calibration a false 'too big' signal. Scenario 11 defines non-convergence as repeated janitor-gate failure within the fix-loop cap, which neither a hang nor a false kill is. Two of the cancelled runs had already published; their next dispatch reclaimed the publish branch and rebuilt the work from implement (bd-ib-kawo6a took five more hours to merge). No clause covers any of this, so the plan's children bd-ib-nfbyot and bd-ib-3snvbf cannot carry gradeable Definitions of Done: the factory dod_gate refused bd-ib-nfbyot on run 01M4RH31376XYRDRARCFTKMWWK because no heading governs where a stall-cancelled item rests. Recovery reuses the mechanism v127 ratified for provider-limit failures, unchanged: the same replay-safe release, the same resume-before-reclaim evaluation, and the same seeded-dispatch fallback. So no new race with Scenario 144's reclaim is introduced, and no second release path needs its own idempotence rules. The one departure from that precedent is deliberate: a provider-limit failure is a property of the host, while a repeated hang may be a property of the item. So a SECOND consecutive stall cancel rests at blocked / needs-human rather than releasing again. That, together with the existing two-resume bound, keeps the rule that a slice is never infinite-retried. This proposal was vetted before filing by an independent Opus reviewer and an independent Codex reviewer; this revision folds in every defect either one found.

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
`watchdog-stall-cancel` record naming the work-item, the dispatch id, the
run id, the factory, and the stage the run was executing. That stage is the
node whose start event has no completion event or, between nodes, the
target of the edge its last succeeded node's outcome selected. When the
run's event stream records a completed `publish_draft`, the record MUST
also name the pull request and the head that the LAST completed
`publish_draft` of the run pushed, read from the run's own record. It MUST
NOT be read from origin at cancel time, because origin's branch may have
moved since. When that head cannot be read, the record MUST say so rather
than omit it.

**Not non-convergence.** A `stalled-no-progress` outcome is NOT factory
non-convergence (§"Dispatcher grooming behavior"). The Dispatcher MUST NOT
bounce the item to `backlog` for it and MUST NOT journal a
`non-convergence-bounce` record for it. The calibration analysis pass MUST
NOT count it as a non-convergence observation, while a fix-loop-cap
non-convergence still counts.

**A first stall cancel is released and recovered.** When the item's
immediately preceding dispatch did not also end `stalled-no-progress`, the
Dispatcher MUST, without a human:
1. Journal the cancel record above.
2. Write a ledger comment on the item naming the cancelled run id, its
   factory, its stage and, when the record names one, the pull request and
   the published head.
3. Release the item's dispatch claim and return it to `ready`, with no
   `blocked_reason`.
4. Leave it to the ordinary admission valve.

That valve's next dispatch of the item applies §"Factory-configurable ACP
fallback priority" → "Recovery from the failed run's preserved work"
unchanged. Before any stale publish-branch reclaim, it evaluates the resume
preconditions, which the cancel record can now anchor (§"Resume from a
published pull request (`resume --item`)"). It invokes resume under its own
invoker identity when they pass, and otherwise makes a dispatch seeded from
preserved work. The release MUST be idempotent and replayable by
reconciliation, keyed by factory and run, exactly as a provider-limit
release is. A released stall cancel MUST NOT consume any budget of §"The
three rework caps", and it neither increments nor resets the item's count
under §"Across-dispatch required-result progress".

**A second consecutive stall cancel rests for a human.** When the item's
immediately preceding dispatch also ended `stalled-no-progress`, the
Dispatcher MUST journal the cancel record, MUST NOT release the item, and
MUST rest it at `blocked` with `blocked_reason` `needs-human`
(§"A factory run never awaits a human"). It counts as one item-attributable
terminal under §"Across-dispatch required-result progress". Its ledger
comment MUST name both cancelled runs, their factories and their stages,
and the remedy the resume refusal ladder computes for the item's current
state. A plain dispatch is the remedy wherever resume would refuse.
Scenario 170 in `scenarios.md` exercises this subsection.
```

In §"Resume from a published pull request (`resume --item`)", replace the
opening paragraph's sentence

```markdown
The one exception to both
statements is an item released under §"Factory-configurable ACP fallback
priority" → "Provider-limit release and re-dispatch":
```

with

```markdown
The exceptions to both
statements are an item released under §"Factory-configurable ACP fallback
priority" → "Provider-limit release and re-dispatch" and an item released
after a first stall cancel under §"Dispatcher progress watchdog":
```

### scenarios.md

Append:

```markdown
## Scenario 170 — A stall-watchdog cancel is never non-convergence: a first cancel is released and recovered, a second rests for a human

```gherkin
Feature: A stall-watchdog cancel keeps the work it can and asks a human only on a repeat
  Scenario: The watchdog does not cancel a run inside an open command node
    Given a dispatched run whose last agent stage completed and whose event stream shows the janitor command node started and not completed
    And the heartbeat has not advanced for longer than the stall window
    When the watchdog samples the run before the janitor node's resolved timeout has elapsed
    Then it does not cancel the run
  Scenario: A newer event is not masked by an older heartbeat
    Given a dispatched run whose heartbeat's newest beat is older than the newest event in its event stream
    When the watchdog samples the run
    Then the sample reports the newer event's instant as the run's progress
  Scenario: A run with no progress and no open command node is still cancelled
    Given a dispatched run whose heartbeat and event stream both stay unchanged for the full stall window with no command node open
    When the watchdog samples it
    Then it cancels the run as stalled-no-progress
  Scenario: A first stall cancel after publishing is released and resumed
    Given a dispatched item whose run completed publish_draft, pushing a head to an open draft pull request
    And the watchdog cancels the run as stalled-no-progress while it executes proof_capture
    And the item's preceding dispatch did not end stalled-no-progress
    When the Dispatcher records the outcome
    Then the journal carries a watchdog-stall-cancel record naming the run id, the factory, proof_capture as the stage, the pull request and that head
    And a ledger comment on the item names the run id, the factory, the stage, the pull request and the head
    And the item is returned to ready with no blocked_reason, is not moved to backlog, and no non-convergence-bounce record is journaled
    And the next dispatch of the item invokes resume and journals neither a publish-branch-reclaim record nor a publish-branch-reclaim-held record
    And when the resumed run's review approves, its record shows no visit to dod_gate, implement or janitor
  Scenario: A first stall cancel before publishing is released and recovered from preserved work
    Given a dispatched item whose run the watchdog cancels as stalled-no-progress while it executes implement
    And the item's preceding dispatch did not end stalled-no-progress
    When the Dispatcher records the outcome
    Then a ledger comment on the item names the run id, the factory and implement as the stage
    And the item is returned to ready, is not moved to backlog, and no non-convergence-bounce record is journaled
  Scenario: A second consecutive stall cancel rests for a human
    Given an item whose preceding dispatch ended stalled-no-progress
    When the watchdog cancels the item's current run as stalled-no-progress
    Then the item rests at blocked with blocked_reason needs-human
    And its ledger comment names both cancelled runs, their factories and stages, and the remedy the resume refusal ladder computes
    And no further dispatch or resume is invoked automatically
  Scenario: Calibration does not read a stall cancel as non-convergence
    Given a journal holding a stall-cancelled dispatch and a fix-loop-cap non-convergence
    When the calibration analysis pass runs
    Then it counts the fix-loop-cap dispatch as a non-convergence observation
    And it does not count the stall-cancelled dispatch as one
```
```

### tests/heading-coverage.json

Add an entry for `## Scenario 170 — A stall-watchdog cancel is never non-convergence: a first cancel is released and recovered, a second rests for a human` with `test: "TODO"` and a reason naming bd-ib-qsk4o5, bd-ib-nfbyot and bd-ib-3snvbf as the implementing items.

## Proposal: Resume anchored on a stall-cancel record when no proof record exists yet

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Let `resume --item` anchor on a `watchdog-stall-cancel` record when the pull request carries no proof record of the earlier run. Every measured stall cancel left exactly that state. The anchor is limited to a cancel at or before proof_capture on the head the run's last completed publish_draft pushed, and the 'nothing to resume from' refusal is narrowed to match.

### Motivation

Today a resume anchors only on the latest proof record naming a head, and refuses when none exists (Scenario 143, 'Nothing to resume from'). A run that published and was cancelled before proof_capture finished has a reviewed, janitor-green head on an open pull request, but no record. So the only route left is a plain dispatch, which reclaims the branch and rebuilds from implement. That is what happened to bd-ib-z6fmp and bd-ib-kawo6a on 2026-10-11 and 2026-10-12. The cancel record of the companion proposal names the run, the stage and the published head, which is everything the resume needs. The head-equality, Definition-of-Done-snapshot, liveness and two-resume refusals still bind unchanged.

### Proposed Changes

### contracts.md, §"Resume from a published pull request (`resume --item`)"

In **What it resumes**, after the sentence defining the *published head*, add:

```markdown
When no proof record on the pull request carries the identifier of the
item's latest journaled dispatch, and that dispatch's journal carries a
`watchdog-stall-cancel` record (§"Dispatcher progress watchdog") naming a
published head, the cancel record anchors the resume instead. A proof
record that carries the dispatch's identifier always takes precedence over
a cancel record. The cancel record anchors only when its stage is
`proof_capture`, or when the run was between its last completed
`publish_draft` and `proof_capture`. A cancel in any other stage, including
a later `janitor`, `fix` or `publish_draft` of a rework loop, does not
anchor, because its head would not carry the rework. Under this anchor the
earlier run is that dispatch, the published head is the head the record
names, and the resumed-at stage is `proof_capture`. The factory's own record
of the run, when the factory still holds it, takes precedence for the stage
exactly as above. The resume record MUST name the cancel record as the
source that decided the stage.
```

In **Refusals**, replace the bullet

```markdown
- the item's publish branch carries no open pull request, or no proof
  record on it names a head (remedy: a plain dispatch);
```

with

```markdown
- the item's publish branch carries no open pull request, or no proof
  record on it names a head and no `watchdog-stall-cancel` record anchors
  one as above (remedy: a plain dispatch);
```

### scenarios.md

In Scenario 142, add after `Scenario: A run that terminated inside a fix loop resumes at fix`:

```gherkin
  Scenario: A stall-cancelled run with no proof record resumes from its cancel record
    Given a ready item whose latest dispatch's run completed publish_draft and was cancelled by the watchdog while executing proof_capture, leaving no proof record on its pull request
    And that dispatch's watchdog-stall-cancel record names a head equal to the pull request's current head
    When resume runs for the item
    Then the new run enters the workflow at proof_capture on that head and no dod_gate, implement or janitor stage precedes it
    And the resume record names the cancel record as the source that decided the stage
    And the dispatch journal carries neither a publish-branch-reclaim record nor a publish-branch-reclaim-held record for the resume
```

In Scenario 143, replace the `Nothing to resume from` Given with:

```gherkin
    Given a ready item whose publish branch carries no open pull request, or whose pull request carries no proof record naming a head and whose latest dispatch left no watchdog-stall-cancel record that anchors one
```
