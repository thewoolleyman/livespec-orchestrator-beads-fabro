---
topic: turn-waits-for-runner-commit
author: claude-opus-5-5
created_at: 2026-10-27T13:19:35Z
---

## Proposal: A turn that ends with a runner commit still running waits for its verdict, and a runner-recorded refusal counts as the turn's refused commit attempt

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

In 'An implement turn that ends incomplete does not succeed': except on a node-timeout cut, before an implement, fix or review_fix stage's outcome is decided, the run waits until every commit run the turn started through the detached commit runner is terminal. The wait consumes no retry budget, its mechanism is left open, and the agent's end-of-turn obligation is unchanged. A latest attempt made through the runner counts as refused when its commit run reached failed with the hook having named a failed target. Its failed targets and hook error lines come from the full recorded output, and a no-verdict run makes the brief state that no commit was made. The non-runner staged-changes definition is kept for non-runner attempts. Scenario 204 gains two cases.

### Motivation

Spec-first for bd-ib-xj3qqb and bd-ib-jzuryr (coordinator ruling R113, urgent; requested by sandbox-commit-gate-ceiling). Measured on v0.243.13/.14: six partial-progress endings mid-hook (64eyd5, atyefi, mfzvdl, c6va2d, wg5zyt, opd3hq; run 01M5Y1P5DD1V's last call was a runner wait with no recorded exit). Two runner-recorded refusals were not counted as refused attempts (bd-ib-k5qp5z run 01M5Y124CVY7, and bd-ib-onrjh3 run 01M5Y465PP3J at 09:21Z), because the paragraph defined a refused attempt only by changes left staged. Two read-only gpt-6-astra rounds: round 1 raised two blockers (the node-timeout carve-out and the overlapping refused-attempt definitions), both folded in; round 2 returned NO BLOCKERS.

### Proposed Changes

No `## ` heading changes, so `tests/heading-coverage.json` needs no co-edit. The diff below is the whole change.

```diff
diff --git a/SPECIFICATION/contracts.md b/SPECIFICATION/contracts.md
index e87db9035..b38eae825 100644
--- a/SPECIFICATION/contracts.md
+++ b/SPECIFICATION/contracts.md
@@ -3348,7 +3348,7 @@ priority".
 
 **Publication is mechanically confined to the scripted publication stages.** The second rule above MUST NOT rest on prompt prose alone; an agent stage MUST be unable to publish. The publication actions are: a push of any ref to origin; and opening a pull request, marking one ready, arming or disarming its auto-merge, merging it, or editing it, by any route, `gh`, the forge's REST or GraphQL API, or `git` included. In every agent stage of the implement-work-item workflow, which is every node whose turn an agent takes, the agent's environment, files and processes MUST hold no credential that can perform a publication action, and no credential or key from which one can be minted: neither the run's forge token nor the GitHub App credentials that mint it. Publication-capable credentials MUST be available only to the command stages `publish_draft`, `pr_refresh` and `pr`, which keep every publication action they are specified to take, and within those stages only to their own publication steps. Repository-controlled code that those stages run, their hooks and gates included, MUST run without the credential: it MUST reach a push only through a credential helper that the hooks and gates cannot read, never through an environment variable or a file they can read. The publication tooling that holds the credential MUST be the Dispatcher-materialized sandbox tooling outside the run's working tree, which no agent stage can modify, so that nothing an agent writes can act with the credential when a publication stage next runs. The forge writes an agent stage's own contract requires MUST go through a trusted broker that runs outside the agent's process tree and holds the credential itself. Those writes are a new comment on the run's own pull request that the stage's contract requires (a Proof of Done record posted through the posting primitive of "Proof of Done record", and the `review` stage's findings record, included) and an upload of proof assets through the proof asset store. The broker MUST perform only those writes, only for the run's own pull request and proof asset store, and MUST take the stage it serves from the workflow that launched the node, never from anything the agent can set. Reading the forge stays allowed. A command node is not an agent stage. A command node that preserves a run's work, such as the needs-human preservation step, therefore keeps the credentials its own contract requires. In addition, the sandbox `gh` wrapper and `push_origin` helper MUST refuse a publication action from an agent stage before it reaches the forge, exiting non-zero and printing `LIVESPEC_AGENT_PUBLICATION_DENIED` with the stage and the refused action, so that the attempt is named rather than surfacing as an authentication failure. Measured 2026-10-26: on run 01M5X2C5FJKSQW84SFG81E6885 (bd-ib-svm3fe) the `implement` agent ran `gh pr create` and then `gh pr merge --rebase` itself with the run-wide token, merging pull request 3731 partway through the run; on bd-ib-q156 a late agent stage ran `gh pr ready` and a merge of pull request 2633. Scenario 202 in `scenarios.md` exercises this paragraph.
 
-**An implement turn that ends incomplete does not succeed.** The `implement` stage's outcome MUST be decided from a structured completion field in the turn's final output, not from the turn merely ending. The `implement` prompt MUST direct the turn to end its final reply with that field, stating whether the work item's Definition of Done is complete on the committed branch. A turn's latest commit attempt counts as refused when the turn left changes staged and the repository's commit hook, run by the run itself over those staged changes, exits non-zero naming at least one failed target; a turn that left nothing staged, or whose staged changes the hook accepts, did not leave a refused commit attempt. When the field reports the work incomplete and the `implement` node's retry budget is not exhausted, the run MUST re-enter the `implement` stage instead of failing it. The re-entered turn's brief MUST carry the previous turn's latest failing gate, taken from the run's recorded tool output rather than from the previous turn's reply, chosen in this order: when the turn's latest commit attempt was refused, the refused commit's failed target names and the hook's own error lines; otherwise, when the turn's latest run of the repository's check suite exited non-zero naming at least one failed target, those failed target names and that run's error lines; otherwise, a statement that the previous turn ended incomplete with no recorded failing gate. When that budget is exhausted, the stage MUST end with a failed outcome, so the run takes the same failure edge as any other `implement` failure, and the dispatch outcome detail MUST carry its cause: the hook's failed targets when the turn's latest commit attempt was refused, and partial progress otherwise. A turn whose final output carries no completion field MUST be treated as incomplete. A turn whose field reports the work complete keeps the succeeded outcome and its existing routing. Scenario 204 in `scenarios.md` exercises this paragraph.
+**An implement turn that ends incomplete does not succeed.** The `implement` stage's outcome MUST be decided from a structured completion field in the turn's final output, not from the turn merely ending. The `implement` prompt MUST direct the turn to end its final reply with that field, stating whether the work item's Definition of Done is complete on the committed branch. When the turn's latest commit attempt did not go through the detached commit runner, it counts as refused when the turn left changes staged and the repository's commit hook, run by the run itself over those staged changes, exits non-zero naming at least one failed target; otherwise that attempt is not refused. For a latest attempt made through the runner, the recorded-run rule below governs instead. When the field reports the work incomplete and the `implement` node's retry budget is not exhausted, the run MUST re-enter the `implement` stage instead of failing it. The re-entered turn's brief MUST carry the previous turn's latest failing gate, taken from the run's recorded tool output rather than from the previous turn's reply, chosen in this order: when the turn's latest commit attempt was refused, the refused commit's failed target names and the hook's own error lines; otherwise, when the turn's latest run of the repository's check suite exited non-zero naming at least one failed target, those failed target names and that run's error lines; otherwise, a statement that the previous turn ended incomplete with no recorded failing gate. When that budget is exhausted, the stage MUST end with a failed outcome, so the run takes the same failure edge as any other `implement` failure, and the dispatch outcome detail MUST carry its cause: the hook's failed targets when the turn's latest commit attempt was refused, and partial progress otherwise. A turn whose final output carries no completion field MUST be treated as incomplete. A turn whose field reports the work complete keeps the succeeded outcome and its existing routing. Except when the turn is ended by its node's resolved timeout, before an `implement`, `fix` or `review_fix` stage's outcome is decided, the run MUST wait until every commit run the turn started through the detached commit runner of "A commit leg completes past one tool call" has reached its own terminal state. That wait MUST NOT consume the node's retry budget or count as a turn, and its mechanism is left to the implementation; it does not relax the agent's obligation to make every commit run terminal or stopped before its final message, and a node-timeout cut remains governed by "A commit run outlives a node-timeout cut". A latest commit attempt made through the runner counts as refused when its commit run reached `failed` and that run's recorded output shows the repository's commit hook ran and named at least one failed target; that run's failed target names and hook error lines MUST then be taken from the commit run's full recorded output, never only from the final lines its terminal report carries. When the turn's latest commit run reached `no-verdict`, the re-entered brief MUST state that the run made no commit. Scenario 204 in `scenarios.md` exercises this paragraph.
 
 **Scripted publication and proof-head integrity.** `pr_refresh` and `pr`
 MUST be command stages with their own resolved timeouts, not agent turns.
diff --git a/SPECIFICATION/scenarios.md b/SPECIFICATION/scenarios.md
index 2a5221a3e..bed7dfe9c 100644
--- a/SPECIFICATION/scenarios.md
+++ b/SPECIFICATION/scenarios.md
@@ -7893,6 +7893,18 @@ Feature: An incomplete implement turn is not recorded as a success
     Given an implement turn whose final output's completion field reports the Definition of Done complete
     When the implement stage ends
     Then the stage outcome is succeeded and the run proceeds to implementation_diff as before
+
+  Scenario: A turn that ends while its runner commit is still running waits for that commit's verdict
+    Given an implement turn that, contrary to its end-of-turn obligation, sent its final message while a commit run it started through the detached commit runner was still running
+    When the run decides the implement stage's outcome
+    Then it first waits until that commit run reaches its own terminal state
+    And that wait consumes none of the implement node's retry budget
+
+  Scenario: A commit the runner recorded as failed counts as the turn's refused commit attempt
+    Given an incomplete implement turn whose latest commit run through the detached commit runner reached failed with the commit hook having named a failed target
+    And that target's name appears only in the commit run's full recorded output, not in its terminal report's final lines
+    When the implement stage re-enters while its retry budget remains
+    Then the re-entered brief carries that commit run's failed target names and hook error lines from its full recorded output
 ```
 
 ## Scenario 205 — Gap detection enumerates headings without an exercising test
```

