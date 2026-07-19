---
topic: out-of-band-edit-2026-07-19t07-42-27z
author: livespec-doctor
created_at: 2026-07-19T07:42:27Z
---

## Proposal: out-of-band-edit-2026-07-19t07-42-27z

doctor detected drift between HEAD-active spec content and the
HEAD-history-vN snapshot; this auto-backfill records the active
state as the new canonical version.

### Proposed Changes

```diff
--- history/vN/contracts.md
+++ active/contracts.md
@@ -1336,6 +1336,24 @@
   permitted — the journal is an append-only audit record, not the work-item
   store.) Because a `--dry-run` invocation launches no run, it produces no
   per-run cost signal and therefore no cost-gate verdict (below).
+
+The Dispatcher's guarded recovery surface for an already-merged item is
+`reconcile-merged --repo <path> --item <work-item-id> [--json]`. It MUST
+refuse unless the named item is currently `active`, because this valve exists
+only for a dispatch whose merged PR did not complete post-run disposition. It
+MUST resolve the PR number and merge SHA from GitHub, by the expected
+`feat/<work-item-id>` branch or a merged PR title/search match carrying the
+work-item id, and MUST NOT require or trust ledger audit metadata for that
+resolution. After a merged PR resolves, the valve MUST NOT launch Fabro and
+MUST NOT rebuild the change; it reruns the same post-merge janitor used by the
+dispatch engine against a fresh checkout of the merged ref. A green janitor
+MUST enter the existing post-merge acceptance path unchanged, including the
+`active → acceptance` ledger-complete write, acceptance journal records, and
+policy-governed `acceptance → done` auto-accept when applicable. A red janitor,
+missing merged PR, or wrong source lane MUST leave the item `active` and report
+the failed guarded precondition or janitor stage. This is a distinct guarded
+entry path and does not widen the `drive move` target set; `acceptance`, `done`,
+and `pending-approval` remain forbidden `move` targets.
 
 ### Fail-closed cost gate (keyed on `--item` presence)
 
```
