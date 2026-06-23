---
topic: review-gate-routing
author: claude-opus-4-8
created_at: 2026-06-23T04:38:09Z
---

## Proposal: review-gate-routes-green-build-through-review-before-pr

### Target specification files

- scenarios.md

### Summary

Add Scenario 20 codifying the Claude review gate between a green janitor and the PR stage: approve -> PR; a blocking finding -> the implementer (address or reject-with-rationale) -> janitor re-validation -> re-review; and ship-on-cap once the review fix-round cap is reached, because the gate is advisory and must never starve a mechanically-valid change.

### Motivation

The implement-work-item loop's only quality gate was the mechanical janitor (`just check`). Slice A adds a senior-engineer review gate (work-item bd-ib-egms32) to catch correctness and design defects the mechanical suite cannot. livespec governs impl via spec in lockstep, so the shipped review-gate routing behavior must be codified as a scenario rather than left as undocumented graph mechanism.

### Proposed Changes

Add a new scenario to `scenarios.md`, immediately AFTER Scenario 19, verbatim:

## Scenario 20 — Review gate routes a green build through advisory code review before PR

```gherkin
Feature: A senior-engineer review gate reviews a green build before the PR stage
  As the Dispatcher running an unattended implementation loop
  I want a code-review gate between a green janitor and the PR stage
  So that correctness and design defects the mechanical check suite cannot
    catch are surfaced, without ever blocking a mechanically-valid change

  Background:
    Given the janitor gate (the mechanical check suite) is green

  Scenario: An approved review proceeds to the PR stage
    When the review gate reviews the change and raises no blocking findings
    Then the run proceeds to the PR stage

  Scenario: A blocking finding routes back to the implementer and re-validates
    Given the review gate raised at least one blocking finding
    And the review fix-round budget is not yet exhausted
    When the implementer addresses or rejects each blocking finding with a rationale
    Then the change is re-validated by the janitor and reviewed again

  Scenario: A capped-out review ships rather than starving a valid change
    Given the review gate has reached its review fix-round cap
    And the review gate still raises a blocking finding
    Then the run ships to the PR stage anyway
    And the still-blocking finding does not gate the change
```

This codifies the review-gate ROUTING behavior shipped by Slice A (work-item bd-ib-egms32): in the implement-work-item Fabro graph a Claude review node sits between a green `janitor` and the `pr` stage. Its verdict routes the run — approve to `pr`; a blocking finding to a `review_fix` node (which addresses or rejects each finding with a rationale) then back through the janitor for re-validation and re-review; and on reaching the review fix-round cap a still-blocking review falls through to `pr` (ship-on-cap), because the janitor is green and the gate is advisory. This behavior is STABLE and ORTHOGONAL to the per-node provider assignment and dual-credential projection that land in Slice B (bd-ib-g7e34u), so the two do not churn each other.

At revise time, also co-edit `../tests/heading-coverage.json` to add the matching entry (mirroring the v013 Scenario 18/19 deferred-binding pattern), appended to the scenarios array:

{
  "heading": "## Scenario 20 — Review gate routes a green build through advisory code review before PR",
  "spec_root": "SPECIFICATION",
  "spec_file": "scenarios.md",
  "test": "TODO",
  "reason": "Added by the review-gate-routing revise pass (Slice A / bd-ib-egms32). This integration/consumer-tier scenario binds to its real integration-tier test id via the governed propose-change/revise resulting_files[] loop once the review-gate routing test lands; tests/integration/test_workflow_acp_adapter_parameterized.py already pins the review node's adapter input."
}
