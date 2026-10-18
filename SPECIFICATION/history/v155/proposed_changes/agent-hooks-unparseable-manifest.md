---
topic: agent-hooks-unparseable-manifest
author: claude-opus-5-5
created_at: 2026-10-18T04:28:55Z
---

## Proposal: A conflicted pyproject.toml does not make the repository's agent hooks refuse every tool call

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

State that a uv-launched PreToolUse hook command committed in this repository's .claude/settings.json does not refuse a tool call because pyproject.toml is unparseable: in that state it allows the guarded call and writes one stderr line naming pyproject.toml and saying its guard was skipped, and with a parseable pyproject.toml every decision is unchanged. Add Scenario 194.

### Motivation

Work item bd-ib-cap6t7 (admitted by driver ruling R145 of gitops-fleet-capacity-monitoring as the root-cause prerequisite of bd-ib-sufca7). Two measured instances on bd-ib-sufca7: fix stage of run 01M50Y9V7G55 (2026-10-15) and implement stage of run 01M56KH6Y9EA (2026-10-18). Both times a rebase or cherry-pick left conflict markers in pyproject.toml, `uv run --no-sync` then exits 2 with 'Failed to parse pyproject.toml', Claude Code reads that exit as a blocking refusal, and every Bash, Write and Edit call was refused, including `git cherry-pick --abort`, so the agent could not repair the file that disabled it. bd-ib-cap6t7's groomed Definition of Done states exactly the behaviour above, but no ratified text governs agent-hook launch behaviour (searched all SPECIFICATION/*.md for PreToolUse, settings.json, agent hook, the guard names and refused tool calls; the only hook clause is 'The run's working tree survives the agent', which governs protected-path refusal), so its references would not govern its assertions at dod_gate. The behaviour is ratified here as groomed, per the driver's direction; a stricter design that survives without allowing is recorded on the item for a later groom.

### Proposed Changes

In SPECIFICATION/contracts.md, section "## ACP node timeouts", immediately after the paragraph "**The run's working tree survives the agent.**", insert this paragraph:

**A repository agent hook survives an unparseable project manifest.** A PreToolUse hook command that this repository commits in `.claude/settings.json` and launches through `uv` MUST NOT refuse a tool call because the repository's `pyproject.toml` cannot be parsed. A `pyproject.toml` carrying unresolved merge-conflict markers is an ordinary intermediate state of a refresh repair, and a refusal there withdraws the very tools that could resolve it. When `pyproject.toml` fails to parse, each such hook command MUST allow the Write, Edit, MultiEdit or Bash call it guards, and MUST write one line to standard error naming `pyproject.toml` as unparseable and stating that its guard was skipped for that call. When `pyproject.toml` parses, each such hook command MUST return the same allow or refuse decision for a tool call that it returned before this paragraph was ratified. This paragraph governs only the launch of those hook commands; it does not change what any guard decides when it runs. Scenario 194 in `scenarios.md` exercises this paragraph.

In SPECIFICATION/scenarios.md, after the last scenario (Scenario 193 is reserved by the in-flight proposal stranded-claim-release), append:

## Scenario 194 — A conflicted pyproject.toml does not make the repository's agent hooks refuse every tool call

```gherkin
Feature: The repository's agent hooks survive an unparseable project manifest
  As an agent repairing a refresh conflict in this repository
  I want the repository's PreToolUse hooks to leave my tools usable while pyproject.toml is conflicted
  So that the repair can fix the file whose conflict would otherwise disable it

  Scenario: A conflicted pyproject.toml lets a guarded tool call through and says so
    Given this repository's pyproject.toml carries unresolved merge-conflict markers
    When an agent makes a Bash, Write, Edit or MultiEdit call that a uv-launched PreToolUse hook command of this repository guards
    Then that hook command allows the call
    And it writes one line to standard error naming pyproject.toml as unparseable and stating that its guard was skipped for that call

  Scenario: A parseable pyproject.toml leaves every guard decision unchanged
    Given this repository's pyproject.toml parses
    When an agent makes a tool call that a uv-launched PreToolUse hook command of this repository guards
    Then that hook command returns the same allow or refuse decision it returned before this scenario was ratified
```

The revise pass that accepts this proposal MUST add a tests/heading-coverage.json entry for the Scenario 194 heading in the same change, with test "TODO" and a reason stating that an integration-tier test is owed and that work-item bd-ib-cap6t7 implements it and owns that binding, plus the matching tests/heading-coverage-debt.json row.
