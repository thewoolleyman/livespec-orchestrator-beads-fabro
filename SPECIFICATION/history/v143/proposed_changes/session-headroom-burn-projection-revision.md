---
proposal: session-headroom-burn-projection.md
decision: modify
revised_at: 2026-10-15T13:35:42Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:factory-configurable-model-fallback-priority
---

## Decision and Rationale

Accepted as reworked after a two-reviewer Fable consensus panel BLOCK on the first draft and a Fable delta-review APPROVE with zero blockers on PR 3049 (merged 5a6901b7), run by the gitops-fleet-capacity-monitoring freeze driver. Revise authorized by the maintainer's 00:08Z/00:22Z delegation recorded on livespec-dev-tooling-dfixhe, relayed by that driver, and by the maintainer's 06:32Z ruling placing plan factory-configurable-model-fallback-priority (epic bd-ib-jxvgq5) against the factory's account-exhaustion failures. The burn projection closes the admission gap measured on 2026-10-15, when bd-ib-dls2qt was admitted at 25 percent remaining on a credential draining about 21 points per hour and died on its session limit; the floor stays 20 and is aligned with the external rotation trigger by configuration only. Carrying work-item: bd-ib-2n2s7b.

## Modifications

(1) The proposal's inserted contract text, which the proposal presents as several paragraphs and two bullet lists, is flattened into running sentences inside the existing single-paragraph clause 'Admission filters candidates by projected Claude session headroom.', with bullet items joined by semicolons and wording otherwise identical (the independent reviewer notes one added 'and' before the final item of the projection-skip list). (2) Carried non-blocking tidy N5 from the approving delta review: the ratified sentence 'A floor of 0 disables both kinds of headroom skip' becomes 'A floor of 0 disables every kind of headroom skip', since the projection adds a third kind.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-15T13:34:15Z
verdict: NO BLOCKERS
proposal_stem: session-headroom-burn-projection
content_digest: 5f29ebae4e550274b68bb2962f41a9ebdb83543880cc6f7d85ea93260550f1a9
