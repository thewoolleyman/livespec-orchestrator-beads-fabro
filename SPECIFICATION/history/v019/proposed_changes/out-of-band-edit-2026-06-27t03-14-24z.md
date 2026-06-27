---
topic: out-of-band-edit-2026-06-27t03-14-24z
author: livespec-doctor
created_at: 2026-06-27T03:14:24Z
---

## Proposal: out-of-band-edit-2026-06-27t03-14-24z

doctor detected drift between HEAD-active spec content and the
HEAD-history-vN snapshot; this auto-backfill records the active
state as the new canonical version.

### Proposed Changes

```diff
--- history/vN/README.md
+++ active/README.md
@@ -2,8 +2,8 @@
 
 This directory holds the natural-language specification for
 `livespec-orchestrator-beads-fabro`. Per
-livespec/SPECIFICATION/non-functional-requirements.md
-§"Implementation plugin ecosystem", every `livespec-impl-*` plugin
+livespec/SPECIFICATION/non-functional-requirements.md,
+every `livespec-impl-*` plugin
 MUST dogfood its own `SPECIFICATION/` and MUST conform to the
 implementation-plugin contract published by `livespec`.
 
--- history/vN/constraints.md
+++ active/constraints.md
@@ -115,8 +115,7 @@
   and maps its harness-neutral vocabulary to the runtime's tools —
   adding no operation behavior of its own. This mirrors livespec CORE's
   prose + thin-Driver-binding decomposition
-  (`livespec/SPECIFICATION/spec.md` §"Contract + reference
-  implementations architecture"). Thin Python helpers MAY exist for
+  (`livespec/SPECIFICATION/spec.md`). Thin Python helpers MAY exist for
   utilities (record-formatting, schema validation); no dialogue logic is
   duplicated across the Claude and Codex bindings.
 - Thin-transport skills (list-work-items, next,
@@ -182,7 +181,7 @@
 The acceptance scenario of a gap-tied item is resolved from the item's
 `gap-id` label through the `clauses[]` gap-id→scenario map in
 `tests/heading-coverage.json` (the same map livespec core's
-`constraints.md` §"Heading taxonomy" defines and the
+`constraints.md` defines and the
 `behavior_scenario_link` check consumes). The "real test, not `TODO`"
 half is the same `tests/heading-coverage.json` `test`-field state the
 existing `heading_coverage` check tolerates as `TODO` but this invariant
--- history/vN/contracts.md
+++ active/contracts.md
@@ -11,8 +11,7 @@
 namespace is fixed by `.claude-plugin/plugin.json` and may not be
 changed without a coordinated rename across consumers (because doctor's
 cross-boundary invariants in `livespec` invoke skills through this
-namespace prefix per `livespec/SPECIFICATION/contracts.md`
-§"Cross-plugin invocation"). Renaming is a major-version-bump
+namespace prefix per `livespec/SPECIFICATION/contracts.md`). Renaming is a major-version-bump
 operation.
 
 ## The eight-skill surface
@@ -20,8 +19,7 @@
 Every entry below is REQUIRED. The descriptions concretize each skill's
 behavior on the beads substrate; cross-boundary semantics (handoffs,
 JSON output schemas, user-consent rules) are defined by
-`livespec/SPECIFICATION/contracts.md` §"Implementation-plugin
-contract — the 10-skill surface" and apply uniformly.
+`livespec/SPECIFICATION/contracts.md` and apply uniformly.
 
 ### Heavyweight authored skills (6)
 
@@ -34,8 +32,7 @@
 harness-neutral vocabulary to the runtime's tools — adding no operation
 behavior of their own (per `constraints.md` §"Skill orchestration
 constraints"). This mirrors livespec CORE's prose + thin-Driver-binding
-architecture (`livespec/SPECIFICATION/spec.md` §"Contract + reference
-implementations architecture"). The six heavyweight ops are
+architecture (`livespec/SPECIFICATION/spec.md`). The six heavyweight ops are
 `capture-impl-gaps`, `capture-spec-drift`, `capture-work-item`,
 `implement`, `groom`, and `plan`. `groom` is the FIFTH heavyweight op; it
 is ALSO the one new maintainer front-end catalogued under §"Skills —
@@ -103,9 +100,7 @@
 `unresolved-spec-commitment` doctor invariant queries via
 `list-work-items --json` to verify each declared spec→impl commitment
 maps to a filed work-item (per
-`livespec/SPECIFICATION/contracts.md` §"Implementation-plugin
-contract — the 10-skill surface" → "Work-item `spec_commitment_hint`
-field").
+`livespec/SPECIFICATION/contracts.md`).
 
 #### `implement`
 
@@ -236,7 +231,7 @@
 
 Each thin-transport skill is a short SKILL.md pass-through over a Python
 `bin/` implementation (the wrapper-shape contract codified in
-`livespec/SPECIFICATION/contracts.md` §"Wrapper CLI surface").
+`livespec/SPECIFICATION/contracts.md`).
 SKILL.md MUST NOT accrete logic — every behavior lives under
 `.claude-plugin/scripts/bin/<skill>.py`.
 
@@ -282,8 +277,8 @@
 #### `next`
 
 Cross-reference: cross-repo dispatch is the Dispatcher's concern
-(`dispatcher.py` `dispatch` / `loop`; see README §"Dispatcher and
-telemetry"). This surface ranks impl-side state only; it MUST NOT
+(`dispatcher.py` `dispatch` / `loop`; see README). This surface ranks
+impl-side state only; it MUST NOT
 bake a cross-repo sequencing or cross-side weighting in — the
 Dispatcher consumes this ranking and handles sequencing externally.
 
@@ -322,10 +317,9 @@
 3. Ties are broken deterministically by `id` lexicographic order.
 4. Apply `--offset` and `--limit` to produce the returned slice.
 
-Output schema (per `livespec/SPECIFICATION/contracts.md`
-§"Implementation-plugin contract — the 10-skill surface" → `next` and
-the upstream §"`/livespec:next` spec-side thin-transport skill" →
-§"Output schema"): the output is a JSON object with two top-level keys,
+Output schema (per `livespec/SPECIFICATION/contracts.md` and the
+upstream `/livespec:next` spec-side thin-transport skill's output
+schema): the output is a JSON object with two top-level keys,
 `candidates[]` and `pagination`:
 
 ```jsonc
@@ -389,8 +383,8 @@
 flag — the skill emits the complete current gap-id set.
 
 The skill reads the live Specification via the Spec Reader, enumerates
-every MUST/SHOULD rule per the gap-rule enumeration contract (per
-upstream §"Spec Reader required-capability surface" capability 1), and
+every MUST/SHOULD rule per the gap-rule enumeration contract (per the
+upstream Spec Reader required-capability surface, capability 1), and
 computes a stable `gap_id` per detected rule. Gap-id derivation is a
 pure function of rule text + canonical heading path; the same rule text
 always yields the same gap-id across runs. This skill is
@@ -545,8 +539,8 @@
 
 This section realizes the repo-agnostic grooming pattern/guidance
 that `livespec`'s `non-functional-requirements.md` carries as
-Orchestrator-internal guidance (beside its existing §"Orchestrator-internal
-Dispatcher guidance"); core gains only the guidance, never a skill,
+Orchestrator-internal guidance (beside its existing Orchestrator-internal
+Dispatcher guidance); core gains only the guidance, never a skill,
 CLI, or doctor invariant. Grooming — how a maintainer breaks and
 sizes work into agent-feedable slices BEFORE autonomous dispatch —
 operates on this plugin's ledger (the beads tenant DB), is
@@ -749,16 +743,16 @@
 
 This section realizes the repo-agnostic Planning Lane pattern/guidance
 that `livespec`'s `non-functional-requirements.md` carries as
-Orchestrator-Plane guidance (§"Planning Lane guidance", beside
-§"Orchestrator-internal grooming guidance"); core gains only the
+Orchestrator-Plane guidance (the Planning Lane guidance, beside the
+Orchestrator-internal grooming guidance); core gains only the
 guidance, never a skill, CLI, or doctor invariant. The Planning Lane —
 the durable, multi-session *planning* work that decides what should
 become spec, implementation, or research before any lane is committed to
 — operates on this plugin's filesystem thread store and ledger, is
 Orchestrator-internal, and is therefore NOT part of `livespec`'s
 functional cross-boundary contract. The architectural frame (the three
-planes and the two seams) is `livespec`'s `spec.md` §"Workflow planes
-and the Planning Lane"; what this section adds is the realization: the
+planes and the two seams) is `livespec`'s `spec.md`; what this section
+adds is the realization: the
 `plan` front-end and the `plan/<topic>/` thread store, the same cut as
 grooming above.
 
@@ -828,8 +822,8 @@
 chain and confirms it can proceed; (2) ONE PATH — the next-session
 command names exactly one path, the handoff; (3) NO DANGLING REFERENCE
 (fail-closed) — every artifact the handoff cites exists and is committed,
-else the gate fails. This realizes `livespec`'s §"Planning Lane
-guidance" → "Handoff self-sufficiency".
+else the gate fails. This realizes `livespec`'s Planning Lane
+guidance on handoff self-sufficiency.
 
 ### Archive on epic close
 
@@ -857,8 +851,8 @@
 ## Dispatch-time baseline conformance gate
 
 This section realizes the **dispatch-time** tier of livespec's
-Conformance Pattern (livespec core `non-functional-requirements.md`
-§"Conformance Pattern", four-tier enforcement-in-depth) for the
+Conformance Pattern (livespec core `non-functional-requirements.md`,
+four-tier enforcement-in-depth) for the
 Beads/Fabro Dispatcher — parallel to how §"Planning Lane realization"
 and §"Grooming and slice-size calibration" realize their repo-agnostic
 core patterns here.
@@ -994,9 +988,8 @@
 - `spec_commitment_hint` — beads native `spec_id` field. When non-null,
   carries the verbatim `id_hint` from a spec-side
   `spec_commitments.impl_followups[]` declaration (per
-  `livespec/SPECIFICATION/contracts.md` §"Implementation-plugin
-  contract — the 10-skill surface" → "Work-item `spec_commitment_hint`
-  field"). Absent for freeform items with no spec-side commitment.
+  `livespec/SPECIFICATION/contracts.md`). Absent for freeform items with
+  no spec-side commitment.
 - `audit` (the whole `AuditRecord`) — serialized losslessly into the
   beads issue's `metadata` JSON column. Present when `resolution` is one
   of `{completed, spec-revised, resolved-out-of-band}` (the resolutions
@@ -1091,8 +1084,8 @@
 it derives gap-ids through the shared `livespec_spec_clauses` extractor
 (the same primitive impl-beads' `detect-impl-gaps` detector already
 imports — single-source gap-id, no duplication), reads the `clauses[]`
-map already defined by livespec core's `constraints.md` §"Heading
-taxonomy", and reads closed gap-tied items through the existing beads
+map already defined by livespec core's `constraints.md`, and reads
+closed gap-tied items through the existing beads
 reader (`bd` store). This check is enforced by
 `just check-closed-item-integrity`.
 
@@ -1101,8 +1094,8 @@
 gap-id→scenario map to be populated in `tests/heading-coverage.json` for
 each gap-tied behavior clause (linking its gap-id to its acceptance
 scenario's H2 section name) — this is the core `clauses[]` contract
-(`constraints.md` §"Heading taxonomy", `non-functional-requirements.md`
-§"Behavior-clause-to-scenario link check") that impl-beads adopts; and
+(`constraints.md`, `non-functional-requirements.md`) that impl-beads
+adopts; and
 (b) the shared `livespec_spec_clauses` extractor available to
 impl-beads' dev-tooling. Both are existing primitives; the impl
 work-item adopts the `clauses[]` map into impl-beads' heading-coverage
@@ -1123,8 +1116,7 @@
 
 ## Spec Reader internal API
 
-Per `livespec/SPECIFICATION/contracts.md` §"Spec Reader
-required-capability surface", every `livespec-impl-*` plugin MUST expose
+Per `livespec/SPECIFICATION/contracts.md`, every `livespec-impl-*` plugin MUST expose
 four capabilities through an internal adapter. The shape is
 implementation-dependent; this plugin's shape is a Python module with
 these public functions:
@@ -1149,8 +1141,8 @@
 The Spec Reader MUST:
 
 - Consult the active template manifest's `spec_files` list rather than
-  hardcoding the well-known file set (per upstream §"Spec Reader
-  required-capability surface" capability 1).
+  hardcoding the well-known file set (per the upstream Spec Reader
+  required-capability surface, capability 1).
 - Surface the `version-directories-complete` pruned-marker exemption
   when reading history (capability 2).
 - Return `int` for the current version (capability 3).
@@ -1195,9 +1187,9 @@
 
 ## `compat` block
 
-Per `livespec/SPECIFICATION/contracts.md` §"Cross-repo
-coordination — pin-and-bump", every consuming project's `.livespec.jsonc`
-declares a `compat` block for each active impl-plugin. For
+Per `livespec/SPECIFICATION/contracts.md`, every consuming project's
+`.livespec.jsonc` declares a `compat` block for each active
+impl-plugin. For
 `livespec-orchestrator-beads-fabro`:
 
 ```jsonc
@@ -1270,8 +1262,8 @@
 
 The configuration block is read by every skill at invocation time. A
 missing or malformed block MUST fire a `fail` finding from doctor's
-`contract-version-compatibility` invariant (upstream §"Cross-boundary
-doctor invariants").
+`contract-version-compatibility` invariant (upstream cross-boundary
+doctor invariants).
 
 ## Cross-boundary handoffs
 
@@ -1287,7 +1279,7 @@
    `no-stale-gap-tied`).
 
 The handoff mechanism is namespace invocation (per
-`livespec/SPECIFICATION/contracts.md` §"Cross-plugin invocation") —
+`livespec/SPECIFICATION/contracts.md`) —
 never direct CLI shelling-out to wrapper paths.
 
 ## Worker credential projection
--- history/vN/spec.md
+++ active/spec.md
@@ -11,8 +11,7 @@
 
 `livespec-orchestrator-beads-fabro` is one realization of the abstract
 implementation-plugin contract that `livespec` publishes in
-`livespec/SPECIFICATION/contracts.md` §"Implementation-plugin
-contract — the 10-skill surface". Other realizations exist on paper
+`livespec/SPECIFICATION/contracts.md`. Other realizations exist on paper
 (`livespec-orchestrator-git-jsonl`, `livespec-orchestrator-gitlab`,
 `livespec-orchestrator-gascity`, `livespec-orchestrator-darkfactory-kilroy`) and are
 out of scope here. This plugin's substrate is a per-repo tenant
@@ -142,8 +141,7 @@
   skills.
 - Not a substitute for the upstream invariant catalog. Doctor
   invariants that span the spec ⇆ impl boundary (per
-  `livespec/SPECIFICATION/contracts.md` §"Doctor cross-boundary
-  invariants") apply uniformly across all impl-plugins; this spec
+  `livespec/SPECIFICATION/contracts.md`) apply uniformly across all impl-plugins; this spec
   describes what the plugin offers, not what doctor enforces.
 - Not the canonical beads ⇄ livespec field-map authority. The field-map
   and connection-model derivation live in
```
