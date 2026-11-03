---
topic: reprioritised-plan-obligation-budget
author: claude-opus-5-5
created_at: 2026-11-03T00:03:03Z
spec_commitments:
  impl_followups:
    - id_hint: reprioritized-supersession-cause
      description: |
        Implement the `reprioritized` supersession cause in commands/_plan_supersession.py and _plan_progress_unmet.py. Verify the epic's latest complete current continuation ruling names both result identities, accept it for an expired obligation, grant the replacement a fresh budget bounded by the ruling's until with zero consumed handoffs, and refuse it from an unattended writer.
---

## Proposal: A recorded re-prioritisation re-aims an expired plan obligation under a fresh, ruling-bounded budget

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a fourth evidenced supersession cause, `reprioritized`. A current recorded continuation ruling that names the superseded obligation and its replacement may supersede that obligation even after it has expired. The replacement then gets a FRESH budget: its deadline is no later than the ruling's `until`, its handoff count starts at zero, and it is capped at the writer's `max_handoffs`. The superseded obligation is retained in the progress history as superseded by that ruling.

### Motivation

Measured 2026-11-02 on plan epic bd-ib-acrr56 (publish-draft-green-work-loss). The maintainer re-prioritised the plan to PRIORITY 3, and the fleet coordinator ruled that its expired obligation's target (bd-ib-elkb33) leaves the plan.

Under the current text the plan still cannot re-aim its pointer:
- Every ratified cause is refused for an expired obligation, because 'a supersession of an already expired obligation remains subject to the expiry rules above'.
- Even an accepted supersession inherits the expired deadline, so the replacement is born expired.
- The only continuation left is a same-obligation continuation ruling for the wrong target.

A recorded human decision is exactly the authority the expiry rules already accept for expired continuation. Letting that decision also rename the obligation and set a bounded new budget closes the gap, while every other rename stays refused. The conformance half (consult the ruling, and verify disposed-by-re-parenting) is filed as bd-ib-cqqzfo. This proposal decides the budget question that item cannot.

### Proposed Changes

In contracts.md, section "### Required result, budget and progress epoch", in the paragraph beginning "**An evidenced causal supersession**", add a fourth bullet after `subsumed`:

- `reprioritized` — a recorded human decision re-aims the plan: the epic's CURRENT continuation ruling (a complete `plan-continuation: authorized` scope event whose `until` is in the future) names, in its directive, the superseded obligation's canonical result identity and the replacement result's canonical identity. The evidence is that ruling's scope-event comment id, which MUST resolve on the epic and MUST be the latest complete ruling in timeline order.

In the paragraph that follows the bullets, replace "The replacement MUST inherit the superseded obligation's original deadline and consumed handoff count unchanged." with:

"Except under `reprioritized`, the replacement MUST inherit the superseded obligation's original deadline and consumed handoff count unchanged. Under `reprioritized` the replacement starts a fresh budget. Its deadline is the earlier of the writer's candidate deadline and the ruling's `until`. Its consumed handoff count is zero. Its `max_handoffs` is the writer's candidate value. The superseded obligation's progress history is retained, and its final event names the ruling id as its disposition."

In the same paragraph, replace "A supersession of an already expired obligation remains subject to the expiry rules above." with:

"A supersession of an already expired obligation remains subject to the expiry rules above. A `reprioritized` supersession carrying a current ruling satisfies them, because that ruling is the recorded human decision those rules accept. Every other cause on an expired obligation additionally requires a current continuation ruling or a fresh typed causal recovery attempt."

Append: "A `reprioritized` supersession written by an unattended session MUST be refused, as the ruling itself already requires an attended writer."

In scenarios.md, add a new scenario after the last existing one:

## Scenario 301 — A recorded re-prioritisation re-aims an expired plan obligation under a fresh budget bounded by the ruling

```gherkin
Feature: A maintainer re-prioritisation can re-aim an expired plan pointer without letting a rename evade expiry
  Scenario: A current ruling naming both results supersedes an expired obligation
    Given a plan obligation whose deadline has passed
    And the epic's latest complete continuation ruling is current and names that obligation's result identity and a replacement result identity
    And the replacement result is unsatisfied
    When an attended set_next_action carries a supersession with cause reprioritized naming that ruling
    Then a plan-progress-event of kind supersession is recorded before the pointer changes
    And the replacement's deadline is the earlier of the candidate deadline and the ruling's until
    And the replacement's consumed handoff count is zero

  Scenario: A ruling that does not name the replacement does not re-aim the obligation
    Given an expired plan obligation and a current continuation ruling whose directive names a different replacement result
    When set_next_action carries a supersession with cause reprioritized naming that ruling
    Then the write is refused and the pointer and obligation are unchanged

  Scenario: An unattended re-prioritisation is refused
    Given an expired plan obligation and a current continuation ruling naming both results
    When an unattended session's set_next_action carries a supersession with cause reprioritized
    Then the write is refused and the pointer and obligation are unchanged
```

The revise pass MUST add a `tests/heading-coverage.json` entry for the new Scenario 301 heading (test MAY be "TODO" with a reason naming the impl follow-up).
