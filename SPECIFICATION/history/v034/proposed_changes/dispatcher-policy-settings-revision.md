---
proposal: dispatcher-policy-settings.md
decision: accept
revised_at: 2026-07-14T05:22:05Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

ACCEPTED by the maintainer (2026-07-14). Retires the monolithic Full autonomous mode and replaces it with independent, orthogonal dispatcher.* policy settings: each a global default, overridable per work-item by a ledger label (wip_cap excepted -- a per-repo concurrency ceiling cannot be per-item), each settable via the orchestrator API and the console. Also ratifies a REAL post-merge AI acceptance pass (pass/fail, replacing the hardcoded stub) with AI-fail -> auto-rework SCOPED to the AI-dispositive modes (ai-only / ai-then-human); under human-only the pass is ADVISORY -- it informs, never decides, and a failing pass leaves the item parked for the human. Makes the in-factory review gate blocking (escalate-on-cap unless merge_on_review_cap), adds two configurable caps bounding the inner (pre-merge review) and outer (post-merge acceptance) rework loops, and codifies the API-configurable => console Settings + inline help + settings doc completeness principle with a mechanical check. Per-item labels BEAT the global default (the inverse of the retired mode, which overrode stored labels). Design record: thewoolleyman/livespec plan/autonomous-mode/handoff.md SESSION UPDATE 2026-07-14 (cont. 12) + its CORRECTION/ADDENDUM and the human-only DECISION section. Independently reviewed read-only by a Fable-model adversarial reviewer over six rounds (eleven blockers raised, all fixed; final verdict NO-BLOCKERS) per the standing pre-ratification review rule.

## Resulting Changes

- spec.md
- constraints.md
- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
