---
topic: pre-commit-staged-precheck
author: claude-opus-5-5:petri-factory-on-gmktec
created_at: 2026-10-29T14:24:09Z
---

## Proposal: Run the staged-file lint and type pre-check at the head of the pre-commit hook

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Add ## Pre-commit staged pre-check to constraints.md: the pre-commit hook runs livespec-dev-tooling's staged_precheck before the pre-commit aggregate, refuses staged type errors and unfixed lint errors naming file, line and rule, and otherwise runs the aggregate exactly as before.

### Motivation

Work-item bd-ib-rqdqkb (a rollout child of livespec-dev-tooling-nil6v7, plan livespec-dev-tooling-dfixhe, maintainer direction 2026-10-24) wires livespec-dev-tooling's `staged_precheck` commit-hook check into this repository's pre-commit hook. That check lints and type-checks staged Python files and refuses in seconds with the tools' own file:line and rule output, before the slow aggregate. Evidence for the need: factory run 01M5QNH88NHN68ST28Y80CZJ48 waited 711 s for a pre-commit refusal on three pyright errors. livespec-dev-tooling ratified the same one-line ordering amendment at its v096. The orchestrator's launch-time Definition-of-Done preflight refused rqdqkb on 2026-10-29: its References line names ## Pre-push gate refinements, which covers only the pre-push gate, and the governing-heading verdict for the pre-commit assertions is kind unstated. This proposal states the behaviour so the item has a heading to cite. Filed under coordinator gitops-fleet-capacity-monitoring ruling R216.

### Proposed Changes

In SPECIFICATION/constraints.md, add a new section after ## Pre-push gate refinements:

## Pre-commit staged pre-check

This section refines the pre-commit step ordering inherited from livespec; it adds one leading step and reorders nothing else.

**Staged Python files are linted and type-checked before the pre-commit aggregate.** The repository's pre-commit hook MUST run `python -m livespec_dev_tooling.workflow_checks.staged_precheck` after any early exit for a commit that stages no Python file, and before any member of its pre-commit aggregate starts. That pre-check lints the staged added or modified Python files and type-checks those the repository's pyright configuration covers. When it reports a type-checker error, or a lint error the lint autofix step does not fix, the hook MUST refuse the commit, naming each file, line and rule, before the pre-commit aggregate starts. When the staged Python files pass, the commit MUST proceed to the pre-commit aggregate, which runs exactly as before. Like the pre-push refinements above, the pre-check MUST NOT be skippable by an environment variable or a flag. The full aggregate still runs at pre-push and in CI, so the pre-check moves a refusal earlier without narrowing what gates a merge.

In SPECIFICATION/scenarios.md, append one scenario (numbered at revise):

## Scenario NNN — A staged type error is refused before the pre-commit aggregate runs

Given a commit that stages a Python file carrying a type-checker error the repository's pyright configuration covers

When the pre-commit hook runs

Then the commit is refused, naming the file, line and rule, before any member of the pre-commit aggregate starts

Scenario: a staged lint error the autofix step does not fix is refused first

Given a commit that stages a Python file carrying a lint error the lint autofix step does not fix

When the pre-commit hook runs

Then the commit is refused, naming the file, line and rule, before the pre-commit aggregate starts

Scenario: a clean staged change runs the aggregate as before

Given a commit whose staged Python files pass the pre-check

When the pre-commit hook runs

Then the pre-commit aggregate runs exactly as before

The revise that accepts this proposal MUST add tests/heading-coverage.json entries for the new ## Pre-commit staged pre-check heading and the new scenario heading, each with test "TODO" and a reason naming bd-ib-rqdqkb as the implementing item.
