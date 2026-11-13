---
topic: a-new-factory-sandbox-pod
author: claude-opus-5-5
created_at: 2026-11-13T03:00:00Z
---

## Proposal: A new factory sandbox pod is steered off a CPU-pressured factory node

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add one bullet to §"Fabro runtime constraints", **Factory sandbox pods are steered off a CPU-pressured node.** It states the placement the fleet already runs:

- Each factory node publishes its measured CPU pressure.
- When the least-pressured eligible node can fit one more sandbox after the gate queue's reserved CPU, the placement taint `livespec.io/factory-pressure=high:PreferNoSchedule` goes on every eligible node at least the committed gap above it, with a smaller committed release gap keeping an already-tainted node tainted. The taint is preference-only and never makes a pod wait.
- An unknown reading clears the taint everywhere and raises a journal alarm, and a gate quota never read applies no taint.
- Each new sandbox pod is annotated (`livespec.io/placement-pressure`) by the first reconcile cycle that sees it.

The section's scope sentence is widened to cover sandbox placement.

One scenario covers the steer, the release-gap hysteresis, the fallback when the lowest node cannot fit, and the unknown-reading alarm.

### Motivation

Work item bd-ib-plon2p (plan kubernetes-sandbox-backend, epic bd-ib-nmuyjc) was held at the ledger screen on the spec-change tier with this linked topic, because no ratified clause states how a new sandbox pod is placed. legacy-coordinator-agent (session 56ce1bcd) routed it back to this plan as a spec-tier orphan on 2026-11-13.

**Who decides the placement design.** plon2p's 2026-11-07 comment reads "The maintainer decides it", tying it to livespec-dev-tooling-gvo7fa option C. That line is a plan session's relay of a coordinator message, not the maintainer's own words.

- Scope searched for the maintainer's own words reserving the call: plon2p's description and every one of its comments; livespec-dev-tooling-gvo7fa's description and comments; sibling bd-ib-v5uti2's description and comments; and the whole bd-ib-nmuyjc timeline.
- None was found. bd-ib-v5uti2's "a design change for the maintainer" is also session prose.
- Under the coordinator's rule P2 the decision therefore belongs to this plan seat, and it is: specify the design that is ALREADY LIVE, the host-side reconciler with a PreferNoSchedule taint.
- That design was accepted by the coordinator under R301 on 2026-11-04 and shipped through livespec-dev-tooling PR #3344 (6e8f56de).
- Plugin-side pinning, option (a), needs a cluster-scoped read grant for the factory credential, so it is not chosen.
- Lowering the sandbox CPU request was measured on 2026-11-04 and does not pay, because the sandboxes are limit-bound at P75.
- gvo7fa's design C governs GATE placement (livespec-dev-tooling, PR #3802) and reads the same pressure publisher. This proposal governs FACTORY sandbox placement only. Relation: `align`.

**Why.** kube-scheduler scores nodes by CPU requests, and the sandbox pods' hostname spread counts pods. Neither sees actual load, and CI runner pods mostly request no CPU, so a node with most of its CPUs busy looks nearly empty.

- Measured 2026-11-04 from Honeycomb over 80 h, implement-turn wall time per run: the more-loaded node took 1.36x the less-loaded node's time at the median and 1.59x at p90.
- CPU-bound CI per-file-coverage jobs ran 2.0-2.2x slower there.

**Live state, read 2026-11-13 01:36Z.**

- The publisher timer runs on the factory nodes, and the reconciler timer runs on the k3s server.
- The reconciler logged `DECISION steer-to:<node>:fit=25650m readings[...] quota=live taint=<other node>`, and that other node carried `livespec.io/factory-pressure=high:PreferNoSchedule`.
- Every new sandbox pod has carried the `livespec.io/placement-pressure` annotation since 2026-11-05 (recorded on bd-ib-plon2p).
- The value is `FACTORY_PRESSURE_GAP`, in `cpu.some` avg60 points above the lowest eligible node. The script's default is 20. The committed unit (`reconcile-factory-pressure-taint.service`) sets 10, plus `FACTORY_PRESSURE_RELEASE_GAP` 5. The coordinator ruled that on 2026-11-07 because the taint flapped at 20. The clause states a committed gap G and release gap R, set by the committed host provisioning, and plon2p's Definition of Done is amended to match.

In-flight survey (pending proposals and open spec PRs in this repository, 2026-11-13 ~03:30Z):
- `the-factory-graph-gate-validates` replaces the "CI graph-gate binary" bullet of this section, the bullet this proposal follows. This bullet is anchored as the LAST bullet of the section, after that bullet as it stands when this revises. Relation: `align`.
- `sandbox-setup-runs-as-explicit-command-nodes` inserts a bullet after "One non-renewable Petri transition." in this section. Relation: `align`.
- #5108 (`a-commit-time-check-refuses`, bd-ib-nuswku) adds a "Routing-schema command nodes" bullet to this section. Relation: `align`.
- #5084 (`a-fork-test-s-verdict-never`, bd-ib-3edyng) amends the "Fork gate and build venue" bullet of this section. Relation: `align`.
- `an-ended-run-s-kubernetes` governs an ended run's pod, not a new pod's placement. Relation: `independent`.

### Proposed Changes

**1. `constraints.md` §"Fabro runtime constraints", scope sentence.** Replace "These constraints govern which Fabro build the factory is allowed to pin." with:

> These constraints govern which Fabro build the factory is allowed to pin, and how the factory's sandbox pods are placed on the cluster's nodes.

**2. `constraints.md` §"Fabro runtime constraints", new last bullet.** Append as the last bullet of the section (after the "CI graph-gate binary" bullet, as worded when this revises):

> - **Factory sandbox pods are steered off a CPU-pressured node.** This bullet applies where the factory's sandboxes are Kubernetes pods. Each factory node that can take a sandbox pod MUST publish its CPU pressure, the `some` avg60 share of `/proc/pressure/cpu`, at least every 30 seconds. A reconciler on the cluster's server MUST compare the published readings on the same cadence. A node is ELIGIBLE when the sandbox pods' node selector and tolerations admit it and its architecture is the sandboxes' architecture; only eligible nodes are compared.
>
>   On each cycle the reconciler MUST compute, for the eligible node with the lowest reading, its allocatable CPU minus the CPU requested by its Pending and Running pods minus the CPU it reserves for the gate queue. That reserve is the gate queue's unused CPU quota for that node, capped at a committed value where the queue sees the node's topology.
>
>   The placement taint is `livespec.io/factory-pressure=high:PreferNoSchedule`. When that remainder fits one more sandbox's CPU request, a node MUST carry the taint if and only if it is either:
>   - an untainted eligible node whose reading is at least the committed gap G above the lowest; or
>   - a tainted eligible node whose reading is at least the committed release gap R (R <= G) above the lowest.
>
>   No other node may carry the taint. G and R are in `cpu.some` avg60 points. They are set by the committed host provisioning that installs the reconciler, and that committed value governs over any number stated in a work item.
>
>   No node may carry the taint in any of these cases:
>   - the remainder does not fit, in which case the pods' existing spread decides;
>   - no eligible node exists;
>   - the gate queue's quota has never been read.
>
>   When a later read of that quota fails, the reconciler MUST reserve the nominal quota from its last good read. The taint MUST be preference-only. A new sandbox pod that no untainted eligible node can fit MUST still be scheduled on a tainted eligible node rather than stay Pending. Every non-factory workload of the shared pool (CI runner pods, their hook pods and gate jobs) MUST tolerate the taint's key, so the taint steers only factory sandbox pods.
>
>   When any eligible node's reading is absent or older than three publish intervals, the reconciler MUST remove the taint from every node. It MUST then write a journal line at priority `err` that begins `ALARM factory-pressure-steer-disabled` and names each such node, and that cycle MUST end non-zero, so a disabled steer is never silent.
>
>   Each factory sandbox pod MUST carry the annotation `livespec.io/placement-pressure`, set by the first reconcile cycle that sees the pod. It names that cycle's per-node readings, writing `unknown` for any reading that could not be taken, and the cycle's taint decision.
>
>   The reconciler holds no CPU of its own, and nothing in this bullet changes a pod's CPU request or limit.

**3. Scenario (`scenarios.md`).** Add, numbered with the next free number:

## Scenario NN — A new factory sandbox pod is steered off the CPU-pressured node and never waits for it

Given two eligible factory nodes A and B, untainted, whose published CPU pressure readings are 45 and 12, with a committed gap G of 10 and a committed release gap R of 5

And node B's allocatable CPU, less its requested CPU and its capped gate reserve, fits one more sandbox's CPU request

When the reconciler runs a cycle

Then node A MUST carry the `livespec.io/factory-pressure=high:PreferNoSchedule` taint and node B MUST NOT

And a sandbox pod created next MUST carry, after the first reconcile cycle that sees it, the annotation `livespec.io/placement-pressure` naming both readings and the taint decision

Given node A's reading falls to 19, which is under G but at least R above node B's

When the reconciler runs a cycle

Then node A MUST still carry the taint

Given node B's remainder no longer fits one more sandbox's CPU request

When the reconciler runs a cycle

Then no node may carry the taint, and a sandbox pod created next MUST NOT stay Pending while an eligible node fits it

Given node A's reading has not been republished for longer than three publish intervals

When the reconciler runs a cycle

Then no node may carry the taint

And the journal MUST hold a priority-`err` line beginning `ALARM factory-pressure-steer-disabled` that names node A

And a sandbox pod created next MUST be annotated with node A's reading as `unknown`

**4. `tests/heading-coverage.json`.** Add one entry in the same revise for the new scenario heading, with `"test": "TODO"`, `"work_item": "bd-ib-plon2p"`, and a non-empty `reason`. The reason states that the scenario is host-captured and owes a test at the integration tier or above: the reconciler run against a real cluster's nodes and its journal, which no factory sandbox reaches. bd-ib-plon2p's host-captured proof is the evidence until that test exists. Regenerate the heading-coverage debt register in the same commit.
