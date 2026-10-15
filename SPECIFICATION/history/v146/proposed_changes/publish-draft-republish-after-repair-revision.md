---
proposal: publish-draft-republish-after-repair.md
decision: accept
revised_at: 2026-10-15T17:53:30Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under the maintainer's delegation recorded on livespec-dev-tooling-dfixhe (00:08Z and 00:22Z rulings; ruling (5) at 00:09Z), as exercised by the stability freeze driver gitops-fleet-capacity-monitoring. The driver's Fable review blocked 2ef3a0a8 with four blockers and approved the rework 4c72f7a0 with 0 blockers. The only deviation from the proposal text is the cosmetic rewrap the driver asked for, keeping the fix-turn clause and the appended paragraph within 80 columns. The spec was self-inconsistent: v134 Refresh repair routes a repaired run back through publish_draft, while two v116 clauses forbade the only push that can publish a rebased repair. Measured on hp runs 01M504QX5PJF0VM35DMZT99S2D and 01M504S9SB8A on v0.201.0. One further deviation, found by the post-step doctor: the citation of "The cancel record" is written as the cancel record of §"Dispatcher progress watchdog", because a § citation must resolve to a heading. The final bytes were re-reviewed (gpt-6-astra, NO BLOCKERS).

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-15T17:53:09Z
verdict: NO BLOCKERS
proposal_stem: publish-draft-republish-after-repair
content_digest: 4a86d938ec45a94091665f15679ce6af7782cb99e7b26e369a584fbbc5f08606
