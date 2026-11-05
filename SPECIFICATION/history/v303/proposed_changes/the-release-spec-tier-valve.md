---
topic: the-release-spec-tier-valve
author: claude-opus-5-5
created_at: 2026-11-05T10:25:15Z
---

## Proposal: The release-spec-tier attestation records the invoking session's computed identity when no invoker is asserted

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Generalize the journal invoker-attribution clause of §"Work-item state semantics" for the `release-spec-tier` attestation's door-specific actor. When no invoker is asserted by `--invoker` or `LIVESPEC_INVOKER`, the attestation's ledger comment and dispatch-journal entry record as actor the identity computed from the invoking session: the agent session id when the session sets one, otherwise the forge login. The actor names which of the two kinds it is. The `unattributed:<os-user>@<hostname>` mark stays the actor only when no session identity can be computed. The envelope-level `invoker` / `invoker_source` stamping is unchanged.

### Motivation

Measured 2026-11-02 at about 16:4xZ by plan dev-host-test-gate-load on livespec-dev-tooling-ialgtq. A delegated `release-spec-tier` attestation under the coordinator's standing rulings (R301/R493) passed, but the ledger recorded its actor as `unattributed:ubuntu@vmi3006760`, so nobody can say who attested. Attestations are human overrides of a model verdict, and the valve exists so a person is accountable for the release, so an attestation that cannot name its actor defeats the purpose of recording one.

The ratified text sets the actor from the journal invoker resolution order: `--invoker`, then `LIVESPEC_INVOKER`, then the fallback mark. It does not let the valve compute an identity. The plan-record and proof-record posting primitives already compute a publishing identity from the invoking session: the agent session id, or the forge login for a human at a terminal. Reusing that computation for the valve's actor when nothing is asserted closes the gap without inventing a second identity source.

The carrier is work item bd-ib-tgkx5f (plan spec-implementation-lockstep, bd-ib-ax3rds). On 2026-11-05T10:20:10Z the spec-stated judgement classified it as a feature whose asked-for behaviour is `partial` and named §"Work-item state semantics" as the heading to generalize. The Dispatcher holds it at the spec-change tier for this topic.

The journal envelope's `invoker` / `invoker_source` stay governed by the existing three-step order. That stamping is the uniform record of who ASSERTED the act, and the clause deliberately records a fallback mark there. Changing it would alter every journal record rather than this one door, and it is out of scope.

### Proposed Changes

Two edits. No `## ` heading is added, removed or renamed, so `tests/heading-coverage.json` needs no edit.

**1. `SPECIFICATION/contracts.md`, §"Work-item state semantics", the journal invoker-attribution clause.**

After the sentence

> Where a ratified door already journals a door-specific actor field (the v051 valve records), that field remains; `invoker`/`invoker_source` is the uniform envelope-level attribution.

insert the following sentences, in the same paragraph:

> The `release-spec-tier` valve's attestation actor (§"Grooming and slice-size calibration" → "An autonomy tier is assigned") is such a door-specific actor. When an invoker is asserted, by `--invoker` or by `LIVESPEC_INVOKER`, the attestation's ledger comment and its dispatch-journal entry MUST record that asserted invoker as the actor. When no invoker is asserted, both MUST record as the actor the identity computed from the invoking session. That is the invoking agent session's id when the session sets one, otherwise the forge login of the human at the terminal, computed exactly as the plan-record and proof-record posting primitives compute their publishing identity. The recorded actor MUST name which of the two kinds it is, as `session:<agent-session-id>` or `human:<forge-login>`, so an actor computed from an agent session is distinguishable from one computed from a forge login. Only when no invoker is asserted and no session identity can be computed does the attestation record the `unattributed:<os-user>@<hostname>` mark as its actor. This computation never changes the journal entry's envelope `invoker` and `invoker_source`, which the append layer stamps by the three-step order above.

**2. `SPECIFICATION/scenarios.md`, `## Scenario 206 — The spec-change tier is decided by the spec-stated judgement, and a feature waits for ratification`.**

Append these scenarios at the end of the existing gherkin fence:

```gherkin
  Scenario: An attestation with no asserted invoker records the invoking session's computed identity
    Given a held feature and an existing H2 heading that states its asked-for behaviour
    And release-spec-tier is driven for the item with no --invoker flag and no LIVESPEC_INVOKER in the environment
    And the invoking session sets an agent session id
    When the valve records the attestation
    Then the ledger comment and the dispatch-journal entry record the actor as session:<that agent session id>
    And neither records an unattributed mark as the actor
    And the journal entry's envelope invoker and invoker_source are stamped by the append layer exactly as before

  Scenario: An attestation from a human terminal with no asserted invoker records the forge login
    Given release-spec-tier is driven for a held feature with no asserted invoker
    And the invoking session sets no agent session id and the forge reports a login
    When the valve records the attestation
    Then the ledger comment and the dispatch-journal entry record the actor as human:<that forge login>

  Scenario: An asserted invoker is the attestation's actor
    Given release-spec-tier is driven for a held feature with an invoker asserted by flag or by environment
    When the valve records the attestation
    Then the ledger comment and the dispatch-journal entry record that asserted invoker as the actor

  Scenario: An attestation with no computable identity records the fallback mark
    Given release-spec-tier is driven for a held feature with no asserted invoker
    And the invoking session sets no agent session id and no forge login can be read
    When the valve records the attestation
    Then the ledger comment and the dispatch-journal entry record the unattributed:<os-user>@<hostname> mark as the actor
```
