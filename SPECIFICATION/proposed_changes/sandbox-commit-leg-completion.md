---
topic: sandbox-commit-leg-completion
author: claude-opus-5-5
created_at: 2026-10-14T23:50:40Z
---

## Proposal: A sandbox commit leg completes past one agent tool call

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Add a contracts.md paragraph, immediately after "Repository hooks that outlive a limit", requiring the implement-work-item workflow to give every committing ACP agent stage a sandbox-side detached commit runner, so that a git commit whose repository hook outlasts one agent tool call still completes with the hook's own verdict. Add Scenario 179 exercising it.

### Motivation

Work item bd-ib-sufca7. On 2026-10-14, hp run 01M4XWYERJEZ15GNMGHV66CSBY (bd-ib-5guqmt) finished a verified Red-Green-Replay change, then lost it: its two Green `git commit --amend` tool calls were ended after 1202366 ms and 1203117 ms while the repository's pre-commit aggregate was still running (16m56s standalone on that loaded host; the same amend took 41 minutes when finished by hand on the host). The run ended at needs-human with nothing published. Run 01M4TZQKSKWFWAZZ3QX6ZM3D8N (bd-ib-mnuo5n) failed the same way at 1202 s. The existing paragraph "Repository hooks that outlive a limit" and Scenario 177 require such a hook to be reaped and named; neither requires the commit to complete, so once they are implemented this instance is reaped, named and still lost. The host side already decouples gate runtime from tool-call patience through a detached runner with a durable verdict; the sandbox agent has no sanctioned equivalent, and every factory stage prompt forbids backgrounding a tool call. Raising the per-call ceiling is not a fix: the outlasting time depends on host load, and any fixed ceiling is outrun by a slower host. The maintainer authorized working this defect on 2026-10-14 ("Go ahead and work the tool call ceiling bug too."); plan sandbox-commit-gate-ceiling, epic bd-ib-qy5wol, research note 001, carries the measurements.

### Proposed Changes

In SPECIFICATION/contracts.md, immediately after the paragraph that begins "**Repository hooks that outlive a limit.**" and ends "Scenario 177 in `scenarios.md` exercises this paragraph.", insert this new paragraph:

> **A commit leg completes past one tool call.** The implement-work-item workflow MUST provide, inside the factory sandbox, a detached commit runner for every stage whose ACP agent commits (`implement`, `fix` and `review_fix`), and each such stage's prompt MUST direct every `git commit` the agent makes — a Red commit, a Green amend, or any later commit — through that runner. Starting a commit through the runner MUST run the given `git commit` arguments unchanged, with the repository's commit hooks running exactly as they run for a foreground commit, in a session that outlives the tool call that started it, and MUST return that commit run's identity without waiting for the commit. Waiting on a commit run MUST block for no longer than a bound in seconds that the caller supplies, MUST then report either `running` or the run's terminal state, MAY be repeated in later tool calls any number of times, and MUST leave the commit run untouched when it returns or is interrupted. The terminal state MUST be derived from records the commit run's own process writes, never from the waiting agent's view: `passed` when the commit process exited on its own with status zero; `failed` when it exited on its own with a status from 1 to 127; and `no-verdict` when it was ended by a signal or is no longer running without having recorded an exit status. A terminal report MUST carry the exit status when one was recorded, the resulting `HEAD` commit id when the state is `passed`, and the final lines of the commit's combined output. A commit run whose state is `failed` or `no-verdict` is not a commit, and the prompt MUST direct the agent not to treat it as one. The runner MUST NOT pass `--no-verify`, set any variable that skips or relaxes a check, or change the severity of any hook, and MUST refuse to start a commit run while an earlier commit run in the same sandbox is still `running`, naming that run. The stage's rule that nothing it started is left running when its turn ends is unchanged: before the agent's final message every commit run it started MUST be terminal or stopped, and the detached commit run with its bounded waits is the only exception that stage's prompt makes to its rule against backgrounding a tool call. This paragraph does not replace "Repository hooks that outlive a limit", which still governs any commit or push that does not go through the runner. Scenario 179 in `scenarios.md` exercises this paragraph.

In SPECIFICATION/scenarios.md, append after the Scenario 177 block:

## Scenario 179 — A sandbox commit whose hook outlasts one tool call completes with the hook's own verdict

```gherkin
Feature: A factory agent's commit leg is not bounded by one tool call
  As the maintainer of a repository whose full gate runs in its commit hook
  I want a sandbox commit to reach its hook's verdict however long the hook runs
  So that a loaded factory host does not turn a verified change into a lost run

  Scenario: A Green amend whose hook outlasts one tool call completes
    Given an implement-stage agent whose Green amend fires a commit hook that runs longer than one of its tool calls
    When the agent starts the amend through the sandbox commit runner and repeats bounded waits in later tool calls
    Then the amend completes with the hook's own verdict
    And the resulting commit carries every trailer the hook wrote
    And the final wait reports the passed state, exit status zero and the resulting commit id

  Scenario: A commit refused by its hook is reported as failed
    Given a commit started through the sandbox commit runner whose hook refuses it
    When the agent waits on it until it is terminal
    Then the wait reports the failed state and the hook's exit status
    And HEAD is unchanged

  Scenario: A commit that dies without a verdict is not a commit
    Given a commit started through the sandbox commit runner whose process is ended by a signal before it exits on its own
    When the agent waits on it
    Then the wait reports the no-verdict state
    And no passed state is reported for that commit run

  Scenario: A second commit does not start while one is running
    Given a commit started through the sandbox commit runner that is still running
    When the agent starts another commit through the runner
    Then the runner refuses the start and names the running commit run
```

In tests/heading-coverage.json, add an entry for the new heading:

```json
{
  "heading": "## Scenario 179 — A sandbox commit whose hook outlasts one tool call completes with the hook's own verdict",
  "spec_root": "SPECIFICATION",
  "spec_file": "scenarios.md",
  "test": "TODO",
  "reason": "Ratified by the revision that accepts proposal sandbox-commit-leg-completion (plan sandbox-commit-gate-ceiling, epic bd-ib-qy5wol). The sandbox commit runner is not implemented yet; an integration-tier test is owed for the four sub-scenarios, and work-item bd-ib-sufca7 implements them and owns that binding.",
  "work_item": "bd-ib-sufca7"
}
```

In tests/heading-coverage-debt.json, add the matching row:

```json
{"spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "heading": "## Scenario 179 — A sandbox commit whose hook outlasts one tool call completes with the hook's own verdict", "work_item": "bd-ib-sufca7", "first_seen": "<the revision date>"}
```

Scenario number 178 is skipped deliberately: the pending proposal pr-refresh-reproof-relevance reserves it. If that proposal is rejected or renumbered before this one is revised, keep 179 rather than renumbering, so the work item's References line stays valid.
