---
proposal: red-turn-changes-no-product-file.md
decision: accept
revised_at: 2026-11-01T13:43:00Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

ACCEPT. Extends v262's "The implement stage runs Red and Green as separate nodes" so that test-first holds for the red turn's WRITES, not only its commit: the red prompt forbids creating, changing or deleting any product file, and commit_red refuses, naming each changed product path, when one differs from the dispatch base, which re-enters red from the dispatch base. Adds one scenario to Scenario 285. Motivation: the Honeycomb alert 'Factory post-hoc Red share' at 96% over eight hours on 2026-11-01, with Codex-ACP calibrations still showing first_product_write_before_red=true (152/228 refusals) after v227. v262 makes the Red commit test-only, but product edits left by the red turn would carry into green. Uses the product-file term v262's fifth commit rule already uses; contradicts no design record. Decided under delegated revise_decision_mode by plan session implement-test-performance (epic livespec-dev-tooling-sv6m5p; maintainer autonomy ruling 2026-11-01; the maintainer asked on 2026-11-01 that this alert's work be done). Independent read-only sonnet review: NO BLOCKERS on these exact bytes; nits left for the implementing item: untracked new product files count; the handoff file and non-product fixtures are exempt; the new sentences could sit after the commit_red staging sentence. No new H2, so no heading-coverage change.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-01T13:41:56Z
verdict: NO BLOCKERS
proposal_stem: red-turn-changes-no-product-file
content_digest: ffc55516f8f4737b71b4c333a555029ff12ebed19fd498bc6f803b0259755384
