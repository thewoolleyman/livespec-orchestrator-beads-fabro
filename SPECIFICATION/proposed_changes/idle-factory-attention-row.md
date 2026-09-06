---
topic: idle-factory-attention-row
author: claude-opus-4-8
created_at: 2026-09-06T16:18:09Z
---

## Proposal: Idle-factory attention row

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add a new orchestrator-owned attention fact, hygiene:idle-factory:<repo>, so that needs-attention surfaces a high-urgency row when a repository has dispatchable ready work but its factory is idle and nothing the orchestrator can see is holding it back. The fact composes deterministically from this repository's own ledger and capacity verdict alone: it fires when (a) at least one ready item is admission-eligible under the admission valve's non-capacity conditions, (b) the single-authority capacity verdict reports zero counted claims, and (c) no unexpired observed provider-exhaustion record is held for the provider the default dispatch would use. It rides the existing hygiene kind (no new wire kind), carries a drive-kind handoff of impl:<first-ranked-id>, and clears the moment any of the three conditions fails.

### Motivation

Measured 2026-09-06: a dev-tooling drain dispatch was refused at admission at 10:46Z on an exhausted CLAUDE_CODE_OAUTH_TOKEN (HTTP 429). The Dispatcher's provider-spend containment behaved exactly as ratified (a bounded 15-minute exhaustion hold that then expired). By 12:05Z the credential probe returned usable, the dispatch journal held NO unexpired exhaustion record, counted claims were zero, and 44 ready items sat dispatchable -- yet the factory stayed idle for roughly two hours and the maintainer noticed only by hand. needs-attention composed nothing about it. Per the section's own enumeration, needs-attention registers every WAIT the orchestrator owns (a person, a slot, a provider hold), and its wait enumeration is 'deliberately closed'. An idle factory is not a wait on a person or a slot, so no existing class composes it -- the operator learns of it only by looking. This fact closes that gap: a repository with dispatchable work and nothing visibly holding it back should SAY SO, high urgency, with the drive action that starts it. It is the immediate converse of the existing ready-aging fact (hygiene:ready-aging:<repo>), which fires only after the ready_aging_threshold_hours has elapsed; idle-factory fires as soon as the factory is idle with dispatchable work, catching the fast-onset case the aging threshold is too slow to see.

Design decision (maintainer-ratified 2026-09-06, plan idle-factory-visibility epic bd-ib-zlpeyg): the fact does NOT perform a live credential usability probe at composition time. An earlier charter draft listed a fourth condition -- 'the admission-time credential usability probe returns usable' -- but a live Messages-API probe is not a function of the store, so it would break the byte-identical-over-an-unchanged-store guarantee this section requires (mirroring the SIDE-EFFECT-FREE projection the capacity fact already mandates) and is unprecedented: every one of the four existing needs-attention fact composers reads only the store, journal, and git. The probe stays where it belongs, in the dispatch admission path. Conditions (a)+(b)+(c) already caught the incident (all three held at 12:05Z), and the design is self-correcting: the impl:<first-id> dispatch the handoff invites re-probes the credential and re-records exhaustion if it is in fact dead, at which point the next snapshot surfaces the provider-exhaustion wait instead.

### Proposed Changes

Two spec edits plus one co-edited test-coverage map. Behavior is stated as a MUST clause in contracts.md AND a Gherkin scenario in scenarios.md per the behavior=>clause+scenario split.

=== 1. contracts.md: add one fact clause to the '### Orchestrator-owned attention facts' section, placed immediately AFTER the 'Ready-work aging (hygiene:ready-aging:<repo>)' clause and BEFORE the 'Wait completeness (enumerated, with forward registration)' clause. It is a new fact class, NOT an addition to the enumerated wait set (an idle factory is not a wait on a person or a slot). Add the following bolded-lead paragraph:

**Idle-factory (`hygiene:idle-factory:<repo>`).** When, and only when, ALL THREE of the following hold for a repository, the snapshot MUST carry exactly one idle-factory fact: (a) the ready set is non-empty and at least one ready item is admission-eligible under the admission valve's non-capacity conditions -- the same eligibility the drain and `next` honor, capacity excepted; (b) the single-authority capacity verdict (this section's “Capacity single authority”) reports ZERO counted claims for this repository, read through the SIDE-EFFECT-FREE capacity projection that clause requires and NEVER from a mutating accounting path; and (c) no unexpired observed provider-exhaustion record is held for the provider the default dispatch would use (§"Provider spend containment"). The fact's `urgency` MUST be `high`. Its `summary` MUST be a deterministic one-line statement naming the count of admission-eligible ready items and the first ranked such id. Its single `handoff` MUST be a `drive`-kind handoff carrying `impl:<first-ranked-id>` for that first ranked item -- executable as advertised (§"The needs-attention machine envelope" → “Executable as advertised”): the `action_id` MUST be one `drive` would accept for that item's state. The fact rides the existing `hygiene` kind with the stable id `hygiene:idle-factory:<repo>`; it introduces NO new wire kind, grammar form, or field (§"The needs-attention machine envelope" → ownership cut). It is derived ONLY from this repository's own ledger, journal, and capacity verdict (§"The ownership boundary") -- it performs NO live credential probe and NO other external call, and two invocations against an unchanged store emit a byte-identical row. The fact CLEARS the instant any of (a), (b), or (c) fails: it does not appear when counted claims are non-zero (the factory is busy), when no admission-eligible ready item exists (there is nothing to dispatch), or when an unexpired exhaustion record is held (that wait already composes under §"Provider spend containment"). Like every fact in this section it composes existing reads, executes nothing, and creates no work-items.

=== 2. scenarios.md: append a new scenario at the end of the file, after '## Scenario 117'. It is the converse of Scenario 84 (ready-work aging):

## Scenario 118 — An idle factory with dispatchable work surfaces its first dispatch

```gherkin
Feature: Idle-factory visibility composes when work is ready and nothing is moving
  As a maintainer whose factory silently sat idle with a full queue
  I want an idle factory surfaced with the dispatch that starts it
  So that an idle repository says so instead of waiting to be noticed by hand

Scenario: The idle-factory fact appears when ready work is dispatchable and nothing holds it back
  Given at least one admission-eligible ready item under the admission valve's non-capacity conditions
  And the single-authority capacity verdict reports zero counted claims for this repository
  And no unexpired observed provider-exhaustion record is held for the default dispatch provider
  When needs-attention composes the snapshot
  Then exactly one hygiene:idle-factory fact appears at high urgency
  And its summary names the count of admission-eligible ready items and the first ranked id
  And its handoff is a drive-kind handoff carrying impl:<first-ranked-id> that drive accepts for that item's state

Scenario: The idle-factory fact clears when any trigger condition fails
  Given the idle-factory fact would otherwise compose
  When a counted claim occupies a slot for this repository
  Then no idle-factory fact appears
  And when instead an unexpired observed provider-exhaustion record is held the idle-factory fact does not appear
  And when instead no admission-eligible ready item exists the idle-factory fact does not appear
```

=== 3. tests/heading-coverage.json: add one entry for the new H2 heading, co-edited atomically with the scenarios.md addition per the revise co-edit discipline. The exercising test lands with the post-ratification implementation child, so `test` is the literal "TODO" with a non-empty reason:

{
  "heading": "## Scenario 118 — An idle factory with dispatchable work surfaces its first dispatch",
  "spec_root": "SPECIFICATION",
  "spec_file": "scenarios.md",
  "test": "TODO",
  "reason": "Scenario ratified spec-first under plan idle-factory-visibility (epic bd-ib-zlpeyg, Carrier A). The exercising integration test binds when the post-ratification implementation child lands the hygiene:idle-factory:<repo> composer."
}
