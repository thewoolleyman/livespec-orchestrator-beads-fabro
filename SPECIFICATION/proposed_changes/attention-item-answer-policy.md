---
topic: attention-item-answer-policy
author: claude-opus (control-plane-accounts-and-dispatch-policy)
created_at: 2026-09-07T02:53:13Z
---

## Proposal: Attention-item answer-disposition policy (who may answer a parked question)

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a dispatcher policy setting `dispatcher.answer_disposition` (values `human` and `consensus`, default `human`) with a per-item override label `answer:<human|consensus>`, governing who may answer an attention item — a work-item resting at `blocked`/`needs-human` (the parked-on-a-question state). Under `human` only a human may answer the `resolve-blocked … --answer` press; under `consensus` an automated or agreed disposition may also answer. `drive` refuses a press the effective disposition does not admit, `needs-attention --json` carries each attention item's effective disposition, and the twelve human valve actions stay twelve because the per-item override is a capture/groom-time label rather than a new valve.

### Motivation

b5 leg 1 of the control-plane accounts-and-dispatch-policy plan (ledger epic bd-ib-rh3iyd, child bd-ib-rh3iyd.1). It transfers the deprecated foreman's valve-disposition capability into the orchestrator (livespec-overseer overseer-5ugiuj.6 removes the foreman seat; overseer-5ugiuj.5 cites this id by name as the by-name transfer target), and it aligns with the just-ratified `consensus` who-may-approve vocabulary (v100 groom cut, `dispatcher.groom_cut_approval: human|consensus`). Under contract v093 a factory run never awaits a human, so a parked question is modeled as ledger state — a single `resolve-blocked` valve lane — which is why the policy attaches to the item and its valve rather than to a suspended run.

### Proposed Changes

Add a normative clause to `SPECIFICATION/contracts.md` and a scenario to `SPECIFICATION/scenarios.md`.

**contracts.md — new `###` clause under the `## Dispatcher policy settings` section.**

The orchestrator MUST define a policy setting `dispatcher.answer_disposition` governing who may answer an attention item — a work-item resting at `blocked` whose blocked-reason is `needs-human` (the parked-on-a-question state under the `A factory run never awaits a human` clause). Its allowed values MUST be exactly `human` and `consensus`, and its default MUST be `human`. The setting mirrors the existing `dispatcher.groom_cut_approval` who-may-approve dial.

The effective answer disposition for an item MUST resolve as the item's per-item override label `answer:<human|consensus>` when present, and MUST fall back to the global `dispatcher.answer_disposition` default otherwise — the same per-item-over-global resolution the existing policy settings use. The per-item override label MAY be written at capture or groom time. This proposal introduces NO new `drive` valve action, so the twelve human valve actions enumerated under the `drive` section MUST remain twelve.

Under an effective disposition of `human`, only a human actor MAY answer the item: a `resolve-blocked:<work-item-id>:ready|backlog` press carrying `--answer` MUST be admitted only for a human invoker. Under `consensus`, an automated or agreed disposition — the successor to the removed foreman valve disposition — MAY also answer. The `--answer` payload MUST continue to land as a ledger comment exactly as it does today; this policy governs only WHO may issue the press and MUST NOT change how the answer is transported.

`drive` MUST refuse a `resolve-blocked` press carrying `--answer` that the item's effective answer disposition does not admit, and the refusal MUST name the work-item and the effective disposition, mirroring the existing effective-manual `approve` refusal. The `needs-attention` `resolve-blocked` lane MUST NOT advertise an answer handoff that `drive` would refuse under the effective disposition, honoring the advertiser-and-enforcer binding.

`needs-attention --json` MUST carry each attention item's effective answer disposition. Until a first-class field ratifies in the `livespec-runtime`-owned attention envelope, the effective disposition MAY ride the existing per-item `summary` string, consistent with the needs-human account already carried there; a plugin-local wire field MUST NOT be added ahead of that runtime ratification.

**scenarios.md — new `## Scenario` binding the rule.**

Add a scenario asserting, against one shared effective-disposition resolver: given a `blocked`/`needs-human` item whose effective answer disposition is `human`, a human `resolve-blocked … --answer` press MUST be admitted while an automated disposition's press MUST be refused with a message naming the item and the disposition; given the same item with effective disposition `consensus`, the automated disposition's press MUST be admitted; and `needs-attention --json` MUST carry each item's effective disposition. The revise that ratifies this scenario MUST update `tests/heading-coverage.json` in the same commit so the new scenario heading is bound to its exercising tests.
