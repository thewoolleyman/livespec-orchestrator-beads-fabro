---
topic: incident-carrier-pr-binding-and-transfer-refusal
author: claude:expedited-incident-response-flag
created_at: 2026-11-05T08:07:29Z
---

## Proposal: Carrier PR binding applies once pr-bound, and the factory-transfer refusal has its own scenario

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Two follow-ups to the v302 incident first-authority and pre-PR carrier amendment, both from its independent ratification review. First, the older `## Expedited incident lifecycle` sentence requiring each attempt to bind its "carrier PR" is qualified to apply once the carrier is `pr-bound`, so it reads consistently with the `branch-reserved` and `head-published` states. Second, the factory-transfer refusal gets a dedicated scenario: incident entry refuses when the installed all-writer capability cannot provide the exclusion.

### Motivation

The independent sonnet ratification reviewer of v302 (bd-ib-dzbwaq, NO BLOCKERS at 2026-11-05T07:00:33Z) raised two non-blocking notes. (1) The pre-existing sentence "Each attempt MUST bind its repository, immutable operation id, attempt id, phase/generation, exact base/head, carrier PR, ..." is overridden only by implication: v302's discriminated-state carrier text is more specific, and `branch-reserved` and `head-published` have no PR number. A reader could take the older sentence to forbid the pre-PR states. (2) `### Factory transfer and recovery of the initial operation` says incident entry MUST refuse when the installed all-writer capability cannot exclude stale factory writers. Only the genesis capability refusal has a scenario; the factory-transfer scenario covers the success path. legacy-coordinator-agent directed, under R301 on 2026-11-05, that both be filed as ONE follow-up proposal under bd-ib-dzbwaq rather than folded into v302.

### Proposed Changes

In `contracts.md` §"Expedited incident lifecycle", amend the attempt-binding sentence so its carrier PR element is conditional on the carrier state:

```diff
-Each attempt MUST bind its repository, immutable operation id, attempt id, phase/generation, exact base/head, carrier PR, complete landed commit/tree identities and cumulative original scope.
+Each attempt MUST bind its repository, immutable operation id, attempt id, phase/generation, exact base/head, carrier identity (including its real PR once the carrier is `pr-bound`, per §"Carrier identity before and after PR creation"), complete landed commit/tree identities and cumulative original scope.
```

No other clause changes. A `branch-reserved` or `head-published` attempt MUST NOT be read as violating the binding rule for lacking a PR number, and a `pr-bound` attempt MUST still bind the exact positive PR number.

In `scenarios.md`, under `## Scenario: incident entry owns one initial authority before a carrier PR exists`, append one gherkin scenario to its feature block:

```gherkin
  Scenario: Missing all-writer exclusion refuses factory takeover instead of claiming a fence
    Given the item has a current queued or live factory claim
    And the installed provider cannot conditionally invalidate that claim for every applicable writer
    When authorized incident entry requests host ownership
    Then incident entry MUST refuse with a named capability refusal
    And it records no host ownership, reports no cancelled or fenced factory run and performs no incident effect
    And the factory claim and its run history remain unchanged
```

No H2 heading is added or removed, so heading coverage is unchanged.
