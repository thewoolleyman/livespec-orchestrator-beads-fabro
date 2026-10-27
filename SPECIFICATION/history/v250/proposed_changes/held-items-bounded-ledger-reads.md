---
topic: held-items-bounded-ledger-reads
author: claude-opus-5-5
created_at: 2026-10-27T14:15:01Z
---

## Proposal: needs-attention's held-items listing reads the ledger a bounded number of times per snapshot, not once per heldable item

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

In 'Judged before admission', the needs-attention listing of items held by the pre-admission judgement must find recorded verdicts with a bounded number of ledger reads per snapshot, independent of the heldable-item count, and must not issue a ledger read per heldable item. The listed facts are unchanged. Scenario 174 gains one case.

### Motivation

Spec-first for bd-ib-hm4obe, a host-load reduction routed by petri-factory-on-gmktec under coordinator R127. The dispatcher's own pre-dispatch judgement refused it at 13:42Z (exit 5): no H2 governs this read shape. held_definition_of_done_items issues one `bd comments` per heldable item, so needs-attention's ledger subprocess count grows with the backlog, which is the per-item fan-out behind needs-attention runs hitting their 900-second budget.

### Proposed Changes

No `## ` heading changes, so `tests/heading-coverage.json` needs no co-edit. The diff below is the whole change.

```diff
diff --git a/SPECIFICATION/contracts.md b/SPECIFICATION/contracts.md
index 7f0623f69..8eede719e 100644
--- a/SPECIFICATION/contracts.md
+++ b/SPECIFICATION/contracts.md
@@ -6480,7 +6480,13 @@ not have seen. A wall finding the judgement did not grade stays
 ADVISORY as above. `needs-attention` MUST list, as hygiene facts, each
 item held by the pre-admission judgement with its verdict's first
 remedy; the ready-item advisory hygiene fact above still applies to
-items the judgement admitted or could not judge. Scenario 174 in
+items the judgement admitted or could not judge.
+To find each held item's recorded verdict, that listing MUST read the ledger a
+bounded number of times per snapshot, independent of how many items are
+heldable, for example from markers already on the loaded records or from one
+snapshot-wide read, and MUST NOT issue a ledger read per heldable item; the
+facts it lists, held items with their recorded remedy and no fact for an item
+with no recorded verdict, are unchanged by that read shape. Scenario 174 in
 `scenarios.md` exercises this paragraph.
 
 **Judged again before dispatch.** Admission is not the only route to
diff --git a/SPECIFICATION/scenarios.md b/SPECIFICATION/scenarios.md
index be5affc1d..9a237a029 100644
--- a/SPECIFICATION/scenarios.md
+++ b/SPECIFICATION/scenarios.md
@@ -6161,6 +6161,12 @@ Feature: A judged Definition-of-Done defect is found before a dispatch is spent
       | pre-dispatch  | no account selection is published                                               |
       | pre-admission | a selected account is published but its credential is absent from the environment |
       | pre-dispatch  | a selected account is published but its credential is absent from the environment |
+
+  Scenario: The held-items listing reads the ledger a bounded number of times per snapshot
+    Given a snapshot holding many heldable items, some held by a recorded pre-admission verdict and some with no recorded verdict
+    When needs-attention lists the items the pre-admission judgement held
+    Then the number of ledger reads it issues does not grow with the number of heldable items
+    And each held item is listed with its recorded verdict's first remedy, and no item without a recorded verdict is listed
 ```
 
 ## Scenario 175 — A run past the whole-run wall budget is exported, cancelled and rested for a human
```

