---
proposal: ended-runs-kubernetes-sandboxes-are.md
decision: accept
revised_at: 2026-10-31T19:15:42Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:revise-label-and-sandbox-retention
---

## Decision and Rationale

Accepted as filed. The proposal adds `### Sandbox retention and collection` under contracts.md §"Dispatcher policy settings", immediately after §"Sandbox image enumeration", the clause the dispatch-time Definition-of-Done preflight named when it held work-item bd-ib-u5facl (plan kubernetes-sandbox-backend): an ended run's provider-held sandbox (driver record plus node workspace directory) is retained, without a time limit, while its work-item rests at `blocked` or `needs-human`, is deleted only through the provider's own delete operation once the item closes, journals and retries a refused deletion without transitioning the closed item, leaves other statuses unchanged, and collects idempotently. Nothing in the ratified spec states sandbox retention or collection, so it contradicts no existing text. The scenario is allocated Scenario 281, carried in fenced-gherkin form with the step text unchanged; the subsection names it, and tests/heading-coverage.json gains its TODO entry owned by bd-ib-u5facl in the same change. The independent sonnet reviewer returned NO BLOCKERS; its advisories (`needs-human` is elsewhere a blocked_reason of a `blocked` item, so the pair is redundant but unambiguous; three MUSTs lack their own scenario; `registered sandbox provider` is glossed rather than defined) are not defects and are left to the implementing item. Step 3.5 stale-branch precondition skipped via `--skip-stale-branch-check` (coordinator decision, 2026-10-31); the two stale `spec/*` branches it reported are NOT being surfaced as blockers this pass, and neither was touched, merged or deleted:
- `spec/host-judgement-isolation` (5cbf3f823, "host judgements launch outside the interactive agent configuration (v221)"): the loser of a v221 numbering collision; master's v221 is fea77b047 and master has since advanced to v260, so it cuts no version this pass could collide with and edits none of the text added here.
- `spec/reprove-merged-item-v2` (e942de03e): a WIP propose-change draft marked "Not for filing yet"; it adds only proposed_changes/reprove-merged-item.md, cuts no history version, and touches neither contracts.md section nor scenarios 280-281.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-31T19:14:48Z
verdict: NO BLOCKERS
proposal_stem: ended-runs-kubernetes-sandboxes-are
content_digest: 9d4a3486c5581820027191b442fb2a7ab2227a8603a0b11f7103667fb0582740
