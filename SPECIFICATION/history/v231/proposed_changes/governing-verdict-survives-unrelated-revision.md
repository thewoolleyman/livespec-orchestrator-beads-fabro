---
topic: governing-verdict-survives-unrelated-revision
author: claude-opus-5-5
created_at: 2026-10-26T21:33:27Z
---

## Proposal: A governing-heading verdict survives a spec revision that leaves its selected clauses unchanged

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Narrow 'a new revision invalidates every earlier verdict' for governing-heading verdicts: the verdict's spec identity is the set of clauses the judgement placed before its model, with their headings and bodies. After a revision the Dispatcher re-runs the selection and reuses the verdict only when the same clauses come back unchanged. A change to a selected clause, to the selection, or to the item's Definition of Done takes it again. Work-item classifications keep whole-revision invalidation.

### Motivation

Coordinator gitops-fleet-capacity-monitoring routed this clause spec-first as ruling R64 (high priority, Anthropic spend) for work-item bd-ib-k5qp5z of plan anthropic-burn-mitigation (epic bd-ib-b2jzxw). Today "The spec-stated judgement is one shared component" says "A new revision under `<spec-root>/history/` invalidates every earlier verdict". This repository cut 12 spec revisions in the 24 hours to 2026-10-26T21Z, so every pending item's governing-heading verdicts were re-taken about twice an hour, each a model call, although almost every revision touched clauses unrelated to the assertion judged. The verdict depends only on the assertion and the clauses its judgement placed before the model, and that selection is a free lexical retrieval the Dispatcher can repeat without a model. Keying reuse on that selection and its bodies keeps the existing guarantee: a ratification that adds or changes the clause a held spec-change-tier item waits for changes the selection, so the release judgement still runs against the ratified text. Work-item classifications judge the whole goal against the whole specification and keep whole-revision invalidation. Rider and Definition-of-Done changes still invalidate through the input, as before.

A first independent read-only Codex review raised two blockers, both folded in. First, the selection can leave out the very clause a held item waits for, so the release judgement now never reuses a verdict taken before the latest revision. Second, the verdict depends on more than the selected bodies, so the identity also includes every clause the verdict names, and the narrowing is scoped to the governing-heading component. Codex also noted the selection must be deterministic, and that is now required.
A second pass found the reuse scenario's premises too loose; they now exclude a held release, a changed input, a changed named clause and a record without clause provenance.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, paragraph "**The spec-stated judgement is one shared component.**", replace the sentence

```
A new revision under `<spec-root>/history/` invalidates every earlier verdict, so the judgement that releases a held spec-change-tier item always runs against the ratified specification.
```

with

```
A new revision under `<spec-root>/history/` invalidates every earlier work-item classification. For a governing-heading verdict, the spec identity is narrower; this narrowing applies to the governing-heading component alone, and the enclosing Definition-of-Done judgement keeps the spec identity of "One rubric, one subject". The identity is the set of clauses the judgement placed before its model in full, together with every clause the verdict names, each with its heading and body. The selection of those clauses MUST be a deterministic function of the item's subject and the specification text, and before reusing a verdict after a new revision the Dispatcher MUST repeat that selection against the new revision. It MUST reuse the verdict only when the newly selected clauses, and every clause the verdict names, are exactly those the verdict was judged against, with unchanged headings and bodies. A revision that adds, removes or changes any of those clauses, or that changes which clauses are selected, therefore invalidates the verdict. A revision that leaves them all unchanged does not, even when it adds, removes or changes clauses elsewhere, including headings the prompt listed without their bodies. A change to the item's Definition of Done changes the verdict's input and invalidates it, as a rider does. A recorded verdict that does not carry the clauses it was judged against is invalidated by every new revision. The judgement that decides whether to release a held spec-change-tier item MUST NOT reuse a verdict taken before the latest revision; it always runs against the ratified specification.
```

2. In `SPECIFICATION/scenarios.md`, inside the gherkin block of "## Scenario 206 — The spec-change tier is decided by the spec-stated judgement, and a feature waits for ratification", append after its last scenario, "A citation that does not govern is remedied with the judgement's heading":

```gherkin

  Scenario: A spec revision that leaves the selected clauses unchanged reuses the governing-heading verdict
    Given an assertion whose governing-heading verdict is recorded with the selected clauses and every clause it names, each with its heading and body
    And the item is not a held spec-change-tier item awaiting release
    And neither the assertion, the item's Definition of Done nor the item's comments have changed since the verdict was taken
    And a new spec revision changes only clauses that the verdict neither selected nor names, and the selection against the new revision returns the same clauses
    When the governing-heading verdict is needed again
    Then the recorded verdict is reused and no model is run

  Scenario: A spec revision that changes a selected clause takes the governing-heading verdict again
    Given an assertion whose governing-heading verdict was taken against a set of selected clauses
    And a new spec revision changes the body of one of those clauses, or the selection against it returns a different set
    When the governing-heading verdict is needed again
    Then the verdict is taken again against the new revision

  Scenario: The release of a held spec-change-tier item never reuses a verdict across a revision
    Given a held spec-change-tier item whose linked proposal is ratified in a new revision
    And the selection against the new revision returns the same clauses as before
    When the next drain pass decides whether to release the item
    Then the governing-heading verdict is taken again against the new revision
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.
