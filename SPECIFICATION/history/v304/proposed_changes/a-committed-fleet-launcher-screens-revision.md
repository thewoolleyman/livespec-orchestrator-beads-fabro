---
proposal: a-committed-fleet-launcher-screens.md
decision: modify
revised_at: 2026-11-05T11:07:56Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:gmktec-factory-placement
---

## Decision and Rationale

Decided in delegated mode by claude:gmktec-factory-placement. legacy-coordinator-agent gave the decision in advance, under its R301 delegated authority (this is not the maintainer's own answer), recorded on bd-ib-v52w7a at 2026-11-05T06:40:06Z: ACCEPT all three findings. (1) A committed fleet-launch launcher screens host-only items with the Dispatcher's shared factory-safety routing predicate, through `dispatcher.py host-only`, before any mutex or preflight, and a drive or resume that exits 5 is never re-ticketed. (2) Every permanent pre-dispatch refusal, the host-only refusal of a hand-picked dispatch included, exits 5 with exactly one `REFUSED:` stderr line. (3) A repository hold file may scope itself to launch kinds (`kinds: dispatch|resume`) and carry `reason:` and `until:` text, a file with no `kinds:` line still holds everything, dispatch stays un-split, and every applicable hold is re-read under the factory mutex at the launch point. Measured motivation: bd-ib-dqxcsh (host-only refusal exited 1 and was re-ticketed, 2026-11-05 05:35-05:39Z), hold (g) (2026-11-05 06:14Z, which could not let resumes run while holding fresh launches), and bd-ib-6gx4mn (launched after hold (g) was set, because the interim launcher never re-read the repository hold under the mutex). The new scenarios take the next free numbers, 314-316. The independent sonnet reviewer reported NO BLOCKERS on these exact bytes.

## Modifications

Five wording changes against the proposal text; none changes behaviour. (a) Finding 3's "An `exempt:` line, once ratified, MUST exempt its work item whatever the `kinds:` line says" becomes "A per-item exemption that a hold file carries under any rule of this section MUST apply whatever the file's `kinds:` line says", so the ratified spec composes with the still-pending a-fleet-launcher-honours-a `exempt:` syntax without citing an unratified rule. (b) Scenario 316 is written as Gherkin from the proposal's prose Given/When/Then, with a third scenario for the hold re-read under the mutex, which the proposal's harness paragraph requires. (c) The harness-case additions are new "The `check-fleet-launch` harness cases MUST also cover ..." paragraphs that name Scenarios 314 and 316, matching the section's existing harness paragraphs. (d) Scenario 314's example REFUSED line reads "is refused" rather than "is held". (e) The new exit-code paragraph names Scenario 315, and Scenario 315's governing clause names the H2 that contains "Dispatcher exit codes".

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T11:03:38Z
verdict: NO BLOCKERS
proposal_stem: a-committed-fleet-launcher-screens
content_digest: 31d807c6ac09f2c30781261e11e10f7ae602542e7ee10bb17fe230ecb02ac6a6
