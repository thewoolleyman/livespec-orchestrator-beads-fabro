---
proposal: claim-token-stand-down-names-its-successor.md
decision: accept
revised_at: 2026-11-06T17:03:23Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-1
---

## Decision and Rationale

Accepted under the project's delegated revise decision mode for bd-ib-kseatc (plan expedited-incident-response-flag, epic livespec-dev-tooling-bqnzcm; the 2026-11-06T09:17:45Z scope event records this item as the step-5 spec change, and the plan owner ruled the amendment on 2026-11-06 about 16:35Z). Step 5 of the Claim tokens bullet existed so a crashed winner never leaves an item unwritable, and its last sentence left one: a takeover that stood down discarded the successor it had already named in its own close of the stranded token, so the item's chain ended in a closed token and every later writer reported claim-changed for ever (measured on master 2026-11-06, bd-ib-7uue5s comments 08:04:36Z and 08:25:40Z). A stand-down now names its own successor on the item in one token-only write, which races nothing because only the holder of that successor can advance an item naming the token it closed; and applying the protocol to a stranded successor is stated to include step 5 itself, so a takeover follows a chain of closed tokens hop by hop with a fresh takeover wait at each hop. Scenario 263's stand-down scenario says the same and a chain scenario is added. The loser's discard in step 3, the lease, the takeover wait, the accepted residual class and the migration pass are unchanged; no heading changes. Independent ratification review (sonnet): NO BLOCKERS.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-06T17:02:42Z
verdict: NO BLOCKERS
proposal_stem: claim-token-stand-down-names-its-successor
content_digest: aa68ea3fc452d24b86a0d431ca110cf75253429ecaa696273d5de132c2c69ec3
