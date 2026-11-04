---
proposal: gap-invariants-measured-not-delegated-to-retired-core-checks.md
decision: modify
revised_at: 2026-10-25T01:03:23Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in substance: livespec core retired gap-tracking-one-to-one and no-stale-gap-tied in core v103 (01c8324b, 2026-06-10), so a bar naming them can never be discharged. The migration clause and its scenario now state the two behaviours those checks verified, measured against this plugin's own list-work-items and detect-impl-gaps output, and the spec no longer names core's doctor as a detect-impl-gaps consumer. Modified after independent review (gpt-6-astra, two BLOCKERS rounds, then NO BLOCKERS re-reviewed on the post-v211 base) found the proposal over-reached and under-reached.

## Modifications

(1) Cross-boundary handoff entry 2 (/livespec:doctor -> list-work-items --json, work-item structural invariants) is KEPT rather than deleted: Scenario 5 'Doctor cross-boundary read' and the list-work-items --project-root / --work-items-path flag text still describe that call, and retiring it changes an H2 heading, which is outside this proposal's gap-invariant scope. Only entry 3 (detect-impl-gaps gap invariants) is deleted, so the list carries entries 1 and 2. Retiring the list-work-items doctor handoff and Scenario 5 is deferred to a separate follow-up proposal. (2) The capture-impl-gaps opening parenthetical, which said 'both this skill and doctor consume the same canonical surface', is reduced to '(no in-skill duplication of the detection logic)': doctor no longer consumes detect-impl-gaps, and the implement skill's closure verification explicitly does NOT invoke it, so no shared-consumer claim remains true. (3) The migration paragraph is re-wrapped so its unchanged trailing sentences flow after the replaced sentence; their wording is unchanged.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-25T01:03:07Z
verdict: NO BLOCKERS
proposal_stem: gap-invariants-measured-not-delegated-to-retired-core-checks
content_digest: b4014854de8177e44e8bfc84d23c0122678f1be27e2c4122d7c637d2d74e0041
