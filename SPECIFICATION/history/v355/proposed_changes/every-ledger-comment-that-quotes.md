---
topic: every-ledger-comment-that-quotes
author: claude-fable-5-2
created_at: 2026-11-11T17:04:23Z
---

## Proposal: A ledger comment that quotes specification text carries each goal-template opener in bracket form

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Every orchestrator writer that appends a ledger comment quoting specification text passes the quote through the one shared goal-template opener rewrite first, so no such comment puts a goal-template opening delimiter on the ledger. The rewrite is opener-only: it never strips, truncates or bounds, and a quote with no opener is unchanged.

### Motivation

Spec v330 defines the opener rewrite for the goal render only, and says the specification carries no delimiter literally because a judgement quoting a clause would copy it into a comment. It puts no obligation on the writers. A rule-K scan on 2026-11-09 found one live clause fleet-wide that writes a delimiter literally (openbrain, constraints.md, under Required secrets) and several hundred lines in history snapshots (livespec 201, this repository 88, openbrain 5, resume 1), so a judgement that quotes such text still writes the delimiter onto an append-only record. Until the goal render's rewrite ships (work item bd-ib-cfgtlo) that comment makes the item undispatchable; after it ships, every other reader of the ledger still inherits the delimiter. On 2026-11-11 livespec-dev-tooling-2zotza became undispatchable through a comment that quoted an opener. legacy-coordinator-agent ruled on 2026-11-09 to fix the writer rather than each specification. This proposal describes the delimiters in words and carries none literally. Carries work item bd-ib-engf4h (plan goal-template-opener-handling, epic bd-ib-fe3zrm); its spec-change tier record links this topic.

### Proposed Changes

In `SPECIFICATION/contracts.md`, section "### A goal-template opener is neutralized in a comment and refused in a field", after the paragraph that begins "**The dispatch-time goal-template preflight.**", add this paragraph:

**A writer that quotes specification text writes the bracket form.** Every orchestrator writer that appends a ledger comment quoting text read from a specification tree MUST pass each quoted span through the goal-template opener rewrite defined above before the write, so the comment it appends carries no goal-template opening delimiter. The quoted text covered is clause bodies, heading text and scenario text, whether read from the live specification files or from a `history/` snapshot. The writers covered include the Definition-of-Done finding that names a governing heading, the Definition-of-Done clause record, the spec-stated judgement records that carry a selected or named clause, and the comment that records a `dod_gate` refusal; the obligation is on the class, so a writer added later that quotes specification text is covered without being listed here. Every such writer MUST call ONE shared function for the rewrite, the same function the goal render uses, and MUST NOT carry a rewrite of its own. The rewrite MUST leave a quote that carries no goal-template opening delimiter byte-for-byte unchanged, and MUST NOT strip, truncate, bound or escape the quoted text. A digest that a record carries over clause text MUST be computed over the text as read from the specification, before the rewrite, so the rewrite never changes a verdict-reuse key. A reader that compares a recorded quote against the specification MUST compare it against the specification text passed through the same rewrite, so a record whose quote was rewritten still matches the clause it quotes. This obligation is defence in depth beside the goal render's own rewrite: the render keeps a comment from refusing a dispatch, and the writer keeps the delimiter off the ledger record, where every other reader of the ledger would otherwise inherit it.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario <next free number> — A ledger comment that quotes specification text carries each goal-template opener in bracket form

Governing clause: `contracts.md` §"Dispatcher policy settings" → "A goal-template opener is neutralized in a comment and refused in a field".

```gherkin
Feature: A judgement that quotes a specification clause cannot copy a template opener onto the ledger
  As an operator whose specification, or one of its history snapshots, carries a goal-template opening delimiter
  I want every comment that quotes that text to carry the bracket form
  So that the ledger record itself is free of the delimiter for every reader

  Scenario: a governing-heading finding quotes a clause that carries an opener
    Given a specification clause K whose body carries a goal-template opening delimiter
    And a work item W whose Definition of Done judgement names K's heading as governing and omitted
    When the finding that quotes K is appended to W as a ledger comment
    Then the comment carries K's quoted text whole and untruncated with every opening curly brace of each delimiter replaced by an opening square bracket
    And the comment carries no goal-template opening delimiter

  Scenario: a clause record and a dod_gate refusal comment quote the same clause
    Given a specification clause K whose body carries a goal-template opening delimiter
    When a Definition-of-Done clause record quoting K and a comment recording a dod_gate refusal that quotes K are each appended to a work item
    Then each comment carries the quote in bracket form and no goal-template opening delimiter
    And the clause digest each record carries equals the digest of K as read from the specification

  Scenario: a clause with no opener is quoted verbatim
    Given a specification clause Q whose body carries no goal-template opening delimiter
    When a ledger comment quoting Q is appended to a work item
    Then the quoted text in the comment is byte-for-byte Q's text
```

The revise that accepts this proposal MUST add the new scenario heading to `tests/heading-coverage.json` in the same change (the `test` value MAY be the literal `TODO` with a reason naming work item bd-ib-engf4h, which owns the scenario).
