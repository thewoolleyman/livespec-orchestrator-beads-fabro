---
topic: master-ci-green-ancestor-passes-preflight
author: claude-opus-5-5
created_at: 2026-11-02T06:31:45Z
---

## Proposal: The master-CI preflight passes on a concluded green ancestor run while the newest default-branch run is still pending

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md "A still-running master CI run is not a failure" and Scenario 171 so that, whenever the latest default-branch run is pending, the master-CI preflight also reads the newest CONCLUDED run (green or red) and passes at once when it concluded green on the current head or an ancestor of it with no red run created after it. A red newest concluded run never passes and never refuses on its own; the existing bounded wait continues. A latest run that itself concludes red still refuses, one that concludes green still passes, and the PENDING deferral at the 1800-second bound remains only when no poll found a qualifying green ancestor. The caller-does-not-gate list is updated to name the new pass. Scenario 171's heading is unchanged; its gherkin gains the green-ancestor, red-newest-concluded and non-ancestor scenarios, and its existing scenarios gain the precondition that no green ancestor qualifies.

### Motivation

Factory-throughput defect brief from legacy-coordinator-agent (2026-11-02 ~06:25Z), routed to plan factory-idle-with-ready-work (epic bd-ib-opbzv3) because it defeats that plan's Definition of Done assertion 1 (a dispatch starts within the configured bound whenever ready work exists). The ratified preflight waits only on the NEWEST default-branch run, and Scenario 171 ratifies that a newer run replaces the one being waited on. CI here takes 16-24 minutes and the runs overlap rather than cancel, while merges land every 2-8 minutes on a busy master, so the run being waited on is never the one that concludes and every launch defers at the bound with rc=1 and no claim. Measured by legacy-dispatcher-agent: livespec-dev-tooling items etoyip, qgv3tb and t4rx4t deferred at 05:34-05:41Z with runs started 05:13:56, 05:21:28, 05:26:52 and 05:41:26Z; this repository's nmuyjc.6 deferred at 06:23:01Z with runs started 06:14:17, 06:16:18 and 06:18:46Z in progress while the last concluded run (06:00:41Z, commit d4512195) was green. Re-measured by this session with gh run list: the three CI runs on 1b783ad3, 7de0cda0 and d74c8eda were in_progress concurrently and d4512195 had completed success. The fleet sat at 3 of 10 slots with ready work queued. Coordinator direction: pass on a concluded green ancestor with no red after it; a red still refuses; the pending-at-bound deferral remains only when no concluded green ancestor exists. This proposal keeps 'a red still refuses' as: a red latest run refuses as today, and a red newest concluded run blocks the green-ancestor pass and leaves the existing wait in charge rather than refusing outright, so a pending fix for a red default branch can still admit dispatch when it concludes green (today's behaviour in that case, preserved). No in-flight spec branch or open PR touches this clause (surveyed 2026-11-02).

### Proposed Changes

### contracts.md — "**A still-running master CI run is not a failure.**" paragraph

Replace the sentence that begins "On each poll it MUST re-read the LATEST run of the resolved pipeline on the resolved default branch, so a newer run that starts during the wait (because the default branch moved) replaces the one being waited on." through the end of the sentence "When it concludes red, the preflight MUST refuse exactly as for a run that was red on first read." with the text below, leaving every later sentence of the paragraph (the immediate-refusal list, the PENDING outcome and the progress line) unchanged except the one sentence named after it:

> On each poll it MUST re-read the LATEST run of the resolved pipeline on the resolved default branch, so a newer run that starts during the wait (because the default branch moved) replaces the one being waited on. When the latest run's aggregate job concludes green, the preflight MUST pass exactly as for a run that was green on first read, journaling the pass with the run it finally read. When it concludes red, the preflight MUST refuse exactly as for a run that was red on first read.
>
> **A concluded green ancestor passes while newer runs are pending.** Rationale: CI on this repository's default branch takes longer than the interval between merges on a busy day, and the runs overlap rather than cancel one another, so the latest run is replaced before it concludes and a wait on the latest run alone defers every dispatch at the bound while the default branch is demonstrably green (design record: repository `thewoolleyman/livespec-orchestrator-beads-fabro`, plan epic `bd-ib-opbzv3` (`factory-idle-with-ready-work`), the scope event of 2026-11-02; measured that morning: four livespec-dev-tooling dispatches and one in this repository deferred at the 1800-second bound while a run on an earlier default-branch commit had concluded green and three newer runs were still in progress, leaving 7 of 10 fleet slots idle with ready work queued). Each time the preflight observes the latest run, or its aggregate job, still pending — on the first read and on every poll of the wait — it MUST also read the NEWEST CONCLUDED run of the resolved pipeline on the resolved default branch: the most recently created run whose aggregate job concluded green or red. Runs whose aggregate conclusion is neither green nor red (cancelled, skipped) are passed over by this read; they neither qualify nor disqualify. The preflight MUST then pass at once, without further waiting, when ALL of the following hold:
>
> 1. the newest concluded run's aggregate job concluded green;
> 2. its head commit is the resolved default branch's current head commit or an ancestor of it, as the forge reports the branch at the time of the read; and
> 3. no run of the resolved pipeline on the resolved default branch created after it has concluded red (which holds by construction for the newest concluded run, and is stated so an implementation that selects the run another way MUST still honour it).
>
> Such a pass MUST be journaled as a pass naming the green run it passed on, that run's head commit, and the still-pending latest run, and its operator text MUST say that it passed on a concluded green ancestor while the named newer run is still running. When any of the three conditions does not hold — the newest concluded run is red, no concluded run exists, its commit is not an ancestor of the current head (the default branch was rewritten), or the branch head or the ancestry cannot be read — the preflight MUST NOT pass on that run and MUST NOT refuse on that observation; it MUST continue the bounded wait on the latest run exactly as above. A red newest concluded run therefore never passes and never refuses on its own while a newer run is pending: the wait continues, so a pending run that fixes a red default branch can still admit the dispatch when it concludes green. A latest run that has itself concluded red MUST still refuse as red, and a latest run that has itself concluded green MUST still pass, exactly as before.

In the same paragraph, replace the sentence "Only when the bound expires with the latest run still pending does the preflight end without a verdict, and it MUST then return a distinct PENDING outcome," with:

> Only when the bound expires with the latest run still pending, and no poll found a newest concluded run satisfying the three conditions above, does the preflight end without a verdict, and it MUST then return a distinct PENDING outcome,

### contracts.md — "**A caller does not gate a dispatch on the default branch's CI.**" paragraph, numbered item 1

Replace item 1 with:

> 1. The master-CI preflight of this section. While the latest run is pending it passes on a concluded green ancestor run as specified above; otherwise it waits on the pending run for its bounded window, refuses on a run that concludes red or on an unprovable condition, and, when the window expires with the run still pending and no concluded green ancestor found, returns the distinct PENDING outcome, journaled as `deferred` with reason `master-ci-pending`, without claiming the work item.

A caller MUST NOT duplicate the green-ancestor read either; it is one of the conditions the Dispatcher owns.

### scenarios.md — "## Scenario 171 — A still-running master CI run makes the preflight wait, not refuse"

The H2 heading is UNCHANGED (so `tests/heading-coverage.json` needs no edit). Replace the scenario's gherkin block with:

```gherkin
Feature: Master-CI preflight waits on a pending run instead of treating it as failed
  As an operator dispatching work while the default branch's CI is still running
  I want the preflight to pass on a concluded green ancestor run, or else wait for the pending run's verdict
  So that a run that has not failed is never reported as a failure and overlapping runs never starve dispatch

  Scenario: a concluded green ancestor passes while the latest run is pending
    Given the latest default-branch run's aggregate job is in progress when the master-CI preflight starts
      And the newest concluded default-branch run concluded green on a commit that is an ancestor of the current default-branch head
    When the preflight reads the runs
    Then the dispatch proceeds without waiting
      And the journaled pass names the green run, its head commit and the still-pending latest run

  Scenario: a red newest concluded run does not pass, and the preflight waits on the latest run
    Given the latest default-branch run's aggregate job is in progress when the master-CI preflight starts
      And the newest concluded default-branch run concluded red
    When the preflight reads the runs
    Then the dispatch is neither started nor refused on that red run
      And the preflight waits on the latest run

  Scenario: a concluded green run that is not an ancestor of the head does not pass
    Given the latest default-branch run's aggregate job is in progress when the master-CI preflight starts
      And the newest concluded default-branch run concluded green on a commit that is not an ancestor of the current default-branch head
    When the preflight reads the runs
    Then the dispatch does not proceed on that run
      And the preflight waits on the latest run

  Scenario: a pending run that concludes green lets the dispatch proceed
    Given the latest default-branch run's aggregate job is in progress when the master-CI preflight starts
      And no concluded green ancestor run satisfies the pass conditions
    When that job concludes green within the bounded wait
    Then the dispatch proceeds and the journaled pass names the run that concluded green

  Scenario: a pending run that concludes red refuses as red
    Given the latest default-branch run's aggregate job is in progress when the master-CI preflight starts
      And no concluded green ancestor run satisfies the pass conditions
    When that job concludes red within the bounded wait
    Then the dispatch is refused naming the red run with the reason master-ci-red

  Scenario: a newer run replaces the one being waited on
    Given the preflight is waiting on an in-progress run because the newest concluded run is red
    When a newer run starts on the default branch and concludes green within the original bounded wait while it is still the latest run
    Then the preflight waits on the newer run and the journaled pass names the newer run

  Scenario: a run concluding green during the wait passes as a green ancestor while a newer run is pending
    Given the preflight is waiting on an in-progress run because the newest concluded run is red
    When that run concludes green on an ancestor of the current head while a newer run is still in progress
    Then the next poll passes on that green run and the journaled pass names it and the still-pending newer run

  Scenario: a run still pending at the bound is deferred, not failed
    Given the latest default-branch run stays in progress for the whole bounded wait
      And no poll finds a concluded green ancestor run satisfying the pass conditions
    When the bound expires
    Then the dispatch does not start and the work item is not claimed
      And the journal records reason master-ci-pending with status deferred
      And the operator text says the run is still running and has not failed, without the ERROR prefix or the red-default-branch recovery text
```

Every scenario above is a behaviour the amended contracts.md clause states with MUST; the implementation MUST make each one an executable test.
