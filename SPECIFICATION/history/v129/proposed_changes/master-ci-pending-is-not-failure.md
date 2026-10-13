---
topic: master-ci-pending-is-not-failure
author: claude-opus-5-5:agent-session-stall-prevention
created_at: 2026-10-13T07:10:02Z
---

## Proposal: A still-running master CI run is not a failure: wait for its verdict, then defer distinctly

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Replace the ratified rule that a still-pending latest default-branch CI run is an unprovable refusal. The master-CI preflight instead waits a bounded 1800 seconds for the latest run's aggregate job to conclude (following a newer run if the branch moves), passes on green and refuses on red as today, and only when the bound expires still pending returns a distinct PENDING outcome: no dispatch, no claim, journal reason master-ci-pending with status deferred, operator text that says the run is still running and has not failed, and none of the red-default-branch recovery text. A new Scenario 171 states the behaviour.

### Motivation

On 2026-10-13 two dispatches from plan bd-ib-jnpvh4 (impl:bd-ib-g6g3dg and impl:bd-ib-jqvqlf) were refused with 'ERROR: the latest master run of workflow CI is not proven green' plus the master-health-restoration recovery text while master CI was merely queued or in progress; the journal recorded status failed. A run that has not concluded has not failed, so the wording and the journal record misreport it. This repository merges often (12 master CI runs in about 4.5 hours that day), so the pending window is frequent, and every caller has to hand-roll a wait-and-retry loop that itself races newer runs. The fleet sweep found the same question already answered correctly elsewhere: livespec-dev-tooling's check-master-ci-green treats a pending run as non-blocking, and livespec-overseer's drain engine (engine-on-green.sh) waits on queued or in-progress runs and refuses only on red. No other fleet repository carries a master-CI dispatch preflight.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Master-CI pipeline resolution" (the paragraph that begins "This clause RETIRES the three shipped fail-open cases"), REPLACE the sentence

> A still-pending latest run remains an unprovable refusal (retry when the run concludes).

with the following rule:

**A still-running master CI run is not a failure.** When the latest run of the resolved pipeline on the resolved default branch, or its aggregate job, is still pending (queued, in progress, waiting, pending or requested), the master-CI preflight MUST NOT refuse on that observation. It MUST instead wait, polling at an interval of no more than 60 seconds, for a bounded window of 1800 seconds measured from the start of the preflight. On each poll it MUST re-read the LATEST run of the resolved pipeline on the resolved default branch, so a newer run that starts during the wait (because the default branch moved) replaces the one being waited on. When the latest run's aggregate job concludes green, the preflight MUST pass exactly as for a run that was green on first read, journaling the pass with the run it finally read. When it concludes red, the preflight MUST refuse exactly as for a run that was red on first read. Every other unprovable condition (no usable `gh` credential, an unresolvable pipeline, no runs yet, an unresolvable default branch, an aggregate conclusion that is neither green nor red) MUST still refuse immediately, without waiting.

Only when the bound expires with the latest run still pending does the preflight end without a verdict, and it MUST then return a distinct PENDING outcome, which:

- MUST NOT start the dispatch and MUST NOT claim the work item, exactly like a refusal;
- MUST carry its own journal reason `master-ci-pending`, distinct from `master-ci-red` and `master-ci-unprovable`, and a journal `status` of `deferred`, never `failed`;
- MUST state in its operator text, on its first line, that the run is still running and has not failed, naming the run, its pending status, the branch and how long the preflight waited, and MUST NOT open with the `ERROR:` prefix or the words "not proven green";
- MUST name the remedy as retrying the dispatch when the run concludes; and
- MUST NOT carry the red-default-branch recovery text (the master-health-restoration worktree -> PR -> merge escape and the repeat-flake caveat), which applies only to a red default branch.

The master-CI preflight's waiting MUST be visible: each poll that observes a pending run SHOULD emit one progress line naming the run and its status, so an operator watching a dispatch can tell a wait from a hang.

ADD to `SPECIFICATION/scenarios.md`, after the last numbered scenario, this new scenario:

```
## Scenario 171 — A still-running master CI run makes the preflight wait, not refuse

```gherkin
Feature: Master-CI preflight waits on a pending run instead of treating it as failed
  As an operator dispatching work while the default branch's CI is still running
  I want the preflight to wait for that run's verdict
  So that a run that has not failed is never reported as a failure and callers need no retry loop of their own

Scenario: A pending run that concludes green lets the dispatch proceed
  Given the latest default-branch run's aggregate job is in progress when the master-CI preflight starts
  When that job concludes green within the bounded wait
  Then the dispatch proceeds and the journaled pass names the run that concluded green

Scenario: A pending run that concludes red refuses as red
  Given the latest default-branch run's aggregate job is in progress when the master-CI preflight starts
  When that job concludes red within the bounded wait
  Then the dispatch is refused naming the red run with the reason master-ci-red

Scenario: A newer run replaces the one being waited on
  Given the preflight is waiting on an in-progress run
  When a newer run starts on the default branch and later concludes green
  Then the preflight waits on the newer run and the journaled pass names the newer run

Scenario: A run still pending at the bound is deferred, not failed
  Given the latest default-branch run stays in progress for the whole bounded wait
  When the bound expires
  Then the dispatch does not start and the work item is not claimed
  And the journal records reason master-ci-pending with status deferred
  And the operator text says the run is still running and has not failed, without the ERROR prefix or the red-default-branch recovery text
```
```

`tests/heading-coverage.json` MUST gain one entry for the new heading `## Scenario 171 — A still-running master CI run makes the preflight wait, not refuse` (spec_file `scenarios.md`, `test` MAY be `"TODO"` with a non-empty reason naming the implementing work item) in the same revision.

