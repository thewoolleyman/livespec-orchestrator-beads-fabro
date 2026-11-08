---
topic: claim-token-stand-down-names-its-successor
author: claude-fable-5-1
created_at: 2026-11-06T16:39:46Z
---

## Proposal: A claim-token takeover that stands down names its own successor, and a takeover follows the chain of closed tokens to the open one

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend step 5 of the Claim tokens bullet so that a takeover writer which stands down, because the original winner's item write landed between the takeover's close and its re-read, makes no status, assignee or run-stamp change and reports claim-changed but names its own successor on the item in one token-only write, instead of discarding it. State in the same step that applying the protocol to the stranded successor includes step 5 itself, so a takeover follows a chain of closed tokens hop by hop, observing each unapplied transition for the takeover wait, to the first open token. Scenario 263's stand-down scenario says the same, and a scenario for the chain is added.

### Motivation

Measured 2026-11-06 on master (the 08:04:36Z and 08:25:40Z comments on bd-ib-7uue5s; coordinator ruling 08:26:40Z; plan-scope event 2026-11-06T09:17:45Z on livespec-dev-tooling-bqnzcm; work item bd-ib-kseatc). Step 5 exists so that a winner that crashed between its close and its item write "never leaves the item unwritable", and its own last sentence leaves one: a takeover that stands down has already closed the stranded successor S naming its own successor S2, so after the prescribed discard the item names S (closed, names S2) and S2 is closed too. Every later writer waits out the transition, treats S2 as current, cannot close it, and reports claim-changed for ever; the only recovery is the migration pass, which runs with every claim writer of the tenant stopped. _store_claim_tokens.py::_stand_down_if_original_writer_landed implements the sentence exactly, so this is a spec change and not a conformance fix. The replacement is safe because only the writer holding S2 can advance an item that names S: it closed S itself, so the token-only write that names S2 races nothing, and the item keeps an open current token. A second measured shape has the same end under a one-hop reading of the step: a takeover writer stranded after its own close leaves the item naming T (closed, names S) with S closed naming an open S2, which a writer that follows one hop can never close. The step already says to "apply this protocol to S"; making explicit that this includes step 5 ratifies the hop-by-hop follow with a fresh takeover wait at each hop. Nothing in this proposal changes the accepted residual class, the lease, the takeover wait, the loser's discard in step 3, or the migration pass.

### Proposed Changes

Two edits, one per file; every other sentence of the edited step and scenario block is unchanged, and no `## ` heading is added, renamed or removed, so `tests/heading-coverage.json` needs no co-edit.

**1. `SPECIFICATION/contracts.md`, § "Dispatcher policy settings" → "Stranded claim release" → the **Claim tokens** bullet, step 5.** The last sentence, which today reads "A writer that wins S this way MUST re-read the item immediately before its item write and, when the item now names S, MUST write nothing, MUST discard its own successor and MUST report `claim-changed`, because the original winner's transition has landed.", becomes: the writer MUST make no status, assignee or run-stamp change and MUST report `claim-changed`, but MUST name its own successor S2 as the item's current token in one write that changes nothing else, and MUST NOT discard S2, so the item names an open current token and the chain stays writable; the token-only write races nothing, because the writer closed S itself and only the writer holding the successor that S's close reason names can advance an item that names S. The same step states that "apply this protocol to S" includes this step, so a writer that finds S itself closed naming a successor the item does not name observes that transition afresh for the same wait and follows the chain hop by hop to the first open token. Step 5's stated purpose, that a crashed winner never leaves the item unwritable, is kept word for word.

**2. `SPECIFICATION/scenarios.md`, `## Scenario 263 — Exactly one writer changes a dispatch claim, and every other writer stands down`.** The `Then` line of "A takeover stands down when the original transition lands first" says the same as the clause ("writes no status change, names its successor as the item's current token, and reports claim-changed") and gains the line "And the next claim writer wins that successor and its write lands"; one scenario is added, "A takeover follows a chain of closed tokens to the open one", for the hop-by-hop wait. The first scenario of the block, where a LOSER of a contested token discards its own successor (step 3), is unchanged: a loser never closed anything, so its discard dead-ends no chain.

Exact diff:

```diff
--- a/SPECIFICATION/contracts.md
+++ b/SPECIFICATION/contracts.md
@@ -7962,12 +7962,22 @@
      across at least 180 seconds of elapsed time on its own monotonic
      clock, from its first such observation to a fresh read; only then
      MUST it treat S as the item's current token and apply this protocol
-     to S, so a winner that crashed between its close and its
-     item write never leaves the item unwritable. A writer that wins S
-     this way MUST re-read the item immediately before its item write
-     and, when the item now names S, MUST write nothing, MUST discard
-     its own successor and MUST report `claim-changed`, because the original
-     winner's transition has landed.
+     to S, this step included: when S is itself closed naming a successor
+     the item does not name, the writer MUST observe that transition
+     afresh for the same wait before it treats that successor as current,
+     and so follows the chain of closed tokens hop by hop until it
+     reaches an open one. So a winner that crashed between its close and
+     its item write never leaves the item unwritable. A writer that wins
+     S this way MUST re-read the item immediately before its item write
+     and, when the item now names S, MUST make no status, assignee or
+     run-stamp change and MUST report `claim-changed`, because the
+     original winner's transition has landed; but it MUST name its own
+     successor S2 as the item's current token in one write that changes
+     nothing else, and MUST NOT discard S2, so the item names an open
+     current token and the chain stays writable. That token-only write
+     races nothing: the writer closed S itself, and only the writer
+     holding the successor that S's close reason names can advance an
+     item that names S.
   Exactly one writer therefore wins each token, a loser never writes, and
   a writer that reads an earlier, already-closed token loses that token's
   close; the only way an earlier winner's item write can still land after
--- a/SPECIFICATION/scenarios.md
+++ b/SPECIFICATION/scenarios.md
@@ -10996,7 +10996,15 @@
     Given a takeover writer that has won successor token S of an item whose closed token T named S
     And the original winner's item write naming S lands before the takeover's re-read
     When the takeover writer re-reads the item immediately before its write
-    Then it writes nothing, discards its own successor and reports claim-changed
+    Then it writes no status change, names its successor as the item's current token, and reports claim-changed
+    And the next claim writer wins that successor and its write lands
+
+  Scenario: A takeover follows a chain of closed tokens to the open one
+    Given an item naming closed token T whose close reason names S, and S is closed naming S2, and S2 is open
+    And a claim writer has observed T closed and S not named for the takeover wait on its own clock
+    When that writer treats S as current and finds it closed naming S2, which the item does not name
+    Then it reports claim-transition-pending until it has observed that state for the takeover wait too
+    And it then wins S2 and its write lands
 
   Scenario: After cutover, an item with no token is refused, not written blind
     Given dispatcher.claim_tokens is committed true
```

