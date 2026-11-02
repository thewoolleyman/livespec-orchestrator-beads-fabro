---
proposal: recover-redispatch-after-needs-human-or-non-converged.md
decision: modify
revised_at: 2026-11-02T01:36:09Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

MODIFY. Accepts the proposal's rule: an item whose latest dispatch ended at the needs_human or a non_converged terminal, and that has since returned to ready with no newer dispatch, is released for recovery, so recovery routing resumes it at the anchored node when the resume preconditions pass, seeds it from preserved work otherwise, routes it fresh only on confirmed absence, and holds it on a non-fallback refusal. Modifications: (1) the ordering is stated explicitly and correctly: the proposal said the across-dispatch no-progress refusal is graded before admission, but recovery routing already runs before the admission valve, so the final text grades the refusal of 'Across-dispatch required-result progress' BEFORE recovery routing for such an item, a refused item is neither routed nor offered to the admission valve in that pass, and the text names that ordering as the bound on a release that consumes no rework-cap budget (the delegated decider's stated safety condition); (2) the four scenarios land inside the existing Scenario 185 gherkin block instead of a new Scenario 296 heading, so no H2 changes and no heading-coverage entry is owed. Motivation: livespec-dev-tooling plan codex-implement-cost-per-run (epic livespec-dev-tooling-vspttc), research 003: 48 re-dispatches in 7 days followed an implement that ended ok and re-ran implement from scratch, $379.45 of Codex implement spend (upper bound), plus part of $475.87 after errored implements. Alignment: pending proposal transient-infra-release-and-re-dispatch adds a release route to the same section; it is compatible (align) and untouched by this pass, which narrows to this one topic. No design record is contradicted: the sentence 'An item not released for recovery is routed fresh' stands unchanged and the preserved-work preference order is the existing one. Decided under delegated revise_decision_mode: delegated decider legacy-coordinator-agent (ACCEPT under ruling R301, 2026-11-02, authorizing blocker fixes before ratification); revise run by plan seat codex-implement-cost-per-run. Independent read-only reviewer (sonnet, claude-sonnet-5-5) found NO BLOCKERS on these exact bytes, digest cb9ad2b09228446366fc4beb1ffa80eecf94fbc5c3a3578db110f38da3bfba3d. Reviewer nits left: the resume anchor wording for a needs_human run is the existing wording, and the no-rework-cap statement is stated twice.

## Modifications

Ordering made explicit: the across-dispatch required-result progress refusal is graded BEFORE recovery routing for an item released by this rule; a refused item is neither routed nor offered to the admission valve in that pass; the text names this ordering as the bound on a release that consumes no rework-cap budget. Scenarios placed as four new Scenario cases inside the existing Scenario 185 gherkin block instead of a new Scenario 296 heading.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T01:35:00Z
verdict: NO BLOCKERS
proposal_stem: recover-redispatch-after-needs-human-or-non-converged
content_digest: cb9ad2b09228446366fc4beb1ffa80eecf94fbc5c3a3578db110f38da3bfba3d
