---
topic: calibration-selected-implement-adapter
author: claude-opus-5-5
created_at: 2026-10-27T19:37:52Z
---

## Proposal: Calibration attributes the implement adapter to the candidate the dispatch selected, not the chain primary

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Under 'Grooming and slice-size calibration' -> 'Completed-cycle progress and runtime size limits', the terminal calibration journal row and span report livespec.implement.adapter as the agent id of the implement candidate the dispatch's per-node selection record selected, and livespec.implement.selected_index as that record's index; with no selection record they report the resolved acp_nodes primary and a null selected_index. The per-node selection record additionally carries the selected candidate's resolved agent id, so the attribution is a journal read. Scenario 127 gains one case.

### Motivation

Spec-first for bd-ib-eqiw4f, routed by petri-factory-on-gmktec after its launch-time screen refused the item at 19:24Z: neither '## Grooming and slice-size calibration' nor Scenario 127 governed calibration adapter attribution. Measured 2026-10-24 on dispatch 0209f2cf...: the selection record chose codex-acp at index 1 while the calibration row reported claude-acp, because the label is classified from the acp-nodes resolution (the chain primary).

### Proposed Changes

No `## ` heading changes, so `tests/heading-coverage.json` needs no co-edit. The diff below is the whole change.

```diff
diff --git a/SPECIFICATION/contracts.md b/SPECIFICATION/contracts.md
index ae05226f8..1a720e1e7 100644
--- a/SPECIFICATION/contracts.md
+++ b/SPECIFICATION/contracts.md
@@ -1894,6 +1894,23 @@ null in the journal and omitted numeric attributes on the span, with an
 accompanying reason. No new always-on service or Fabro platform modification is
 permitted by this contract.
 
+The terminal calibration journal row and span MUST attribute the implement node
+to the candidate the dispatch executed, not to the chain primary.
+`livespec.implement.adapter` MUST be the agent id of the implement candidate
+that the dispatch's per-node selection record (§"Factory-configurable ACP
+fallback priority" → "Per-node selection") selected, so a dispatch that
+selected a fallback candidate reports that fallback's agent id.
+`livespec.implement.selected_index` MUST be that record's selected candidate
+index for the implement node. The per-node selection record MUST additionally
+carry the selected candidate's resolved agent id, or null when unavailable.
+Both calibration fields MUST be read from that record for the same dispatch. An
+unavailable selected agent id MUST remain null in the calibration journal and
+be omitted on the span. When the dispatch has no selection record for
+the implement node, `livespec.implement.adapter` MUST be the agent id of the
+resolved `acp_nodes` primary for that node, and
+`livespec.implement.selected_index` MUST be null in the journal and omitted on
+the span. An agent id MUST NOT be inferred from a model name.
+
 ### Gate type determines hard versus advisory
 
 Resolve the hard-versus-advisory question by gate TYPE. The STRUCTURAL
diff --git a/SPECIFICATION/scenarios.md b/SPECIFICATION/scenarios.md
index cb0038d5f..f3ea34e13 100644
--- a/SPECIFICATION/scenarios.md
+++ b/SPECIFICATION/scenarios.md
@@ -3999,6 +3999,12 @@ Feature: Factory-configurable ACP fallback priority
     When the Dispatcher evaluates adapter launch release
     Then it surfaces unavailable evidence and schedules another observation
     And it neither journals adapter-launch-release nor creates a needs-human decision from the missing evidence
+
+  Scenario: Calibration attributes the implement node to the candidate the dispatch selected
+    Given a dispatch whose implement selection record selected candidate one, a codex-acp fallback, after the claude-acp primary was skipped for session headroom
+    When the Dispatcher writes the terminal calibration journal row and span
+    Then livespec.implement.adapter is codex-acp and livespec.implement.selected_index is 1
+    And a dispatch with no selection record for the implement node reports the resolved acp_nodes primary's agent id, with selected_index null in the journal and omitted on the span
 ```
 
 ## Scenario 128 — An unrunnable ready item is visible but never advertised for dispatch
```

