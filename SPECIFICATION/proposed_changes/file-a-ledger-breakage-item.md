---
topic: file-a-ledger-breakage-item
author: claude-opus-5-5
created_at: 2026-11-03T05:24:53Z
---

## Proposal: A host-side breakage pass files one ledger item for each failed job of a watched scheduled workflow on the default branch

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a `breakage-pass` Dispatcher verb, run on the dev host. For every workflow the governed repository declares as watched, it reads the latest completed run on the default branch. It files exactly one work item for each failed job of a failed run, through the same filing seam `capture-work-item` uses. It deduplicates on workflow, job and head commit across the whole ledger, files nothing for a green run, and fails visibly when it cannot read the run.

### Motivation

Maintainer directive 2026-11-03, relayed by legacy-coordinator-agent: the uid-doubled pull-request jobs of this repository's CI (check-per-file-coverage, check-coverage, check-lint, check-format, check-types, check-python-batch) keep only the uid-1000 leg on pull requests. The root leg moves to a scheduled workflow on master every three hours (work item bd-ib-xufdwx). The root leg was measured at 263.7 k3s job-hours in 7 days, 27.3% of all fleet k3s CI time (livespec-dev-tooling plan ci-runtime-and-cost, research 002). That move is safe only if a red scheduled run becomes owned work, which is the coordinator's condition and the reason bd-ib-sfa2 kept both legs gated at fail_under = 100. A scheduled run reports its failure only on GitHub. Neither GitHub-hosted nor k3s runners can reach the beads tenant on the dev host's 127.0.0.1:3307, so the workflow cannot file the item itself, and today nothing turns a red scheduled run into a ledger item. The master-CI preflight reads default-branch CI only to gate a dispatch, and a caller is forbidden to read that state itself (§"Dispatch preflight and post-merge step discipline"), so it cannot carry this. The Dispatcher's dispatch-stage tier classifier ruled the carrier, bd-ib-pgbr52, spec-change for exactly this reason (2026-11-03T03:42Z, linked topic file-a-ledger-breakage-item). Until this lands, the ci-runtime-and-cost plan seat does the same job by hand each tick (coordinator ruling 2026-11-03).

### Proposed Changes

In `contracts.md`, inside §"Dispatcher admission, WIP cap, and post-merge acceptance", insert the following new subsection immediately before `### Repository integration contract`:

### Scheduled-workflow breakage pass

A scheduled workflow on the default branch reports its failure only on the forge. The runners that execute it cannot reach the beads tenant, so the workflow cannot file the failure as work itself. The breakage pass turns such a failure into a ledger work item from the host that can reach the tenant.

**Watched workflows.** A governed repository MAY declare watched workflows in `.livespec.jsonc` as `dispatcher.breakage_workflows`: an array of workflow file names relative to `.github/workflows/`, for example `["ci-root-uid.yml"]`. An absent or empty array means no workflow is watched. A value that is not an array of non-empty strings MUST make the pass fail visibly, naming the key, and MUST NOT be read as an empty array.

**The pass.** `dispatcher.py breakage-pass --repo <path>` MUST, for each watched workflow, read that workflow's most recently created COMPLETED run on the resolved default branch, of any trigger event. It MUST read through the forge's cached or conditional request path and MUST NOT poll in a loop: one invocation is one pass, and the host schedules repeat passes. Then:

1. When the run concluded success, the pass MUST file nothing for that workflow.
2. When the run concluded failure, the pass MUST compute, for each job of that run that concluded failure, the breakage key `<workflow-file>:<job-name>:<head-sha>`. It MUST file exactly one work item for each key that no item in the ledger already carries. That covers items of every lifecycle status, closed included, so a re-run of the same commit that fails the same job files nothing new.
3. When the run concluded cancelled, skipped, or any other conclusion that is neither success nor failure, the pass MUST file nothing for that workflow and MUST report the conclusion.
4. When no completed run exists, the pass MUST file nothing and MUST report that no completed run exists.
5. When the forge credential is unusable, the default branch, the workflow, its runs or its jobs cannot be read, or the ledger's dedupe read fails, the pass MUST file nothing for that workflow, MUST report the failure naming what could not be read, and MUST exit non-zero. An unreadable workflow MUST NOT be reported as green.

**The filed item.** Each item MUST be filed through the filing seam the `capture-work-item` operation uses, never by a raw `bd create`. Its title MUST name the workflow and the failing job. Its description MUST name the run URL, the head commit, and each failing test the job's log names, read from the test runner's per-test failure lines. When the log names no failing test, the description MUST say so and name the job's failing step instead. The item MUST carry the label `breakage:<workflow-file>` and MUST record the breakage key in its metadata as `breakage_key`, which is what the dedupe read compares. It enters the lifecycle exactly as any captured item does, and this subsection grants it no admission of its own. The description MUST pass the shared template-opener detector before the item is filed. A description that fails the detector MUST NOT be filed, and the pass MUST report that key as unfiled and exit non-zero.

**Verdicts.** Each pass MUST print one verdict line per watched workflow, naming the workflow, the run it read when it read one, and one of `green`, `filed <item-id>[, <item-id>...]`, `already-filed <item-id>[, <item-id>...]`, `not-concluded <conclusion>`, `no-completed-run`, or `unreadable <reason>`. When the pass runs under a host timer, these lines are what the timer's journal shows. The pass is idempotent over an unchanged run, so the host that reaches the tenant SHOULD run it at least every 30 minutes. Installing that schedule belongs to the host's provisioning, not to this plugin.

The pass reads default-branch CI state only to file work. It MUST NOT gate, hold, defer or start any dispatch, so it is not a caller gating a dispatch on the default branch's CI under §"Dispatch preflight and post-merge step discipline", and it changes no admission condition. Scenario 302 in `scenarios.md` exercises this subsection.

In `scenarios.md`, add the following scenario after the highest-numbered scenario. When 302 is already taken at revise time, use the next free number and update the closing sentence of the contracts.md subsection to match. In the revise commit, add the matching `tests/heading-coverage.json` row as a spec-first `"test": "TODO"` entry whose reason names the integration tier and the owning work item bd-ib-pgbr52, and regenerate the debt register.

## Scenario 302 — A failed scheduled default-branch workflow run becomes one ledger item per failed job

Governing clause: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Scheduled-workflow breakage pass".

```gherkin
Feature: a red scheduled workflow on the default branch becomes owned work
  As the maintainer who moved a CI leg off pull requests onto a schedule
  I want every failed job of that scheduled run filed as a ledger item from the host
  So that a failure found after merge is owned work rather than a red mark nobody reads

  Scenario: a failed run files one item per failed job
    Given .livespec.jsonc declares dispatcher.breakage_workflows as ["ci-root-uid.yml"]
    And the latest completed default-branch run of ci-root-uid.yml concluded failure with jobs check-coverage and check-types failed
    When dispatcher.py breakage-pass runs
    Then it files two work items through the capture-work-item filing seam
    And each title names ci-root-uid.yml and its failed job
    And each description names the run URL, the head commit and each failing test the job log names
    And each item carries the label breakage:ci-root-uid.yml and its breakage_key
    And the verdict line reads filed with both item ids

  Scenario: a later pass over the same failure files nothing new
    Given a prior pass filed an item for ci-root-uid.yml:check-coverage at head commit H, and that item is now closed
    And the latest completed run is a re-run at head commit H whose check-coverage job failed again
    When dispatcher.py breakage-pass runs
    Then it files no item
    And the verdict line reads already-filed naming the closed item

  Scenario: a green run files nothing
    Given the latest completed default-branch run of ci-root-uid.yml concluded success
    When dispatcher.py breakage-pass runs
    Then it files no item
    And the verdict line reads green

  Scenario: an unreadable workflow fails visibly
    Given the forge credential is unusable
    When dispatcher.py breakage-pass runs
    Then it files no item
    And the verdict line reads unreadable naming what could not be read
    And the pass exits non-zero
```
