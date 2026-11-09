---
topic: filing-flags-a-definition-of
author: claude-opus-5-5 (spec-implementation-lockstep, session 70ee70cb)
created_at: 2026-11-09T16:04:27Z
---

## Proposal: A Definition of Done that permits a TODO heading-coverage row against a shrink-only debt register is a mechanical filing finding

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add one kind to the MECHANICAL filing-time Definition-of-Done findings in contracts.md §"Effective acceptance criteria". The finding fires when the item's repository carries a committed tests/heading-coverage-debt.json and a bullet of the item's Definition of Done section names tests/heading-coverage.json and the token TODO. Such a bullet offers a TODO row the shrink-only register refuses, so the item cannot be completed as written. A new scenario exercises the finding: display, ledger comment, pending-approval under auto admission, approve refusal, and release after the edit, plus the no-register case.

### Motivation

On 2026-11-08 plan spec-implementation-lockstep filed three consumer repairs (overseer-lx5l7i, bd-ib-5a222e, livespec-qke72f) whose Definitions of Done allowed a coverage row to be 'set to TODO with a reason'. All three repositories carry tests/heading-coverage-debt.json as a shrink-only ratchet. check-heading-coverage-debt-register refuses any TODO row whose key the register does not already hold (unregistered_todo), with one exception: spec-first admission of a heading a spec revision adds, which an implementation item never does. overseer-lx5l7i's factory run 01M70F5YKC8K took the option for five rows and ended BLOCKED on four unregistered_todo findings, after fix and janitor both failed. The defect was in the filed text, so filing is where it should be caught, exactly as Scenario 334 catches a goal-template opener. legacy-coordinator-agent ruled that the lesson be made mechanical rather than left in a handoff (2026-11-09; work item bd-ib-cm2k55).

### Proposed Changes

In contracts.md §"Effective acceptance criteria", the paragraph opening "The findings divide in two." MUST list one further MECHANICAL kind beside the goal-template opener: an unsatisfiable coverage escape. The detection MUST be deterministic and MUST NOT call a language model. The finding MUST fire when BOTH of these hold: (a) the repository the filing front-end runs against carries a committed `tests/heading-coverage-debt.json` at its project root; and (b) one `- ` bullet of the item's `## Definition of Done` section contains both the literal path `tests/heading-coverage.json` and the whole-word token `TODO`. The finding MUST quote that bullet. It MUST name `tests/heading-coverage-debt.json` as the shrink-only register that refuses a `TODO` row whose key it does not already hold. Its remedy MUST name the description as the field to edit and MUST say that each row the bullet governs must name an existing test. Like every mechanical finding, it MUST be displayed by `filing_display`, MUST be recorded on the item as a `definition-of-done finding (mechanical):` ledger comment, and MUST withhold `ready`: an item filed with it outstanding MUST NOT be routed to `ready` by intake, even when its effective `admission_policy` is `auto`. The existing `approve` rule for an auto-admission item held by intake, which re-runs the intake Definition-of-Done check against the item's current text, MUST apply to this finding unchanged. Where the repository carries no committed `tests/heading-coverage-debt.json`, the same bullet MUST NOT produce this finding. Bullets outside the `## Definition of Done` section, and the legacy acceptance-criteria field, MUST NOT be read for it. The rule is lexical by design. A bullet that names the token only to exclude it (for example "names an existing test, never `TODO`") still produces the finding. Its remedy is the same edit: state the requirement without the token, as "names an existing test that exercises that row's heading" does.

scenarios.md MUST gain one scenario, numbered as the next free scenario number at revise time, headed "A Definition of Done that permits a TODO coverage row against a shrink-only debt register is a mechanical filing finding", with governing clause `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Effective acceptance criteria":

```gherkin
Feature: An unsatisfiable coverage escape is caught at filing, not at the run's last gate
  As an operator filing a coverage-repair work item
  I want a TODO escape that the debt register will refuse reported where it was written
  So that no factory run spends its budget taking an option no merge can accept

  Scenario: the filing display reports the bullet and approve refuses until it is edited
    Given a repository whose project root carries a committed tests/heading-coverage-debt.json
    And a work item W filed through the capture filing seam whose Definition of Done section has a bullet naming tests/heading-coverage.json and allowing a row to be set to TODO, and which otherwise carries no mechanical finding
    Then filing_display reports a (mechanical) finding that quotes that bullet and names tests/heading-coverage-debt.json as the shrink-only register
    And W carries that finding as a definition-of-done finding (mechanical) ledger comment
    And W rests at pending-approval even when its effective admission_policy is auto
    And an approve of W leaves it at pending-approval with a result naming the finding
    And once the bullet is edited to require an existing test for every row, an approve of W routes it onward as it would any other item

  Scenario: no register, no finding
    Given a repository whose project root carries no tests/heading-coverage-debt.json
    When the same work item is filed there
    Then filing_display reports no debt-register finding for that bullet
```

The revise that ratifies this MUST add a spec-first `tests/heading-coverage.json` row for the new scenario heading (test `TODO`, work_item `bd-ib-cm2k55`, reason naming bd-ib-cm2k55 as the owner of the integration-tier test), per the repository's revise co-edit discipline.
