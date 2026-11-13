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
- When the least-pressured eligible node can fit one more sandbox after the gate queue's reserved CPU, every eligible node at least a committed gap above it gets a preference-only placement taint. The taint never makes a pod wait.
- An unknown reading clears the taint everywhere and raises an alarm.
- Each new sandbox pod names the readings its placement used.

One scenario covers the steer, the fallback when the lowest node cannot fit, and the unknown-reading case.

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
- The committed gap is 10 points with a 5-point release hysteresis (`reconcile-factory-pressure-taint.service`). plon2p's Definition of Done says 20. The clause therefore states "a committed gap", and the value stays an operator setting in livespec-dev-tooling.

In-flight survey (pending proposals in this repository, 2026-11-13 ~03:00Z, grepped for "sandbox pod", "placement" and "taint"): no pending proposal states factory sandbox pod placement. `an-ended-run-s-kubernetes` governs an ended run's pod, not a new pod's placement. Relation: `independent`.

### Proposed Changes

**1. `constraints.md` §"Fabro runtime constraints".** Append after the bullet that begins "**CI graph-gate binary.**":

> - **Factory sandbox pods are steered off a CPU-pressured node.** Where the factory's sandboxes are Kubernetes pods, each factory node that can take a sandbox pod MUST publish its CPU pressure (the `some` avg60 share of `/proc/pressure/cpu`) at least every 30 seconds, and a reconciler on the cluster's server MUST compare the published readings on the same cadence. A node is ELIGIBLE when the sandbox pods' node selector and tolerations admit it and its architecture is the sandboxes' architecture; only eligible nodes are compared. On each cycle the reconciler MUST compute, for the eligible node with the lowest reading, its allocatable CPU minus the CPU requested by its Pending and Running pods minus the CPU it reserves for the gate queue. That reserve is the gate queue's unused CPU quota for that node, capped at a committed value where the queue sees the node's topology. When that remainder fits one more sandbox's CPU request, every eligible node whose reading is at least a committed gap above the lowest MUST carry a `PreferNoSchedule` placement taint, and no other node may carry it. When the remainder does not fit, no node may carry the taint, and the pods' existing spread decides. The taint MUST be preference-only: a new sandbox pod that no untainted eligible node can fit MUST still be scheduled on a tainted eligible node rather than stay Pending. When any eligible node's reading is absent or older than three publish intervals, the reconciler MUST remove the taint from every node and MUST raise an alarm naming each such node, so a disabled steer is never silent. Each new sandbox pod MUST carry an annotation naming the cycle's per-node readings and taint decision, or naming a reading `unknown` when it could not be taken. The reconciler holds no CPU of its own, and nothing in this bullet changes a pod's CPU request or limit.

**2. Scenario (`scenarios.md`).** Add, numbered with the next free number:

## Scenario NN — A new factory sandbox pod avoids the CPU-pressured node and never waits for it

Given two eligible factory nodes A and B, whose published CPU pressure readings are 45 and 12, and a committed gap of 10

And node B's allocatable CPU, less its requested CPU and its capped gate reserve, fits one more sandbox's CPU request

When the reconciler runs a cycle

Then node A MUST carry the `PreferNoSchedule` placement taint and node B MUST NOT

And a sandbox pod created next MUST be scheduled on node B, and MUST carry an annotation naming both readings and the taint decision

Given node B's remainder no longer fits one more sandbox's CPU request

When the reconciler runs a cycle

Then no node MUST carry the placement taint, and a sandbox pod created next MUST NOT stay Pending while an eligible node fits it

Given node A's reading has not been republished for longer than three publish intervals

When the reconciler runs a cycle

Then no node MUST carry the placement taint, the reconciler MUST raise an alarm naming node A, and a sandbox pod created next MUST carry an annotation naming node A's reading `unknown`

**3. `tests/heading-coverage.json`.** Add one entry in the same revise for the new scenario heading, with `"test": "TODO"`, `"work_item": "bd-ib-plon2p"`, and a non-empty `reason`. The reason states that the scenario is host-captured: it needs the live cluster's nodes and the reconciler's journal, which no factory sandbox reaches, so bd-ib-plon2p's host-captured proof is its evidence until a cluster-level test exists.
