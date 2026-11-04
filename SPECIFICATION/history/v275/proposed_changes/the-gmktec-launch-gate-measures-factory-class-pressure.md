---
topic: the-gmktec-launch-gate-measures-factory-class-pressure
author: claude-opus-5-5
created_at: 2026-11-02T06:40:43Z
---

## Proposal: A provisional launcher's shared-node gate measures factory-class pressure, not whole-host idle

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds to contracts.md §"Provisional fleet launch scripts" a clause for a launcher that gates launches on the CPU load of a node the factory shares with CI. Such a gate MUST measure factory-class pressure (the factory namespaces' pods plus system.slice, as a percentage of node CPU), never whole-host idle. The threshold lives in fleet-launch/config.sh and can be overridden through FLEET_LAUNCH_. An unreadable reading holds the launch, and every decision logs its value and the threshold. The section's harness cases are extended to match, and Scenario 296 states the behaviour.

### Motivation

Filed for work-item bd-ib-nmuyjc.6, which the dispatcher refused pre-dispatch at 2026-11-02T06:37:43Z: the item is spec-change tier, its behaviour is only PARTIAL in the spec, and the heading to generalize is ## Provisional fleet launch scripts. The behaviour comes from coordinator legacy-coordinator-agent's ruling of 2026-11-02 (about 02:2xZ, refined about 02:3xZ, recorded on livespec-dev-tooling-6tgd2z): factory admission on a shared node MUST measure the pressure factory work actually competes with, keyed on what a workload IS, not on its QoS class, and CI workflow pods get no CPU limits. Measured on gmktec-xubuntu at about 02:14-02:29Z: whole-host idle fell below 1 percent during CI bursts, and one burstable runner pod reached about 24.7 cores, while factory pods were not starved. The current gmk_green gate in fleet-launch/dispatch-dual.sh holds on mpstat whole-host idle, so a CI burst wrongly holds every gmktec factory launch.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Provisional fleet launch scripts", insert the following paragraph after the paragraph that ends "...MUST log the work-item id it was launching and the queue ticket it held.":

> A `fleet-launch/` launcher MAY gate its launches onto a factory whose node it shares with CI workloads on that node's CPU load. When it does, the gate MUST measure *factory-class pressure*, never whole-host idle. Factory-class pressure is the CPU used over the sample window by two things, as a percentage of the node's CPU capacity:
>
> - pods in the factory namespaces that factory's sandboxes run in;
> - the host's `system.slice`, which holds the k3s agent, the Fabro servers and any resident host service.
>
> The measure is chosen by WHAT a workload is, never by its Kubernetes QoS class: CI workflow pods carry no CPU limits, so a burstable or best-effort CI pod can drive whole-host idle to zero without competing with factory pods for the CPU they request.
>
> The threshold MUST be assigned in `fleet-launch/config.sh` and MUST be overridable by a `FLEET_LAUNCH_` environment variable, like every other host value. A launcher MUST treat the factory as green for this gate only when factory-class pressure is at or below the threshold. Above the threshold it MUST hold the launch. A reading that cannot be taken or parsed MUST hold the launch, and MUST NOT be read as green. Every gate decision MUST log the pressure value the launcher used, or `unknown`, together with the threshold.

In the same section's `check-fleet-launch` harness paragraph, the harness cases MUST additionally cover: treating a shared factory node as green when CI pods drive whole-host idle down while factory-class pressure is at or below the threshold; holding a launch when factory-class pressure is above the threshold; and holding a launch when the reading cannot be taken or parsed.

Append to `SPECIFICATION/scenarios.md`:

## Scenario 296 — The provisional launcher's shared-node gate holds on factory-class pressure, not whole-host idle

Governing clause: `contracts.md` §"Provisional fleet launch scripts".

```gherkin
Feature: a CI burst on a shared factory node does not hold factory launches
  Scenario: CI pods drive whole-host idle down while factory-class pressure stays low
    Given fleet-launch/config.sh values overridden to a stub node reading and throwaway directories
    And the stub reading shows CI workflow pods in non-factory namespaces, burstable or best-effort, taking whole-host idle below the launcher's old idle floor
    And the stub reading shows the factory namespaces plus system.slice using CPU at or below the factory-pressure threshold
    When the launcher evaluates that factory for a ready item
    Then it treats the factory as green and proceeds to that factory's mutex
    And its log names the factory-class pressure value it used and the threshold

  Scenario: factory-class pressure above the threshold holds the launch
    Given a stub node reading whose factory namespaces plus system.slice use CPU above the factory-pressure threshold
    When the launcher evaluates that factory for a ready item
    Then it holds the launch
    And its log names the factory-class pressure value and the threshold that held it

  Scenario: an unreadable reading holds the launch
    Given a stub node reading that cannot be taken or cannot be parsed
    When the launcher evaluates that factory for a ready item
    Then it holds the launch
    And its log names the pressure reading as unknown and the threshold
    And it does not treat the factory as green

  Scenario: the threshold is a declared, overridable host value
    Given the factory-pressure threshold the launcher reads
    When the scripts are searched for where it is assigned
    Then it is assigned only in fleet-launch/config.sh
    And setting its FLEET_LAUNCH_ environment variable before the launcher runs changes the threshold the launcher uses
```

The new `## Scenario 296` heading MUST get a `tests/heading-coverage.json` entry in the same change, `test` "TODO" with a reason naming work-item bd-ib-nmuyjc.6, which owns the harness cases.
