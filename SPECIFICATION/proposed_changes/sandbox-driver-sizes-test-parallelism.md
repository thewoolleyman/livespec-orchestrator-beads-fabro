---
topic: sandbox-driver-sizes-test-parallelism
author: claude-opus-5-5 (kubernetes-sandbox-backend seat)
created_at: 2026-11-14T00:50:16Z
---

## Proposal: A factory sandbox's CPU limit sizes every parallel tool, and the Dispatcher projects no constant

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Move the source of a factory sandbox's test parallelism from the Dispatcher's constant LIVESPEC_TEST_PARALLELISM=4 projection to the sandbox's own CPU limit: the sandbox provider sets LIVESPEC_TEST_PARALLELISM, PYTEST_XDIST_AUTO_NUM_WORKERS and OMP_NUM_THREADS to that limit (a value the sandbox's spec sets wins), and the Dispatcher stops projecting a constant. Adds Scenario 372.

### Motivation

Two defects, one cause. (1) The projected constant has drifted: it was set to 4 for 4-CPU factory sandboxes (bd-ib-z7qrnd, spec v223), and the sandboxes now carry a 6-CPU limit. A constant cannot track a resize; the sandbox's own limit can. (2) The projection covers only tools that read LIVESPEC_TEST_PARALLELISM. A CPU limit is a CFS quota, not an affinity mask, so any tool that sizes itself from the CPU count sees the node's CPUs. Measured 2026-11-13, bd-ib-vy75ws run 01M7AFVCPSK2GT0W2SWXP3258Z on gmktec-xubuntu (32 CPUs): the agent ran `uv run pytest -q -n auto tests` in a 6-CPU, 7630 MiB sandbox; xdist started 32 workers of about 230 MiB each, and at 14:12:34Z a memory-cgroup OOM killed codex (the agent's app-server) and the run idled until its 2 h stall watchdog cancelled it. bd-ib-yq4x4g recorded the same `-n auto` shape at 70-72 workers on poweredge in October. The sandbox provider already knows each sandbox's CPU limit, so it is the one place that can size every parallel tool in every factory, image and repository from the real number. sandbox-driver-kubernetes PR #21 (bd-ib-p3g5tp) implements the provider half; this proposal ratifies the contract and retires the Dispatcher's constant so there is one source. Route ruled by legacy-coordinator-agent (session 719514f8, 2026-11-14), who asked for this proposal as a draft for grade.

### Proposed Changes

**1. `SPECIFICATION/contracts.md`, `## Dispatcher policy settings` → `### Sandbox test-worker parallelism`, first paragraph.** Replace these four sentences, verbatim:

> The Dispatcher MUST project `LIVESPEC_TEST_PARALLELISM` into every dispatched sandbox's environment, beside the harness shell policy it already projects there. The value MUST be a positive integer that does not exceed the CPU limit of the sandbox it is projected into. This repository projects 4, for its 4-CPU factory sandboxes. Four workers fit the sandbox's 7630 MiB memory limit: measured on 2026-10-26, a full per-file-coverage gate run at four workers peaked at 2748 MiB of cgroup memory, with no worker above 467 MiB resident. A gate run in the sandbox that sizes its test workers from this variable therefore follows the sandbox's CPU limit, not the node's visible CPUs.

with:

> A factory sandbox's environment MUST carry `LIVESPEC_TEST_PARALLELISM`, `PYTEST_XDIST_AUTO_NUM_WORKERS` and `OMP_NUM_THREADS`, each equal to the sandbox's CPU limit in whole cores, unless the sandbox's spec already sets that variable, in which case the spec's value MUST reach the sandbox unchanged. The sandbox provider sets them from the CPU limit it applies to the sandbox; for the Kubernetes provider that is sandbox-driver-kubernetes v0.8.5 and later, which writes them into the sandbox container's environment, so every command executed in the sandbox inherits them. A sandbox with no CPU limit carries none of the three from its provider. The Dispatcher MUST NOT project a constant `LIVESPEC_TEST_PARALLELISM` into a dispatched sandbox's environment: the sandbox's own CPU limit is the single source of every parallel tool's size, because a constant drifts from the limit the moment the sandbox is resized (the projected 4 was set for 4-CPU sandboxes and outlived their resize to 6). A CPU limit is a CFS quota, not an affinity mask, so without these variables a command in the sandbox sees the node's CPUs: on 2026-11-13 a bare `pytest -n auto` in a 6-CPU, 7630 MiB sandbox on a 32-CPU node started 32 xdist workers of about 230 MiB each and a memory-cgroup OOM killed the agent (bd-ib-vy75ws). With the variables set, a gate run that sizes its test workers from `LIVESPEC_TEST_PARALLELISM`, a bare `pytest -n auto` or `-n logical`, and `nproc` all follow the sandbox's CPU limit, not the node's visible CPUs. A gate run at the CPU-limit worker count MUST stay within the sandbox's memory limit, together with the check aggregate's concurrent targets. The 2026-10-26 measurement bounds the pytest lane: a full per-file-coverage gate run peaked at 2748 MiB of cgroup memory at four workers, with no worker above 467 MiB resident, so six workers hold at most about 2.8 GiB of the 7630 MiB limit; that figure is arithmetic from the per-worker maximum, and a measured gate run at six workers is owed before the Dispatcher's constant is removed (see the rollout order). Scenario 372 in `scenarios.md` exercises these sentences.

Every later sentence of that paragraph (the worker-count resolver's fallback when `LIVESPEC_TEST_PARALLELISM` is unset, and "Scenario 290 in `scenarios.md` exercises these sentences") is unchanged, except that its closing sentence now reads "Scenarios 290 and 372 in `scenarios.md` exercise this paragraph." No `## ` heading is added, changed or removed in `contracts.md`.

**2. `SPECIFICATION/scenarios.md`.** Append, after Scenario 371:

## Scenario 372 — A factory sandbox sizes its parallel tools from its CPU limit

```gherkin
Feature: A factory sandbox hands its CPU limit to the tools that count CPUs
  As the operator of the factory
  I want every parallel tool in a sandbox to size itself from the sandbox's CPU limit
  So that a command on a large node does not start more workers than the sandbox's memory holds

  Scenario: The CPU limit reaches the tools that count CPUs
    Given a factory sandbox with a CPU limit of 6 cores on a node with 32 CPUs
    And the sandbox's spec sets none of LIVESPEC_TEST_PARALLELISM, PYTEST_XDIST_AUTO_NUM_WORKERS and OMP_NUM_THREADS
    When a command in the sandbox runs pytest -n auto, runs nproc, and reads LIVESPEC_TEST_PARALLELISM
    Then pytest-xdist starts 6 workers
    And nproc prints 6
    And LIVESPEC_TEST_PARALLELISM reads 6

  Scenario: A value the sandbox's spec sets wins
    Given a factory sandbox with a CPU limit of 6 cores whose spec sets LIVESPEC_TEST_PARALLELISM to 4
    When a command in the sandbox reads LIVESPEC_TEST_PARALLELISM
    Then it reads 4

  Scenario: The Dispatcher projects no constant parallelism
    Given an item dispatched to a factory
    When the Dispatcher renders the harness shell environment it projects into the sandbox
    Then that environment carries no LIVESPEC_TEST_PARALLELISM entry
```

**2b. `SPECIFICATION/scenarios.md`, Scenario 254, its scenario "The concurrent aggregate stays within the sandbox memory limit".** Replace its Given line

    Given a factory sandbox with a 7630 MiB memory limit and LIVESPEC_TEST_PARALLELISM of 4

with

    Given a factory sandbox with a 7630 MiB memory limit and a 6-core CPU limit, whose LIVESPEC_TEST_PARALLELISM is its CPU limit

so the memory guarantee is stated at the worker count factory sandboxes actually run. The Scenario 254 heading and its other scenarios are unchanged; its first scenario's "Given LIVESPEC_TEST_PARALLELISM is 4" stays, because it fixes an input value rather than a factory's configuration.

Scenario 290 is unchanged: it governs the worker-count resolver's fallback, which still applies wherever `LIVESPEC_TEST_PARALLELISM` is unset (a CI runner, the dev host, or a sandbox with no CPU limit).

**3. `tests/heading-coverage.json`.** Add one entry for the new `## Scenario 372 — A factory sandbox sizes its parallel tools from its CPU limit` heading, with `test` set to `"TODO"` and `reason` "bound by bd-ib-p3g5tp's follow-up: the Dispatcher harness-shell test asserting no LIVESPEC_TEST_PARALLELISM entry, plus the driver's own cluster test in sandbox-driver-kubernetes (tools_that_count_cpus_see_the_pods_cpu_limit)". No entry is removed.

**Rollout order (implementation, not spec text).** The implementation that removes the Dispatcher's `("LIVESPEC_TEST_PARALLELISM", "4")` row from `_HARNESS_SHELL_ENV` (`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_harness_shell_policy.py:140` at master c92c2a6ff) and its pinning tests (`test_dispatcher_overlay_harness_shell_env.py`, `test_dispatcher_harness_settings_file.py`) lands only after two things hold: every configured factory's sandbox provider is at a release that sets the three variables (sandbox-driver-kubernetes v0.8.5 re-pinned on every factory), so no sandbox is ever left with neither source; and a full `just check` aggregate run inside a 6-CPU, 7630 MiB factory sandbox at six workers is measured to peak under the memory limit (the Scenario 254 memory case at the new Given), recorded on bd-ib-p3g5tp. Until that removal ships, the projected 4 reaches the sandbox through its spec and wins over the provider's value, as the new paragraph requires.
