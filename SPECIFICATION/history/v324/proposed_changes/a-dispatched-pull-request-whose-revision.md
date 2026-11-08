---
proposal: a-dispatched-pull-request-whose.md
decision: modify
revised_at: 2026-11-08T15:22:36Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted with one refinement. legacy-coordinator-agent (session a6ed462d, claude-opus-5-5) decided this digest under R301 on 2026-11-08 and states that it read the proposal itself: the two contracts.md replacements, which make an armed pull request with passing or running required checks at budget exhaustion a handed-off merge wait and make stranded-claim item 8 run reconcile-merged on the handoff, and the six-sub-scenario Scenario 220. Plan factory-run-work-preservation is maintainer-driven, and the coordinator keeps the maintainer's FYI-for-objection line open. The plan seat factory-run-work-preservation drafted the bytes. An independent sonnet reviewer returned NO BLOCKERS on the exact bytes at 2026-11-08T15:19:53Z and recomputed the digest itself. The coordinator accepted both of its non-blocking notes as written: the counted-claims exclusion relies on §"Per-repo WIP cap" treating a succeeded run's active row as green-terminal, and the two unreadable-forge cases differ by design, since the merge wait rests the item while the stranded-claim pass holds the claim, as item 8 already states. Dependency: the fleet in-flight marker the handoff releases is governed by the stopped-launcher-marker root fix bd-ib-m3vdsv (closed, landed as PR #4663), on which this handoff's not-counted guarantee relies. Cut as v324 on b303e65c4, because publish-draft-green-work-loss took v323 under the coordinator's ordering rule.

## Modifications

Added to the handoff, after 'A handed-off merge wait is completed by §"Stranded claim release".', the coordinator-accepted sentences: 'The handoff MUST end the dispatching process, so the fleet launcher that started it removes its fleet in-flight marker as §"Provisional fleet launch scripts" requires when a launch ends. A handed-off row MUST NOT be counted by the shared fleet count, by a repository's counted claims, or by the in-flight addition.' Added the matching Then-steps to Scenario 220's first sub-scenario: 'And the dispatching process ends, so its launcher removes its fleet in-flight marker' and 'And the handed-off row is counted by neither the shared fleet count, the repository's counted claims, nor the in-flight addition'. The heading-coverage row for the retitled Scenario 220 heading is marked TODO for bd-ib-bacahf in the same change, because its earlier bound test asserts the superseded rest and exit code 4.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T15:19:53Z
verdict: NO BLOCKERS
proposal_stem: a-dispatched-pull-request-whose
content_digest: 0fb38b04f722ef6efce8fcad507f50467f1e0ff3d028d7aebc4342b694f79ff9
