---
topic: sandbox-test-worker-parallelism
author: claude-opus-5-5
created_at: 2026-10-25T17:28:00Z
---

## Proposal: Project a bounded test-worker parallelism into every sandbox

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The Dispatcher projects LIVESPEC_TEST_PARALLELISM into every dispatched sandbox's environment, with a value no greater than the sandbox's CPU limit (2 for the 4-CPU factory sandboxes), so a gate's test-worker count follows the sandbox's CPU limit rather than the node's visible CPUs.

### Motivation

Fleet coordinator ruling (gitops-fleet-capacity-monitoring, 2026-10-25, ruling (a) for work-item bd-ib-yq4x4g). The factory's leading infrastructure ending, 'the sandbox became unreachable', was measured as a memory-cgroup OOM kill: in six runs on 2026-10-25, gate runs in 4-CPU, 7630 MiB factory pods on the 72-CPU node poweredge-xubuntu started 18 coverage-traced pytest-xdist workers from nproc/4, because nproc inside a pod reports the node's CPUs. No spec heading governs the sandbox's test-worker parallelism, so the fix item cannot cite one. The clause is a ### subsection inside the existing H2 '## Dispatcher policy settings', with no new scenario, because a new scenario H2 would need an exercising test before the implementation exists. The implementing work-item references that H2.

### Proposed Changes

In SPECIFICATION/contracts.md, inside section '## Dispatcher policy settings', insert this subsection immediately before '### Factory addresses resolved from a host registry':

### Sandbox test-worker parallelism

The Dispatcher MUST project `LIVESPEC_TEST_PARALLELISM` into every dispatched sandbox's environment, beside the harness shell policy it already projects there. The value MUST be a positive integer that does not exceed the CPU limit of the sandbox it is projected into. This repository projects 2, for its 4-CPU factory sandboxes. A gate run in the sandbox that sizes its test workers from this variable therefore follows the sandbox's CPU limit, not the node's visible CPUs.

The reason is that a sandbox's CPU limit is a quota, not an affinity mask, so `nproc` inside the sandbox reports every CPU on its node. On 2026-10-25, a gate run in a 4-CPU, 7630 MiB factory pod on a 72-CPU node derived 18 coverage-traced test workers from `nproc`. Six such runs were killed by the pod's memory limit in one day. The projection does not bound a worker count that an agent names explicitly on a command line.


