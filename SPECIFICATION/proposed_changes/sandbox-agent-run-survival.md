---
topic: sandbox-agent-run-survival
author: claude-opus-5-5
created_at: 2026-10-18T06:07:59Z
---

## Proposal: The clone's repository metadata and its whole top level survive the agent

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a paragraph after "The run's working tree survives the agent." that refuses an agent shell command which would remove, move or replace the clone's .git directory, or remove every non-hidden top-level entry of the clone. Carve that case out of the earlier paragraph's in-tree allowance. Add Scenario 197 to exercise it. Ordinary in-tree removals stay allowed.

### Motivation

Work-item bd-ib-quzpge, from the Fable review of PR 3034 (v142). v142 protects /workspace, the run's working directory, the working-directory link and the clone's own directory, and it expressly allows removing any file or directory inside the repository tree. Two in-tree commands are therefore allowed, yet each reproduces the checkpoint loss of run 01M4YJGC55V86C9V1X07QG3Y2H by another route. `rm -rf <clone>/.git` destroys the repository, so the engine's next checkpoint git add or git commit fails. `rm -rf <clone>/*` leaves a checkpoint commit that deletes the whole tree. Protecting exactly those two shapes closes both routes, and leaves every ordinary removal of a file or subdirectory alone. Decision recorded by session checkpoint-commit-hook-failures under freeze-driver ruling R154: extend the protected set rather than bound in-tree removals generally, because a general bound would refuse ordinary refactors and the two measured routes are both nameable exactly.

### Proposed Changes

In `SPECIFICATION/contracts.md`, in the paragraph beginning "**The run's working tree survives the agent.**", replace the sentence

> A command none of whose executed segments would remove, move, or replace a protected path MUST NOT be refused, including one that removes, moves, or replaces a path under a scratch directory such as `/tmp`, or a file or directory inside the repository tree.

with

> A command none of whose executed segments would remove, move, or replace a protected path MUST NOT be refused, including one that removes, moves, or replaces a path under a scratch directory such as `/tmp`, or a file or directory inside the repository tree other than the ones the next paragraph protects.

Immediately after that paragraph, insert this new paragraph:

> **The run's repository survives the agent.** Inside the factory sandbox, a shell command that an ACP agent runs MUST be refused before any part of it executes when any executed segment of it would remove, move, or replace the clone's `.git` directory, or would remove every non-hidden entry at the top level of the clone's own directory. The matching rules of the preceding paragraph apply unchanged: a target written literally, written with a trailing slash, reached through a relative path from a directory the same command changed into, or produced by a glob that the shell would expand to it. A glob such as `<clone>/*` that the shell would expand to every non-hidden top-level entry of the clone counts as removing every such entry. The refusal MUST name the clone's `.git` directory, or the clone's own directory, as the path it matched. A path that appears in the command only as data MUST NOT cause a refusal, exactly as the preceding paragraph defines data. A command that removes, moves, or replaces a file or directory inside the repository tree other than the clone's `.git` directory, and that does not remove every non-hidden top-level entry of the clone, MUST NOT be refused. The protection applies to the same ACP agent adapters as the preceding paragraph. Scenario 197 in `scenarios.md` exercises this paragraph.

In `SPECIFICATION/scenarios.md`, append after the highest-numbered scenario:

## Scenario 197 — A sandbox agent cannot remove the clone's repository or empty its whole tree, and ordinary in-tree removals still run

Governing clause: `contracts.md` §"ACP node timeouts" → "The run's repository survives the agent."

```gherkin
Feature: The clone's repository and its whole tree survive the agent inside the factory sandbox
  As the maintainer of a repository dispatched through the factory
  I want an agent command that would destroy the clone's repository or empty its tree refused before it runs
  So that the engine's next checkpoint commit neither fails nor deletes the run's work

  Background:
    Given the implement-stage agent's ACP adapter runtime offers a hook that runs before each shell command
    And an implement-stage agent inside a factory sandbox whose clone is <clone>

  Scenario: removing the clone's .git directory is refused before it runs
    When the agent runs a shell command "rm -rf <clone>/.git"
    Then the command is refused before any part of it executes
    And the refusal names <clone>/.git as the protected path

  Scenario: emptying the clone's top level through a glob is refused
    When the agent runs a shell command "cd <clone> && rm -rf ./*"
    Then the command is refused and the refusal names <clone> as the protected path

  Scenario: removing a file and a subdirectory inside the repository still runs
    When the agent runs "rm -rf <clone>/build" and then removes one file inside the repository tree
    Then neither command is refused

  Scenario: the clone's .git directory mentioned only as data is not refused
    When the agent runs a shell command that passes "rm -rf <clone>/.git" to echo
    Then the command is not refused
```

## Proposal: The sandbox's PID 1 and the agent adapter survive the agent's signals

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a paragraph that refuses an agent shell command which would signal the sandbox container's PID 1, every process, or the ACP agent adapter process, whether named by id or matched by a name or command-line pattern. Add Scenario 198 to exercise it. Signals to processes the pattern or id does not reach stay allowed.

### Motivation

Work-item bd-ib-dpkip6, measured 2026-10-15 on livespec-overseer run 01M4ZSVE4JHHGYDHX4AW2HVHT7. The proof_capture agent's cleanup ran `pkill -f "sleep 3600"`. The sandbox container's PID 1 command line is `/bin/bash -lc "mkdir -p /workspace && sleep infinity"`, which that pattern matches, so PID 1 took SIGTERM. The container exited 143, and the engine's checkpoint git add then failed in the dead container. That ended a run whose implement, publish and proof had all succeeded. v142 covers removal, move and replacement of protected paths, not signalling processes. Decision recorded by session checkpoint-commit-hook-failures under freeze-driver ruling R154: add a sibling clause on the same pre-shell hook seat, and leave the companion proof_capture prompt fix (kill only process ids it recorded) to the implementing item, as an implementation detail.

### Proposed Changes

In `SPECIFICATION/contracts.md`, immediately after the new paragraph "**The run's repository survives the agent.**", insert this paragraph:

> **The run's sandbox processes survive the agent.** Inside the factory sandbox, a shell command that an ACP agent runs MUST be refused before any part of it executes when any executed segment of it would send a signal to the sandbox container's PID 1, to every process, or to the process of the ACP agent adapter that launched the agent. A command MUST be refused whether the target is named by process id (the id `1`, the id `-1` that addresses every process, or the adapter's own process id) or selected by a process-name or command-line pattern, as `pkill`, `pkill -f` and `killall` select, that matches the name or command line of PID 1 or of the adapter process. The refusal MUST name the process it matched and the id or pattern that reached it. A protected target that appears in the command only as data MUST NOT cause a refusal, exactly as the paragraph "The run's working tree survives the agent." defines data. A command that signals only processes that neither its ids nor its patterns reach in PID 1 or the adapter process MUST NOT be refused, including one that signals a process id the agent recorded when it started that process. The protection applies to the same ACP agent adapters as that paragraph. Scenario 198 in `scenarios.md` exercises this paragraph.

In `SPECIFICATION/scenarios.md`, append after Scenario 197:

## Scenario 198 — A sandbox agent cannot signal the sandbox's PID 1 or its own adapter, and signals to its own processes still run

Governing clause: `contracts.md` §"ACP node timeouts" → "The run's sandbox processes survive the agent."

```gherkin
Feature: The sandbox's PID 1 and the agent adapter survive the agent's signals inside the factory sandbox
  As the maintainer of a repository dispatched through the factory
  I want an agent command that would signal the sandbox's PID 1 or its own adapter refused before it runs
  So that a cleanup step cannot kill the sandbox the engine still needs

  Background:
    Given the implement-stage agent's ACP adapter runtime offers a hook that runs before each shell command
    And a factory sandbox whose PID 1 command line is "/bin/bash -lc mkdir -p /workspace && sleep infinity"

  Scenario: a pattern that matches PID 1's command line is refused
    When the agent runs a shell command "pkill -f 'sleep'"
    Then the command is refused before any part of it executes
    And the refusal names PID 1 and the pattern sleep

  Scenario: signalling PID 1 or every process by id is refused
    When the agent runs a shell command "kill -TERM 1" or "kill -9 -1"
    Then each command is refused and the refusal names the process id it matched

  Scenario: signalling a process the agent started still runs
    Given the agent started "sleep 3600" in the background and recorded its process id <pid>
    When the agent runs a shell command "kill <pid>"
    Then the command is not refused

  Scenario: a pattern that matches only the agent's own process still runs
    Given the agent started "python3 -m http.server 8765" in the background
    When the agent runs a shell command "pkill -f 'http.server 8765'"
    Then the command is not refused
```
