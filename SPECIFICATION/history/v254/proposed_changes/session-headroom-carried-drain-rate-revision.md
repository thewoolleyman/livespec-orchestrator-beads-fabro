---
proposal: session-headroom-carried-drain-rate.md
decision: accept
revised_at: 2026-10-30T20:41:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under the delegated revise path (coordinator gitops-fleet-capacity-monitoring task, maintainer direction 2026-10-30: move pending proposals forward with AI-only consensus). Separate read-only Sonnet ratification review returned NO BLOCKERS. Adaptations to current text: DEPENDS ON session-headroom-baseline: apply that topic's edits FIRST. Edits 1 and 2 (contracts) and the three scenarios.md edits use anchors that exist only in the post-baseline text, because both proposals rewrite the same sentences (the 'projection is unavailable' sentence, the 'assessment history' sentences, and the no-baseline sub-scenario). The proposal's sentence replacement is merged with the baseline wording ('neither the journal nor the host history holds such a baseline and no carried rate exists'); the 'not assessed' case reads 'on the dispatching host' per the baseline. The carried rate is read from the checkout's journal only, as the proposal states; the baseline proposal's SHOULD about widening it is not applied. The proposal's replacement sub-scenario is expressed as a retitle plus an added Given step (same net text, plus the baseline's host-history step); the two new sub-scenarios are placed after the baseline's two, not directly after the no-baseline one. Edit 3 inserts the carried-rate clause after the 'whether a projection skip applied;' text and is independent of the baseline.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-30T20:11:53Z
verdict: NO BLOCKERS
proposal_stem: session-headroom-carried-drain-rate
content_digest: 6445cc93e53e67c7156043692250ffa151c1c0af88c937a7cc2d480faf1f5f78
