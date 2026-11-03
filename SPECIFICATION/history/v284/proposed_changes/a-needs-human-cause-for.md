---
topic: a-needs-human-cause-for
author: claude-opus-5-5
created_at: 2026-11-03T01:32:37Z
---

## Proposal: A refused commit's needs-human cause carries a bounded first failure line, says when its target is unknown, and carries no sandbox environment value

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add one paragraph to contracts.md §"ACP node timeouts", directly after "The recorded hook verdict outranks the agent's account of it.", so that every needs-human cause naming a refused commit — a fix or review_fix turn's refused attempt, or an exhausted commit_red or commit_green re-entry of the Scenario 285 graph — also carries the first failing test id or error line of the hook's recorded output, truncated to at most 200 characters; says the failing target is unknown and why when the recorded output cannot name one, instead of the hook script's exit status alone; and never carries a value of an environment variable the dispatch supplied to the run's sandbox. Add three scenarios inside Scenario 285's existing gherkin block.

### Motivation

Work-item bd-ib-2h512 (plan sandbox-commit-gate-ceiling, epic bd-ib-qy5wol, plan assertion 5). Measured by plan dev-host-test-gate-load (epic livespec-dev-tooling-6vuiwe, comment 2026-11-02T23:34Z): in the 48 h to 2026-11-03T00:09Z, 17 runs ended needs-human at implement_completion@2, implement_hook_route@2, and in 10 of them the livespec-needs-human-cause comment says only 'script exited with status 1'; the other 7 carry LIVESPEC_IMPLEMENT_HOOK_REFUSED_BUDGET_EXHAUSTED and also omit the target. 51 such endings in 7 days against 3 in the 2026-10-28 to 10-30 baseline. Attributing one today needs a full fabro dump (5 to 15 minutes per run on a loaded server) and a hand read of stage output. The existing paragraph "The recorded hook verdict outranks the agent's account of it." already requires the exit status and failed target names, and its last sentence (carried by bd-ib-rf7fvk) extends that to an exhausted commit_red or commit_green re-entry; this proposal does not restate those. It adds the residue the ledger still lacks: a bounded first failure line, an explicit target-unknown statement with its reason, and the exclusion of sandbox environment values. The last exists because a failing test's assertion repr printed a sandbox CODEX_AUTH_JSON value into stage output (overseer-uzvcbn.13, 2026-11-02); a cause comment quoting hook output would carry that credential into the ledger. The wording names the commit_red and commit_green command nodes so it survives the Scenario 285 graph split (bd-ib-yuwftp), which removes implement_hook_route.

### Proposed Changes

Two edits. Every other sentence of the edited sections is unchanged.

**1. `SPECIFICATION/contracts.md`, §"ACP node timeouts".** Insert this paragraph immediately after the paragraph that begins "**The recorded hook verdict outranks the agent's account of it.**" and before the paragraph that begins "**A commit leg completes past one tool call.**":

> **A refused commit's needs-human cause is attributable from the ledger.** This paragraph governs every needs-human cause that the preceding paragraph requires to name a refused commit's recorded exit status and failed target names: the cause after a `fix` or `review_fix` turn whose latest commit attempt was refused, and the cause after an exhausted `commit_red` or `commit_green` re-entry of the implement stage. Each such cause MUST also carry one failure excerpt taken from the same recorded hook output: the first failing test id that output reports, or, when it reports none, its first line that reports an error. The excerpt MUST be at most 200 characters, and an excerpt shortened to that bound MUST say that it was truncated. When the recorded hook output is absent, cannot be read, or names no failed target, the cause MUST state that the failing target is unknown and MUST name which of those three reasons applies; it MUST NOT consist of the hook script's exit status alone, such as `script exited with status 1`. Neither the cause nor the excerpt MAY carry the value of any environment variable that the dispatch supplied to the run's sandbox. Before the cause is written, the Dispatcher MUST withhold any excerpt line that contains such a value, written verbatim or as a JSON-escaped string, and MUST put in its place a statement naming the environment variable by its key name only. A value shorter than eight characters is exempt from this check. The excerpt MUST NOT replace the exit status and failed target names that the preceding paragraph requires. Scenario 285 in `scenarios.md` exercises this paragraph.

**2. `SPECIFICATION/scenarios.md`, `## Scenario 285 — Red and Green run as separate nodes and every implement commit is made by a command node`.** Insert these three scenarios inside the existing gherkin fence, immediately after the "Scenario: An exhausted commit re-entry ends the stage failed with the recorded verdict" block and before the "Scenario: An exhausted test-wrong route ends the stage failed with both sides' sections" block. No `## ` heading is added or changed, so `tests/heading-coverage.json` needs no edit.

```gherkin
  Scenario: An exhausted commit re-entry's cause carries the first failure line of the hook's output
    Given commit_green's hook has refused naming the failed target check-types
    And the hook's recorded output reports a first error line longer than 200 characters
    And the green node's max_visits is exhausted
    When the run ends at the needs_human terminal
    Then the needs-human cause names commit_green's recorded exit status and the failed target check-types
    And the cause carries that first error line shortened to 200 characters and marked as truncated

  Scenario: A refused commit whose hook output names no target says the target is unknown and why
    Given commit_red's hook has refused and its recorded output cannot be read
    And the red node's max_visits is exhausted
    When the run ends at the needs_human terminal
    Then the needs-human cause states that the failing target is unknown because the hook's recorded output could not be read
    And the cause is not the hook script's exit status alone

  Scenario: A failure line that quotes a sandbox credential is withheld from the cause
    Given the dispatch supplied CODEX_AUTH_JSON to the run's sandbox
    And commit_green's hook refused with a first error line that quotes that variable's value
    And the green node's max_visits is exhausted
    When the run ends at the needs_human terminal
    Then the needs-human cause does not contain the value of CODEX_AUTH_JSON
    And the cause states that an excerpt line was withheld because it contained the value of CODEX_AUTH_JSON
```
