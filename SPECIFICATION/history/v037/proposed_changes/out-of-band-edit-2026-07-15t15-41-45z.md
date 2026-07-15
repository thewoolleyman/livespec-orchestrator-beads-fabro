---
topic: out-of-band-edit-2026-07-15t15-41-45z
author: livespec-doctor
created_at: 2026-07-15T15:41:45Z
---

## Proposal: out-of-band-edit-2026-07-15t15-41-45z

doctor detected drift between HEAD-active spec content and the
HEAD-history-vN snapshot; this auto-backfill records the active
state as the new canonical version.

### Proposed Changes

```diff
--- history/vN/scenarios.md
+++ active/scenarios.md
@@ -395,6 +395,14 @@
     Then the change does not ship
     And the item transitions to blocked with blocked_reason needs-human
     And it is surfaced to a human
+
+  Scenario: A terminal dispatch emits review-gate telemetry from Fabro events
+    Given a Fabro run has reached any terminal Dispatcher outcome: green, blocked, or failed
+    And `fabro events <run-id> --json` contains `edge.selected` events from the review node
+    When the Dispatcher observes the terminal outcome
+    Then it queries the structured Fabro event stream for that run
+    And it emits a `livespec-dispatcher` span carrying `review.verdict`, `review.fix_rounds`, `review.hit_cap`, and `pr.shipped_on_cap`
+    And a review-to-PR fallthrough at the review cap is queryable as `pr.shipped_on_cap=true`
 ```
 
 ## Scenario 21 — Codex skills picker discovers drive by short name
```
