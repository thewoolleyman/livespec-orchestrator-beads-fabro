---
topic: each-python-pretooluse-hook-command
author: claude-opus-5-5
created_at: 2026-11-12T18:25:50Z
---

## Proposal: A repository agent hook starts its guard through one path-named launcher

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Every python PreToolUse hook command this repository commits (the four started by `python3` and `beads-access-guard.sh`) in `.claude/settings.json` MUST start through ONE hook launcher. The launcher is committed under `.claude/hooks/` and invoked as `/bin/sh` with its path under `$CLAUDE_PROJECT_DIR`, so no shell, Python interpreter or version-manager shim is resolved through `PATH`. It runs each guard on the project virtualenv's interpreter when that is executable. Otherwise it uses `/usr/bin/python3` for a standalone-script guard, and the uv fallback for a guard that needs the project's dependencies. When nothing can start the guard, the call is REFUSED, never silently allowed. Each python hook command MUST spend at most 0.4 CPU-seconds per guarded Bash call, measured on the dev host by a stated method; that bound is host-captured. The paragraph governs this repository's own hook commands. livespec-dev-tooling's own registrations and the fleet rollout of the shared hook modules are carried by livespec-dev-tooling work item livespec-dev-tooling-imltxe.

### Motivation

Work item bd-ib-k4ltmr (plan anthropic-burn-mitigation, epic bd-ib-b2jzxw) was dropped from the dispatch queue on 2026-11-12T17:09Z as spec-change tier. The verdict was partial, the generalization target was "## ACP node timeouts", and the linked topic was this one. The judgement's rationale: the stand-down paragraph and Scenario 194 "do not state the new parts: avoiding PATH python3 resolution through the mise shim, running on the project virtualenv's python, or the 0.4 CPU-s per-invocation bound." Measured on the dev host at about 07:08-07:12Z on 2026-11-03 against the v0.279.0 hooks, in a live seat's environment, with a minimal Bash payload, as the median of three `/usr/bin/time` user+sys runs. The launcher-wrapped `pretooluse_background_guard` spent 0.59-0.70 CPU-s through the PATH `python3`, against 0.20 through `/usr/bin/python3`. The launcher-wrapped `livespec_tdd_order_guard` spent 0.46-0.53, against 0.21. The plain `livespec_footgun_guard` and `livespec_sandbox_path_guard` spent 0.15 and 0.27, against 0.07 and 0.10. A fifth python hook, `.claude/hooks/beads-access-guard.sh`, runs `beads_access_guard.py` through `python3` on PATH and exits 0, allowing the call, when `python3` is missing; it is inside this paragraph's definition and goes through the same launcher. On seat PATHs `python3` is the mise shim, and strace shows the chain mise shim, then /usr/bin/python3, then .venv/bin/python. legacy-coordinator-agent's grade of the first draft (2026-11-12 about 17:5xZ) asked for four fixes, all taken here: an exact CPU method marked host-captured; a no-.venv scenario plus a named behaviour when no interpreter can start the guard (33 of 47 sampled orchestrator worktrees have no .venv, and today that case silently fails open); narrowing the rule so a path-named `/bin/sh` launcher is the form rather than a PATH-resolved `sh -c`; and fleet scope. The coordinator also preferred one path-named sh launcher for all four python hooks, matching livespec-dev-tooling's existing venv-first form, and this revision adopts that.

### Proposed Changes

Two edits to `SPECIFICATION/contracts.md` (Edits 1 and 1a) and one to `SPECIFICATION/scenarios.md` (Edit 2). No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.

**Edit 1 — `contracts.md`, §"ACP node timeouts".** Insert a new paragraph immediately AFTER the paragraph that begins **A repository agent hook survives an unparseable project manifest.** and BEFORE the next `## ` heading:

> **A repository agent hook starts its guard through one path-named launcher.** A python PreToolUse hook command is a hook command that this repository commits in `.claude/settings.json` whose guard is a Python program, including `.claude/hooks/beads-access-guard.sh`, whose guard is `beads_access_guard.py`. Every one MUST start through the repository's ONE python hook launcher, a POSIX shell script committed under `.claude/hooks/` and invoked as `/bin/sh` with the launcher's path under `$CLAUDE_PROJECT_DIR`. No python hook command MAY resolve a shell, a Python interpreter or a version-manager shim through `PATH` to start its launcher or its guard. The launcher MUST start the guard on the first of these that can run it: `$CLAUDE_PROJECT_DIR/.venv/bin/python`, when that file is executable; `/usr/bin/python3`, when it is executable and the guard is a standalone script that imports nothing from the project's dependencies; and otherwise the hook's uv fallback, `mise exec -- uv run --no-sync python ...`. The uv fallback MAY resolve its tools through `PATH`, because it is the route a checkout without a virtualenv takes for a guard that needs the project's dependencies. When none of them can start the guard, the hook command MUST refuse the tool call and write one line to standard error naming each interpreter it tried. It MUST NOT allow the call without running the guard, except by the preceding paragraph's stand-down. The command MUST return the guard's own allow or refuse decision and exit status. The preceding paragraph's stand-down on an unparseable `pyproject.toml` is unchanged, applies to every guard the launcher starts through `uv`, and MUST happen without starting a guard. Each python PreToolUse hook command MUST spend at most 0.4 CPU-seconds of user plus system time on one invocation for a guarded Bash call, measured as follows. The measurement is taken on the dev host, in an agent seat's own environment, with the real checkout and its virtualenv. The command is run four times with the standard input `{"tool_name":"Bash","tool_input":{"command":"true"}}` under `/usr/bin/time`; the first, cold run is discarded; and the bound applies to the median user-plus-system reading of the remaining three. The bound is hardware-bound and HOST-CAPTURED: no scenario exercises it, and it is proved only by that measurement on the dev host. This paragraph governs only how this repository's hook commands start their guards; it does not change what any guard decides. livespec-dev-tooling's own hook commands, and the registrations of its shared hook modules in the other fleet repositories, are outside this repository and adopt the same form through livespec-dev-tooling work item livespec-dev-tooling-imltxe. The reason is cost, measured on 2026-11-03 on the dev host against the v0.279.0 hooks. On agent seats `python3` resolves to the mise shim, so every Bash call started four processes before any guard ran, and the launcher-wrapped `pretooluse_background_guard` spent 0.59 to 0.70 CPU-seconds per call against 0.20 through `/usr/bin/python3`. Scenario 194 in `scenarios.md` exercises every sentence of this paragraph except its CPU bound.

**Edit 1a — `contracts.md`, the paragraph that begins **A repository agent hook survives an unparseable project manifest.**** Replace its sentence "When `pyproject.toml` parses, each such hook command MUST return the same allow or refuse decision for a tool call that it returned before this paragraph was ratified." with "When `pyproject.toml` parses, each such hook command MUST return the same allow or refuse decision for a tool call that it returned before this paragraph was ratified, except that a call whose guard no interpreter can start is refused as the following paragraph requires." Every other sentence of that paragraph is unchanged.

**Edit 2 — `scenarios.md`, §"Scenario 194 — A conflicted pyproject.toml does not make the repository's agent hooks refuse every tool call".** Append these scenarios to the end of that scenario's Gherkin block, inside the same fenced block, after the existing scenario "A parseable pyproject.toml leaves every guard decision unchanged". The scenario's heading is unchanged. In the same block, replace the existing step "Then that hook command returns the same allow or refuse decision it returned before this scenario was ratified" with "Then that hook command returns the same allow or refuse decision it returned before this scenario was ratified, unless no interpreter can start its guard", and append the new scenarios after it:

```gherkin
  Scenario: A python hook command runs no shell or python3 that PATH supplies
    Given a directory holding an executable python3 and an executable sh that each record when they run, placed first on PATH
    And $CLAUDE_PROJECT_DIR/.venv/bin/python is executable
    When an agent makes a tool call that each python PreToolUse hook command of this repository guards
    Then every one of those hook commands runs its guard
    And neither the python3 nor the sh on PATH runs

  Scenario: With a virtualenv the guard runs on the project virtualenv's interpreter
    Given this repository's pyproject.toml parses and $CLAUDE_PROJECT_DIR/.venv/bin/python is executable
    When an agent makes a tool call that a python PreToolUse hook command of this repository guards
    Then the guard runs on $CLAUDE_PROJECT_DIR/.venv/bin/python
    And the hook command returns the guard's own allow or refuse decision and exit status

  Scenario: Without a virtualenv the guard decision is unchanged
    Given a checkout of this repository with no $CLAUDE_PROJECT_DIR/.venv
    When an agent makes a tool call that a python PreToolUse hook command of this repository guards
    Then a standalone-script guard runs on /usr/bin/python3 and a guard needing the project's dependencies runs through the uv fallback
    And the launcher itself was started by /bin/sh named by path
    And the hook command returns the same allow or refuse decision and exit status it returns with a virtualenv

  Scenario: A guard no interpreter can start refuses the call
    Given a checkout with no $CLAUDE_PROJECT_DIR/.venv and a uv fallback that cannot start
    When an agent makes a Bash call that a python PreToolUse hook command of this repository guards with a guard needing the project's dependencies
    Then the hook command refuses the call
    And it writes one line to standard error naming each interpreter it tried

  Scenario: The stand-down on a conflicted pyproject.toml starts no guard
    Given this repository's pyproject.toml carries unresolved merge-conflict markers
    When an agent makes a Bash call that a python PreToolUse hook command of this repository guards through uv
    Then the hook command allows the call and writes its one-line stand-down notice
    And no guard process is started
```
