---
topic: dod-subject-clause-identity
author: claude-opus-5-5
created_at: 2026-10-26T22:28:42Z
---

## Proposal: The Definition-of-Done subject takes its spec identity from the governing-heading verdicts' clause provenance

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

In 'One rubric, one subject', the SPEC IDENTITY component of the Definition-of-Done subject becomes the clause provenance of the governing-heading verdicts the taking uses (v231), so a spec revision outside those clauses no longer changes the subject digest and re-runs the full grading. It falls back to the whole-tree digest when any assertion's governing verdict did not run or carries no provenance, and for a held spec-change-tier item's release.

### Motivation

Requested by the anthropic-burn-mitigation seat (plan bd-ib-b2jzxw) after v231, and ratified under the coordinator's standing ruling R67. v231 lets a governing-heading verdict survive a spec revision that leaves its selected clauses unchanged, but the Definition-of-Done subject digest still embeds a digest of the WHOLE governed spec tree (the SPEC IDENTITY component of "One rubric, one subject"; judgement_subject_digest in _dispatcher_dod_judgement.py hashes spec_tree_identity). So every revision still changes every item's subject digest and re-runs the full Definition-of-Done grading: 12 times in the last day, about 14% of claude -p spend by token-spend-analysis. The whole-tree identity exists because the governing-heading verdict reads the whole tree; v231 gives that verdict a precise provenance, so the subject can key on the same clauses. The referenced headings' bodies are already a separate subject component. A whole-tree fallback is kept where no provenance exists, and for the held spec-change-tier release judgement, which v231 already forbids from reusing.
A first read-only Codex review raised four blockers, folded in: governing verdicts are established before the subject digest is computed and the reuse lookup made; the pre-dispatch taking records its SPEC IDENTITY and the dod_gate node computes its digest from it, preserving the disagreement binding; provenance is encoded per assertion, keeping selected and named clauses apart so a selection change always changes the digest; and Scenario 239's unreferenced-scenario step is narrowed to an addition that changes an assertion's selection.
A second pass required the stability sentence to speak of the SPEC IDENTITY component rather than the whole subject, and the reuse scenario to hold the other components unchanged; that is folded in.
The configured ratification reviewer (opus) then raised three blockers, folded in: the dod_gate node uses the whole-tree digest when the pre-dispatch judgement did not run; the pre-dispatch taking records its SPEC IDENTITY in the dispatch journal (and in its record when it appends one), on the reuse path too; and a digest-only surface such as drain enumeration takes no governing verdict and treats a missing one as a differing digest.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, §"Effective acceptance criteria" → "One rubric, one subject", replace the SPEC IDENTITY bullet

```
- The SPEC IDENTITY: a digest of the bytes of every file under the governed spec root at the resolved commit, excluding `proposed_changes/` and `history/`, so that a ratified revision or any change to a governing scenario, referenced or not, changes it.
```

with

```
- The SPEC IDENTITY: the CLAUSE PROVENANCE of the governing-heading verdicts the taking uses for the subject's assertions (§"Dispatcher admission, WIP cap, and post-merge acceptance" → "The spec-stated judgement is one shared component"), kept per assertion: for each assertion, the clauses its verdict was judged against and, separately, every clause that verdict names, each with its heading and body. A ratified revision that changes any of those clauses, or that changes which clauses any assertion's selection returns or its verdict names, therefore changes the SPEC IDENTITY, and a revision that leaves them all unchanged leaves the SPEC IDENTITY unchanged; the other subject components change the subject digest exactly as before. When any of the subject's assertions has a governing-heading verdict that did not run or carries no clause provenance, and for the judgement that decides whether to release a held spec-change-tier item, the SPEC IDENTITY is instead the WHOLE-TREE DIGEST: a digest of the bytes of every file under the governed spec root at the resolved commit, excluding `proposed_changes/` and `history/`. A host taking therefore establishes each assertion's governing-heading verdict before it computes the subject digest: it reuses each recorded verdict that verdict's own reuse rule allows, which runs no model, and takes the others. A surface that only compares a subject digest and is not a taking, such as drain candidate enumeration or a `needs-attention` hygiene fact, MUST NOT take a governing-heading verdict: it uses only recorded verdicts that their reuse rule allows, and when any assertion has none, the digest it compares is treated as differing from every record. The pre-dispatch taking MUST record the SPEC IDENTITY it used, with its form and its clause provenance, in the dispatch journal, and in its judgement record when it appends one, and MUST supply them to the run, whether it reused a record or appended one. The `dod_gate` node MUST compute its subject digest from that supplied identity rather than from verdicts of its own, so that the node's outcome and the matching host record compare on one digest, and the node still runs. When the run was supplied no SPEC IDENTITY, because the pre-dispatch judgement did not run, the node uses the WHOLE-TREE DIGEST at the resolved commit.
```

2. In the same section's encoding paragraph, replace

```
the SPEC IDENTITY is itself a SHA-256 over the included files sorted by their path relative to the spec root, each contributing its path, a NUL byte, its byte length in ASCII decimal, a NUL byte and its bytes;
```

with

```
the SPEC IDENTITY is the ASCII prefix `clauses:` followed by the CLAUSE PROVENANCE digest, or `tree:` followed by the WHOLE-TREE DIGEST; the CLAUSE PROVENANCE digest is a SHA-256 over the subject's assertions in Definition of Done order, each contributing its assertion text, then its selected clauses and then its verdict-named clauses as two separately length-prefixed lists, each list sorted by spec file path and then heading line, and each clause contributing its file path relative to the spec root, a NUL byte, its heading line, a NUL byte, its body's byte length in ASCII decimal, a NUL byte and its body; the WHOLE-TREE DIGEST is a SHA-256 over the included files sorted by their path relative to the spec root, each contributing its path, a NUL byte, its byte length in ASCII decimal, a NUL byte and its bytes;
```

3. In the same section, replace

```
Before running any judge, a host taking MUST look for the earliest cache-eligible record whose subject digest and rubric digest both equal its own.
```

with

```
Before running the Definition-of-Done judge, and after establishing the governing-heading verdicts its SPEC IDENTITY needs, a host taking MUST look for the earliest cache-eligible record whose subject digest and rubric digest both equal its own.
```

4. In `SPECIFICATION/scenarios.md`, Scenario 239, scenario "A change to an unreferenced governing scenario invalidates an admission verdict", replace

```
    And a scenario heading the item does not reference is added to the ratified spec tree before dispatch
    When the Dispatcher selects the item for a dispatch
```

with

```
    And a scenario the item does not reference is added to the ratified spec tree before dispatch, and the selection for one of the item's assertions now returns it
    When the Dispatcher selects the item for a dispatch
```

5. In `SPECIFICATION/scenarios.md`, inside the gherkin block of "## Scenario 240 — A recorded Definition-of-Done verdict binds every host taking on identical digests, and opposite verdicts are journaled", append after its last scenario:

```gherkin

  Scenario: A spec revision outside the governing clauses leaves the subject digest unchanged
    Given an item carrying a host record for its current digests, whose assertions' governing-heading verdicts carry clause provenance
    And the item is not a held spec-change-tier item awaiting release
    And a new spec revision changes only clauses outside that provenance and outside the headings the item references, and each verdict's selection against it returns the same clauses
    And the item's goal, the grading set and the rubric are unchanged
    When the pre-dispatch judgement judges the item
    Then the subject digest it computes equals the recorded one and the record is reused without running any judge

  Scenario: A spec revision that changes a governing clause changes the subject digest
    Given an item carrying a host record for its current digests, whose assertions' governing-heading verdicts carry clause provenance
    And a new spec revision changes the body of a clause in that provenance
    When the pre-dispatch judgement judges the item
    Then its subject digest differs from the recorded one and the judgement runs

  Scenario: Without clause provenance the subject keeps the whole-tree digest
    Given an item one of whose assertions has a governing-heading verdict that did not run
    When a host taking computes the item's subject digest
    Then its SPEC IDENTITY is the whole-tree digest and any spec revision changes it

  Scenario: The dod_gate node binds to the pre-dispatch taking's recorded spec identity
    Given a pre-dispatch taking that passed an item, whether by reusing a record or by appending one, and recorded its SPEC IDENTITY, in either form, in the dispatch journal
    When a run of the item reaches the dod_gate node
    Then the node runs and computes its subject digest from the supplied SPEC IDENTITY
    And when the node refuses the item, the dispatch journal carries a dod-judgement-disagreement row naming the run and the taking that wrote the matching record

  Scenario: A digest comparison that is not a taking runs no model
    Given a refused item one of whose assertions has no reusable governing-heading verdict after a new spec revision
    When drain candidate enumeration compares the item's subject digest with the refusing verdict's
    Then no governing-heading verdict is taken and the digest is treated as differing from the refusing verdict's
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.
