---
topic: committed-admission-setting-wins-over-item-label
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T23:21:28Z
---

## Proposal: A committed auto_approve_ready setting wins over a stored per-item admission label

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Today an item's stored `admission_policy` label overrides the repository's `dispatcher.auto_approve_ready` setting, so a stale `admission:manual` label silently holds an item at `pending-approval` in a repository whose committed configuration says to auto-approve. This proposal reverses that precedence when the repository COMMITS the setting. When `.livespec.jsonc` commits `dispatcher.auto_approve_ready`, the committed value decides the effective `admission_policy` and a stored per-item label does not override it. When the key is not committed, today's behaviour is unchanged: a stored label governs and an unlabelled item inherits the shipped default. The spec-change-tier floor is unchanged and still wins over everything. Because a label written by `set-admission` would then have no effect while the committed setting stands, that valve MUST say so in its result instead of returning a bare green.

### Motivation

Work-item bd-ib-pz7x, which records the maintainer's ruling of 2026-08-21: "the config file setting should always be respected." That ruling postdates Scenario 33 (ratified in v034, 2026-07-14), whose second case ratifies the opposite. Measured on 2026-08-21, all 14 governed repositories committed `auto_approve_ready: true`, yet 19 work-items across three tenants rested at `pending-approval` under a per-item `admission:manual` label, and each had to be flipped through the valve one at a time. A deliberate per-item hold remains available through surfaces that exist for holding: the `blocked` status, `factory_safety`, and the per-item merge hold. The spec-stated judgement that now decides the spec-change tier (§"Effective acceptance criteria") keeps design-human-gated work at `pending-approval` regardless of this change. Plan spec-implementation-lockstep R1 batch 10 routes the item here.

### Proposed Changes

In SPECIFICATION/contracts.md, section "The five policy settings", bullet "**`dispatcher.auto_approve_ready`**", replace the two sentences beginning "Per-item override: the existing `admission_policy` label" with:

> Precedence: when this repository's `.livespec.jsonc` commits `dispatcher.auto_approve_ready`, the committed value decides the item's effective `admission_policy` (`true` ⇒ `auto`, `false` ⇒ `manual`) and a stored per-item `admission_policy` label MUST NOT override it. When the key is not committed, the stored per-item label governs, and an item carrying no label inherits the shipped default.

In the same section, in the bullet describing the permission settled at the `approve` transition (the sentence beginning "governed by the item's effective `admission_policy` (`item.admission_policy`, with `None` inheriting the global"), replace the parenthetical with "(resolved per §\"The five policy settings\" → `dispatcher.auto_approve_ready`: a committed setting wins over a stored label; otherwise the stored label governs and `None` inherits the shipped default)".

In SPECIFICATION/contracts.md, section "`drive`", immediately after the paragraph that lists `set-admission:<work-item-id>:auto|manual` among the policy-edit actions, add: "When this repository commits `dispatcher.auto_approve_ready`, the valve still writes the label, and its result MUST state that the committed setting decides the item's effective admission while it stands, naming that setting and its value; it MUST NOT report the write as changing the item's admission."

In SPECIFICATION/scenarios.md, in "## Scenario 33 — auto_approve_ready governs admission and a per-item label wins", rename the heading to "## Scenario 33 — auto_approve_ready governs admission, and a committed setting wins over a per-item label" (tests/heading-coverage.json MUST rename its entry in the same revise), and replace the scenario "A per-item manual label beats the permissive global" with:

```gherkin
  Scenario: A committed permissive setting beats a stored per-item manual label
    Given dispatcher.auto_approve_ready is committed as true in the repository configuration
    And a routine `pending-approval` item carrying an explicit admission_policy label of manual
    When the Dispatcher reaches it
    Then its effective admission_policy is auto and it is approved into `ready` without a human
    And the auto-approval is journaled with the item id and the committed setting that governed it

  Scenario: A per-item label governs where the setting is not committed
    Given the repository configuration does not commit dispatcher.auto_approve_ready
    And a `pending-approval` item carrying an explicit admission_policy label of auto
    When the Dispatcher reaches it
    Then its effective admission_policy is auto and it is approved into `ready`

  Scenario: set-admission reports that a committed setting decides admission
    Given dispatcher.auto_approve_ready is committed as true
    When the operator invokes set-admission:<work-item-id>:manual
    Then the label is written and the result states that the committed setting decides the item's admission while it stands
```

Add the following line to the Background of Scenario 33 so the unlabelled case states its premise: "And the repository configuration commits that value".
