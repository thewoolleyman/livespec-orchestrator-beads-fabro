---
topic: a-spec-change-tier-verdict
author: claude-opus-5-5
created_at: 2026-11-02T21:04:38Z
---

## Proposal: Reuse the spec-change tier decision across a revision that leaves its judged clauses unchanged

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend the clause-provenance reuse rule that governing-heading verdicts already use to the spec-change tier decision, so an item's tier verdict is reused across a spec revision that leaves the clauses it was judged against unchanged, instead of being re-taken by a model on every dispatch path after any revision anywhere in the tree.

### Motivation

Measured 2026-11-02 on livespec-dev-tooling-m2x5pt (radar readiness reader): its spec-change tier read `stated` at filing against spec v114 (16:41:56Z) and `partial` on its dispatch path against v115 (19:54:21Z), with the same behaviour digest, and the dispatch refused it pre-claim as an unratified topic. The v114->v115 revision did not touch `## Maintainer radar`, the clause both verdicts cite; it only added `## Interactive fleet seat profile` and its scenario. The flip is a re-roll of a nondeterministic model verdict, caused by an unrelated revision. The current text states that every new revision invalidates every earlier classification, and the implementation keys tier reuse on (spec version, behaviour digest), so every revision anywhere re-takes every pending item's tier on its next dispatch path, and a borderline item can be refused after it was admitted with no change to the clause that governs it. The governing-heading verdict already got this exact narrowing (bd-ib-k5qp5z, closed), and the release-spec-tier attestation already survives unrelated revisions; the tier decision is the one verdict left on whole-tree identity. Root-fix work-item: bd-ib-otl2ey (plan spec-implementation-lockstep, epic bd-ib-ax3rds), routed by legacy-coordinator-agent. The release judgement for a held item keeps its always-run-against-the-latest-revision rule, so ratification still releases a hold only on a fresh judgement.

### Proposed Changes

Two edits, one in each target file. Both keep every other sentence of the edited paragraph unchanged.

**1. `SPECIFICATION/contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance" → "The spec-stated judgement is one shared component".**

Replace the two sentences

> For a work-item classification, the input is the subject's goal. A new revision under `<spec-root>/history/` invalidates every earlier work-item classification.

with

> For a work-item classification, the input is the subject's goal. The spec-change tier decision of "An autonomy tier is assigned" — the item's classification taken together with the verdict on its asked-for behaviour — has as its input the asked-for behaviour statement, and its spec identity is the clause provenance defined below for a governing-heading verdict: the set of clauses the judgement placed before its model in full, together with every clause the verdict names, each with its heading and body. Every spec-change tier record appended at filing, at groom or on a dispatch path MUST carry that clause provenance. A tier decision MUST be reused across a new revision under `<spec-root>/history/` exactly when a governing-heading verdict would be: the asked-for behaviour statement is unchanged, the selection repeated against the new revision returns the same clauses, and every clause the verdict names is unchanged in heading and body. Classifying an item "again on every dispatch path" is satisfied by that reuse and does not require a new model judgement. A recorded tier decision that does not carry the clauses it was judged against is invalidated by every new revision.

and replace

> For a governing-heading verdict, the spec identity is narrower; this narrowing applies to the governing-heading component alone, and the enclosing Definition-of-Done judgement keeps the spec identity of "One rubric, one subject".

with

> For a governing-heading verdict, the spec identity is narrower; this narrowing applies to the governing-heading component and to the spec-change tier decision above, and the enclosing Definition-of-Done judgement keeps the spec identity of "One rubric, one subject".

The sentence "The judgement that decides whether to release a held spec-change-tier item MUST NOT reuse a verdict taken before the latest revision; it always runs against the ratified specification." is kept unchanged, so a hold is still released only on a judgement taken against the latest revision.

**2. `SPECIFICATION/scenarios.md`, `## Scenario 206 — The spec-change tier is decided by the spec-stated judgement, and a feature waits for ratification`.**

Insert these two scenarios immediately before the existing "Scenario: The release of a held spec-change-tier item never reuses a verdict across a revision" block, inside the same gherkin fence. No `## ` heading is added or changed, so `tests/heading-coverage.json` needs no edit.

```gherkin
  Scenario: A spec revision that leaves the judged clauses unchanged reuses the spec-change tier decision
    Given a feature whose spec-change tier record reads verdict stated and carries the clauses its verdict was judged against and every clause it names, each with its heading and body
    And the item's asked-for behaviour is unchanged since the record was taken
    And a new spec revision changes only clauses that the verdict neither selected nor names, and the selection against the new revision returns the same clauses
    When the item reaches a dispatch path
    Then the recorded tier decision is reused, no model is run, and the item is not held

  Scenario: A spec revision that changes a judged clause takes the spec-change tier decision again
    Given a feature whose spec-change tier record carries the clauses its verdict was judged against
    And a new spec revision changes the body of one of those clauses, or the selection against it returns a different set
    When the item reaches a dispatch path
    Then the tier decision is taken again against the new revision
```

