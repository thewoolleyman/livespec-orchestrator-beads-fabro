---
topic: adopt-the-shared-actionlint-workflow
author: claude-opus-5-5
created_at: 2026-11-07T20:33:42Z
---

## Proposal: This repository adopts the shared actionlint workflow-parse check

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

The pre-commit gate and a gating CI job refuse a workflow actionlint reports as unparseable, through the pinned livespec-dev-tooling.

### Motivation

On 2026-11-03 this repository's bd-ib-43abuz release-please.yml edit took the same unchecked path as livespec-dev-tooling#3317, which merged an unparseable workflow and stopped dev-tooling releases for about two hours. This adopts the shared check rather than copying it, and only after a livespec-dev-tooling release carries it. Carries work item bd-ib-l654x4.

### Proposed Changes

In `SPECIFICATION/constraints.md`, section "## Pre-commit staged pre-check", add this paragraph:

**Workflow files must parse.** A commit that stages a `.github/workflows/*.yml` file actionlint reports as unparseable MUST be refused by the pre-commit gate, which MUST name the file, the line and actionlint's syntax-check message. A pull request whose tree carries such a file MUST fail a gating CI job that names the file and the line. The check MUST run through this repository's pinned livespec-dev-tooling, with no copy of its logic here.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario <next free number> — A workflow actionlint cannot parse is refused

```gherkin
Feature: A workflow actionlint cannot parse is refused

  Scenario: A workflow actionlint cannot parse is refused
    Given a `.github/workflows/*.yml` file that actionlint reports as unparseable
    When it is committed or carried by a pull request
    Then the pre-commit gate refuses the commit, naming the file, the line and the syntax-check message
    And a gating CI job fails, naming the file and the line
```
