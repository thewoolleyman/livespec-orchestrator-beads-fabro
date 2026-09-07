---
topic: credential-probe-reprobe
author: claude-opus-4-8
created_at: 2026-09-07T04:25:56Z
---

## Proposal: Credential-probe refusal re-probes on a bounded cadence

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

A loop invocation whose admission-time credential-usability probe refuses (the projected worker credential returns a provider-limit / rate-limit condition before any sandbox launch) MUST NOT exit on that refusal while its budget is unspent. It MUST re-run the probe on a bounded cadence -- a committed-only dispatcher.credential_reprobe_interval_seconds, default 300 -- and resume normal admission on the first usable result, journaling each refused probe as one record. The refusal's operator-facing remedy MUST NOT present a provider-stated reset instant as a wait-until-clock instruction. This clause governs ONLY the loop's response to a probe refusal; it creates NO new exhaustion-record retirement route -- a usable probe MUST NOT retire an unexpired observed-exhaustion record.

### Motivation

Measured 2026-09-06 (same incident as the idle-factory carrier, epic bd-ib-zlpeyg): a dev-tooling drain dispatch was refused at 10:46Z by the admission-time credential-usability probe (probe_claude_credential / the claude-cred-status surface) with an HTTP 429 whose body carried a provider reset instant ('resets 15:50 Europe/Berlin = 13:50Z'). The refusal was terminal for the loop invocation, and its remedy text ('wait before retrying') invited exactly the clock-gated behavior that followed: the session wrote three detached resumers that slept until 13:55Z, while the credential was in fact usable again far earlier (usable at 12:05Z, measured). Two effects compounded the idle factory: the loop EXITED on a probe refusal instead of re-probing, and a provider timing claim was treated as an instruction. The ratified spend-containment section is already explicit that a provider timing claim 'MUST NOT be adopted as the expiry' and that 'The Dispatcher MUST NOT assume that any given provider communicates availability timing at all'. This carrier applies that same principle to the admission-time PROBE: the probe's own next result is the retirement signal for the loop's wait, not a clock.

Design decision (resolved from the ratified spec, not a values call): the charter (research/001 §3) flagged an open question -- should a usable probe ALSO retire an unexpired exhaustion record? The answer is a hard NO, and it follows directly from ratified text rather than from the charter's default. §'An exhaustion record is falsifiable by a dispatch outcome' states the Dispatcher trusts NONE of the availability signals a provider offers except a dispatch outcome; §'Observed, not predicted' states host and sandbox credential state diverge by construction (the worker credential projection substitutes a non-rotatable sentinel for the refresh token before the sandbox receives it), so a host-side credential read is 'specifically insufficient'. A live credential probe is precisely such a non-dispatch-outcome, host-side availability signal. Making it retire a record would contradict both clauses. The three ratified retirement routes -- bounded expiry, dispatch-outcome falsification, operator clearance -- therefore stand unchanged, and this carrier adds none.

### Proposed Changes

Two spec edits plus one co-edited test-coverage map. Behavior is stated as MUST clauses in contracts.md AND a Gherkin scenario in scenarios.md per the behavior=>clause+scenario split.

=== 1. contracts.md: add two clauses to the '### Provider spend containment' section, placed immediately AFTER the 'An operator may retire an exhaustion record early.' clause group (i.e., after the paragraph ending 'the bounded-expiry obligation continues to govern every record the Dispatcher mints.') and BEFORE the 'No silent containment.' clause. Add the following two bolded-lead paragraphs:

**The admission-time credential-probe refusal re-probes rather than exiting.** A `loop` invocation (§"Dispatcher loop invocation surface") whose admission is refused by the admission-time credential-usability probe -- the projected worker credential returning a provider-limit or rate-limit condition BEFORE any sandbox is launched -- MUST NOT exit on that refusal while its `--budget` is unspent. It MUST re-run the probe on a bounded cadence and resume normal admission on the first usable probe result, subject to every other admission-valve condition (§"Admission valve (`ready → active`)"). The cadence is a committed-only `dispatcher.credential_reprobe_interval_seconds` (positive integer, default **300**); it is NOT declared API-configurable and is therefore committed-only per §"The declared-API-configurable class". Each refused probe MUST be journaled as one record under §"Control surface and audit" -- the re-probe wait is not silent. This clause governs ONLY the loop's response to a probe refusal; it creates NO new exhaustion-record retirement route. A usable probe result MUST NOT retire an unexpired observed-exhaustion record: the three ratified retirement routes -- bounded expiry, dispatch-outcome falsification (§"An exhaustion record is falsifiable by a dispatch outcome"), and operator clearance -- stand unchanged, because a live credential probe is precisely a non-dispatch-outcome, host-side availability signal, of which the Dispatcher trusts none, and host and sandbox credential state diverge by construction (§"Observed, not predicted"). Where an unexpired exhaustion record ALSO governs the provider, admission remains refused by that record until it retires by one of its own routes; the re-probe keeps the loop alive and re-attempts admission rather than substituting for the record's retirement.

**The probe refusal's remedy carries no timing claim as an instruction.** The credential-probe refusal surfaced to the operator MUST NOT present a provider-stated reset instant as an instruction to wait until a clock time. This is the same principle §"Every exhaustion record expires" already applies to the exhaustion record, now applied to the probe refusal: a provider's timing claim MUST NOT be adopted as an instruction and MUST NOT gate the re-probe cadence; if the provider's refusal carried such a claim it MAY be recorded as provenance, clearly marked as an unverified provider claim rather than as an observation. The probe's OWN next result is the retirement signal for the loop's wait, not a clock.

=== 2. scenarios.md: append a new scenario at the end of the file. It is numbered 119 on the assumption that the idle-factory carrier's Scenario 118 (bd-ib-zlpeyg Carrier A) is applied first per the plan's revise ordering; if revise applies both carriers together, these are the next two contiguous numbers (118 for Carrier A, 119 for Carrier B).

## Scenario 119 — A refused credential probe re-probes on a cadence instead of exiting, and no clock gates it

```gherkin
Feature: A rate-limited credential re-probes rather than parking the loop on a provider clock
  As a maintainer whose factory sat idle after a transient rate limit
  I want the loop to re-probe the credential on a bounded cadence and resume itself
  So that a recovered credential is used promptly and no provider clock claim strands the drain

Scenario: The loop re-probes and resumes on the first usable result, journaling each refusal
  Given a loop invocation whose budget is unspent
  And whose admission-time credential-usability probe first returns a provider rate-limit refusal
  When the bounded re-probe cadence elapses and a subsequent probe returns usable
  Then the loop resumes normal admission on that first usable result without having exited
  And each refused probe was journaled as exactly one record
  And the refusal's remedy text carried no provider-stated reset instant as a wait-until-clock instruction

Scenario: A usable probe does not retire an unexpired exhaustion record
  Given an unexpired observed-exhaustion record held for the provider
  And a credential-usability probe that returns usable
  When admission is attempted
  Then admission remains refused by the exhaustion record
  And the record retires only by bounded expiry, a dispatch outcome, or an operator clearance
```

=== 3. tests/heading-coverage.json: add one entry for the new H2 heading, co-edited atomically with the scenarios.md addition per the revise co-edit discipline. The exercising test lands with the post-ratification implementation child, so `test` is the literal "TODO" with a non-empty reason:

{
  "heading": "## Scenario 119 — A refused credential probe re-probes on a cadence instead of exiting, and no clock gates it",
  "spec_root": "SPECIFICATION",
  "spec_file": "scenarios.md",
  "test": "TODO",
  "reason": "Scenario ratified spec-first under plan idle-factory-visibility (epic bd-ib-zlpeyg, Carrier B). The exercising integration test binds when the post-ratification implementation child lands the bounded credential re-probe on the loop path."
}
