---
topic: dod-judgement-at-dispatch-wall
author: claude:hp-factory-failure-follow-ups
created_at: 2026-10-15T00:01:16Z
---

## Proposal: Run the Definition-of-Done judgement again in the pre-dispatch wall

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend the ratified pre-admission Definition-of-Done judgement so the Dispatcher also runs it before claim at dispatch time, for every implement-kind item however it reached ready, refusing with the judgement's own finding text and failing toward current behaviour when the judgement cannot run.

### Motivation

The "Judged before admission" paragraph runs the dod_gate judgement only when intake routes an item to ready from backlog or pending-approval. Items also reach ready through resolve-blocked:<id>:ready after a needs-human ending, or carry a Definition of Done edited after admission; those items reach the in-run dod_gate node with no host-side judgement. On 2026-10-14 the fleet coordinator counted 10 of 54 defective factory endings as dod_gate failures on item text, each found only after claim, sandbox build and a dod_gate node of several minutes. Two measured instances came back through the re-entry path: dolt-server-6fdarx run 01M4YC785CW8 (References line missing two governing headings, failed at dod_gate at 23:41:23Z) and bd-ib-meejjz run 01M4XN5ASP4Z (References line naming a non-scenario heading). The mechanical host-side checks did not catch this class: bd-ib-wehfpc and bd-ib-gj6amh passed filing_display with zero findings and then failed dod_gate. Implementation carrier: bd-ib-7f66ar (coordinator ruling: one item, one judgement, two call sites).

### Proposed Changes

In `SPECIFICATION/contracts.md`, insert the following paragraph immediately AFTER the "**Judged before admission.**" paragraph (before "**Kept current.**"):

> **Judged again before dispatch.** Admission is not the only route to `ready`: an item also reaches it through `resolve-blocked:<id>:ready` after a needs-human ending, and its Definition of Done MAY be edited after it was admitted. So before the Dispatcher claims an implement-kind item for a dispatch — in the pre-dispatch wall, on the single-item and the drain paths alike, whatever route brought the item to `ready` — it MUST run the same Definition-of-Done judgement the "Judged before admission" paragraph names, against the item's effective criteria as they stand at dispatch time. When that judgement would end a run through the structured needs-human ending, the Dispatcher MUST refuse the dispatch before any claim is taken and before any factory run is created, MUST name in the refusal the finding text the judgement produced, and MUST append that verdict, with each remedy, to the item as a ledger comment; the item MUST NOT be moved out of `ready` by the refusal. When the judgement admits the item, the dispatch MUST proceed exactly as it would without the judgement. When the judgement cannot be run (no eligible model, a timeout, or an unparseable verdict), the Dispatcher MUST record on the item that the pre-dispatch judgement did not run and why, and MUST proceed as it would without the judgement; the in-run `dod_gate` node remains the backstop. A Dispatcher MAY reuse a verdict already recorded for the item when the item's effective criteria and referenced headings are unchanged since that verdict was taken. Scenario 174 in `scenarios.md` exercises this paragraph.

In `SPECIFICATION/scenarios.md`, under the existing `## Scenario 174` heading (NO new `## ` heading, so `tests/heading-coverage.json` is unchanged), append these scenarios to the existing gherkin block:

```gherkin
  Scenario: An item that reached ready without admission is judged before dispatch
    Given an implement-kind item released to ready through resolve-blocked whose References line omits the scenario that governs its assertion
    When the Dispatcher selects the item for a dispatch
    Then the Definition-of-Done judgement runs before any claim is taken
    And the dispatch is refused before any factory run is created, naming the judgement's finding text
    And the verdict, with each remedy, is appended to the item as a ledger comment
    And the item remains ready
  Scenario: A judgement that cannot run before dispatch does not refuse the dispatch
    Given the pre-dispatch judgement cannot run for a selected item
    When the Dispatcher dispatches the item
    Then the dispatch proceeds as it would without the judgement
    And a ledger comment records that the pre-dispatch judgement did not run and why
```

