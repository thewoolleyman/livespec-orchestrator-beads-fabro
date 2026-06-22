---
topic: out-of-band-edit-2026-06-21t05-13-39z
author: livespec-doctor
created_at: 2026-06-21T05:13:39Z
---

## Proposal: out-of-band-edit-2026-06-21t05-13-39z

doctor detected drift between HEAD-active spec content and the
HEAD-history-vN snapshot; this auto-backfill records the active
state as the new canonical version.

### Proposed Changes

```diff
--- history/vN/README.md
+++ active/README.md
@@ -18,8 +18,8 @@
 The seed wrapper writes the canonical NLSpec multi-file convention:
 
 - `spec.md` — overall intent and behavior
-- `contracts.md` — wire-level interfaces (the 10-skill surface, the
-  Spec Reader internal adapter, the work-items / memos store schemas,
+- `contracts.md` — wire-level interfaces (the 7-skill surface, the
+  Spec Reader internal adapter, the work-items store schema,
   the `compat` block this plugin pins against `livespec`)
 - `constraints.md` — architecture-level constraints
 - `scenarios.md` — behavioral narratives
@@ -31,12 +31,11 @@
 Per `livespec/SPECIFICATION/contracts.md`, this spec MUST
 document:
 
-- The plugin's ten-skill surface (six heavyweight authored skills:
-  capture-impl-gaps, capture-memo, capture-spec-drift,
-  capture-work-item, implement, process-memos; four thin-transport
-  skills: detect-impl-gaps, list-memos, list-work-items, next)
+- The plugin's seven-skill surface (four heavyweight authored skills:
+  capture-impl-gaps, capture-spec-drift, capture-work-item, implement;
+  three thin-transport skills: detect-impl-gaps, list-work-items, next)
 - The Spec Reader internal API's four required capabilities
-- The work-items + memos store schemas and their on-disk layout
+- The work-items store schema and its on-disk layout
 - The Persistent Agent Knowledge store realization for this plugin
 - The `compat` block declaring this plugin's `livespec` semver
   range and pinned release tag
```
