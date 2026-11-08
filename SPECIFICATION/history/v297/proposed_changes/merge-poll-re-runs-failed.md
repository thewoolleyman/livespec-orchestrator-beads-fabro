---
topic: merge-poll-re-runs-failed
author: claude-opus-5-5
created_at: 2026-11-04T18:07:29Z
---

## Proposal: Merge-poll re-runs failed jobs once on an evidence-backed infrastructure, timeout or load failure

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a paragraph under contracts.md "## Self-contained plugin dispatch", directly after the **Armed pull request overtaken by the default branch.** paragraph. When a required check fails terminally during a run's merge wait, the Dispatcher MUST first classify the failed job. Only when a committed, evidence-backed classifier attributes the failure to infrastructure, a timeout or load, and that failure lies where the in-place pytest retry cannot reach, the Dispatcher requests exactly ONE forge "re-run failed jobs" for that workflow run under the factory App identity and keeps polling. It files one flake work item per re-run and journals the re-run. A test the pull request touched is never re-run, an unattributable failure is never re-run, and a second terminal failure on the same head ends exactly as a terminal required-check failure ends today. Add Scenario 307 to scenarios.md to exercise it.

### Motivation

Maintainer ruling, 2026-11-04 ~16:4xZ, recorded verbatim in the plan-scope-event of 2026-11-04T16:44:36Z on epic livespec-dev-tooling-6tgd2z: 'OK, do these as priority:' followed by the coordinator's three points. Point 2 reads: 'Add a bounded job-level retry for what the plugin can't reach: runner teardown or container faults, OOM kills, and failures outside pytest. The factory's merge-poll would do one automatic "re-run failed jobs", only when a classifier marks the failure as infrastructure, timeout or load. It would file the flake item and still require a root fix. Today that case blocks the run at merge-poll, and it often ends at needs-human or a full rework.' Point 3 reads: 'Never rerun a test the PR itself touched. A failure there can be the PR's own bug, so the existing rule stands.' The coordinator's recorded reading: this amends the 2026-11-02 'never a whole-job rerun' rule exactly once, automatically, by the factory's merge-poll, only for a classified infrastructure, timeout or load failure that the in-place test retry cannot reach. The carrier work item is bd-ib-tckulg, which the Dispatcher refused as spec-change tier, held for this topic. Motivating evidence: on PR #4359 (bd-ib-oueyxf), CI run 41794143832, only the teardown steps 'Post Checkout' and 'Stop containers' of the check-coverage job failed ('Executing the custom container implementation failed'), every real step passed, and a failed-jobs re-run went green. Today that ends the run blocked at merge-poll. Out of scope: PR #4353 (bd-ib-busjvz), CI run 41785521691, a real test flake inside pytest whose root fix is bd-ib-ojpe3a. Factory yield over the trailing 6 h was 33%, partly from runs that succeeded and then blocked at merge-poll on a failure no code change caused.

### Proposed Changes

In SPECIFICATION/contracts.md, under "## Self-contained plugin dispatch", insert the following paragraph immediately after the paragraph that begins **Armed pull request overtaken by the default branch.**:

> **A required check that fails terminally on infrastructure is re-run once.** When the merge wait observes that a check the forge reports as required has failed terminally on the run's pull request, the Dispatcher MUST, before it records any outcome, read the failed job's step conclusions and log and classify the failure. The classifier MUST attribute a failure to exactly one of `runner-teardown` (every failed step of the job is a post-run or container-teardown step, such as `Post Checkout` or `Stop containers`, or the log reports that the runner's container implementation failed, while every other step of the job succeeded), `oom-kill` (the log or the job conclusion reports the job's process or container killed for exceeding its memory limit), `job-timeout` (the forge reports the job cancelled for exceeding its maximum execution time) or `unattributed`. The classifier MUST attribute a class other than `unattributed` only from evidence it matched in that job's step conclusions or log, against a fixed pattern set committed in the plugin. A log it cannot read MUST classify as `unattributed`. A failure inside a pytest session, including a failing test, MUST classify as `unattributed`, because the in-place test retry owns it. When the class is `runner-teardown`, `oom-kill` or `job-timeout`, and no failing test the log names lies in a file the pull request changed, the Dispatcher MUST request one forge "re-run failed jobs" for that workflow run, authenticated as the factory's GitHub App identity, and MUST continue the merge wait within its existing poll budget. The Dispatcher MUST request at most one automatic re-run per pull request head, counted from the journal. The count survives a Dispatcher restart and is not reset by a re-run that fails. For each re-run it requests, the Dispatcher MUST journal one `merge-poll-failed-jobs-rerun` row naming the run id, the pull request number, its head, the workflow run id, the failed job, the class and the matched evidence, and MUST later record the re-run's outcome on that row's run. For each re-run it MUST also file one work item in the governed repository's work-items store, with the same marker-line, identifier-shape and template-opener rules as the `livespec-base-advanced-after-arming` comment above. That work item MUST name the workflow run, the failed job, the class and the matched evidence, so a root fix is owed for every re-run. A failed filing MUST be journaled with its reason and MUST NOT prevent the re-run. The Dispatcher MUST NOT re-run a job for any other class, MUST NOT re-run when a failing test lies in a file the pull request changed, and MUST NOT request a second automatic re-run for the same head. In each of those cases, and when a required check fails terminally again after the automatic re-run, the dispatch outcome MUST be exactly the one a terminal required-check failure records without this paragraph: `blocked` at stage `merge-poll`, naming the failed checks and the recovery chain `resolve-blocked:<work-item-id>:ready`, then `resume --item <work-item-id>`. A re-run MUST NOT close, disarm or rewrite the pull request, and a re-run that goes green MUST NOT close or discharge any flake work item. Scenario 307 in `scenarios.md` exercises this paragraph.

In SPECIFICATION/scenarios.md, append after the last scenario:

```markdown
## Scenario 307 — A required check that fails terminally on infrastructure is re-run once and files a flake item

Governing clause: `contracts.md` §"Self-contained plugin dispatch", the paragraph **A required check that fails terminally on infrastructure is re-run once.**

```gherkin
Feature: merge-poll re-runs an infrastructure failure once, never a touched test
  As an operator
  I want a pull request that failed CI on a runner fault re-run once without me
  So that a sound factory run is not parked for a human, and every re-run still owes a root fix

  Scenario: a teardown-only failure is re-run once and a flake item is filed
    Given a factory run's pull request whose required check failed terminally
    And every failed step of that job is a teardown step and every other step succeeded
    When the merge wait classifies the failure
    Then the class is runner-teardown
    And the Dispatcher requests exactly one re-run of the failed jobs as the factory App identity
    And it journals a merge-poll-failed-jobs-rerun row naming the workflow run, the job, the class and the evidence
    And it files one flake work item naming the same
    And the merge wait continues within its existing poll budget

  Scenario: a second terminal failure on the same head ends blocked as before
    Given the Dispatcher has already re-run the failed jobs once for the pull request's head
    When a required check fails terminally again on that head
    Then no second re-run is requested
    And the outcome is blocked at merge-poll naming the failed checks and the recovery chain

  Scenario: a failing test the pull request touched is never re-run
    Given a required check failed terminally with a failing test in a file the pull request changed
    When the merge wait classifies the failure
    Then no re-run is requested and no flake work item is filed
    And the outcome is blocked at merge-poll naming the failed checks and the recovery chain

  Scenario: an unattributable failure is never re-run
    Given a required check failed terminally and the classifier matched no committed evidence pattern
    When the merge wait classifies the failure
    Then the class is unattributed and no re-run is requested
    And the outcome is blocked at merge-poll naming the failed checks and the recovery chain
```
```

The revise commit MUST add a `tests/heading-coverage.json` entry for the new `## Scenario 307` heading. That entry is a spec-first TODO row naming the integration tier and bd-ib-tckulg as its owner, and the commit MUST register it in the heading-coverage debt register.
