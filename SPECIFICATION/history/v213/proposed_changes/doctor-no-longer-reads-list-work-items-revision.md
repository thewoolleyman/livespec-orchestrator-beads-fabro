---
proposal: doctor-no-longer-reads-list-work-items.md
decision: accept
revised_at: 2026-10-25T02:38:01Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as written. livespec core retired every work-item doctor invariant in core spec v103 (commit 01c8324b), so no core doctor build calls list-work-items --json, and the unresolved-spec-commitment invariant is retired too. v212's reviewer kept the doctor -> list-work-items handoff only because Scenario 5 and the list-work-items flag text still described the call; this revision removes all three together, plus the identical framing on next's flags and in the beads-issue mapping consumer list. No list-work-items or next behaviour changes. Scenario 5 is retired without renumbering, following the precedent of the absent Scenarios 2 and 3, and its rows are dropped from tests/heading-coverage.json and tests/heading-coverage-debt.json in the same change. The independent reviewer (gpt-6-astra, read-only) returned NO BLOCKERS on these exact bytes, with a positive-controlled search over all five live spec files, tests/ and .claude-plugin/. Its one advisory, constraints.md's 'doctor catches violations' for closure metadata, names no core doctor and no list-work-items call, so it is out of this proposal's scope. Not drift-origin; no design record is contradicted.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-25T02:36:09Z
verdict: NO BLOCKERS
proposal_stem: doctor-no-longer-reads-list-work-items
content_digest: 7e3602bccac6a52de0389510b8df61036581837e31827e28c278c28a83541f8a
