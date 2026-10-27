---
topic: check-aggregate-runs-targets-concurrently
author: claude-opus-5-5
created_at: 2026-10-26T22:59:59Z
---

## Proposal: The check aggregate runs its independent targets concurrently beside a single pytest lane

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

In 'Sandbox test-worker parallelism': just check runs its pytest lane as a single LIVESPEC_TEST_PARALLELISM-sized lane and the other targets concurrently with it, still reporting every verdict and failing as the serial loop does, with bounded concurrency keeping peak memory under the sandbox limit.

### Motivation

Routed by petri-factory-on-gmktec under coordinator ruling R69 (throughput, R67 ratification), spec-first for work-item bd-ib-6zy3zd; its Codex-first Definition-of-Done screen found that no H2 specifies aggregate concurrency. dev-tooling/just-check.sh runs every aggregate target in one strictly serial loop; in the factory sandbox the pytest lane dominates, and the many independent lint, type and static targets add their full runtime on top of it, at both the janitor and publish_draft. Measured on gmktec on 2026-10-26: commit-hook and janitor passes of about 1416 to 1470 s at two workers and 737 to 832 s at four (bd-ib-svm3fe run 01M5WFH8GTAJ, bd-ib-ytrpb5 run 01M5WJK5R48W). kubernetes-sandbox-backend measured four-worker coverage at memory.peak 2748 MiB against the 7630 MiB pod, leaving headroom for concurrent non-pytest targets. The paragraph sits beside the LIVESPEC_TEST_PARALLELISM paragraph whose memory measurement it relies on. livespec-dev-tooling's parallel_check_dispatcher may be reused; the clause does not prescribe the mechanism.
The first read-only Codex review raised blockers that are folded in here.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, §"Dispatcher policy settings" → "### Sandbox test-worker parallelism", after its paragraph on `LIVESPEC_TEST_PARALLELISM`, insert immediately after the text

```
A gate run in the sandbox that sizes its test workers from this variable therefore follows the sandbox's CPU limit, not the node's visible CPUs.
```

the following new paragraph (separated by one blank line):

```
**The check aggregate runs its independent targets concurrently.** The repository's `just check` aggregate (`dev-tooling/just-check.sh`) MUST run its pytest lane as a single ordered lane: every target that runs the test suite, sized by `LIVESPEC_TEST_PARALLELISM` exactly as before, followed in the same lane by every target that reads what those targets produce, so that `check-coverage` runs after `check-per-file-coverage` and no two test-suite runs overlap. It MUST run the aggregate's independent targets, those that neither run the test suite nor read its output, such as lint, types and the static checks, concurrently with that lane rather than after it. The concurrent aggregate MUST still report every target's verdict, keeping each target's output together so that a failure stays readable, and MUST fail when any target fails, exactly as the serial loop does; the targets it skips and the green verdict it records are unchanged. In a factory sandbox the concurrent aggregate's peak memory MUST stay within the sandbox's memory limit, so the number of non-pytest targets that run at once MUST be bounded to keep their peak memory, together with the pytest lane's, under that limit. Measured 2026-10-26: the serial aggregate took about 737 to 832 seconds at four test workers, while the pytest lane alone at four workers peaked at 2748 MiB of the 7630 MiB limit. Scenario 254 in `scenarios.md` exercises this paragraph.
```

2. In `SPECIFICATION/scenarios.md`, append:

````
## Scenario 254 — The check aggregate runs its independent targets beside the pytest lane and still reports and fails as the serial loop did

```gherkin
Feature: The check aggregate does not wait for the pytest lane to run its independent targets
  As the operator of a factory
  I want lint, types and static checks to run beside the pytest lane
  So that a check pass costs about as long as its longest lane rather than the sum of every target

  Scenario: Independent targets run beside a single pytest lane
    Given LIVESPEC_TEST_PARALLELISM is 4
    When the just check aggregate runs
    Then the pytest lane runs once with four workers, with check-coverage after check-per-file-coverage and no overlapping test-suite runs
    And the lint, type and static targets run while the pytest lane is running

  Scenario: A failing target still fails the concurrent aggregate
    Given one non-pytest target fails while the pytest lane passes
    When the just check aggregate runs
    Then it reports every target's verdict with each target's output kept together
    And it exits non-zero naming the failed target, exactly as the serial loop does

  Scenario: The concurrent aggregate stays within the sandbox memory limit
    Given a factory sandbox with a 7630 MiB memory limit and LIVESPEC_TEST_PARALLELISM of 4
    When the just check aggregate runs
    Then the sandbox's peak memory stays under its memory limit
```
````

3. Add a TODO row for the new heading to `tests/heading-coverage.json` and a matching debt row to `tests/heading-coverage-debt.json`, both owned by the implementing work-item bd-ib-6zy3zd.
