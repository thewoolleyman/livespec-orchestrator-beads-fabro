---
proposal: a-stale-seed-is-rebased-before-it-runs.md
decision: modify
revised_at: 2026-11-14T00:55:52Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratified under delegated decision. legacy-coordinator-agent graded PASS and gave the GO for this revise (2026-11-13, orchestrator revise slot after v373). It releases bd-ib-zzhy5t's spec-change-tier hold (plan publish-draft-green-work-loss, epic bd-ib-acrr56). Its routing decisions stand: a seeded run never starts behind the default branch's tip read once per pass, a work-free seed routes fresh with reason no-change and consumes a ruling it came from, and a seed already on the tip is used unchanged. Its mechanism is superseded by a-stale-preserved-seed-is, ratified in this same pass, which explicitly REFINES it by replacing its rebase bullets with the diff-apply reseed. Its author, the publish-draft-green-work-loss seat (claude-opus-5-5:publish-draft-green-work-loss), consented on 2026-11-13 to ratifying it together with a-stale-preserved-seed-is. The revise applies decisions in created_at order, so each later decision's resulting files carry every earlier decision's edits.

## Modifications

Applied exactly as a-stale-preserved-seed-is change 2 requires, and nothing else: (1) the paragraph's heading sentence becomes "A seed is moved onto the current default branch before its run starts."; (2) its third bullet ("Otherwise the Dispatcher MUST rebase the seed's work ...") becomes the diff-apply reseed bullet that defers to the paragraph "A stale seed is re-seeded by diff-applying its work onto the default branch's tip" and names the reseed commit and its ref in the run, the seed record and the goal brief; (3) its fourth bullet becomes "When the reseed's apply conflicts, the route MUST be `held` as that paragraph states, with the refusal `seed-reseed-conflict`."; (4) in its closing paragraph "a rebase that cannot be read or attempted" becomes "a reseed that cannot be read or attempted" and "a clean rebase" becomes "a clean apply". Its item 1b ruled-seed sentence is applied with its cross-reference following the renamed heading: it names the paragraph "A seed is moved onto the current default branch before its run starts" and reads "holds one whose reseed conflicts" in place of "holds one whose rebase conflicts". Scenario 348's text is edited to match, as change 2 directs: its heading reads "reseeds its seed ... holds on a reseed conflict"; refs/heads/seed-rebased/ becomes refs/livespec/reseed/<work-item-id>/; a rebase becomes a reseed (the seed's work rebasing becomes the seed's diff against its merge base applying); seed-rebase-conflict becomes seed-reseed-conflict. 348 is kept: it is the number the proposal claimed and master holds no Scenario 348. Its first two bullets, its once-per-pass tip read and its rule that no seeded run starts behind that tip are unchanged. The author, the publish-draft-green-work-loss seat (claude-opus-5-5:publish-draft-green-work-loss), consented on 2026-11-13 to this modification and to ratifying it together with a-stale-preserved-seed-is. tests/heading-coverage.json gains the Scenario 348 row (work item bd-ib-zzhy5t) in the same commit.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T00:55:41Z
verdict: NO BLOCKERS
proposal_stem: a-stale-seed-is-rebased-before-it-runs
content_digest: cf1ef55e71f7bedb2f7c2411c7746956b7b66748bc23a327767df9cb36b16687
