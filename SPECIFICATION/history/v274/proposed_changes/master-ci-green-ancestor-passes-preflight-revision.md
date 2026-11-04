---
proposal: master-ci-green-ancestor-passes-preflight.md
decision: modify
revised_at: 2026-11-02T06:37:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in substance under the delegated decision mode (spec_governance.revise_decision_mode=delegated) with independent ratification review. The proposal fixes a measured factory-throughput defect (overlapping master CI runs starve every dispatch at the 1800 s bound while master is green) without weakening the red-default-branch refusal: a red latest run still refuses, a red newest concluded run blocks the new pass and leaves the existing wait in charge, and every unreadable condition falls back to the wait. It narrows only when the PENDING outcome is reached and so stays compatible with the design record of the clause it amends (proposal master-ci-pending-is-not-failure, history v129, epic bd-ib-jnpvh4). The independent reviewer (sonnet, read-only) returned NO BLOCKERS; its non-blocking notes (an 'except as below' pointer on 'MUST instead wait', denser scenario preconditions, no scenario for the no-concluded-run and unreadable-ancestry fallbacks) are left for a later wording pass and do not change behaviour.

## Modifications

Placement only: the new paragraph '**A concluded green ancestor passes while newer runs are pending.**' is placed as its own paragraph immediately after the existing '**A still-running master CI run is not a failure.**' paragraph (before '**A caller does not gate a dispatch on the default branch's CI.**') instead of splitting that paragraph, so the unchanged sentences keep their bytes and wrapping. Consequently the amended PENDING-outcome sentence reads 'the three conditions of the green-ancestor rule below' instead of 'the three conditions above'. All normative text is otherwise exactly as proposed; Scenario 171's gherkin is replaced exactly as proposed and its H2 heading is unchanged.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T06:35:30Z
verdict: NO BLOCKERS
proposal_stem: master-ci-green-ancestor-passes-preflight
content_digest: 4b53c4ae1d38e7c06cd5a9e48c77bc22a97f92f1a0f8f1ab8b21e1922cf5d9f1
