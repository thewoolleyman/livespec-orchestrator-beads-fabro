---
topic: each-python-pretooluse-hook-command
author: claude-opus-5-5
created_at: 2026-11-12T17:23:10Z
---

## Proposal: A repository agent hook names its interpreter instead of resolving python3 through PATH

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Every python PreToolUse hook command this repository commits in `.claude/settings.json` MUST start its guard without resolving `python3` through `PATH`. A launcher-wrapped hook command MUST run its guard on the project virtualenv's interpreter when that interpreter is executable, and otherwise fall back exactly as its launcher does today. Each launcher-wrapped hook command MUST spend at most 0.4 CPU-seconds of user plus system time per invocation on a guarded Bash call. Today the specification states only the stand-down on an unparseable `pyproject.toml` (Scenario 194). It says nothing about which interpreter a hook starts or what a hook may cost. So a bare `python3` that resolves to the mise shim on every agent seat's `PATH` is conformant, although it starts four processes before any guard runs.

### Motivation

Work item bd-ib-k4ltmr (plan anthropic-burn-mitigation, epic bd-ib-b2jzxw) was dropped from the dispatch queue on 2026-11-12T17:09Z as spec-change tier. The verdict was partial, the generalization target was "## ACP node timeouts", and the linked topic was this one. The judgement's rationale: "The paragraph 'A repository agent hook survives an unparseable project manifest' and Scenario 194 state the stand-down behaviour ... They do not state the new parts: avoiding PATH python3 resolution through the mise shim, running on the project virtualenv's python, or the 0.4 CPU-s per-invocation bound." Measured on the dev host at about 07:08-07:12Z on 2026-11-03 against the v0.279.0 hooks, in a live seat's environment, with a minimal Bash payload, as the median of three `/usr/bin/time` user+sys runs: the launcher-wrapped `pretooluse_background_guard` spent 0.59-0.70 CPU-s through the PATH `python3` and 0.20 CPU-s through `/usr/bin/python3`; the launcher-wrapped `livespec_tdd_order_guard` spent 0.46-0.53 against 0.21; and the plain `livespec_footgun_guard` and `livespec_sandbox_path_guard` spent 0.15 and 0.27 against 0.07 and 0.10. The cause: on seat PATHs `python3` is `~/.local/share/mise/shims/python3`, a symlink to the mise binary, and strace shows the chain mise shim, then /usr/bin/python3, then .venv/bin/python. Every Bash tool call of every agent session pays that before any guard runs. bd-ib-dirscy removed only the inner `mise exec -- uv run`, and its own 0.6 CPU-s host bound does not hold reliably because of this.

### Proposed Changes

One edit to `SPECIFICATION/contracts.md` and one to `SPECIFICATION/scenarios.md`. No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.

**Edit 1 — `contracts.md`, §"ACP node timeouts".** Insert a new paragraph immediately AFTER the paragraph that begins **A repository agent hook survives an unparseable project manifest.** and BEFORE the next `## ` heading:

> **A repository agent hook names its interpreter.** A python PreToolUse hook command is a hook command that this repository commits in `.claude/settings.json` whose guard is a Python program. Each one MUST name the interpreter it starts by an absolute path or by a path under `$CLAUDE_PROJECT_DIR`, and MUST NOT resolve `python3`, or any other interpreter name, through `PATH`, so that no interpreter or version-manager shim a `PATH` entry supplies starts the guard or the launcher in front of it. A hook command that starts its guard through this repository's hook launcher (a launcher-wrapped hook command) MUST run the guard on the project virtualenv's interpreter, `$CLAUDE_PROJECT_DIR/.venv/bin/python`, whenever that file exists and is executable. When it does not, the launcher MUST fall back to the hook's wrapped command exactly as it does today. That fallback MAY resolve its tools through `PATH`, because it is the route a checkout without a virtualenv takes; the interpreter that starts the launcher itself MUST still be named by path. The command MUST return the guard's own allow or refuse decision and exit status. The preceding paragraph's stand-down on an unparseable `pyproject.toml` is unchanged and MUST happen without starting the guard. A launcher-wrapped hook command MUST spend at most 0.4 CPU-seconds of user plus system time on one invocation for a guarded Bash call. That is measured on a developer host, in an agent seat's own environment, with the real checkout and virtualenv, as the median of three `/usr/bin/time` runs of the command with a minimal Bash payload on its standard input. This paragraph governs only how those commands start their guards; it does not change what any guard decides. The reason is cost, measured on 2026-11-03 on the dev host against the v0.279.0 hooks. On agent seats `python3` resolves to the mise shim, so every Bash call started four processes before any guard ran. The launcher-wrapped `pretooluse_background_guard` spent 0.59 to 0.70 CPU-seconds per call that way, against 0.20 through `/usr/bin/python3`. Scenario 194 in `scenarios.md` exercises this paragraph.

**Edit 2 — `scenarios.md`, §"Scenario 194 — A conflicted pyproject.toml does not make the repository's agent hooks refuse every tool call".** Append these scenarios to the end of that scenario's Gherkin block, inside the same fenced block, after "Then that hook command returns the same allow or refuse decision it returned before this scenario was ratified". The scenario's heading is unchanged:

```gherkin
  Scenario: A python hook command runs no python3 that PATH supplies
    Given a directory holding an executable python3 that records each time it runs, placed first on PATH
    And $CLAUDE_PROJECT_DIR/.venv/bin/python is executable
    When an agent makes a tool call that each python PreToolUse hook command of this repository guards
    Then every one of those hook commands runs its guard
    And the python3 on PATH never runs

  Scenario: A launcher-wrapped hook command runs its guard on the project virtualenv's interpreter
    Given this repository's pyproject.toml parses and $CLAUDE_PROJECT_DIR/.venv/bin/python is executable
    When an agent makes a tool call that a launcher-wrapped PreToolUse hook command of this repository guards
    Then the guard runs on $CLAUDE_PROJECT_DIR/.venv/bin/python
    And the hook command returns the guard's own allow or refuse decision and exit status

  Scenario: The stand-down on a conflicted pyproject.toml starts no guard
    Given this repository's pyproject.toml carries unresolved merge-conflict markers
    When an agent makes a Bash call that a launcher-wrapped PreToolUse hook command of this repository guards
    Then the hook command allows the call and writes its one-line stand-down notice
    And no guard process is started
```
