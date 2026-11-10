---
topic: merge-hold-release-arms-a-message-only-head-move
author: claude-opus-5-5
created_at: 2026-11-10T07:44:47Z
---

## Proposal: The merge-hold release arms a head that differs from the proved head only in its commit message

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The host-side hold release (set-merge-hold:<work-item-id>:off) today arms only a pull request whose current head is exactly the head named by the latest verified or carried_forward record of the item's latest run. This proposal adds one bounded exception: a current head with the same tree and the same single parent as that proved head, differing only in its commit message, MAY be armed, and the release reports both heads and the shared tree. A different tree, a different parent, a non-single-parent commit or an unreadable tree or parent still refuses, naming the measurement that failed, and leaves the pull request unarmed. Scenario 184's one merge-hold release scenario is replaced by four that state the arming case and each refusal.

### Motivation

Routed by legacy-coordinator-agent; carrier work item bd-ib-nceul6 (spec-change tier, child of bd-ib-ynnykl). Measured case: livespec-dev-tooling#3999 (livespec-dev-tooling-8o8e.16). The coordinator's hygiene grade asked for a subject on a factory commit that carried only trailers (the bd-ib-7cixf3 class). The reword moved the head ef218b75 -> caa9ec00; both commits have tree 5053e2e2 and parent a9e9178a, so the delivered bytes and their base are identical. set-merge-hold:off refused because run 82f0c2c2's verified record names ef218b75, and the pull request had to be hand-landed. No host-side carry-forward verb exists, and a re-proof run would rebuild the same tree and likely open a second pull request. Comparing tree and parent is the discriminator: equal tree and equal single parent mean the merge would land exactly the proved content on exactly the proved base, so the proof still describes what merges; the forge's required checks still run on the new head before the merge lands. Fleet scope: the guard is orchestrator code shared by every member, so this one clause covers every repository and no per-repository mirror is needed.

### Proposed Changes

Amend contracts.md §"Self-contained plugin dispatch", the sentence pair that governs the one arming outside a run, as follows. The release MUST still NOT arm while a run of the item is live. It MAY arm a head that differs from the proved head only in its commit message, defined mechanically as: distinct commits, each with exactly one parent, the same parent commit, and the same tree object. It MUST report the proved head, the current head and the shared tree when it does. Every other mismatch MUST refuse, naming the tree or parent comparison that failed and reporting both heads; an unreadable tree or parent MUST refuse naming the read. The release MUST NOT write a proof record for the moved head, and `pr`'s in-run arming rule is unchanged.

```diff
--- a/SPECIFICATION/contracts.md
+++ b/SPECIFICATION/contracts.md
@@ §"Self-contained plugin dispatch" (the pr_refresh / arming paragraph) @@
-The one arming outside a run is the host-side hold release of §"The per-item merge hold". That release MUST NOT arm while a run of the item is live, and it MUST arm only a pull request whose current head is named by the latest `verified` or `carried_forward` record of the item's latest run; otherwise it MUST refuse, naming the measurement that failed, and leave the pull request unarmed.
+The one arming outside a run is the host-side hold release of §"The per-item merge hold". That release MUST NOT arm while a run of the item is live, and it MUST arm only a pull request whose current head is either named by the latest `verified` or `carried_forward` record of the item's latest run (the proved head), or differs from the proved head only in its commit message. A head differs from the proved head only in its commit message when the two commits are distinct, each has exactly one parent, that parent is the same commit, and their trees are the same tree object. When the release arms such a message-only move it MUST report the proved head, the current head and their shared tree in its result. In every other case it MUST refuse, MUST name the measurement that failed (the tree comparison when the trees differ, the parent comparison when the trees match but the parents differ or either commit does not have exactly one parent), MUST report both heads, and MUST leave the pull request unarmed. When the release cannot read the tree or the parent of either head it MUST refuse, naming the read that failed, and leave the pull request unarmed. The release MUST NOT write a `verified` or `carried_forward` record for a message-only move, and this exception MUST NOT change what `pr` arms within a run.
```

In scenarios.md, Scenario 184, replace the scenario "A merge-hold release cannot arm a head that no proof record names" with the four scenarios below. No `## ` heading is added, removed or renamed, so tests/heading-coverage.json MUST NOT change.

```diff
--- a/SPECIFICATION/scenarios.md
+++ b/SPECIFICATION/scenarios.md
@@ ## Scenario 184 — ... (replace the one merge-hold release scenario with the four below) @@
-  Scenario: A merge-hold release cannot arm a head that no proof record names
-    Given an item under a merge hold whose pull request head is H2
-    And the latest verified or carried_forward record of the item's latest run names H1, not H2
-    When the operator releases the hold
-    Then the release refuses, naming the head comparison that failed, and the pull request stays unarmed
+  Scenario: A merge-hold release arms a head that differs from the proved head only in its commit message
+    Given an item under a merge hold whose pull request head is H2
+    And the latest verified or carried_forward record of the item's latest run names H1, not H2
+    And H1 and H2 each have exactly one parent, the same commit P, and the same tree T
+    When the operator releases the hold
+    Then auto-merge is armed on the pull request with the merge method journaled with the dispatch that opened it
+    And the release result names the proved head H1, the current head H2 and their shared tree T
+    And no verified or carried_forward record is written for H2
+
+  Scenario: A merge-hold release cannot arm a head whose tree differs from the proved head
+    Given an item under a merge hold whose pull request head is H2
+    And the latest verified or carried_forward record of the item's latest run names H1, not H2
+    And H2's tree differs from H1's tree
+    When the operator releases the hold
+    Then the release refuses, naming the tree comparison as the measurement that failed and reporting H1 and H2
+    And the pull request stays unarmed
+
+  Scenario: A merge-hold release cannot arm a head with the proved tree on a different parent
+    Given an item under a merge hold whose pull request head is H2
+    And the latest verified or carried_forward record of the item's latest run names H1, not H2
+    And H2 has the same tree as H1 but a different parent
+    When the operator releases the hold
+    Then the release refuses, naming the parent comparison as the measurement that failed and reporting H1 and H2
+    And the pull request stays unarmed
+
+  Scenario: A merge-hold release that cannot read a head's tree or parent refuses
+    Given an item under a merge hold whose pull request head is H2
+    And the latest verified or carried_forward record of the item's latest run names H1, not H2
+    And the tree or the parent of H1 or H2 cannot be read
+    When the operator releases the hold
+    Then the release refuses, naming the read that failed, and the pull request stays unarmed
```
