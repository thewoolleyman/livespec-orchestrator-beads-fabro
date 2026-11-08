---
topic: an-implement-turn-opens-up
author: claude-opus-5-5 (sandbox-commit-gate-ceiling plan session)
created_at: 2026-11-08T15:44:39Z
---

## Proposal: The commit runner refuses a wait while another wait on the same commit run is open

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add one stage-independent rule to contracts.md's "A commit leg completes past one tool call" paragraph: the sandbox commit runner MUST refuse a wait on a commit run while another wait on that same run is still open, returning at once with the run's current state and leaving the run untouched. A sequential wait, and a wait after a killed one, stay unaffected. Two Scenario 179 cases exercise the rule. It is carried by work item bd-ib-hfhezo, a child of plan sandbox-commit-gate-ceiling (epic bd-ib-qy5wol).

### Motivation

Measured 2026-11-08 from factory run exports. An agent turn opens up to nine concurrent waits on one commit run, and each wait's return is a separate full-context LLM round trip.
- livespec-dev-tooling-togi6z run 01M6XM2HXR8T0MJHC8FMZJRTFN: 120 and 97 waits across its two turns, 224.1 and 432.0 minutes summed inside about 56-minute unions, at most 9 concurrent.
- livespec-dev-tooling-nvh3dl run 01M6X8DXM600WC3Z0JJCH2GQ4Y: 74 waits, 298.5 minutes summed inside a 106.6-minute union, at most 9 concurrent.
Counting each ACP usage_update as one round trip, with its context size as the token proxy:
- Round trips that follow only runner-wait returns carry 76% and 62% of togi6z's implement-turn input tokens, and 27% of nvh3dl's.
- They do not batch: 102 of 110, 81 of 84 and 67 of 69 such trips carry exactly one wait return.
The class of runs ending HOOK_REFUSED_BUDGET_EXHAUSTED or GIT_REFUSED_BUDGET_EXHAUSTED cost $211.90 in the 24 h to 2026-11-08T15:35Z, input-dominated (531M input vs 0.68M output tokens; token-spend-analysis). Cache pricing shrinks the dollar share of the context-size proxy. The existing per-visit rule for fix and review_fix refuses only a wait that follows an earlier 'running' report; nothing refuses a wait while another wait on the run is still open. legacy-coordinator-agent ruled the guard pulled forward on that measurement. The rule is stage-independent so it holds both for the stages this paragraph names and for any stage that waits on a commit run.

### Proposed Changes

In SPECIFICATION/contracts.md, paragraph "**A commit leg completes past one tool call.**", insert the following sentences immediately after "...and MUST name the stage's commit-run settle as what will wait on it.":

> Independently of the stage, the runner MUST refuse a wait on a commit run while another wait on that same commit run is still open, so that concurrent waits on one run never each return into the agent's turn. That refusal MUST return at once without waiting, MUST exit with a non-zero status, MUST report the commit run's current state and that another wait on it is open, and MUST leave the commit run untouched. A wait that starts after every earlier wait on that commit run has returned MUST NOT be refused by this rule, and a wait whose process ended without returning MUST NOT count as open.

In SPECIFICATION/scenarios.md, under "## Scenario 179 — A sandbox commit whose hook outlasts one tool call completes with the hook's own verdict", append these two scenarios inside the existing gherkin block, after "A fix turn cannot wait twice on one running commit":

```gherkin
  Scenario: A wait is refused while another wait on the same commit run is open
    Given a commit started through the sandbox commit runner that is still running
    And a wait on that commit run that has not yet returned
    When the agent starts a second wait on the same commit run
    Then the runner refuses the second wait at once with a non-zero exit status
    And the refusal reports the commit run's current state and that another wait on it is open
    And the commit run is left untouched and later reports its own terminal state

  Scenario: A wait after a returned or killed wait is not refused for concurrency
    Given a commit started through the sandbox commit runner that is still running
    And an earlier wait on that commit run that either returned or was killed before returning
    When the agent waits on that commit run
    Then the wait blocks for no longer than its bound
    And it reports running or the commit run's terminal state
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` MUST NOT change.
