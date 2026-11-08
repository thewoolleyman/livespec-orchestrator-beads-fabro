---
proposal: a-same-run-needs-human-descendant-wins.md
decision: modify
revised_at: 2026-11-08T07:26:01Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted with two refinements. legacy-coordinator-agent ruled the direction under R301 on 2026-11-08 and decided this digest; plan factory-run-work-preservation is maintainer-driven, and the coordinator keeps the maintainer's FYI-for-objection line open. The v308 name preference mandated bd-ib-ofvsr3's older tree d7f0102e1 over its descendant 578a981c2. The plan seat factory-run-work-preservation drafted the bytes. The decider selected exactly this digest and states that it did not re-read the resulting bytes line by line itself; it decided on the two refinements as worded, the exact three-ref outcome and the independent review. An independent sonnet reviewer returned NO BLOCKERS on the exact bytes twice: at 05:55:06Z on the v320-based accept, and at 07:22:21Z on these rebased, modified bytes, re-confirmed at 07:24:57Z on the digest computed with spec-relative paths.

## Modifications

Closed the reviewer's two non-blocking notes, which the coordinator approved. (1) When no tip descends from all the others, the newest-by-committer-time fallback considers only the maximal tips, those that no other carrying ref's tip descends from, so an ancestor is never taken over its descendant under clock skew. (2) On an equal committer time, the ref whose full name sorts first in byte order is taken. Two scenarios were added to the Scenario 185 block: a three-ref partial-descent case whose Then step is exactly 'routing takes needs-human/C', and an equal-committer-time tie. Cut as v322 on 886ebe8c7, because v321 took the earlier slot.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T07:24:57Z
verdict: NO BLOCKERS
proposal_stem: a-same-run-needs-human-descendant-wins
content_digest: db029418a85d209dab9e8047825949de70b382b32231ff639a4ca358d095d4a4
