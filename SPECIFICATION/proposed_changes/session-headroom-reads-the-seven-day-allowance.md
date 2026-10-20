---
topic: session-headroom-reads-the-seven-day-allowance
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T18:07:34Z
---

## Proposal: Session-headroom admission also reads the seven-day allowance, skips an exhausted one, and journals it

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

"Admission filters candidates by projected Claude session headroom" reads only the provider's five-hour session utilization. A Claude account can have five-hour headroom while its SEVEN-DAY allowance is exhausted, so admission dispatches into a certain refusal. This proposal adds the seven-day reading from the same provider response. A covered candidate whose seven-day status reports the weekly allowance exhausted is skipped exactly as one below the five-hour floor, and per-node selection continues to the next eligible candidate. The assessment journal carries the seven-day utilization beside the five-hour one. An absent or unparseable seven-day reading never skips a candidate. A projected weekly exhaustion is not added here; it would need a separate threshold.

### Motivation

Work-items bd-ib-u3jq5r (spec-change tier; its deliverable is this proposal) and bd-ib-jtlyoj. On 2026-10-15 a one-token Messages call with the factory token returned anthropic-ratelimit-unified-7d-utilization 0.95 with status allowed_warning, so the next cliff was the seven-day window, which the five-hour floor cannot see. On 2026-10-20 this plan's own host-side Definition-of-Done preflight hit "You've hit your weekly limit" on the wrapped Claude account. bd-ib-2n2s7b (five-hour threshold disagreement with the caam loop) is adjacent, not overlapping. The pending proposal session-headroom-carried-drain-rate amends the five-hour projection, which this leaves unchanged. Plan spec-implementation-lockstep R1 batch 7 routes both items here as one amendment of the headroom clause.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Provider spend containment", paragraph "**Admission filters candidates by projected Claude session headroom.**", insert immediately AFTER the sentence "It MUST read the provider's five-hour session utilization using the exact credential snapshot that the dispatch would project." the following sentences:

> From the same provider response it MUST also take the seven-day utilization and the seven-day status where the provider reports them. A covered candidate whose seven-day status reports the weekly allowance exhausted MUST be skipped exactly as a candidate below the floor is, and per-node selection MUST continue to the next eligible candidate. An absent or unparseable seven-day reading MUST NOT skip a candidate. The journal record of each assessment MUST carry the seven-day utilization percentage, or an explicit unobservable result, beside the five-hour figures. Scenario 228 in `scenarios.md` exercises these sentences.

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 228 — Admission skips a Claude candidate whose seven-day allowance is exhausted

```gherkin
Feature: A weekly-exhausted account is never dispatched into a refusal
  As an operator running Claude-routed factory nodes
  I want admission to read the seven-day allowance beside the five-hour one
  So that a run is not launched on an account the provider will refuse

  Scenario: A seven-day exhaustion skips the candidate
    Given a covered claude-acp candidate whose five-hour headroom is above the floor
    And the same provider response reports the seven-day allowance exhausted
    When admission assesses the candidate
    Then the candidate is skipped and selection continues to the next eligible candidate
    And the journal records the seven-day utilization beside the five-hour figures

  Scenario: An absent seven-day reading skips nothing
    Given a covered claude-acp candidate above the five-hour floor
    And the provider response carries no seven-day reading
    When admission assesses the candidate
    Then the candidate is not skipped and the journal records the seven-day reading as unobservable
```

