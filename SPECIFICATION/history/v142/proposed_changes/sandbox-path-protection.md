---
topic: sandbox-path-protection
author: claude-opus-5-5
created_at: 2026-10-15T02:23:35Z
---

## Proposal: A sandbox agent cannot remove the run's working tree

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Add one contracts.md paragraph, placed directly after "A commit leg completes past one tool call", requiring that a shell command an ACP agent runs inside the factory sandbox is refused before it executes when it would remove, move or replace the sandbox root, the run's working directory, its working-directory link, or the run's clone, while data-only mentions and removals under a scratch directory or inside the repository tree run normally. Add Scenario 180 exercising it, and a heading-coverage entry owned by work-item bd-ib-jgedjo.

### Motivation

Run 01M4YJGC55V86C9V1X07QG3Y2H (work-item bd-ib-54q7fn, hp, 2026-10-15) lost about 47 minutes of finished implement work this way. The sandbox's clone lived at /repos/thewoolleyman/livespec-orchestrator-beads-fabro, and the engine's working directory /workspace/livespec-orchestrator-beads-fabro was a link to it. To simulate a sandbox layout for the test it was writing, the implement agent ran `cd /tmp && rm -rf /workspace && mkdir -p /workspace && git init ...`. That removed the link, the agent kept working in the clone and committed, and the engine's next checkpoint could not start in its working directory (`OCI runtime exec failed: ... chdir to cwd ... no such file or directory`, reported as `git add failed (exit 127)`). The run ended workflow_error, needs_human never ran, and the commit was recovered only by hand from the stopped container. Nothing in the specification protects the paths the engine depends on, so work-item bd-ib-jgedjo, which adds that protection, has no clause its Definition of Done can reference: Scenario 170 governs attribution of a failed checkpoint, not its prevention. The rule must not refuse ordinary work: agents legitimately delete files inside the repository, build scratch trees under /tmp, and mention these paths in test fixtures, here-documents and commit messages.

### Proposed Changes

1. In SPECIFICATION/contracts.md, directly after the paragraph that begins "**A commit leg completes past one tool call.**" (and before the next paragraph), insert this paragraph:

**The run's working tree survives the agent.** Inside the factory sandbox, a shell command that an ACP agent runs MUST be refused before any part of it executes when any executed segment of it would remove, move, or replace one of the run's protected paths: the sandbox root `/workspace`, the run's working directory, the working-directory link that points at the run's clone, and the clone's own directory. A command MUST be refused whether the protected path is written literally, written with a trailing slash, reached through a relative path from a directory the same command changed into, or produced by a glob that the shell would expand to it. The refusal MUST name the protected path it matched. A protected path that appears in the command only as data MUST NOT cause a refusal: an argument to `echo` or `printf`, a here-document body, a commit message, or a quoted pattern given to a search command. A command that removes, moves, or replaces a path under a scratch directory such as `/tmp`, or a file or directory inside the repository tree, MUST NOT be refused. The protection MUST apply to every ACP agent adapter the workflow launches whose runtime offers a hook that runs before each shell command; an adapter whose runtime offers no such hook is outside this paragraph. Scenario 180 in `scenarios.md` exercises this paragraph.

2. In SPECIFICATION/scenarios.md, after Scenario 179, append:

## Scenario 180 — A sandbox agent cannot remove the run's working tree, and ordinary removals still run

```gherkin
Feature: The run's protected paths survive the agent inside the factory sandbox
  As the maintainer of a repository dispatched through the factory
  I want an agent command that would delete the run's working tree refused before it runs
  So that a finished implementation is not lost to a checkpoint that cannot find its working directory

  Scenario: removing the sandbox root is refused before it runs
    Given an implement-stage agent inside a factory sandbox whose working directory is /workspace/<repository>
    When the agent runs a shell command "cd /tmp && rm -rf /workspace && mkdir -p /workspace"
    Then the command is refused before any part of it executes
    And the refusal names /workspace as the protected path
    And the run's working directory still exists

  Scenario: a relative removal from a parent directory is refused
    Given an implement-stage agent inside a factory sandbox whose working directory is /workspace/<repository>
    When the agent runs a shell command "cd / && rm -rf workspace/"
    Then the command is refused and the refusal names /workspace as the protected path

  Scenario: removals under a scratch directory and inside the repository still run
    Given an implement-stage agent inside a factory sandbox
    When the agent runs "rm -rf /tmp/layout-sim" and then removes a file inside the repository tree
    Then neither command is refused

  Scenario: a protected path mentioned only as data is not refused
    Given an implement-stage agent inside a factory sandbox
    When the agent runs a shell command that passes "rm -rf /workspace" to echo, or writes it in a here-document body
    Then the command is not refused
```

3. In tests/heading-coverage.json, append an entry for the new heading "## Scenario 180 — A sandbox agent cannot remove the run's working tree, and ordinary removals still run" with spec_root "SPECIFICATION", spec_file "scenarios.md", test "TODO", work_item "bd-ib-jgedjo", and reason: "Ratified by the revision accepting proposal sandbox-path-protection (plan checkpoint-commit-hook-failures, epic bd-ib-hcwmnq). The sandbox path guard is not implemented yet; an integration-tier test is owed for the four sub-scenarios, and work-item bd-ib-jgedjo implements them and owns that binding."

4. In tests/heading-coverage-debt.json, append a register row for the same heading with spec_root "SPECIFICATION", spec_file "scenarios.md", work_item "bd-ib-jgedjo" and first_seen set to the revision date, as the v137 revision did for Scenario 179 under the spec-first admission exception.

Numbering: Scenario 178 is reserved by the pending proposal pr-refresh-reproof-relevance and Scenario 179 is ratified, so this proposal takes 180. If the revise pass finds 180 taken, it takes the next free number and updates the contracts.md cross-reference, the heading-coverage entry and the heading-coverage-debt register row to match.
