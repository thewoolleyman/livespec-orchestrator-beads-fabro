---
topic: delegated-valve-authority
author: claude-opus-5-5
created_at: 2026-11-02T23:27:53Z
---

## Proposal: Delegated valve authority is a first-class, verified invoker form for the human valves

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a delegated invoker form, `delegate:<delegate-name>`, that `drive` accepts on a short allowlist of human valves (resolve-blocked, approve, accept, reject, release-spec-tier) only when the press also names `--delegation <ref>` and that ref resolves to a maintainer delegation recorded in the committed `dispatcher.valve_delegations` setting for exactly that delegate. A verified delegated press satisfies the `human` answer disposition, is journaled and recorded on the item's ledger as an act under maintainer delegation citing the ref and its grantor, and never writes a `human:<name>` identity. Every other press carrying the delegate role or `--delegation` is refused before any write.

### Motivation

On 2026-11-02 the maintainer ruled, verbatim: "human valve - option 1, make coordanitor delegation authority a first class concept so this stops blocking." (plan-scope-event on livespec-dev-tooling-6tgd2z, 2026-11-02T23:22:22Z). The standing delegation is R493 (scope event on the same epic, 2026-11-01T22:36:24Z): "the coordinator presses human valves on the maintainer's authority, except credentials, irreversible or outward-facing acts." Today the only identity the `human` answer disposition admits is `human:<name>`, so a seat pressing on a coordinator ruling either forges the maintainer's identity (measured: bd-ib-yqcuwl's 23:12:54Z answer comment was stamped `human:Chad Woolley` and needed an attribution-correction comment 40 s later) or refuses and holds the item until the maintainer presses personally. Both outcomes are wrong: the first puts an unverifiable human claim on an append-only ledger, the second re-parks a decision the maintainer has already delegated. A delegated identity that the valve verifies against a committed record makes the delegated press honest and accepted, keeps the record auditable, and keeps the R493 exclusions mechanical rather than a matter of each seat's judgement.

### Proposed Changes

Two edits.

**1. `SPECIFICATION/contracts.md`, §"Journal invoker attribution".** Insert, immediately before the paragraph that opens "**`dispatcher.require_invoker`**", this new paragraph block:

> **Delegated valve authority.** A maintainer MAY delegate the pressing of human valves to a named delegate (for this fleet, the coordinator seat under ruling R493). The delegation is first-class: the press asserts the reserved role `delegate`, as `--invoker delegate:<delegate-name>`, and MUST also name the delegation it acts under with `--delegation <ref>`. `drive` MUST verify the press against **`dispatcher.valve_delegations`** (committed `.livespec.jsonc`, a list; default empty), each entry an object with the non-empty strings `ref` (the delegation's identifier, e.g. `R493`), `delegate` (the `<delegate-name>` it authorizes), `grantor` (the delegating human, a `human:<name>` identity) and `record` (where the grant is recorded, e.g. the plan-scope-event's epic and timestamp). A press is a **verified delegated press** exactly when its invoker role is `delegate`, its `--delegation` ref equals one entry's `ref`, that entry's `delegate` equals the invoker's `<delegate-name>`, and the action's verb is on the **delegable valve allowlist**: `resolve-blocked`, `approve`, `accept`, `reject` and `release-spec-tier`. Like `dispatcher.require_invoker`, `dispatcher.valve_delegations` is deliberately NOT API-configurable: a delegation is granted only by a committed, reviewable change, so no press can invent the reference it cites. A list that does not parse, or an entry missing any of the four fields or whose `grantor` is not a named `human:` identity, makes the whole setting unreadable, and an unreadable setting verifies no press.
>
> The delegation NEVER covers a credential, irreversible or outward-facing act, and the allowlist is the mechanical form of that exclusion: the factory-safety opt-out and its clearance (host secrets and host machinery), the merge hold (a forge write), the policy, cap, queue and workflow-scope edits, `impl:` and `driver-dispatch:` dispatches, and every entry point outside `drive` (the provider-exhaustion and ACP-hold clearances among them) are not delegable. `drive` MUST refuse, before any store read that could lead to a write, any journal write or any ledger write: a `delegate:` invoker without `--delegation`; `--delegation` without a `delegate:` invoker; a delegated press of a verb off the allowlist; and a ref that matches no entry, or matches an entry for a different delegate, or cannot be verified because the setting is unreadable. Each refusal names the action, the asserted invoker and ref, and why. No environment variable or flag bypasses this verification.
>
> A verified delegated press satisfies every gate on the allowlisted valves that admits a human operator's press, the `human` answer disposition of §"Dispatcher policy settings" included. Its records MUST say plainly that the delegate acted under maintainer delegation and MUST NOT carry a `human:<name>` identity: `invoker` stays the asserted `delegate:<delegate-name>`, every journal record the press writes additionally carries a stamped `delegation` object (`ref`, `grantor`, `record`) applied by the same append layer that stamps `invoker`, an answer comment's header names the delegation ref and grantor after the invoker, and a green press appends one ledger comment to the item opening with the marker `livespec-delegated-valve-press` that names the action id, the delegate, the ref, the grantor and the record. A refused press writes none of these. Scenario 301 binds this behavior.

In §"Dispatcher policy settings", in the paragraph that begins "An item's **effective answer disposition** resolves as", replace

> — under `human`, an automated/non-human disposition's press is refused —

with

> — under `human`, an automated/non-human disposition's press is refused, and a verified delegated press (§"Journal invoker attribution" → "Delegated valve authority") is admitted as a human operator's —

**2. `SPECIFICATION/scenarios.md`.** Append a new heading after the last scenario:

````markdown
## Scenario 301 — A verified delegated press satisfies a human valve and is recorded as delegated

```gherkin
Feature: The maintainer's delegation of human valves is a verified, first-class invoker form
  As a maintainer who has delegated human valves to a coordinator
  I want a delegated press to be verified against a committed delegation and recorded as delegated
  So that delegated decisions stop blocking without anyone forging my identity

  Scenario: A verified delegated answer is admitted and recorded under the delegation
    Given dispatcher.valve_delegations carries ref R493 for delegate legacy-coordinator-agent granted by human:thewoolleyman
    And a work-item at blocked with blocked_reason needs-human and effective answer disposition human
    When drive runs resolve-blocked:<work-item-id>:ready with --answer, --invoker delegate:legacy-coordinator-agent and --delegation R493
    Then the press is admitted and the answer lands as a ledger comment naming delegation R493 and grantor human:thewoolleyman
    And every journal record of the press carries invoker delegate:legacy-coordinator-agent and a delegation object citing R493
    And the item gains a livespec-delegated-valve-press ledger comment, and no record carries a human: identity

  Scenario: A delegation that cannot be verified is refused before any write
    Given dispatcher.valve_delegations carries ref R493 for delegate legacy-coordinator-agent
    When drive runs an allowlisted valve with --invoker delegate:legacy-coordinator-agent and a --delegation ref that no entry carries, or with no --delegation at all, or with --delegation and a non-delegate invoker
    Then drive refuses the press naming the action, the invoker, the ref and the reason
    And nothing is written to the store, the journal or the ledger

  Scenario: A delegated press of a non-delegable valve is refused
    Given dispatcher.valve_delegations carries ref R493 for delegate legacy-coordinator-agent
    When drive runs set-merge-hold, set-factory-safety or an impl: dispatch with --invoker delegate:legacy-coordinator-agent and --delegation R493
    Then drive refuses the press because the verb is not on the delegable valve allowlist
```
````

The new `## Scenario 301` heading needs a `tests/heading-coverage.json` entry in the revise commit.
