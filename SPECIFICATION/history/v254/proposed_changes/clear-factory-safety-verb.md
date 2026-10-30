---
topic: clear-factory-safety-verb
author: claude-opus-5-5
created_at: 2026-10-21T05:15:19Z
---

## Proposal: clear-factory-safety is the sanctioned route back into factory eligibility

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a status-independent `clear-factory-safety:<id>:<rationale>` drive action as the inverse of `set-factory-safety`. It clears the intrinsic `factory_safety` field only after journaling the rationale, the invoker and the removed reason. It refuses an empty rationale and an item carrying no hold, and it leaves lifecycle status and `admission_policy` unchanged. Three Scenario 48 scenarios state that behaviour.

### Motivation

contracts.md makes `set-factory-safety` the only sanctioned route OUT of factory eligibility, so the reason is journaled rather than written by a raw `bd label add`. There is no matching route back in: lifting a hold today takes a raw `bd label remove`, which is exactly the unattributable label edit the set verb exists to retire. Live case, 2026-10-21: coordinator ruling R388 lifted the `mutates-host-machinery` hold on livespec-dev-tooling-x36is7 through a rationale comment plus a raw `bd label remove`. R392 accepted that once and directed work-item bd-ib-mdp2pr. livespec-dev-tooling-vxkmab's pending `needs-host-secrets` clear is the next case. The contract's own rule, that a work-item introducing a first-class operator verb MUST include specification coverage for it, routes this spec half through propose-change before the factory implements the verb.

### Proposed Changes

Five coordinated edits. Every one of them MUST land together in a single revision.

**1. `SPECIFICATION/contracts.md` §"`drive`", the action-id grammar sentence.** "one of the thirteen human valve/policy actions" becomes "one of the fourteen human valve/policy actions". `clear-factory-safety:` is inserted immediately after `set-factory-safety:` in that parenthesized list.

**2. `SPECIFICATION/contracts.md` §"`drive`", the policy-edit enumeration.** Immediately after the `set-factory-safety:...` clause and its parenthetical, insert:

> the status-independent factory-safety clearing assertion `clear-factory-safety:<work-item-id>:<rationale>` (clears the intrinsic `factory_safety` field with a journaled rationale; §"Per-state operator verb vocabulary"),

**3. `SPECIFICATION/contracts.md`, the Dispatcher-boundary list of human-triggered operator commands.** In the backticked action-id list `approve:/accept:/.../set-factory-safety:/...`, insert `clear-factory-safety:` immediately after `set-factory-safety:`.

**4. `SPECIFICATION/contracts.md` §"Per-state operator verb vocabulary".** In the **Status-independent verbs.** paragraph, after the sentence introducing `set-factory-safety`, add: "`clear-factory-safety:<id>:<rationale>` is its inverse and is likewise status-independent and not enumerated per row." After the `#### set-factory-safety:...` subsection, insert a new subsection:

```
#### `clear-factory-safety:<id>:<rationale>`

A status-independent operator verb that CLEARS the target work-item's
`factory_safety` field, returning it to null and therefore to factory
eligibility. It is the inverse of `set-factory-safety`, and it MUST be the
only sanctioned route back into factory eligibility: lifting a host-only
hold through a raw `bd label remove` leaves no attributable record, which is
exactly what `set-factory-safety` exists to prevent on the way out.

The `<rationale>` is the remainder of the action id after the second colon
and MAY itself contain colons. A rationale that is empty or only whitespace
MUST be refused, with a message naming the missing rationale, and the item
MUST keep its `factory_safety` value. A `clear-factory-safety` on an item
whose `factory_safety` is already null MUST be refused, with a message saying
no hold is set, and MUST write nothing to the ledger or the journal.

On an accepted clear, the verb MUST append the rationale, the invoker and the
removed reason to the item's ledger comments and to the dispatch journal
BEFORE it removes the value, so that a failed mutation leaves an explained
intent rather than a silent change. Like `set-factory-safety`, it is valid on
a work-item in ANY lane, it does NOT change item status, and it MUST NOT
alter `admission_policy`.
```

**5. `SPECIFICATION/scenarios.md` §"Scenario 48 — Dispatcher refuses a not-factory-safe item at admission".** Immediately after the scenario "set-factory-safety requires one of the three canonical factory_safety reasons", insert:

```gherkin
  Scenario: clear-factory-safety journals its rationale and returns the item to factory eligibility
    Given a `ready` work-item whose `factory_safety` is `needs-host-secrets`
    When the operator invokes `clear-factory-safety:<work-item-id>:host secrets no longer needed`
    Then the rationale, the invoker and the removed reason `needs-host-secrets` are recorded in the item's ledger comments and in the journal before the field changes
    And the item's `factory_safety` is null
    And the item's lifecycle status and `admission_policy` are unchanged

  Scenario: clear-factory-safety refuses an empty rationale
    Given a `backlog` work-item whose `factory_safety` is `mutates-host-machinery`
    When the operator attempts `clear-factory-safety:<work-item-id>:` with an empty rationale
    Then the action is refused, naming the missing rationale
    And the item's `factory_safety` remains `mutates-host-machinery`

  Scenario: clear-factory-safety refuses an item that carries no hold
    Given a `ready` work-item whose `factory_safety` is null
    When the operator attempts `clear-factory-safety:<work-item-id>:no reason needed`
    Then the action is refused, saying no hold is set
    And nothing is written to the item's ledger comments or to the journal
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.
