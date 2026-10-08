---
proposal: factory-size-justification-gate.md
decision: modify
revised_at: 2026-10-08T23:25:18Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: codex
---

## Decision and Rationale

Adopt the proposed conditional size gate without selecting a numeric ceiling. Preserve all other admission gates and the existing stricter consensus first-cut bound. This is the explicitly proposed change from permanently advisory size routing, not an implementation reinterpretation of the former rule. Independent read-only review: Sonnet session cdab7371-57ab-4d85-9b9e-f2fdbcc41d63, actual reported model claude-sonnet-5-5; the CLI reviewer_identity field uses its required alias sonnet.

## Modifications

Make the boolean refusal explicit; cover approval and every factory dispatch entry path; define exact justification keys and value types; retain the stricter consensus first-cut bound; add boundary and malformed-input scenarios as Scenario 153 on the current v117 base; co-edit the owned integration-test debt acknowledgment. No numeric threshold is adopted.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-08T23:23:20Z
verdict: NO BLOCKERS
proposal_stem: factory-size-justification-gate
content_digest: 395e5e8dc96034d64dd2892aba94e67f162b09919d325d6cb47012fe79e4e069
