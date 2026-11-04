---
proposal: merge-poll-re-runs-failed.md
decision: modify
revised_at: 2026-11-04T18:16:38Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:fleet-flaky-tests
---

## Decision and Rationale

Decided in delegated mode by claude:fleet-flaky-tests under legacy-coordinator-agent ruling R301, which accepted this proposal on the maintainer's behalf (cross-session message, 2026-11-04 ~18:0xZ). The source is the maintainer ruling of 2026-11-04 ~16:4xZ, recorded verbatim in the plan-scope-event of 2026-11-04T16:44:36Z on epic livespec-dev-tooling-6tgd2z. It amends the 2026-11-02 'never a whole-job rerun' rule for exactly one bounded case: one automatic failed-jobs re-run at merge-poll, only for a classified infrastructure, timeout or load failure, a flake item filed for each re-run, and never a re-run of a test the pull request touched. MODIFY rather than accept, for four reasons. Scenario 307 was taken on master by v296, so the scenario is renumbered 308. The independent sonnet reviewer raised four blockers across three passes, and each was resolved in the final bytes. First, kill and timeout evidence classifies a job even when it interrupts a pytest session, so oom-kill and job-timeout are reachable, and the touched-file guard covers failing tests named before the kill. Second, the re-run requires every failed job backing a required check to classify as infrastructure. Third, after the re-run only the higher run-attempt is judged. Fourth, a re-run request the forge rejects counts as the one re-run and ends blocked at once. The re-run outcome is journaled against the same row. No design record is contradicted, and this is not a drift-origin proposal. Carrier work item: bd-ib-tckulg.

## Modifications

Renumber the new scenario from 307 to 308, because v296 took 307. Classify every failed job of the workflow run; a kill or timeout that interrupts pytest is classified by that evidence; only a pytest failure with no kill or timeout evidence is unattributed. Re-run only when every failed required job classifies as runner-teardown, oom-kill or job-timeout and no failing test named before a job's end is in a PR-changed file. After the re-run, judge only the re-run attempt (the higher run-attempt number). A rejected or errored re-run request is journaled with its reason, counts as the one re-run, and ends blocked without waiting on the poll budget. The re-run outcome is journaled against the same row. Scenario 308 gains cases for an OOM kill re-run, an OOM kill after a touched failing test, mixed failed jobs, a pytest failure, and a forge-rejected request.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-04T18:15:29Z
verdict: NO BLOCKERS
proposal_stem: merge-poll-re-runs-failed
content_digest: 992e986fef8ad94212e05f1b540e66233e488f8fdc8e0a95b9b38f2b9181fdb0
