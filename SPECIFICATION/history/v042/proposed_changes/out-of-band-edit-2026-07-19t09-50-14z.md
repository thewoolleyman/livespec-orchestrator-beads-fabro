---
topic: out-of-band-edit-2026-07-19t09-50-14z
author: livespec-doctor
created_at: 2026-07-19T09:50:14Z
---

## Proposal: out-of-band-edit-2026-07-19t09-50-14z

doctor detected drift between HEAD-active spec content and the
HEAD-history-vN snapshot; this auto-backfill records the active
state as the new canonical version.

### Proposed Changes

```diff
--- history/vN/contracts.md
+++ active/contracts.md
@@ -1338,22 +1338,40 @@
   per-run cost signal and therefore no cost-gate verdict (below).
 
 The Dispatcher's guarded recovery surface for an already-merged item is
-`reconcile-merged --repo <path> --item <work-item-id> [--json]`. It MUST
+`reconcile-merged --repo <path> --item <work-item-id> [--json]` and, only after
+an operator has confirmed the original dispatcher process is dead,
+`reconcile-merged --repo <path> --item <work-item-id> --force [--json]`. It MUST
 refuse unless the named item is currently `active`, because this valve exists
-only for a dispatch whose merged PR did not complete post-run disposition. It
-MUST resolve the PR number and merge SHA from GitHub, by the expected
+only for a dispatch whose merged PR did not complete post-run disposition.
+Before resolving the PR or provisioning any janitor checkout, the valve MUST
+read the dispatch heartbeat for the work-item id and refuse by default when a
+recent heartbeat indicates a still-live dispatch. That refusal is load-bearing:
+a live dispatch can legitimately be `active` with a merged PR while its
+one-hour post-merge janitor window is still running, and a second janitor would
+otherwise target the same deterministic checkout. The refusal message MUST tell
+the operator to confirm liveness with `fabro ps`, wait for the janitor window to
+close, or use `--force` only after confirming the original dispatcher process is
+dead. `--force` bypasses only the heartbeat refusal; it MUST NOT bypass source
+lane checks, merged-PR resolution, post-merge janitor execution, or acceptance
+journaling. The shared post-merge janitor path MUST also hold a per-work-item
+janitor checkout lock before precleaning or provisioning, so concurrent normal
+and reconcile janitors for the same item cannot remove each other's checkout or
+run duplicate completion.
+
+The valve MUST resolve the PR number and merge SHA from GitHub, by the expected
 `feat/<work-item-id>` branch or a merged PR title/search match carrying the
 work-item id, and MUST NOT require or trust ledger audit metadata for that
 resolution. After a merged PR resolves, the valve MUST NOT launch Fabro and
 MUST NOT rebuild the change; it reruns the same post-merge janitor used by the
 dispatch engine against a fresh checkout of the merged ref. A green janitor
 MUST enter the existing post-merge acceptance path unchanged, including the
-`active → acceptance` ledger-complete write, acceptance journal records, and
-policy-governed `acceptance → done` auto-accept when applicable. A red janitor,
-missing merged PR, or wrong source lane MUST leave the item `active` and report
-the failed guarded precondition or janitor stage. This is a distinct guarded
-entry path and does not widen the `drive move` target set; `acceptance`, `done`,
-and `pending-approval` remain forbidden `move` targets.
+`active -> acceptance` ledger-complete write, acceptance journal records, and
+policy-governed `acceptance -> done` auto-accept when applicable. A red janitor,
+missing merged PR, wrong source lane, or held janitor checkout lock MUST leave
+the item `active` and report the failed guarded precondition or janitor stage.
+This is a distinct guarded entry path and does not widen the `drive move` target
+set; `acceptance`, `done`, and `pending-approval` remain forbidden `move`
+targets.
 
 ### Fail-closed cost gate (keyed on `--item` presence)
 
```
