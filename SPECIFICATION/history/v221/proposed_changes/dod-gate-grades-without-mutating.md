---
topic: dod-gate-grades-without-mutating
author: claude-opus-5-5
created_at: 2026-10-25T20:17:38Z
---

## Proposal: The dod_gate node grades without modifying the tree

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State that the `dod_gate` node is an adjudication node that grades the Definition of Done and changes nothing. It MUST NOT modify the sandbox working tree, create a commit, or run the repository's declared check suite. Its turn MUST leave the working tree clean and HEAD at the commit the node started on. A turn that modifies either MUST end the node failed with a reason naming the mutation, and route through its existing Blocked edge to `needs_human` rather than proceeding to `implement`. The node's rendered prompt MUST state this boundary.

### Motivation

The `dod_gate` clause in §"Self-contained plugin dispatch" says what the node MUST verify and how its findings end the run, but nothing says the node may not change the tree. A ratified heading stating that rule is what a Definition of Done for its enforcement needs to cite. Measured 2026-10-25 on petri, run 01M5SWSTWJZBAG194Q8NHS2RGB (work-item bd-ib-nz4av6): the `dod_gate` turn on codex-acp gpt-5.6-terra high IMPLEMENTED the item instead of grading it. Its 165 tool calls include 'Editing files', 'uv run ruff format tests/integration/...', and dozens of polling loops over `just check`, lefthook and `git commit`. It ran two full 30-minute turns (the second was the `max_retries=1` retry) and cost about one sandbox-pod hour before reaching needs-human. The other seven `dod_gate` turns in the same window took 0.7-1.6 minutes, so this is a role-boundary failure, not slowness. The implementing work-item bd-ib-al54tl was held at its launch-time preflight because its assertions cite no heading that states this rule.

### Proposed Changes

In SPECIFICATION/contracts.md §"Self-contained plugin dispatch", in the **`dod_gate`.** paragraph, insert the following sentences after the sentence ending "...is incoherent.":

The node is an adjudication node: it grades the Definition of Done and changes nothing. It MUST NOT modify the sandbox working tree, create a commit, or run the repository's declared check suite, and its turn MUST leave the working tree clean and HEAD at the commit the node started on. A `dod_gate` turn that modifies the working tree or HEAD MUST end the node with a failed outcome whose failure reason names the mutation, routing through the node's existing Blocked edge to `needs_human` rather than proceeding to `implement`; no new edge, state transition or exit code is introduced. The prompt the node renders MUST state this boundary to the agent.

In SPECIFICATION/scenarios.md, inside the existing `## Scenario 131 — The Definition of Done gate admits a coherent item, refuses a malformed one host-side, and rests an incoherent one at needs-human` gherkin block, append this scenario (no new H2 heading, so tests/heading-coverage.json is unchanged):

```gherkin
  Scenario: A dod_gate turn that edits or commits fails the gate
    Given a dispatched work-item whose dod_gate turn edits a file in the sandbox working tree or creates a commit
    When the dod_gate turn ends
    Then the dod_gate node ends with a failed outcome whose failure reason names the mutation
    And the run does not enter the implement node
    And the Dispatcher rests the item at blocked / needs-human

  Scenario: A dod_gate turn that only grades leaves the tree unchanged
    Given a dispatched work-item whose dod_gate turn grades the Definition of Done and makes no change
    When the dod_gate turn ends
    Then the sandbox working tree is clean and HEAD equals the commit the node started on
    And the run proceeds to implement exactly as before
```
