---
topic: step-span-names-the-sandbox-cluster-node
author: claude-opus-5-5
created_at: 2026-11-01T13:33:34Z
---

## Proposal: A pod-sandboxed run's step and run_turn spans name the cluster node the pod ran on

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Adds one attribute obligation to contracts.md §"Factory step span attributes". When a run's sandbox is a Kubernetes pod, every step span and every run_turn span of that run MUST carry `k8s.node.name`, the name of the cluster node the pod was scheduled on. A run whose sandbox is not a pod carries no such attribute and does not list it as unavailable. Adds Scenario 291 to state the behaviour, and adds its heading-coverage entry.

### Motivation

Plan kubernetes-sandbox-backend (epic bd-ib-nmuyjc) assertion 4 requires that a dispatch executing on a worker node other than the factory host has a run_turn record in Honeycomb naming both the stable factory identity and the node that ran it. Measured 2026-11-01 over the Honeycomb fabro dataset's columns written since 2026-10-25: `livespec.dispatch.factory` is present, but there is no cluster-node dimension (no `k8s.node.name`, no `host.name`). The sandbox-driver-kubernetes plugin reads the pod's spec.node_name only internally. Work item bd-ib-motuct was filed to deliver it. Its intake classification recorded tier spec-change with verdict unstated against this very heading (topic name-the-kubernetes-sandbox-pod), because no clause states the behaviour. Coordinator gitops-fleet-capacity-monitoring ruled on 2026-11-01 that this needs a real ratification rather than a tier release. The attribute name follows the OpenTelemetry Kubernetes semantic convention, so a Honeycomb query can group by node without a mapping table. The obligation is scoped to pod sandboxes because on the Docker backend the sandbox runs on the factory host, and a node value there would be fabricated. Under the section's own rule, a fabricated value is forbidden.

### Proposed Changes

In SPECIFICATION/contracts.md, §"Factory step span attributes", insert the following paragraph immediately BEFORE the paragraph that begins "A value the factory cannot observe MUST be omitted rather than fabricated":

> When a run's sandbox is a Kubernetes pod, every step span of that run, and every `run_turn` span the run's engine exports, MUST additionally carry `k8s.node.name`: the name of the cluster node the pod was scheduled on, as the cluster reports it in the pod's `spec.nodeName`. That is the node `kubectl get pod -o wide` shows for the pod. The value names where the sandbox ran, not where the engine's worker ran. A dispatch whose pod is scheduled on a node other than the factory host therefore names that other node, beside the `livespec.dispatch.factory` value naming the factory. A run whose sandbox is not a Kubernetes pod (for example a Docker container on the factory host) MUST NOT carry `k8s.node.name`, and its omission is not an unobservable value, so it is not named in `fabro.step.unavailable_fields`. When the sandbox IS a pod but its node cannot be read, the attribute follows the unobservable-value rule below.

No other sentence of the section changes. The existing sentence "The receiver allowlist that this orchestrator owns MUST admit every attribute this section names" thereby extends to `k8s.node.name`.

In SPECIFICATION/scenarios.md, append:

## Scenario 291 — A pod-sandboxed run's spans name the cluster node its pod ran on

```gherkin
Feature: Factory spans name the cluster node of a pod sandbox
  As a triager of a factory run on the Kubernetes backend
  I want each span of the run to name the node its sandbox pod ran on
  So that one query shows where every step executed beside which factory dispatched it

  Scenario: A dispatch whose pod is scheduled off the factory host
    Given a factory whose environment selects the Kubernetes sandbox provider
    And a dispatch to that factory whose sandbox pod is scheduled on a cluster node other than the factory host
    When the run's spans are queried in Honeycomb filtered by the run id
    Then every step span and every run_turn span of the run carries k8s.node.name naming the node the pod ran on
    And each of those spans carries livespec.dispatch.factory naming the factory

  Scenario: A Docker-sandboxed run names no cluster node
    Given a factory whose environment selects the Docker sandbox provider
    When a dispatch to that factory runs and its spans are queried by run id
    Then no span of the run carries k8s.node.name
    And no step span names k8s.node.name in its unavailable fields
```

In tests/heading-coverage.json, add one entry for the new heading:

{"heading": "## Scenario 291 — A pod-sandboxed run's spans name the cluster node its pod ran on", "spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "test": "TODO", "reason": "An integration-tier test is owed for this heading: the exercising proof is a host-captured Honeycomb query over spans from a real Kubernetes-backend factory dispatch whose pod ran off the factory host; owned by work-item bd-ib-motuct (run_turn spans), with the step-span half riding livespec-dev-tooling-ipcm33.", "work_item": "bd-ib-motuct"}

No `## ` heading is added to or removed from contracts.md, so no other heading-coverage entry changes.
