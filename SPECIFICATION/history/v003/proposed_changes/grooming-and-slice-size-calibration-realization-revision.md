---
proposal: grooming-and-slice-size-calibration-realization.md
decision: accept
revised_at: 2026-06-19T07:57:32Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accept as-written: graduate the concrete realization of the work-grooming design into this reference orchestrator's own SPECIFICATION/. Adds a new contracts.md H2 '## Grooming and slice-size calibration' (after '## Store-write consent discipline', before '## Beads connection model') codifying the four maintainer touchpoints, augmented-versus-new skill inventory, the Dispatcher's grooming behavior, the calibration telemetry + single Fabro DOT tweak, and the gate-type hard-versus-advisory split; and a new scenarios.md H2 '## Scenario 7 — Regroom an oversized work-item'. The '### Open realization choices' subsection (groom as its own skill versus an epic mode of capture-work-item; needs-regroom as a label versus a status) is PRESERVED as documented-open and deliberately NOT resolved by this revise pass. The co-edit adds one tests/heading-coverage.json entry per new H2 per the self-application heading-coverage discipline.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
