---
topic: factory-size-justification-gate
author: codex-gpt-5
created_at: 2026-09-30T05:52:25Z
spec_commitments:
  impl_followups:
    - id_hint: factory-size-justification-gate
      description: |
        Implement the ratified adopted-ceiling admission rule, auditable size_justification escape hatch, lifecycle routing, and calibration tag in livespec-orchestrator-beads-fabro.
---

## Proposal: Adopted size ceilings use an auditable single-run exception

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Change the predictive size gate from permanently advisory to conditionally enforceable only after a maintainer adopts a calibrated assertion-count ceiling, while preserving legitimate single-run work through an explicit, attributed justification instead of forcing an artificial split.

### Motivation

The current contract says the size gate only flags oversized work advisorily and is never auto-enforced. That cannot realize the requested deterministic gate: an above-ceiling item with no exception must be kept out of autonomous dispatch. At the same time, a hard assertion cap would force legitimately atomic work to split. An adopted-ceiling gate with an auditable single-run exception supplies a mechanical routing decision without pretending that every large item is decomposable.

### Proposed Changes

Amend `contracts.md` under `Grooming and slice-size calibration` so that calibration proposals MUST remain advisory and MUST NOT affect lifecycle state until a maintainer explicitly adopts a threshold. Adoption MUST be the committed-configuration-only setting `dispatcher.adopted_assertion_count_ceiling`: absence means no ceiling is adopted, and a present value MUST be a positive integer or configuration resolution refuses before any lifecycle mutation. Once that setting is present, capture and groom MUST compare the sanctioned effective-criteria assertion count with its value. An item above the adopted ceiling and lacking a valid `size_justification` MUST route to `backlog` for decomposition and MUST surface the ceiling, observed count, and missing-justification reason; it MUST NOT enter `ready` or autonomous dispatch.

Define `size_justification` as an auditable metadata object carrying exactly the non-empty fields `rationale`, `author`, and `at`, where `at` is an ISO-8601 timestamp. A valid justification MUST act as a narrow admission waiver: the oversized item continues through every other Definition-of-Ready gate, and passing the size exception MUST NOT bypass coherence, autonomous-verifiability, dependency, repo-target, acceptance-policy, or approval gates. Dispatch of a justified oversized item MUST emit the calibration attribute `tdd.size_justified=true` so calibration can compare justified outcomes with ordinary runs. Missing, malformed, or empty justification fields MUST be treated as no justification.

Clarify the hard-versus-advisory split: unadopted threshold proposals remain advisory; a ceiling explicitly adopted through `dispatcher.adopted_assertion_count_ceiling` becomes a deterministic conditional admission gate with the declared-justification escape hatch. The setting MUST remain outside the API-configurable policy set so adoption is a reviewed committed-config change. No numeric ceiling MUST be embedded in the specification, inferred from the current non-discriminating dataset, or auto-adopted by the analysis pass.

Add Gherkin scenarios in `scenarios.md` covering: (1) absent adoption leaves lifecycle routing unchanged; (2) an invalid adoption value refuses before mutation; (3) an above-ceiling item without justification routes to `backlog` with the measured reason; (4) a valid justification lets the item proceed only through the remaining DoR and approval gates and tags its dispatch; and (5) malformed justification is treated as absent. Update `tests/heading-coverage.json` atomically so each new behavioral clause is linked to its scenario.
