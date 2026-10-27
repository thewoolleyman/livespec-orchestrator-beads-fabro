---
topic: review-stage-read-only
author: claude-opus-5-5
created_at: 2026-10-27T13:23:01Z
---

## Proposal: The review stage is read-only on the run branch and runs no whole-suite check, and still records its verdict after a refusal

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

In the proof workflow paragraphs of 'Self-contained plugin dispatch': the sandbox refuses, within seconds and before any hook starts, every review-turn command that moves or edits the run branch, so the head is unchanged. It refuses a whole-suite check invocation with a message to run named test ids only. The review prompt states its grading contract, and each refusal is returned to the turn so it can still record its verdict label within its allowance. Scenario 20 gains two cases. This is the review-stage sibling of proof_capture's read-only contract (bd-ib-ytrpb5).

### Motivation

Spec-first for bd-ib-azxvoo (coordinator ruling R127; routed by petri-factory-on-gmktec). Its launch-time screen at 10:22Z found all four assertions incoherent with the referenced sections, which govern review of the latest captured record and the unlabeled-turn retry but give the review stage no read-only branch boundary, no whole-suite prohibition, no instruction contract, and no rule that a refused turn still records its verdict. Evidence: bd-ib-davaxq run 01M5Y3EGXZSS, where review@2 ran a rebase and `just check` and timed out at 1800 s with no verdict.

### Proposed Changes

No `## ` heading changes, so `tests/heading-coverage.json` needs no co-edit. The diff below is the whole change.

```diff
diff --git a/SPECIFICATION/contracts.md b/SPECIFICATION/contracts.md
index e87db9035..1a5249d48 100644
--- a/SPECIFICATION/contracts.md
+++ b/SPECIFICATION/contracts.md
@@ -3782,6 +3782,7 @@ latest captured record alongside the code; because `review_fix`
 re-enters `janitor`, every accepted fix round re-enters `publish_draft`
 and `proof_capture` before `review`, so the record `review` reads is
 normally current.
+`review` is read-only on the run branch. The sandbox, not the prompt alone, MUST refuse within seconds, before any repository hook starts, every command a `review` turn runs that moves or edits the run branch, such as `git rebase`, `git commit`, `git push` or `git reset`, so the run branch's head after the turn equals its head before it. It MUST likewise refuse a `review` turn's invocation of the whole declared check suite, whether `just check` or the sandbox check-suite runner, with a message telling the reviewer to run named test ids only. The `review` prompt MUST state that the reviewer grades the published diff and the latest captured record, makes no branch edits, runs no whole-suite check, and ends with its verdict label within its turn allowance, and each refusal MUST be returned to the turn as a refusal, so that a turn that attempted a refused command can still record its verdict label within that allowance.
 
 A blocking review finding whose subject is the latest captured record
 rather than the tree is a PROOF-RECORD finding. Each of these is one: a
diff --git a/SPECIFICATION/scenarios.md b/SPECIFICATION/scenarios.md
index 2a5221a3e..b2f5b90e7 100644
--- a/SPECIFICATION/scenarios.md
+++ b/SPECIFICATION/scenarios.md
@@ -406,6 +406,18 @@ Feature: A senior-engineer review gate reviews a green build before the PR stage
     Then it queries the structured Fabro event stream for that run
     And it emits a `livespec-dispatcher` span carrying `review.verdict`, `review.fix_rounds`, `review.hit_cap`, and `pr.shipped_on_cap`
     And a review-to-PR fallthrough at the review cap is queryable as `pr.shipped_on_cap=true`
+
+  Scenario: A review turn cannot move the run branch or run the whole check suite
+    Given a review turn in the implement-work-item workflow
+    When the turn runs git rebase, git commit or git push, or invokes the whole declared check suite
+    Then the sandbox refuses the command within seconds, before any repository hook starts
+    And the suite refusal tells the reviewer to run named test ids only
+    And the run branch's head after the turn equals its head before it
+
+  Scenario: A review turn that attempted a refused command still records its verdict
+    Given a review turn that attempted a refused command
+    When the turn continues after the refusal
+    Then it records its verdict label within its turn allowance rather than ending on the turn timeout
 ```
 
 ## Scenario 21 — Codex plugin discovery and full-access posture
```

