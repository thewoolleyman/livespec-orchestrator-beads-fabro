---
topic: test-performance-gates
author: claude-opus-5-5
created_at: 2026-11-01T03:56:22Z
---

## Proposal: A Green-amend pre-commit runs its staged tests before the whole-suite coverage run and refuses on them first

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Extend constraints.md "## Pre-commit staged pre-check" so that, for a Green-amend commit, the staged test files run, after the staged lint and type pre-check, before any member of the pre-commit aggregate that runs the whole test suite starts; a failing staged test refuses the commit naming it without starting the whole-suite run; and the hook's output names which phase refused. Adds one scenario.

### Motivation

Linked proposal for held work item bd-ib-v3iw35 (spec-change-tier record: generalization target ## Pre-commit staged pre-check, linked topic a-green-amend-pre-commit). Plan implement-test-performance (livespec-dev-tooling tenant, epic livespec-dev-tooling-sv6m5p), assertion 2: during Red/Green only the changed tests run and the whole suite runs once before the commit is final; the maintainer ruled 2026-11-01 that running only changed tests without the whole-suite run is not acceptable, so this orders the gate and never narrows it. Measured (livespec-dev-tooling plan/implement-test-performance/research/001-002): a Green amend in a factory sandbox takes 5-17 min; a Green amend that fails on a staged test today still pays the whole-suite coverage run before it refuses, because the aggregate reports its failures only at the end.

### Proposed Changes

In SPECIFICATION/constraints.md, "## Pre-commit staged pre-check": change the opening sentence's "it adds one leading step" to "it adds two leading steps", and append a paragraph:

> **A Green amend runs its staged tests before the whole suite.** When the commit is a Green amend — it stages at least one implementation file and `HEAD` carries Red-only red-green-replay trailers — the pre-commit hook MUST, after the staged pre-check passes and before any member of its pre-commit aggregate that runs the whole test suite starts, run the test files staged in the amend and in `HEAD`. When any of them fails, the hook MUST refuse the commit naming each failing test and MUST NOT start the whole-suite run. When they pass, the hook MUST run the pre-commit aggregate exactly as before, including the whole-suite coverage members, once. The hook's output MUST state which phase refused a commit: the staged pre-check, the staged tests, or the aggregate. Like the pre-check, this step MUST NOT be skippable by an environment variable or a flag, and it narrows nothing: the whole-suite run still gates every Green amend.

In SPECIFICATION/scenarios.md add a scenario, numbered at revise as the next free number, "A Green amend whose staged test fails is refused before the whole suite runs", with Given a Green amend staging an implementation file whose Red test still fails / When the pre-commit hook runs / Then the commit is refused naming that test / And no whole-suite coverage run started / And the output names the staged-test phase; plus a second case where the staged tests pass and the whole-suite coverage members run once.

## Proposal: The test worker count follows the CPUs the process may use when no parallelism is projected

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend the contracts.md paragraph that projects LIVESPEC_TEST_PARALLELISM into factory sandboxes so that, where the variable is unset (CI runners, the dev host), the repository's worker-count resolver derives the worker count from the CPUs the process may use — the cgroup CPU quota, else the affinity mask — and never from the host's visible core count. Extends Scenario 254.

### Motivation

Linked proposal for held work item bd-ib-zneh24. Plan implement-test-performance (epic livespec-dev-tooling-sv6m5p), assertion 4. Measured (research 003, CI run 41266553603): CI runner pods carry no CPU limit, so `nproc / 4` gave 8 workers on one leg and 18 on the other and the 18-worker leg was 45 s slower; the sandbox case is already governed by the projected variable.

### Proposed Changes

In SPECIFICATION/contracts.md, at the end of the paragraph beginning "The Dispatcher MUST project `LIVESPEC_TEST_PARALLELISM` into every dispatched sandbox's environment", append:

> Where `LIVESPEC_TEST_PARALLELISM` is unset and the CI lane is not `hosted`, the repository's worker-count resolver (`dev-tooling/just-test-nprocs.sh`) MUST derive the worker count from the number of CPUs the process may use — the cgroup v2 CPU quota divided by its period when one is set, else the CPUs in the process's affinity mask — and MUST NOT derive it from the host's visible core count. The divisor applied to that number is unchanged.

In SPECIFICATION/scenarios.md, add to Scenario 254 a scenario: Given LIVESPEC_TEST_PARALLELISM is unset in a container whose CPU quota allows 4 CPUs on a 32-core host / When the worker-count resolver runs / Then it prints the count derived from 4 CPUs.

## Proposal: Coverage measurement omits the test modules, as the inherited coverage policy prescribes

### Target specification files

- SPECIFICATION/constraints.md

### Summary

State in constraints.md "## Inherited from livespec" that this repository's coverage omit list excludes its test modules under `tests/`, applying livespec's rule that coverage excludes test scaffolding through an omit-only blocklist, while first-party source keeps 100% line and branch coverage.

### Motivation

Linked proposal for held work item bd-ib-hjo7lb. Plan implement-test-performance (epic livespec-dev-tooling-sv6m5p), assertion 4. livespec SPECIFICATION/non-functional-requirements.md: coverage "excludes non-first-party code (vendored libraries, the project virtualenv, and test scaffolding) through an omit-only blocklist"; this repository omits only tests/e2e, tests/e2e-cli and tests/prompts. Measured (research 003): test code is 134,705 of 187,838 measured statements (72%), and the coverage data is analysed on one CPU, so each analysis pass should shrink by roughly 60-70%.

### Proposed Changes

In SPECIFICATION/constraints.md, "## Inherited from livespec", replace the bullet "100% line + branch coverage; pytest discipline; hypothesis property-based test coverage on pure modules." with:

> - 100% line + branch coverage of first-party source; the coverage `omit` list MUST exclude the test modules under `tests/`, as livespec's omit-only blocklist excludes test scaffolding; pytest discipline; hypothesis property-based test coverage on pure modules.

## Proposal: The coverage-running check prints the thirty slowest test phases of every run

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add to the contracts.md paragraph "The check aggregate runs its independent targets concurrently." that the target running the whole test suite with coverage prints the thirty slowest test phases of that run with their durations, locally and in CI.

### Motivation

Linked proposal for held work item bd-ib-fapmpq. Plan implement-test-performance (epic livespec-dev-tooling-sv6m5p), assertion 4: research 003 could not name the slow tail of the suite because no run records per-test durations.

### Proposed Changes

In SPECIFICATION/contracts.md, at the end of the paragraph "**The check aggregate runs its independent targets concurrently.**" (before its Scenario 254 sentence), append: "The target that runs the whole test suite with coverage MUST print the thirty slowest test phases of that run with their durations, so that the run's slow tail is named in every local, sandbox and CI log."
