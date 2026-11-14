---
topic: exhausted-pool-slot-is-skipped
author: claude:gmktec-factory-placement session 212bd5
created_at: 2026-11-14T08:27:31Z
---

## Proposal: A pool slot whose credential identity a live provider-exhaustion record names is skipped, and the next qualifying slot is projected

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md section "Provider spend containment", paragraph "Admission filters candidates by projected Claude session headroom", so that a Claude pool slot whose opaque credential identity is named by a live provider-exhaustion record does not qualify. It takes a new provider-exhaustion skip, decided before every headroom test and not disabled by a floor of 0, and the next qualifying slot in the existing rank order is projected. The assessment's journal record names the skip as a provider-exhaustion skip and carries the record's expiry. When the skip leaves no slot qualifying, it has the per-node semantics of a floor skip, so selection continues to the node's next eligible candidate, such as a configured codex-acp fallback. Add one scenario heading that exercises it.

### Motivation

Work item bd-ib-wx4yha, held at the spec-change tier (topic session-headroom-admission-keeps-selecting; generalization target "## Dispatcher admission, WIP cap, and post-merge acceptance"). On 2026-11-14, between 05:09:23Z and 07:21:50Z, session-headroom admission chose CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_0 (credential identity a98e4044cc631956) for all eleven admissions in the orchestrator journal. Its five-hour window reset soonest and its seven-day reading was 98 percent with status allowed_warning, so it qualified and won the ranking. Its account had hit the organisation's monthly spend limit, and every run on it died at its first Claude node with "You've hit your org's monthly spend limit". From 07:44:51Z the Dispatcher journaled provider-exhaustion-observed records naming identity a98e4044cc631956 (bd-ib-fde4ie, bd-ib-yw7yot, bd-ib-pof4aa, bd-ib-auedbf), yet slots ANTHROPIC_3 and ANTHROPIC_4 stood at 1 and 0 percent seven-day utilization and were passed over as ranked-lower-later-reset. Every petri launch was then paused. The clause cannot express the fix today. Its qualification list is closed (the floor, the seven-day status and the projection), and it REQUIRES the soonest-reset qualifying slot, so it mandates the choice that failed. The provider rate windows it reads cannot see an organisation spend cap. The only fact that can see it is the per-identity provider-exhaustion record, and the exhaustion paragraph of this section lets that record refuse a dispatch projecting its identity but never move admission to another slot. Scenario 186 already scopes such a record to one credential identity, so excluding exactly that slot is the narrow, already-scoped use of an observation the Dispatcher holds. The rate windows and the reset ranking are unchanged.

### Proposed Changes

### contracts.md — §"Provider spend containment", paragraph "Admission filters candidates by projected Claude session headroom"

1. Immediately after the sentence that ends "and its projection does not call for a projection skip.", insert:

> Whatever the floor, a pool slot whose opaque credential identity is named by a live provider-exhaustion record (the per-identity records of "Every observed availability record is scoped, versioned, and expires" in this section) does NOT qualify: it takes a **provider-exhaustion skip**, which the Dispatcher MUST decide before every headroom test of this clause. A floor of 0 MUST NOT disable it, because it is an observed hold on that credential's account and not a headroom skip; a floor of 0 "disables no other admission condition". A provider-exhaustion record that carries no credential identity names no slot. It leaves slot qualification unchanged and keeps the vendor-wide coverage that paragraph states. The skip lasts only while the record is live: it ends at the record's expiry, or when the record is retired by a later matching execution or an operator clearance, and it creates no record and retires none.

2. Replace "With a floor of 0 every pool slot qualifies, and the ranking below still applies." with:

> With a floor of 0 every pool slot that is not taken by a provider-exhaustion skip qualifies, and the ranking below still applies.

3. In the sentence beginning "Every assessment's journal record MUST name the chosen slot's opaque non-secret credential identity", replace the reason list "a floor skip, a seven-day skip, a projection skip, an unobservable reading, or a qualifying slot ranked lower" with "a provider-exhaustion skip, a floor skip, a seven-day skip, a projection skip, an unobservable reading, or a qualifying slot ranked lower". Immediately after that sentence, insert:

> The journal record of an assessment taken by a provider-exhaustion skip MUST also carry the expiry instant of the live record that named the slot's credential identity, so a reader can see when the slot becomes eligible again without consulting the exhaustion records.

4. Immediately after the sentence beginning "A projection skip has exactly the semantics of a floor skip:", insert:

> A provider-exhaustion skip has the same per-node semantics. When it leaves no pool slot qualifying, every covered candidate of the dispatch is skipped, and per-node selection MUST continue in configured order to the next candidate satisfying every eligibility condition, such as a node's configured `codex-acp` fallback. When it leaves an admission-required node with no eligible candidate, a `ready` item remains `ready` without a claim or blocked reason, and reevaluation follows the Per-node selection scheduling rule of §"Factory-configurable ACP fallback priority", where the earliest expiry among the records that emptied the chain is the governing hold expiry. A headroom-governed refusal record and the per-node selection record MUST name it as a provider-exhaustion skip, distinct from a floor skip, a seven-day skip and a projection skip. A dispatch whose covered candidates were all skipped this way and that proceeds on an uncovered candidate projects no covered candidate, so under "No record, current or legacy, MAY refuse a dispatch whose resolved candidates all lie outside its coverage" the skipping records do not refuse it.

No other sentence of the clause changes. The rate-window readings, the floor, the seven-day rule, the projection and the soonest-reset ranking among qualifying slots are unchanged.

### scenarios.md — add one scenario

Add the following scenario after the current last scenario, numbered with the next unused scenario number when the revise lands (372 against master on 2026-11-14), and reference it from the amended paragraph as the scenario exercising the provider-exhaustion skip:

```gherkin
Feature: A pool slot whose account a live provider-exhaustion record names is skipped
  As a factory operator whose account hit a spend cap the provider's rate windows cannot see
  I want admission to pass over that account's slot while its exhaustion record is live
  So that the factory keeps dispatching on the slots that can still spend, instead of re-choosing the capped one

  Background:
    Given the credential wrapper injects the pool slots "ANTHROPIC_0" and "ANTHROPIC_1"
    And dispatcher.session_headroom_floor_percent is 20
    And both slots read 10 percent five-hour utilization
    And slot "ANTHROPIC_0"'s five-hour window resets sooner than slot "ANTHROPIC_1"'s
    And an item whose implement node's candidate is covered by the admission session-headroom clause, with a configured codex-acp fallback
    And every other admission-valve condition is satisfied

  Scenario: The exhausted slot is passed over for the next qualifying slot
    Given a live provider-exhaustion record names slot "ANTHROPIC_0"'s credential identity and expires at a known instant
    When the Dispatcher evaluates admission
    Then slot "ANTHROPIC_1" is projected
    And the assessment record names the "ANTHROPIC_0" identity as not chosen with the reason provider-exhaustion skip
    And that assessment carries the record's expiry instant

  Scenario: Every slot is exhausted, so the codex fallback is selected
    Given live provider-exhaustion records name the credential identities of both slots
    When the Dispatcher evaluates admission
    Then no pool slot is chosen
    And the covered candidate is skipped with the reason provider-exhaustion skip
    And the implement node selects its configured codex-acp fallback and the item is admitted

  Scenario: A floor of 0 does not disable the provider-exhaustion skip
    Given dispatcher.session_headroom_floor_percent is 0
    And a live provider-exhaustion record names slot "ANTHROPIC_0"'s credential identity
    When the Dispatcher evaluates admission
    Then slot "ANTHROPIC_0" is not chosen, with the reason provider-exhaustion skip

  Scenario: A record that names no credential identity leaves slot qualification unchanged
    Given a live provider-exhaustion record for the anthropic provider carries no credential identity
    When the Dispatcher evaluates admission
    Then no slot takes a provider-exhaustion skip
    And that record keeps its vendor-wide coverage under the exhaustion paragraph
```

The revise that ratifies this topic also adds the new scenario heading to `tests/heading-coverage.json`, owned by bd-ib-wx4yha, per the repository's heading-coverage co-edit discipline.
