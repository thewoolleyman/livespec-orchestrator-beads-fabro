---
proposal: janitor-check-suite-venue.md
decision: modify
revised_at: 2026-10-18T02:23:18Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:kubernetes-sandbox-backend
---

## Decision and Rationale

Ratifies the post-merge janitor check-suite venue that bd-ib-26deyw shipped in v0.210.0 (dispatcher.janitor.venue: host_local by default, cluster_job through the shared delegated gate, a lost cluster verdict is red), and the janitor-post-merge row fields that bd-ib-nsrgxl implements (venue, suite_source, started_at, gate_state, gate_tree_hash, copied Job keys). bd-ib-nsrgxl's dispatch (run 01M55WT5FB3G) was refused at the Definition of Done gate because no ratified clause governed these; this supplies it. Ratified under delegated revise (coordinator rulings R134, R136, R137 from gitops-fleet-capacity-monitoring) with an auto-spawned gpt-6-astra review.

## Modifications

Three gpt-6-astra review rounds. Round 1 (BLOCKERS): the cluster path's suite selection conflicted with the 'Janitor check-suite resolution' paragraph, and the verdict stream was not named. Round 2, under coordinator ruling R136 (option b): a new bullet makes the gate client's own suite resolution (pyproject.toml [tool.livespec_dev_tooling] gate_check_suite, or the client's documented default) govern under cluster_job, as the one exception to that paragraph, which keeps governing host_local. Standard error is pinned as the verdict stream in the clause and scenarios. A new suite_source row field names the rule that chose the suite. The three round-1 advisories are applied (attempted venue and submitted tree in the no-verdict case; presence-based copying includes an explicit null; the verdict line is the last state-bearing standard-error line). Scenario 190 gains differing-declaration and stdout-only sub-scenarios. Round 2 (BLOCKERS) found the fallback also covers a present but empty array. Round 3, under ruling R137: the fallback reads 'absent or declares an empty array', and the suite_source row assertion moved from Scenario 190 into Scenario 191, so 190 describes only shipped behaviour. Round 3 returned NO BLOCKERS, with one non-blocking advisory (Scenario 191's heading says 'ran' where 'was attempted' is more precise), left as reviewed. The tests/heading-coverage.json and heading-coverage-debt.json entries land as a same-PR hand edit outside the spec target, as v149 and v152 did; work item bd-ib-nsrgxl owns both bindings. A concurrent revision v153 (bd-ib-ptnxyg) landed first and added Scenario 192, so the resulting files were rebuilt on that master with Scenarios 190 and 191 inserted before Scenario 192; a fourth gpt-6-astra round re-reviewed the rebased bytes and returned NO BLOCKERS.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-18T02:22:59Z
verdict: NO BLOCKERS
proposal_stem: janitor-check-suite-venue
content_digest: b940e695ecd8c682066cb141ee8c072cca61bd503e3199e7d27cff4aa3f00543
