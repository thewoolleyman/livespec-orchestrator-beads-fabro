---
proposal: implement-hook-refusal-reenters-implement.md
decision: modify
revised_at: 2026-10-24T22:51:27Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratifies bd-ib-y7372n (plan livespec-dev-tooling-dfixhe assertion 13) under coordinator gitops-fleet-capacity-monitoring's maintainer-directed stability priority: an incomplete implement turn whose staged changes the commit hook refuses, naming failed targets, re-enters implement with the hook's verdict in its brief while the retry budget lasts, instead of quitting on a fixable gate. MODIFIED after an independent read-only review (gpt-6-astra, session 01a17018-eabf-7df0-bd28-7aed79814bf0) found three blockers; the final review over the exact resulting bytes (session 01a1701a-bb95-7bc0-979c-30c1872381d7) returned NO BLOCKERS.

## Modifications

Partial-progress failure is kept as the explicit fallback for every incomplete turn that does not qualify for recovery. 'Refused' is defined operationally: the turn left changes staged and the repository's commit hook, run by the run itself over them, exits non-zero naming at least one failed target. Scenario 204 gains a staged-but-accepted scenario, the exhausted-budget scenario asserts the dispatch outcome detail, and the no-completion-field case is split into its nothing-staged and hook-refused arms.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-24T22:50:09Z
verdict: NO BLOCKERS
proposal_stem: implement-hook-refusal-reenters-implement
content_digest: cac0fcd360dcd24928d3db0efd38c7900f86913112aa02306adb7d36d66a6e5d
