---
topic: pr-refresh-clean-once
author: claude-opus-5-5
created_at: 2026-10-28T06:04:02Z
---

## Proposal: pr_refresh counts only conflicting or gate-failing refreshes, refreshes cleanly at most once, and leaves later default-branch movement to the merge path

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Under '## Self-contained plugin dispatch': the three-refresh non-convergence bound counts only pr_refresh refreshes that conflict or whose refreshed head fails the gate; a clean refresh does not count. A run refreshes cleanly onto an advanced default branch at most once; later pr_refresh visits do not refresh again (except one entered on a refresh-route marker recorded because the forge reports a conflict) and proceed to pr. After that clean refresh, pr records the refresh-route marker only for a forge-reported conflict, and otherwise retries the head-bound arming of the same head within a bounded number of attempts before failing closed. Scenarios 176 and 184 are revised to match. A 'counted refresh' is defined once in 'Scripted publication and proof-head integrity' (a conflicting or gate-failing refresh, or any refresh entered on a forge-reported conflict after the clean refresh, even when it applies cleanly) and the bound and accounting sentences refer to it, so that route cannot loop. The 'Refresh is idempotent and bounded' scenario's stale 'three completed refreshes' step is updated.

### Motivation

Spec-first for bd-ib-6sugaf (coordinator ruling R150, routed by petri-factory-on-gmktec). The bound counted clean refreshes, so on a busy default branch (13 commits in 2 h on 2026-10-27) finished, reviewed and proven runs ended pr-refresh-non-converged: bd-ib-v5f7fd runs 01M5Z7EWQSGD and 01M5ZM43QDAE, whose PR 3818 was then merged by hand. Coordinator direction: refresh to a pinned base once, publish, and let rebase-merge on ci-green absorb later movement.

### Proposed Changes

No `## ` heading changes, so `tests/heading-coverage.json` needs no co-edit. The diff below is the whole change.

```diff
diff --git a/SPECIFICATION/contracts.md b/SPECIFICATION/contracts.md
index a11316c0a..734351652 100644
--- a/SPECIFICATION/contracts.md
+++ b/SPECIFICATION/contracts.md
@@ -3469,9 +3469,25 @@ MUST return to `proof_capture`, then `review` and `proof_verify`, and on
 `carried_forward` it MUST proceed to `pr`; in either case only a proof record
 naming the new head — a `verified` record taken on it, or a `carried_forward`
 record carrying an earlier `verified` record to it — can reach final
-publication. Repeated default-branch movement is bounded to three refreshes per
+publication. Repeated default-branch movement is bounded to three counted refreshes per
 run, after which the run terminates with an explicit non-convergence cause and
-preserved work. An unchanged head proceeds to `pr`, except that when the
+preserved work. A counted refresh is a `pr_refresh` refresh onto an advanced
+default branch that conflicts or whose refreshed head fails the
+repository-declared gate, or any refresh entered through `pr_route` on a
+forge-reported conflict after the run's first clean refresh, which counts once
+at that visit even when it applies cleanly. Any other clean refresh, one whose
+rebase applied without conflict or with only conflicts that "Declared record
+files merge without a repair round" resolved, whose refreshed head passed that
+gate and whose leased push succeeded, does not count toward that bound. A run refreshes cleanly onto an
+advanced default branch at most once: after its first clean `pr_refresh`
+refresh onto an advanced default branch, a later `pr_refresh` visit of the run
+MUST NOT refresh onto the default branch again, except a visit entered through
+`pr_route` on a refresh-route marker that `pr` recorded because the forge
+reported the pull request in conflict with the default branch, and MUST
+proceed to `pr` with the run's published head, which only a `verified` or
+`carried_forward` record naming it lets reach the arming. Default-branch
+movement after that clean refresh is left to the merge path, including
+"Armed pull request overtaken by the default branch". An unchanged head proceeds to `pr`, except that when the
 default branch is already contained in the published head and that head
 carries any of the run's own empty commits (commits the run itself created
 that change no tree, such as engine checkpoint commits), `pr_refresh` MUST
@@ -3557,9 +3573,9 @@ third refresh would need repair, the stage MUST fail closed to `needs_human`
 with the named cause `refresh-repair-exhausted` and a recovery artifact pointer
 naming that stage's pre-refresh head. A refresh-repair round MUST NOT consume
 `dispatcher.review_fix_cap` or any review-fix round. `pr_refresh`'s
-three-refresh non-convergence bound counts each `pr_refresh` visit that
-refreshes onto an advanced default branch, whether that refresh succeeds or
-routes to repair, and counts it once at that visit; `publish_draft` refreshes,
+three-refresh non-convergence bound counts each counted refresh as
+"Scripted publication and proof-head integrity" defines it, once at that visit;
+any other clean refresh does not count; `publish_draft` refreshes,
 repaired or not, do not count toward that bound, and the re-entry of
 `publish_draft` after a repair does not count a second time for the refresh
 that was repaired. The `fix` node's visit limit MUST accommodate the two
@@ -3699,7 +3715,7 @@ unless the item's merge hold is active. It MUST retain existing `PR_NUMBER` and
 merge-hold result markers. A pull request already merged is a recorded success;
 one closed without merging or carrying an unexpected head MUST fail closed.
 Publication metadata MUST be passed as data, not interpolated as shell syntax.
-A merge hold MUST preserve the ready pull request and leave auto-merge unarmed. When the forge rejects the head-bound auto-merge arming and a re-read reports the pull request OPEN rather than MERGED, `pr` MUST read the pull request's current head, the forge's mergeability report for it, and the authoritative default branch's current tip, read from a fetch of the authoritative branch on origin and never from a local tracking ref, before deciding what the rejection means. When the head is still the head that the latest `verified` or `carried_forward` record of this run names, and the default branch's current tip is not an ancestor of that head (the same test `pr_refresh` applies), `pr` MUST record a refresh-route marker naming this `pr` visit in the run's publication state and exit zero, and the run MUST return to `pr_refresh` through `pr_route`. That `pr_refresh` visit refreshes onto an advanced default branch, so it counts toward the three-refresh non-convergence bound; it MUST NOT consume a refresh-repair round unless the refresh itself takes the refresh-repair route. The refreshed head then takes the decision of "Proof carry-forward across a refresh" exactly as any other changed-head refresh, so only a head named by a `verified` or `carried_forward` record can reach the next arming. When `pr` is entered again on that route it finds the pull request already out of draft and reports that it readied nothing, which is expected and is not a failure. When the head differs from the recorded head, `pr` MUST fail closed as for any unexpected head. When the default branch's tip is an ancestor of the head, or when the forge cannot report the head, the mergeability or the default branch's tip, `pr` MUST fail closed naming the forge's rejection cause or the measurement it could not take, and MUST NOT route to `pr_refresh` on an unobservable answer. Every rejected arming that does not end in `MERGED` MUST write one stage-output line naming the forge's rejection message verbatim, the pull request's state, the forge's mergeability report, the pull request's current head, whether that head equals the head of the latest `verified` or `carried_forward` record of this run, the default branch's current tip, and whether that tip is an ancestor of the head. The line MUST NOT state that the head differs from the verified head unless that comparison was taken and differed.
+A merge hold MUST preserve the ready pull request and leave auto-merge unarmed. When the forge rejects the head-bound auto-merge arming and a re-read reports the pull request OPEN rather than MERGED, `pr` MUST read the pull request's current head, the forge's mergeability report for it, and the authoritative default branch's current tip, read from a fetch of the authoritative branch on origin and never from a local tracking ref, before deciding what the rejection means. When the head is still the head that the latest `verified` or `carried_forward` record of this run names, and the default branch's current tip is not an ancestor of that head (the same test `pr_refresh` applies), `pr` MUST record a refresh-route marker naming this `pr` visit in the run's publication state and exit zero, and the run MUST return to `pr_refresh` through `pr_route`. That `pr_refresh` visit refreshes onto the advanced default branch (the run's first clean refresh, or, after that, a refresh entered on a forge-reported conflict); it counts toward the three-refresh non-convergence bound exactly when it is a counted refresh as defined above, and it MUST NOT consume a refresh-repair round unless the refresh itself takes the refresh-repair route. After the run has taken its one clean `pr_refresh` refresh, `pr` MUST record the refresh-route marker only when the forge's mergeability report says the pull request conflicts with the default branch. Otherwise it MUST NOT record the marker, and MUST retry the head-bound arming of the same head, re-reading the mergeability report before each retry, within a bounded implementation-defined number of attempts; when an arming succeeds the run proceeds as after any armed pull request, and when the attempts are exhausted `pr` MUST fail closed naming the forge's last rejection cause. The refreshed head then takes the decision of "Proof carry-forward across a refresh" exactly as any other changed-head refresh, so only a head named by a `verified` or `carried_forward` record can reach the next arming. When `pr` is entered again on that route it finds the pull request already out of draft and reports that it readied nothing, which is expected and is not a failure. When the head differs from the recorded head, `pr` MUST fail closed as for any unexpected head. When the default branch's tip is an ancestor of the head, or when the forge cannot report the head, the mergeability or the default branch's tip, `pr` MUST fail closed naming the forge's rejection cause or the measurement it could not take, and MUST NOT route to `pr_refresh` on an unobservable answer. Every rejected arming that does not end in `MERGED` MUST write one stage-output line naming the forge's rejection message verbatim, the pull request's state, the forge's mergeability report, the pull request's current head, whether that head equals the head of the latest `verified` or `carried_forward` record of this run, the default branch's current tip, and whether that tip is an ancestor of the head. The line MUST NOT state that the head differs from the verified head unless that comparison was taken and differed.
 Resume from an earlier verified head MUST enter `pr_refresh` before `pr`,
 preserving the existing exact-head and run-attribution refusals. A later head
 change requires fresh proof or a `carried_forward` record for that head;
diff --git a/SPECIFICATION/scenarios.md b/SPECIFICATION/scenarios.md
index f3ea34e13..bd16ab7c4 100644
--- a/SPECIFICATION/scenarios.md
+++ b/SPECIFICATION/scenarios.md
@@ -4261,7 +4261,7 @@ Feature: Proof of Done is captured and independently reproduced before publicati
     Given a refresh already pushed a new head with durable run provenance
     When the same refresh is retried against the matching remote
     Then it resumes from that head and requires proof naming it
-    And three completed refreshes followed by more base movement end with an explicit non-convergence cause
+    And three refreshes that conflicted or failed the repository-declared gate, each repaired, followed by a further conflicting or gate-failing refresh end with an explicit non-convergence cause
   Scenario: Publication renders metadata as data and verifies the exact pull request
     Given the title and body contain shell metacharacters
     When pr executes the deterministic publication recipe
@@ -6355,12 +6355,18 @@ Feature: A janitor-green run survives a default branch that moved under it
     When a publish_draft refresh conflict routes the run to a refresh-repair round
     Then the run still has the same number of review-fix rounds remaining as before the repair
 
-  Scenario: Repaired and clean refreshes share the non-convergence bound
-    Given a run whose pr_refresh has refreshed cleanly twice
-    And whose third pr_refresh refresh conflicted and was repaired
-    When the default branch advances again before pr
+  Scenario: Only conflicting or gate-failing refreshes count toward the non-convergence bound
+    Given a run whose pr_refresh refreshes have conflicted or failed the gate three times, each repaired
+    When the default branch advances again before pr and that refresh conflicts
     Then the run ends with the explicit non-convergence cause and preserved work
 
+  Scenario: A run refreshes cleanly once and leaves later default-branch movement to the merge path
+    Given a run whose pr_refresh has refreshed cleanly onto an advanced default branch once
+    And the default branch advances again, without conflicting with the run's commits, before the pull request merges
+    When the run next reaches pr_refresh and then pr
+    Then pr_refresh does not refresh again and the clean refresh is not counted toward the non-convergence bound
+    And pr arms auto-merge for the head the latest verified or carried_forward record names, and the run does not end pr-refresh-non-converged
+
   Scenario: The repair budget is bounded
     Given a run that has already taken two refresh-repair rounds across publish_draft and pr_refresh
     When its next refresh conflicts again
@@ -6920,13 +6926,26 @@ Feature: Default-branch movement after pr_refresh is absorbed inside the run, an
   So that a proof-verified run is not ended for a human because master moved a few seconds too late
 
   Scenario: A refreshable advance before the arming re-enters pr_refresh and then arms
-    Given a run whose latest verified record names head H
+    Given a run that has not yet refreshed cleanly onto an advanced default branch and whose latest verified record names head H
     And the default branch advances to tip T, which is not an ancestor of H, with a commit that does not conflict with the run's commits
     When pr marks the draft ready and the forge rejects the head-bound arming as not rebaseable
-    Then pr records the refresh-route marker and pr_route routes the run to pr_refresh, which counts one refresh toward the three-refresh bound and takes no refresh-repair round
+    Then pr records the refresh-route marker and pr_route routes the run to pr_refresh, which refreshes cleanly, counts no refresh toward the three-refresh bound and takes no refresh-repair round
     And the refreshed head takes the carry-forward decision before pr is entered again
     And pr reports the pull request already ready and arms auto-merge for the head its latest verified or carried_forward record names
 
+  Scenario: After its one clean refresh a run retries a rejected arming instead of refreshing again
+    Given a run that has taken its one clean pr_refresh refresh and whose latest carried_forward record names head H
+    And the default branch advances again with a commit that does not conflict with the run's commits
+    When pr marks the draft ready and the forge rejects the head-bound arming without reporting a conflict
+    Then pr records no refresh-route marker and retries the arming of H, re-reading the mergeability report before each retry
+    And when an arming succeeds the run proceeds as after any armed pull request, and when the bounded attempts are exhausted pr fails closed naming the forge's last rejection cause
+
+  Scenario: A conflict re-entry after the clean refresh counts even when it applies cleanly
+    Given a run that has taken its one clean pr_refresh refresh
+    And pr recorded the refresh-route marker because the forge reported the pull request in conflict with the default branch
+    When pr_route routes the run to pr_refresh and that refresh applies cleanly
+    Then that visit counts once toward the three-refresh non-convergence bound
+
   Scenario: A conflicting advance before the arming re-enters pr_refresh and takes refresh repair
     Given a run whose latest verified record names head H
     And the default branch advances to tip T with a commit that conflicts with the run's commits
```

