---
topic: fix-review-fix-single-runner-wait-then-settle
author: claude-opus-5-5
created_at: 2026-11-05T11:33:03Z
---

## Proposal: A fix or review_fix turn waits on a runner commit at most once, then leaves it to the stage's commit-run settle

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

In "A commit leg completes past one tool call", replace the permission to repeat waits on a commit run "any number of times" with a limit: inside one visit of a fix or review_fix stage, the agent may wait on each commit run it started at most once. The runner refuses a second wait from the same stage visit on a commit run already reported running, and names the stage's commit-run settle. A commit run waited on once may still be running at the agent's final message; the run waits on it before the stage's outcome is decided. The matching sentence of "An implement turn that ends incomplete does not succeed" is amended to name that wait. Scenario 179's first scenario is rewritten to the one-wait-then-settle shape, and a scenario is added for the refused second wait.

### Motivation

Plan implement-test-performance (livespec-dev-tooling tenant, epic livespec-dev-tooling-sv6m5p) has, as plan assertion 6: "Over at least 20 consecutive factory implement dispatches after the fixes ship, no run ends LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS or REENTRY_BUDGET_EXHAUSTED because its turn was spent waiting on a test gate." The repeated-wait permission defeats that assertion in fix and review_fix turns. Measured on bd-ib-s5idxj run 01M6N40ME98DE6TDZKSQ3G377P (0.287.1, a resume onto PR #4374): the fix turn started runner commit fc729... at minute 0.6. It then polled that commit about 45 times between minutes 0.7 and 46.5, while the commit was the turn's only remaining work. The commit's hook ran the per-file coverage gate for about 46 minutes and FAILED. The turn ended fix@1 on the 3600 s turn timeout and went to needs_human. fix.md already carried bd-ib-oueyxf's prompt rule against this, so a PROMPT-ONLY rule did not hold. Earlier gate-wait endings in the same window: review_fix at 7200 s on s5idxj, and the yuwftp wall budget.

The run already provides the safe alternative. fix_commit_settle and review_fix_commit_settle (bd-ib-y4oq27, bd-ib-xj3qqb) wait on every commit run the turn left running before the stage's outcome is decided, under the existing clause "An implement turn that ends incomplete does not succeed". A turn that keeps polling a running hook therefore buys nothing except a turn timeout. That clause explicitly keeps the agent's obligation to make every commit run terminal before its final message, and "A commit leg completes past one tool call" allows waits "any number of times". This proposal removes that obligation for a commit run waited on once, and makes the one-wait limit MECHANICAL: the runner refuses the second wait. A refusal that names the settle gives the agent nothing to poll. Scenario 179's first scenario ratifies "repeats bounded waits in later tool calls", so it is rewritten to the one-wait-then-settle shape.

The implement stage is deliberately not covered here. The split red/green graph (Scenario 285, still ratified; its re-land is bd-ib-vy75ws) gives implement commits to model-free command nodes, so no implement turn waits on a hook at all. Coordinated with legacy-coordinator-agent, who answers this revise under R301 (cross-session message, 2026-11-05 ~11:15Z). In-flight survey: livespec-orchestrator-beads-fabro#4463 (revise a-committed-fleet-launcher-screens, v304) and #4451 (incident-carrier-pr-binding-and-transfer-refusal) touch other paragraphs; aligned.

### Proposed Changes

Four edits.

**1. `SPECIFICATION/contracts.md`, §"Self-contained plugin dispatch", paragraph "**A commit leg completes past one tool call.**".**

- Replace "Waiting on a commit run MUST block for no longer than a bound in seconds that the caller supplies, MUST then report either `running` or the run's terminal state, MAY be repeated in later tool calls any number of times, and MUST leave the commit run untouched when it returns or is interrupted." with:

> Waiting on a commit run MUST block for no longer than a bound in seconds that the caller supplies, MUST then report either `running` or the run's terminal state, and MUST leave the commit run untouched when it returns or is interrupted. Inside one visit of a `fix` or `review_fix` stage the agent MAY wait on each commit run it started at most once. The runner MUST refuse a second wait, from the same stage visit, on a commit run that an earlier wait in that visit reported `running`. That refusal MUST leave the commit run untouched, MUST report the run's current state, and MUST name the stage's commit-run settle as what will wait on it. The stage's prompt MUST direct the agent to end its turn, rather than poll, once a commit run it waited on is still `running`. Polling the runner's own records by any other means counts as a wait.

- Replace "The stage's rule that nothing it started is left running when its turn ends is unchanged: before the agent's final message every commit run it started MUST be terminal or stopped, and the detached commit run with its bounded waits is the only exception that stage's prompt makes to its rule against backgrounding a tool call." with:

> The stage's rule that nothing it started is left running when its turn ends keeps exactly one exception. A commit run that the agent started through the runner and waited on once MAY still be `running` at the agent's final message, and the agent MUST NOT stop it. That commit run is then waited on by the run before the stage's outcome is decided, as "An implement turn that ends incomplete does not succeed" requires. Every other process the turn started MUST be terminal or stopped before the agent's final message. The detached commit run is the only exception that stage's prompt makes to its rule against backgrounding a tool call.

**2. `SPECIFICATION/contracts.md`, §"Self-contained plugin dispatch", paragraph "**An implement turn that ends incomplete does not succeed.**":** replace "it does not relax the agent's obligation to make every commit run terminal or stopped before its final message, and a node-timeout cut remains governed by \"A commit run outlives a node-timeout cut\"." with:

> it is the wait that "A commit leg completes past one tool call" names for a commit run the agent left `running` after its one wait. A node-timeout cut remains governed by "A commit run outlives a node-timeout cut".

**3. `SPECIFICATION/scenarios.md`, `## Scenario 179 — A sandbox commit whose hook outlasts one tool call completes with the hook's own verdict`:** replace the scenario "A Green amend whose hook outlasts one tool call completes" with:

```gherkin
  Scenario: A Green amend whose hook outlasts one tool call completes
    Given a review_fix-stage agent whose Green amend fires a commit hook that runs longer than one of its tool calls
    When the agent starts the amend through the sandbox commit runner, waits on it once, and ends its turn while the commit run is still running
    Then the run waits on that commit run before the review_fix stage's outcome is decided
    And the amend completes with the hook's own verdict
    And the resulting commit carries every trailer the hook wrote
    And the settled commit run reports the passed state, exit status zero and the resulting commit id
```

**4. `SPECIFICATION/scenarios.md`, the same Scenario 179:** append this scenario after "A second commit does not start while one is running":

```gherkin
  Scenario: A fix turn cannot wait twice on one running commit
    Given a fix-stage agent that started a commit through the sandbox commit runner
    And the agent's first wait on that commit run reported it running
    When the agent waits on the same commit run again in the same stage visit
    Then the runner refuses the wait and leaves the commit run untouched
    And the refusal reports the commit run as still running
    And the refusal names the stage's commit-run settle as what will wait on it
```

No `## ` heading is added, renamed or removed, so `tests/heading-coverage.json` needs no co-edit. The Scenario 179 row's existing test entry gains the new case when the implementation lands.
