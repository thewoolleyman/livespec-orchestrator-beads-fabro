---
proposal: run-wall-budget-continues-while-progressing.md
decision: modify
revised_at: 2026-11-10T22:44:45Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Maintainer ruling 2026-11-10 (plan factory-run-work-preservation, epic bd-ib-nckst7), verbatim: "if there is autonomous progress that can be made, and the item isn't thrashing or wasting tokens/infra resources, then it should be allowd to continue. And any items waiting on a human should not block other things from entering the factory." Then: "Decision 1: Yes file that proposal, and make it part of your plan." The proposal replaces the progress-independent whole-run wall budget. A run past the budget continues while it records committed progress (a new work-in-progress capture, or a first node completion) within a progress window equal to the dispatch's largest node timeout. Liveness does not count, and an ungradable run is not progressing. A hard ceiling (default three times the budget) bounds every run. A run that is not progressing takes the existing budget disposition and, while it waits for a person, holds no slot and no counted claim. The credential-use window is re-based on the ceiling. Measured 2026-11-10 with codex-cred-status: the requirement rises from 111600 s to 154800 s at defaults, against 667805 s of remaining Codex credential life, so the change only moves the host refresh about 12 h earlier. Departure from a prior design: the factory-run-wall-budget plan (research 001, 2026-10-14) made the budget a slot bound independent of progress, because liveness signals proved unreliable (plan stall-watchdog-false-kills). This revision deliberately departs from 'independent of progress' on the maintainer's 2026-11-10 ruling, and keeps that plan's lesson by grading committed work, never liveness, and by adding the hard ceiling as the slot bound.

## Modifications

(1) Added one sentence to 'Progress past the budget': a run continuing past its budget keeps its slot only while progressing, and a run waiting on a human after a budget cancel holds no slot and is not a counted claim under 'Per-repo WIP cap'. (2) Retitled Scenario 175's Feature line to match the retitled heading. (3) Applied the 'no capture and no first node completion within its progress window' condition to exactly the six Scenario 175 cases that cancel on the budget (the base needs-human case, the three held-export cases, the unreadable-ref-listing case and the budget-over-stall precedence case); cases premised on a cancel that already happened are unchanged. (4) Scenario 228 (independent-review blocker): each case that derives the credential-use window from the queue allowance and the budget now also states the ceiling, equal to the budget (21600 s), so every existing figure remains correct under allowance plus ceiling. (5) The new prose is written as single-line paragraphs. tests/heading-coverage.json is co-edited in the same change to rename Scenario 175's heading key.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T22:44:00Z
verdict: NO BLOCKERS
proposal_stem: run-wall-budget-continues-while-progressing
content_digest: f95f33018932f252680dfbbdfce8dc384de57ccd174b85fd8e6ebb6d01ecbdba
