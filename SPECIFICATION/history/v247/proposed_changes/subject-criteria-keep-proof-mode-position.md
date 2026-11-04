---
topic: subject-criteria-keep-proof-mode-position
author: claude-opus-5-5
created_at: 2026-10-27T09:14:12Z
---

## Proposal: The judgement subject's effective criteria keep each assertion as its own bullet under its proof-mode sub-heading

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

In 'One rubric, one subject', the GOAL component's effective criteria render as a block in which each assertion is its own `- ` bullet in Definition-of-Done order, with each `### Host-captured` / `### Human-attested` sub-heading and its `Reason:` line placed exactly where the item's description places it, so every assertion's proof mode is visible by position. Scenario 239 gains one case.

### Motivation

Spec-first for bd-ib-7l6yti (coordinator gitops-fleet-capacity-monitoring ruling R112, high priority because it removes wasted dispatches). judgement_subject renders the effective criteria as a flat list with no bullet markers, no proof-mode sub-headings and no Reason lines, beside a raw description whose sub-headings position the same assertions, so the judge guesses where the proof-mode boundary falls. Measured: the dod_gate misread livespec-driver-claude-5jr2xu twice (run 01M5X80M3D0WGV5V8FA67NAWEW and a second run), placing an assertion that sits above ### Host-captured as if it were under it, and misread bd-ib-qxq4jb once. No clause governs how the subject renders this block.

### Proposed Changes

Two coordinated edits; no `## ` heading changes, so `tests/heading-coverage.json` needs no co-edit. The diff below is the whole change.

```diff
diff --git a/SPECIFICATION/contracts.md b/SPECIFICATION/contracts.md
index e87db9035..5a5e8528a 100644
--- a/SPECIFICATION/contracts.md
+++ b/SPECIFICATION/contracts.md
@@ -6450,7 +6450,7 @@ below. Scenario 140 in `scenarios.md` exercises this clause.
 
 Every taking MUST grade one SUBJECT, made of four components.
 
-- The GOAL: the item's rendered goal exactly as the Dispatcher renders it for the node — title, description, effective criteria, notes, lessons and every ledger comment except the Definition-of-Done JUDGEMENT RECORDS: each comment whose first line begins with `livespec-dod-judgement`, whichever taking or surface wrote it (verdict, did-not-run and disagreement records alike). Those records are receipts, not brief, so the Dispatcher MUST omit them from the node's rendered goal as well, and recording one MUST NOT change any subject digest.
+- The GOAL: the item's rendered goal exactly as the Dispatcher renders it for the node — title, description, effective criteria, notes, lessons and every ledger comment except the Definition-of-Done JUDGEMENT RECORDS: each comment whose first line begins with `livespec-dod-judgement`, whichever taking or surface wrote it (verdict, did-not-run and disagreement records alike). Those records are receipts, not brief, so the Dispatcher MUST omit them from the node's rendered goal as well, and recording one MUST NOT change any subject digest. Within the GOAL, the effective criteria returned by the shared primitive MUST render as a block in which each assertion is its own `- ` bullet, in source order. When the source is `description-definition-of-done`, the block MUST preserve each `### Host-captured` and `### Human-attested` sub-heading and its `Reason:` line from that section in their original positions relative to the assertions, so that every assertion's proof mode is visible by position; an assertion above every proof-mode sub-heading MUST remain above all of them. For the legacy `criteria-field` and `description-exit-criteria` sources, the block MUST render the resolved assertions without importing proof-mode sub-headings or `Reason:` lines from other description sections.
 - The HEADINGS: the verbatim body of each heading the reference line names.
 - The SPEC IDENTITY: the CLAUSE PROVENANCE of the governing-heading verdicts the taking uses for the subject's assertions (§"Dispatcher admission, WIP cap, and post-merge acceptance" → "The spec-stated judgement is one shared component"), kept per assertion: for each assertion, the clauses its verdict was judged against and, separately, every clause that verdict names, each with its heading and body. A ratified revision that changes any of those clauses, or that changes which clauses any assertion's selection returns or its verdict names, therefore changes the SPEC IDENTITY, and a revision that leaves them all unchanged leaves the SPEC IDENTITY unchanged; the other subject components change the subject digest exactly as before. When any of the subject's assertions has a governing-heading verdict that did not run or carries no clause provenance, and for the judgement that decides whether to release a held spec-change-tier item, the SPEC IDENTITY is instead the WHOLE-TREE DIGEST: a digest of the bytes of every file under the governed spec root at the resolved commit, excluding `proposed_changes/` and `history/`. A host taking therefore establishes each assertion's governing-heading verdict before it computes the subject digest: it reuses each recorded verdict that verdict's own reuse rule allows, which runs no model, and takes the others. A surface that only compares a subject digest and is not a taking, such as drain candidate enumeration or a `needs-attention` hygiene fact, MUST NOT take a governing-heading verdict: it uses only recorded verdicts that their reuse rule allows, and when any assertion has none, the digest it compares is treated as differing from every record. The pre-dispatch taking MUST record the SPEC IDENTITY it used, with its form and its clause provenance, in the dispatch journal, and in its judgement record when it appends one, and MUST supply them to the run, whether it reused a record or appended one. The `dod_gate` node MUST compute its subject digest from that supplied identity rather than from verdicts of its own, so that the node's outcome and the matching host record compare on one digest, and the node still runs. When the run was supplied no SPEC IDENTITY, because the pre-dispatch judgement did not run, the node uses the WHOLE-TREE DIGEST at the resolved commit.
 - The GRADING SET: the committed `dispatcher.sandbox_capabilities` array at that commit, as sorted names, or the literal `unpublished`.
diff --git a/SPECIFICATION/scenarios.md b/SPECIFICATION/scenarios.md
index 2a5221a3e..966848afd 100644
--- a/SPECIFICATION/scenarios.md
+++ b/SPECIFICATION/scenarios.md
@@ -9425,6 +9425,13 @@ Feature: A Definition of Done passed before dispatch is graded in-run by the sam
     When the pre-dispatch Definition-of-Done judgement is taken
     Then the taking follows its did-not-run route
     And its record names no deciding candidate and lists each candidate the bound ended
+
+  Scenario: The subject's effective criteria keep each assertion's proof-mode position
+    Given an item whose Definition of Done lists one assertion above every proof-mode sub-heading and one under a Host-captured sub-heading with its Reason line
+    When any taking renders the item's judgement subject
+    Then the effective criteria render each assertion as its own bullet in Definition-of-Done order
+    And the first assertion renders above every proof-mode sub-heading
+    And the second renders under the Host-captured sub-heading with its Reason line
 ```
 
 ## Scenario 240 — A recorded Definition-of-Done verdict binds every host taking on identical digests, and opposite verdicts are journaled
```

