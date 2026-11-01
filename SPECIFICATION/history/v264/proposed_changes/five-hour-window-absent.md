---
topic: five-hour-window-absent
author: claude-opus-5-5
created_at: 2026-11-01T04:09:13Z
---

## Proposal: An absent five-hour window means no five-hour limit, not an unobservable reading

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md §"Provider spend containment" → "Admission filters candidates by projected Claude session headroom" so that a five-hour window ABSENT from a successfully answered, authenticated usage response means the provider reports no five-hour limit for that credential: with a positive floor the slot passes the floor, no drain rate or projection is attempted (`not-projected`, reason `five-hour-window-absent`), the seven-day status still governs it, it ranks below every qualifying slot with a measured or carried projection, and the journal names the absent window distinctly as `five-hour-window-absent`. A present-but-malformed or out-of-range figure and every transport-failed, authentication-failed, timed-out or refused (non-2xx) response stay unobservable and floor-skip exactly as today. Scenario 231 is named beside a new Scenario 288 that exercises the absent window; one `## ` heading is added.

### Motivation

STOP-THE-LINE from the fleet coordinator (gitops-fleet-capacity-monitoring), 2026-11-01: the factory has dispatched nothing since about 01:35Z. Every launch is refused pre-run with "no candidate remains for admission-required ACP nodes dod_gate, proof_capture, proof_verify, disposition, review_fix" and governing_condition=session-headroom-shortfall. Measured in this repository's dispatch journal at 2026-11-01T03:43:16Z: every pool slot (CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_0, __ANTHROPIC_1, and the rest) journaled `unobservable: unreadable-utilization`, `unverified_provider_reset_claim: null`, and `not_chosen_reason: floor-skip`, while the SAME response's seven-day block read `status: allowed` with utilization 2.0 and 0.0. The provider answered, the credential authenticated, and the weekly window was reported — only the five-hour window is gone from the response (the provider now reports `five_hour: null` for every account). Re-measured directly at about 05:10Z on slot CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_0 with the exact request `_dispatcher_session_headroom_io` sends: HTTP 200 carrying `anthropic-ratelimit-unified-status: allowed`, `-representative-claim: seven_day`, `-7d-status: allowed`, `-7d-utilization: 0.02`, `-7d-reset`, `-reset` and the overage trio, and NO `anthropic-ratelimit-unified-5h-*` header of any kind. The current clause classifies a missing five-hour figure as unobservable, and "With a positive floor, a covered candidate is skipped ... when ... its reading is unobservable", so with the default floor of 20 in every repository every slot is floor-skipped and the factory is idle on accounts with almost their whole allowance remaining. The clause's unobservable rule exists so a FAILURE TO MEASURE is never read as headroom; a successful, authenticated answer that reports no five-hour window is not a failure to measure — it is the provider stating there is no five-hour limit to measure. Precedent: caam hit the same shape and livespec-overseer item overseer-yizu3e fixed it (livespec-overseer 5.43.0, merge 3798347e, "feat: name absent caam short window") by treating an absent short window as "no short-window limit" and naming it distinctly. Changing any repository's floor is explicitly out of scope; that is a separate maintainer decision.

### Proposed Changes

### contracts.md — §"Provider spend containment", paragraph "Admission filters candidates by projected Claude session headroom"

1. Replace the sentence "With a positive floor, a slot QUALIFIES when its reading is valid, its remaining headroom is not strictly below the floor, its seven-day status is not exhausted, and its projection does not call for a projection skip." with:

> With a positive floor, a slot QUALIFIES when either its reading is valid and its remaining headroom is not strictly below the floor, or its five-hour window is absent as defined below; and, in both cases, its seven-day status is not exhausted and its projection does not call for a projection skip.

2. Replace the sentence "A slot whose projection is unavailable qualifies by the fail-open rule below, but ranks below every qualifying slot whose projection was measured or carried." with:

> A slot whose projection is unavailable qualifies by the fail-open rule below, and a slot whose five-hour window is absent qualifies by the absent-window rule below; each ranks below every qualifying slot whose projection was measured or carried.

3. Replace the sentence "Scenario 231 in `scenarios.md` exercises these sentences." with:

> Scenario 231 in `scenarios.md` exercises these sentences, and Scenario 288 exercises them for a slot whose five-hour window is absent.

4. Replace the sentence "Missing, malformed, out-of-range, transport-failed, authentication-failed, or timed-out readings are unobservable and MUST be journaled as such, never coerced to a numeric reading." with:

> Except for an absent five-hour window as defined in the next sentences, missing, malformed, out-of-range, transport-failed, authentication-failed, or timed-out readings are unobservable and MUST be journaled as such, never coerced to a numeric reading. The five-hour window is ABSENT when the bounded usage request was answered successfully by the provider with the projected credential authenticated (for Claude, a 2xx response to the usage request) and that response reports no five-hour window at all (for Claude, it carries no `anthropic-ratelimit-unified-5h-utilization` header): the provider is then reporting no five-hour limit for that credential, which is not a failure to measure. An absent window MUST NOT be coerced to a numeric reading and MUST NOT be journaled or treated as unobservable. With a positive floor, a slot whose five-hour window is absent MUST pass the floor; no drain rate and no projection MUST be attempted for it, and its projection result MUST be `not-projected` with the reason `five-hour-window-absent`; its seven-day status MUST still govern it exactly as it governs any other slot, so a seven-day status of `rejected` MUST still yield a seven-day skip; and it MUST rank as a slot carrying no reset instant and no measured or carried projection. The journal record of the assessment MUST name the absent window distinctly, as `five-hour-window-absent`, never as an unobservable result and never as a numeric figure. A five-hour figure that is present but malformed or out of range, and every transport-failed, authentication-failed, timed-out or refused (non-2xx) response, MUST remain unobservable even when that response carries no five-hour figure. This mirrors the caam handling of an absent short window (livespec-overseer item overseer-yizu3e).

5. In the projection-result enumeration, replace "or an explicit `not-projected` result when no projection was attempted because the floor is 0, the reading was skipped by the floor, or the reading was unobservable." with:

> or an explicit `not-projected` result when no projection was attempted because the floor is 0, the reading was skipped by the floor, the reading was unobservable, or the five-hour window was absent.

Every other sentence of the paragraph, including the default floor of **20**, is unchanged.

### scenarios.md — new heading

Append, after the last scenario heading, a new scenario `## Scenario 288 — An absent five-hour window is no five-hour limit, and the seven-day status still governs`:

```gherkin
Feature: A provider response with no five-hour window does not idle the factory
  As an operator running Claude-routed factory nodes
  I want admission to read an absent five-hour window as no five-hour limit
  So that the factory is not refused on accounts the provider still serves

  Background:
    Given dispatcher.session_headroom_floor_percent is 20
    And an item whose admission-required node's candidate is covered by the admission session-headroom clause
    And every other admission-valve condition is satisfied

  Scenario: An authenticated 2xx response with no five-hour window qualifies the slot
    Given the usage request for the only pool slot is answered with a 2xx status
    And the response carries no five-hour utilization and no five-hour reset instant
    And the same response reports the seven-day status as allowed
    When the Dispatcher evaluates admission
    Then the slot qualifies and the item is admitted with that slot projected
    And the assessment record names the five-hour window as five-hour-window-absent, not as an unobservable result
    And the assessment record carries a not-projected projection result with the reason five-hour-window-absent

  Scenario: The seven-day status still governs a slot whose five-hour window is absent
    Given the usage request for the only pool slot is answered with a 2xx status
    And the response carries no five-hour window
    And the same response reports the seven-day status as rejected
    When the Dispatcher evaluates admission
    Then the slot is skipped by a seven-day skip
    And the item stays ready without a claim

  Scenario: A slot with a measured five-hour reading outranks a slot whose window is absent
    Given slot "ANTHROPIC_0" is answered with a 2xx status carrying no five-hour window
    And slot "ANTHROPIC_1" reads 10 percent five-hour utilization with a measured projection
    When the Dispatcher evaluates admission
    Then slot "ANTHROPIC_1" is projected
    And the record names "ANTHROPIC_0" as qualifying but ranked lower

  Scenario: A malformed figure or a failed request is still unobservable
    Given the usage request for the only pool slot is answered with a five-hour figure that is not a number, or is refused with a non-2xx status carrying no five-hour figure, or times out
    When the Dispatcher evaluates admission
    Then the reading is journaled as unobservable and the slot is skipped by a floor skip
```

The revise that ratifies this topic MUST add the Scenario 288 heading to `tests/heading-coverage.json` in the same change.
