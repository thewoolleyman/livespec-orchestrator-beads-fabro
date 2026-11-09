---
topic: recovery-seed-never-outranks-a-newer-published-head
author: claude-opus-5-5
created_at: 2026-11-07T14:06:51Z
---

## Proposal: An earlier run's needs-human or preservation ref never outranks a newer run's published head, and a non-ancestor publish head is preserved before reclaim

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Bound the preference order of "Recovery from the failed run's preserved work" by run age, and protect a non-ancestor publish head before reclaim. Today the needs-human ref and a failed-checkpoint preservation ref are preferred over the observed published head whichever run published them. After this change that preference applies only to refs of the run that published the observed head, or of a later run; a ref of an earlier run never outranks a newer run's published head. A seeded route whose publish branch head is not an ancestor of the seed commit first pushes that head to a preserved ref on origin and verifies it by a remote read, or else routes held.

### Motivation

Measured 2026-11-06 on livespec-dev-tooling-phakbp:
- The item was meant to RESUME from its published draft livespec-dev-tooling#3649 (head d7f6cd37c).
- Recovery routing instead routed it SEEDED from needs-human/01M6S5B67ANM2BE1DX8YFN305M = 88a502b2c, an OLDER run's pre-emptive implement@1 partial tree on an unrelated lineage (36 files, +1494/-81 apart).
- The seeded route then closed #3649 and deleted feat/livespec-dev-tooling-phakbp. legacy-dispatcher-agent cancelled run 01M6SGH9AGNG (0 files changed) and saved d7f6cd37c by hand at preserved/livespec-dev-tooling-phakbp-pr3649.
- livespec-dev-tooling-wou75w run 01M6S6S0HG9E hit the same selection trap earlier.

The routing conformed to the current text, so this is a spec change, not a bug fix:
- The clause prefers the needs-human and failed-checkpoint refs over the observed published head with no run limit. The latest-run limit added for work-in-progress refs covers only those refs.
- Scenario 185 requires the SEED's preservation to be verified before the reclaim, but nothing requires the head being reclaimed to be preserved. A head newer than the seed is therefore deleted with no copy on origin.

Interim containment is a standing order from legacy-coordinator-agent to legacy-dispatcher-agent: preserve a non-ancestor publish head by hand before any reclaim. This proposal makes that order mechanical. The maintainer approved starting this work on 2026-11-07 ("OK start these", recorded on livespec-dev-tooling-6tgd2z at 14:04:11Z). Root-fix work item: bd-ib-so6fef (plan factory-run-work-preservation, epic bd-ib-nckst7), held at the spec-change tier for this topic.

### Proposed Changes

1. contracts.md, "Recovery from the failed run's preserved work", at the end of the sentence beginning "Its preserved work MUST be taken in the preference order this clause states below", append:

   > A needs-human ref or a failed-checkpoint preservation ref outranks the observed published head only when it was published by the run that published that head or by a later run of the item. A needs-human ref or preservation ref of an earlier run MUST NOT be preferred over a head published by a later run. When routing cannot determine which run published such a ref or the observed head, the route MUST be `held`.

2. Same clause, the seed-record paragraph ("The Dispatcher MUST prefer the failed run's successfully preserved terminal tree ..."): qualify "the failed run's successfully preserved terminal tree" with "of the run that published the observed head, or of a later run", and replace the sentence "It MUST verify preservation before deleting the publish branch." with:

   > It MUST verify the seed's preservation before deleting the publish branch. When the publish branch head is not an ancestor of the seed commit, the Dispatcher MUST also push that head to a preserved ref on origin and MUST verify that ref by a remote read before it closes the pull request or deletes the branch, and the seed record MUST name that preserved ref. When that preserved ref cannot be verified, the route MUST be `held`: the journal carries one `recovery-held` record naming the publish branch head, and the pull request MUST stay open with its branch at that head.

3. scenarios.md: add a new heading `## Scenario 323 — An earlier run's preserved ref never outranks a newer run's published head, and a non-ancestor head is preserved before reclaim`, with the governing-clause line `contracts.md` §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work", and these Gherkin scenarios under `Feature: Run-age-bounded recovery preference and preserve-before-reclaim`:

   - Scenario: An earlier run's needs-human ref does not outrank a later run's published head. Given an item whose latest run published head H to its publish branch, and an earlier run of the item holds needs-human ref N. When recovery routing grades the item. Then the route names H, or a needs-human or preservation ref the run that published H wrote, as the tree the next dispatch starts from. And the route never names N.
   - Scenario: The same run's needs-human ref is preferred over its own published head. Given an item whose latest run published head H and, at its ending, needs-human ref N. When recovery routing grades the item. Then the route is seeded from N.
   - Scenario: A non-ancestor publish head is preserved before reclaim. Given a seeded route whose publish branch head P is not an ancestor of the seed commit. When the route executes. Then P is pushed to a preserved ref on origin and verified by a remote read before the pull request is closed or the branch deleted. And the seed record names that preserved ref.
   - Scenario: An unverifiable preserved head holds the route. Given a seeded route whose publish branch head P is not an ancestor of the seed commit, and the preserved ref of P cannot be verified. When the route executes. Then the item is held with a `recovery-held` record naming P. And the pull request stays open with its branch at P.

   The scenario number MUST be re-checked at revise time and renumbered if 323 was taken in the meantime. The same revise pass MUST add a `tests/heading-coverage.json` entry for the new scenario heading (`test` MAY be `"TODO"` with a non-empty reason naming bd-ib-so6fef).
