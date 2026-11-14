---
topic: sandbox-driver-sizes-test-parallelism
author: claude-opus-5-5 (kubernetes-sandbox-backend seat)
created_at: 2026-11-14T00:50:16Z
---

## Proposal: A factory sandbox's CPU limit sizes every parallel tool, and the Dispatcher projects no constant

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Move the source of a factory sandbox's test parallelism from the Dispatcher's constant LIVESPEC_TEST_PARALLELISM=4 projection to the sandbox's own CPU limit. The sandbox provider sets LIVESPEC_TEST_PARALLELISM, PYTEST_XDIST_AUTO_NUM_WORKERS and OMP_NUM_THREADS to that limit, and a value the sandbox's spec sets wins. Once every factory's provider does this, the Dispatcher stops projecting a constant. Adds Scenario NNN with its heading-coverage entry and its regenerated debt-register row.

### Motivation

Two defects, one cause.

(1) The projected constant has drifted. It was set to 4 for 4-CPU factory sandboxes (bd-ib-z7qrnd, spec v223), and the sandboxes now carry a 6-CPU limit. A constant cannot track a resize; the sandbox's own limit can.

(2) The projection covers only tools that read LIVESPEC_TEST_PARALLELISM. A CPU limit is a CFS quota, not an affinity mask, so any tool that sizes itself from the CPU count sees the node's CPUs. Measured on 2026-11-13, bd-ib-vy75ws run 01M7AFVCPSK2GT0W2SWXP3258Z on gmktec-xubuntu (32 CPUs):
- the agent ran `uv run pytest -q -n auto tests` in a 6-CPU, 7630 MiB sandbox;
- xdist started 32 workers of about 230 MiB each;
- at 14:12:34Z a memory-cgroup OOM killed codex, the agent's app-server;
- the run idled until its 2 h stall watchdog cancelled it.
bd-ib-yq4x4g recorded the same `-n auto` shape at 70-72 workers on poweredge in October.

The sandbox provider already knows each sandbox's CPU limit. So it is the one place that can size every parallel tool, in every factory, image and repository, from the real number. sandbox-driver-kubernetes PRs #21 and #23 (bd-ib-p3g5tp) implement the provider half; #23 makes a zero limit set nothing. This proposal ratifies the contract and retires the Dispatcher's constant, so there is one source. legacy-coordinator-agent (session 719514f8, 2026-11-14) ruled the route and asked for this proposal as a draft for grade; this revision applies that grade's six fixes.

### Proposed Changes

**1. `SPECIFICATION/contracts.md`, `## Dispatcher policy settings` → `### Sandbox test-worker parallelism`, first paragraph.** Replace these five sentences, verbatim:

> The Dispatcher MUST project `LIVESPEC_TEST_PARALLELISM` into every dispatched sandbox's environment, beside the harness shell policy it already projects there. The value MUST be a positive integer that does not exceed the CPU limit of the sandbox it is projected into. This repository projects 4, for its 4-CPU factory sandboxes. Four workers fit the sandbox's 7630 MiB memory limit: measured on 2026-10-26, a full per-file-coverage gate run at four workers peaked at 2748 MiB of cgroup memory, with no worker above 467 MiB resident. A gate run in the sandbox that sizes its test workers from this variable therefore follows the sandbox's CPU limit, not the node's visible CPUs.

with:

> A factory sandbox's environment MUST carry `LIVESPEC_TEST_PARALLELISM`, `PYTEST_XDIST_AUTO_NUM_WORKERS` and `OMP_NUM_THREADS`, each equal to the sandbox's CPU limit in whole cores, unless the sandbox's spec already sets that variable, in which case the spec's value MUST reach the sandbox unchanged. The sandbox's CPU limit in whole cores is the integer `resources.cpu_cores` of the sandbox's resources. A limit of 0 sets none of the three, and neither does a sandbox with no CPU limit. The sandbox's spec is the environment the engine passes the sandbox provider when it creates the sandbox, which is the Dispatcher's `[environments.<id>.env]` table. The sandbox provider sets the three variables from the CPU limit it applies to the sandbox. For the Kubernetes provider that is sandbox-driver-kubernetes v0.8.5 and later, which writes them into the sandbox container's environment, so every command executed in the sandbox inherits them. Once every configured factory's sandbox provider is at a release that sets them (for the Kubernetes provider, sandbox-driver-kubernetes v0.8.5 or later), the Dispatcher MUST NOT project a constant `LIVESPEC_TEST_PARALLELISM` into a dispatched sandbox's environment. Until then it MAY keep projecting one, and while it does, the spec's value wins for `LIVESPEC_TEST_PARALLELISM` only, while `PYTEST_XDIST_AUTO_NUM_WORKERS` and `OMP_NUM_THREADS` take the CPU limit. The sandbox's own CPU limit is to be the single source of every parallel tool's size, because a constant drifts from the limit the moment the sandbox is resized: the projected 4 was set for 4-CPU sandboxes and outlived their resize to 6. On 2026-11-13, a bare `pytest -n auto` in a 6-CPU, 7630 MiB sandbox on a 32-CPU node started 32 xdist workers of about 230 MiB each, and a memory-cgroup OOM killed the agent (bd-ib-vy75ws). With the variables set, three things follow the sandbox's CPU limit rather than the node's visible CPUs: a gate run that sizes its test workers from `LIVESPEC_TEST_PARALLELISM`, a bare `pytest -n auto` or `-n logical`, and `nproc`. A gate run at the CPU-limit worker count MUST stay within the sandbox's memory limit, together with the check aggregate's concurrent targets. The 2026-10-26 measurement bounds the pytest lane. A full per-file-coverage gate run at four workers peaked at 2748 MiB of cgroup memory, with no worker above 467 MiB resident, so about 880 MiB of that peak was held besides the workers. Six workers therefore come to roughly 3682 MiB (about 3.6 GiB) of the 7630 MiB limit. That figure is arithmetic, not a measurement: a measured gate run at six workers is owed before the Dispatcher's constant is removed (see the rollout order). Delegated gate-Job pods, rendered by livespec-dev-tooling's gate Job template, are not created by the sandbox provider and are not governed by this paragraph; their twin is livespec-dev-tooling-3yj6kx. Scenario NNN in `scenarios.md` exercises these sentences.

Every later sentence of that paragraph is unchanged: the worker-count resolver's fallback when `LIVESPEC_TEST_PARALLELISM` is unset, and its closing sentence. That closing sentence now reads "Scenarios 290 and NNN in `scenarios.md` exercise this paragraph."

**1b. `SPECIFICATION/contracts.md`, same subsection, the paragraph that follows the one ending "Scenario 254 in `scenarios.md` exercises this paragraph."** Replace it whole, verbatim:

> The reason is that a sandbox's CPU limit is a quota, not an affinity mask, so `nproc` inside the sandbox reports every CPU on its node. On 2026-10-25, a gate run in a 4-CPU, 7630 MiB factory pod on a 72-CPU node derived 18 coverage-traced test workers from `nproc`. Six such runs were killed by the pod's memory limit in one day. The projection does not bound a worker count that an agent names explicitly on a command line.

with:

> The reason is that a sandbox's CPU limit is a quota, not an affinity mask, so without the variables above `nproc` inside the sandbox reports every CPU on its node. On 2026-10-25, a gate run in a 4-CPU, 7630 MiB factory pod on a 72-CPU node derived 18 coverage-traced test workers from `nproc`. Six such runs were killed by the pod's memory limit in one day. These variables do not bound a worker count an agent names explicitly, such as `-n 32`.

No `## ` heading is added, changed or removed in `contracts.md`.

**2. `SPECIFICATION/scenarios.md`.** Append it as the last scenario, numbered NNN. NNN is the next free scenario number when the revise is cut: 372 goes to the v374 revise (`a-stale-preserved-seed-is`), so NNN is at least 373. Every `NNN` in this proposal, including the heading-coverage and debt-register rows below, takes that one number.

## Scenario NNN — A factory sandbox sizes its parallel tools from its CPU limit

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
    When a command in the sandbox reads LIVESPEC_TEST_PARALLELISM and runs pytest -n auto
    Then LIVESPEC_TEST_PARALLELISM reads 4
    And pytest-xdist starts 6 workers

  Scenario: The Dispatcher projects no constant parallelism once every provider sizes the sandbox
    Given every configured factory's sandbox provider sets the three CPU-sized variables
    And an item dispatched to a factory
    When the Dispatcher renders the harness shell environment it projects into the sandbox
    Then that environment carries no LIVESPEC_TEST_PARALLELISM entry
```

**2b. `SPECIFICATION/scenarios.md`, Scenario 254, its scenario "The concurrent aggregate stays within the sandbox memory limit".** Replace its Given line

    Given a factory sandbox with a 7630 MiB memory limit and LIVESPEC_TEST_PARALLELISM of 4

with

    Given a factory sandbox with a 7630 MiB memory limit and a 6-core CPU limit, whose LIVESPEC_TEST_PARALLELISM is its CPU limit

This states the memory guarantee at the worker count factory sandboxes actually run. The Scenario 254 heading and its other scenarios are unchanged. Its first scenario's "Given LIVESPEC_TEST_PARALLELISM is 4" stays, because it fixes an input value rather than a factory's configuration.

Scenario 290 is unchanged. It governs the worker-count resolver's fallback, which still applies wherever `LIVESPEC_TEST_PARALLELISM` is unset: a CI runner, the dev host, or a sandbox with no CPU limit or a zero one.

**3. `tests/heading-coverage.json`: add the new heading in the same revise.** The revise that ratifies this MUST add one entry, using the heading as numbered at revise:

```json
{"heading": "## Scenario NNN — A factory sandbox sizes its parallel tools from its CPU limit", "spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "test": "TODO", "work_item": "bd-ib-p3g5tp", "reason": "A test at the integration tier or above is owed, delivered by bd-ib-p3g5tp's follow-up. The cluster tier is the driver's own kind-cluster test in sandbox-driver-kubernetes (tools_that_count_cpus_see_the_pods_cpu_limit), which proves nproc and the variables at the pod's CPU limit. The integration tier here is the Dispatcher harness-shell test asserting no LIVESPEC_TEST_PARALLELISM entry once every factory's provider sizes the sandbox."}
```

No entry is removed.

**4. `tests/heading-coverage-debt.json`: regenerate it in the same revise.** The register is generated, never authored by hand. The revise MUST regenerate it with `uv run python -m livespec_dev_tooling.heading_coverage_debt` and stage the result. The generated row is expected to read:

```json
{"spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "heading": "## Scenario NNN — A factory sandbox sizes its parallel tools from its CPU limit", "work_item": "bd-ib-p3g5tp", "first_seen": "<revise date>"}
```

The heading-coverage map changes in lockstep with the one new `## ` heading, per AGENTS.md §"Revise co-edit discipline".

**Rollout order (implementation, not spec text).** One implementation removes the Dispatcher's `("LIVESPEC_TEST_PARALLELISM", "4")` row from `_HARNESS_SHELL_ENV`, at `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_harness_shell_policy.py:140` at master c92c2a6ff. It also updates the tests that pin that row: `test_dispatcher_overlay_harness_shell_env.py` and `test_dispatcher_harness_settings_file.py`. It lands only after two things hold:

1. Every configured factory's sandbox provider is at a release that sets the three variables, meaning sandbox-driver-kubernetes v0.8.5 re-pinned on every factory. This is the condition under which the new paragraph's MUST NOT applies, and it means no sandbox is ever left with neither source.
2. A full `just check` aggregate run inside a 6-CPU, 7630 MiB factory sandbox at six workers is measured to peak under the memory limit, which is the Scenario 254 memory case at its new Given. The measurement is recorded on bd-ib-p3g5tp.

Until that removal ships, the projected 4 reaches the sandbox through its spec. So during rollout only `LIVESPEC_TEST_PARALLELISM` stays at 4, while `PYTEST_XDIST_AUTO_NUM_WORKERS` and `OMP_NUM_THREADS` take the CPU limit, as the new paragraph's spec-wins rule provides.
