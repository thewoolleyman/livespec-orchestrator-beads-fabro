---
topic: a-spec-change-hold-whose
author: claude-opus-5-5
created_at: 2026-11-08T00:38:43Z
---

## Proposal: A held item names a relink candidate when its generalization target was ratified under another topic

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend the autonomy-tier bullet of contracts.md §"Grooming and slice-size calibration". When an item is held for an unratified linked topic, and a revision ratified after the item's newest tier record amended that record's generalization-target heading under a different topic, the pre-dispatch wall's refusal names that topic and its specification version as a relink candidate, and needs-attention surfaces the item as a new hygiene:spec-tier-relink fact whose handoff is the relink. A rejected revision is never named. Naming a candidate does not release or relink the hold. Two scenarios are added to the existing Scenario 206 block, so no H2 heading is added.

### Motivation

Held work item bd-ib-jnbcny (plan spec-implementation-lockstep, epic bd-ib-ax3rds), filed on legacy-coordinator-agent's R301 order of 2026-11-08. The hold clears only when the spec history ratifies the EXACT linked topic. The ratified remedy for a proposal filed under a different stem is the `relink-spec-tier:<work-item-id>:<topic>` route, but nothing tells a seat that its filing-time stem has gone stale. On 2026-11-07 that cost three separate relink hunts: seven items relinked by this plan; livespec-dev-tooling-7upzav, whose clause ratified in v155 as orchestrator-build-explicit-adoption; and homelab hl-jq6ov3, ratified in homelab v011 as plugin-hook-holds-orchestrator-build. One candidate offered by hand that night, plugin-build-record-corrections, carried decision reject in v155, so the rule must exclude rejected revisions. The change is visibility only: releasing a hold on any ratified edit to a busy heading would free items whose own behaviour is still unratified, and the re-run judgement remains what decides stated.

### Proposed Changes

In SPECIFICATION/contracts.md, §"Grooming and slice-size calibration", autonomy-tier bullet, insert immediately after the sentence that ends "the hold MUST thereafter name the replacement topic as the one awaiting ratification.":

> When an item is held because its linked topic has no revision record with decision `accept` or `modify`, and a revision record with decision `accept` or `modify` cut after the specification version of the item's newest spec-change tier record amended the body of that record's generalization-target heading under a different topic, the pre-dispatch wall's refusal of the item MUST name that revision's proposed-change topic and specification version as a relink candidate, and `needs-attention` MUST surface the item under the existing `hygiene` kind as `hygiene:spec-tier-relink:<work-item-id>`, per §"Orchestrator-owned attention facts", with a `summary` naming the linked topic, the candidate topic and its specification version, and a `handoff` naming `relink-spec-tier:<work-item-id>:<candidate-topic>`. When more than one such revision exists, the refusal and the fact MUST name the most recently cut one. A revision whose decision is `reject` MUST NOT be named. Naming a candidate MUST NOT release the hold, relink the item, or write any ledger record. The hold is still released only as this bullet states, and the relink is still the `relink-spec-tier` route's.

In SPECIFICATION/scenarios.md, append to the end of the gherkin block under `## Scenario 206 — The spec-change tier is decided by the spec-stated judgement, and a feature waits for ratification`, before its closing fence:

```gherkin
  Scenario: A held item whose generalization target was ratified under another topic names that topic as a relink candidate
    Given a held spec-change-tier item whose linked topic has no revision record
    And a revision with decision accept, cut after the item's tier record, amended the body of that record's generalization-target heading under a different topic
    When a dispatch of the item is refused, and when needs-attention is composed
    Then the refusal names that topic and its specification version as a relink candidate
    And needs-attention carries hygiene:spec-tier-relink:<work-item-id> whose handoff is relink-spec-tier:<work-item-id>:<that topic>
    And the hold is not released, the item is not relinked, and no ledger record is written

  Scenario: A rejected revision is never named as a relink candidate
    Given a held spec-change-tier item whose linked topic has no revision record
    And the only revision cut after the item's tier record that amended its generalization-target heading carries decision reject
    When a dispatch of the item is refused, and when needs-attention is composed
    Then the refusal names no relink candidate and needs-attention carries no hygiene:spec-tier-relink fact for the item
```

No H2 heading is added, changed or removed, so tests/heading-coverage.json needs no edit.
