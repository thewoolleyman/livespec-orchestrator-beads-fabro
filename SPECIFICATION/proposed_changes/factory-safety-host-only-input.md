---
topic: factory-safety-host-only-input
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T23:21:28Z
---

## Proposal: A fourth factory_safety reason, needs-host-only-input

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The closed `factory_safety` enum names three reasons an item cannot run in a sandbox, and none fits an item whose authoritative INPUT exists only on the host, such as a gitignored host file or a host-local review verdict. Such an item stays factory-eligible, and its dispatch searches the sandbox, finds no legitimate source, and stops having produced nothing. This proposal adds a fourth reason, `needs-host-only-input`: the item's authoritative input is reachable only on the host and cannot be committed to, or fetched into, the sandbox. It host-routes the item exactly as the other three reasons do.

### Motivation

Work-item bd-ib-fv4w. On 2026-08-12, overseer-pfpfty.8 in livespec-overseer took as its input a 782-line review verdict on a gitignored host path. None of the three reasons fit, and choosing one anyway would record a false reason on a typed field. The item's second finding, that `set-admission:<id>:manual` does not hold an item already in `ready`, is correct per the ratified rule that a policy dial is valid only while its decision is still ahead of the item, and it is not changed here. Plan spec-implementation-lockstep R1 batch 10 routes the item here.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Work-item beads-issue mapping", bullet `factory_safety`:
- extend the label form to `factory-safety:<needs-host-secrets|mutates-host-machinery|needs-privileged-host|needs-host-only-input>`;
- replace "The three reasons name work" with "The four reasons name work";
- after the `needs-privileged-host` definition, add: "and `needs-host-only-input` (the item's authoritative input — a file, verdict or state it must read — exists only on the host and cannot be committed to the repository or fetched into the sandbox; an input that CAN be committed is not this reason, and committing it is the remedy)".

In the same file, update every enumeration of the three reasons to include `needs-host-only-input`: the `set-factory-safety` action grammar in the drive action list, the "`set-factory-safety:<id>:<...>`" heading and its body ("one of the three canonical `factory_safety` values" becomes "one of the four"), and the human-valve action list. tests/heading-coverage.json MUST rename the entry for the renamed heading in the same revise.

In SPECIFICATION/scenarios.md, in the scenario "set-factory-safety requires one of the three canonical factory_safety reasons", rename it to "set-factory-safety requires one of the four canonical factory_safety reasons" and extend its refusal line to list `needs-host-only-input`. Add at the end of the file (tests/heading-coverage.json MUST gain an entry in the same revise):

## Scenario 230 — An item whose input exists only on the host is host-routed

```gherkin
Feature: Host-only input is an honest factory_safety reason
  As an operator filing work whose authoritative input lives only on the host
  I want a factory_safety reason that says so
  So that the item is host-routed instead of dispatched into a sandbox that cannot read its input

  Scenario: needs-host-only-input host-routes the item
    Given a ready work-item whose authoritative input is a gitignored host file
    When the operator invokes set-factory-safety:<work-item-id>:needs-host-only-input
    Then the item's factory_safety is needs-host-only-input and its lifecycle status is unchanged
    And the Dispatcher refuses to dispatch it to a factory and names the reason
```
