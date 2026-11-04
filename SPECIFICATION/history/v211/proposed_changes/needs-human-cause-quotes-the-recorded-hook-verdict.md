---
topic: needs-human-cause-quotes-the-recorded-hook-verdict
author: claude-fable-5-1
created_at: 2026-10-24T23:52:25Z
---

## Proposal: needs-human-cause-quotes-the-recorded-hook-verdict

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When a run ends at needs-human after the failing agent stage's latest `git commit` attempt was refused by the repository's commit hook, the needs-human cause comment and the dispatch journal's outcome row MUST carry the hook's RECORDED verdict — its exit status and the failed target names, read from the run's own recorded tool output — in a field separate from the agent's failure text, and MUST label the agent's own account of the hook as agent-reported wherever that account describes the hook as interrupted or not completed while the recorded output shows it completed with a refusal.

### Motivation

The paragraph **A commit leg completes past one tool call.** (contracts.md, under the ACP node timeouts section) already requires that a commit run's terminal state be "derived from records the commit run's own process writes, never from the waiting agent's view", and that a terminal report carry the exit status. Nothing yet says that the needs-human cause written to the ledger, or the dispatch journal's outcome row, must prefer that recorded verdict over the agent's description of it. The gap was measured on bd-ib-8zyan run 01M5QNH88NHN68ST28Y80CZJ48 (gmktec, petri, 2026-10-24): the Green amend tool call (`mise exec -- git commit --amend --no-edit`, 19:50:57–20:02:50Z) completed with recorded exit status 1 and the hook's own output — `Failed targets (1): - check-types`, `✗ 03-check-pre-commit (711.40 seconds)` — in the ACP `tool_call_update` record's `rawOutput` (`exit_code: 1`, `_meta.terminal_exit.exit_code: 1`). The agent's final text, carried as the stage's `failure_reason`, said instead that "the Green amend hook did not complete". With bd-ib-36d3x5 that agent text becomes the innermost cause; without this clause, the one line a triager reads would misdescribe a completed, fixable refusal as an interruption.

In-flight survey (2026-10-25): 24 remote spec/* branches and open PR 3601 (governing-heading omission advisory) were surveyed; none touches Scenario 179 or the commit-leg paragraph, so each resolves to default-align.

### Proposed Changes

**1. `SPECIFICATION/contracts.md`**, immediately after the paragraph beginning **A commit leg completes past one tool call.**, insert a new paragraph:

```
**The recorded hook verdict outranks the agent's account of it.** When a run
ends at the `needs_human` terminal after an `implement`, `fix` or `review_fix`
turn whose latest commit attempt was refused, as "An implement turn that ends
incomplete does not succeed" defines a refused attempt, the needs-human cause
recorded on the item MUST name that attempt's recorded exit status and the
failed target names the hook's recorded output reports, read from the run's
recorded tool output and never from the agent's reply, and the dispatch
journal's outcome row for the run MUST carry the same exit status and failed
target names in a field separate from the agent's own failure text. When the
agent's failure text describes that hook as interrupted, terminated or not
completed while the recorded output shows the hook completed with a refusal,
the needs-human cause MUST label the agent's text as agent-reported and MUST
state the recorded refusal beside it. A commit attempt whose recorded output
shows no hook run, or one ended by a limit before its hook finished, is not
governed by this paragraph and keeps the `hook-over-limit` and `no-verdict`
classifications above. Scenario 179 in `scenarios.md` exercises this paragraph.
```

**2. `SPECIFICATION/scenarios.md` §"Scenario 179 — A sandbox commit whose hook outlasts one tool call completes with the hook's own verdict"**, inside the existing gherkin block, immediately after the scenario "A commit refused by its hook is reported as failed" and before "A commit that dies without a verdict is not a commit", insert:

```gherkin
  Scenario: A needs-human ending after a hook-refused commit names the hook's recorded verdict
    Given an implement turn whose latest commit attempt was refused by the commit hook with a recorded non-zero exit status and named failed targets
    And the turn's own failure text describes that hook as not completed
    When the run ends at the needs_human terminal
    Then the needs-human cause comment names the recorded exit status and the failed target names as read from the run's recorded tool output
    And the dispatch journal's outcome row carries that exit status and those target names in a field separate from the agent's failure text
    And the cause comment labels the agent's failure text as agent-reported and states the recorded refusal beside it
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.
