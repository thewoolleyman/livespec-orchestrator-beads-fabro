---
topic: in-ci-the-check-coverage
author: claude-opus-5-5
created_at: 2026-11-07T20:33:40Z
---

## Proposal: In CI, the check-coverage consumers refuse a missing canonical per-file verdict

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

The root and nonroot GitHub Actions check-coverage consumers read the canonical per-file verdict or fail by name, and never fall back to a full run.

### Motivation

This repository ran the same silent fallback from 2026-11-01 to 2026-11-04: 941 fallback legs and about 15,470 wasted runner-minutes (research note plan/ci-runtime-and-cost/research/006-coverage-fallback-post-mortem-2026-11-06.md on livespec-dev-tooling). Each repository adopts its own refusal before a fleet check is armed. Carries work item bd-ib-k6cq6e.

### Proposed Changes

In `SPECIFICATION/constraints.md`, section "## Inherited from livespec", add this paragraph:

**The CI coverage consumers never fall back to a full run.** When a GitHub Actions check-coverage consumer, root or nonroot, finds no canonical per-file verdict in `.coverage-gates`, it MUST exit non-zero with a message naming the missing verdict and MUST NOT start a pytest process. When it finds a verdict produced for a different commit or uid than its own, it MUST exit non-zero naming the mismatch and MUST NOT start a pytest process. With a matching verdict it MUST read it, exit zero at a 100 percent aggregate total and non-zero below it. A standalone local `just check-coverage` with no verdict MUST still run and measure the clean suite.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario <next free number> — A CI coverage consumer with no usable per-file verdict fails by name

```gherkin
Feature: A CI coverage consumer with no usable per-file verdict fails by name

  Scenario: A CI coverage consumer with no usable per-file verdict fails by name
    Given a GitHub Actions check-coverage consumer, root or nonroot
    And the canonical per-file verdict in `.coverage-gates` is missing, or was produced for a different commit or uid
    When the consumer runs
    Then it exits non-zero with a message naming the cause
    And no pytest process starts
```

## Scenario <next free number> — A local coverage run with no verdict still measures

```gherkin
Feature: A local coverage run with no verdict still measures

  Scenario: A local coverage run with no verdict still measures
    Given a standalone local `just check-coverage`
    And no verdict is present
    When it runs
    Then it runs and measures the clean suite
```
