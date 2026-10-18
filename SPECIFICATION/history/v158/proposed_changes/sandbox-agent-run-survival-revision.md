---
proposal: sandbox-agent-run-survival.md
decision: modify
revised_at: 2026-10-18T07:32:36Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:checkpoint-commit-hook-failures
---

## Decision and Rationale

Accepted with modifications under revise_decision_mode delegated. Freeze-driver ruling R154 (2026-10-18, under maintainer direction R148) directed this session to decide bd-ib-quzpge and bd-ib-dpkip6 and route them through propose -> revise under the repository's delegated ratification. quzpge: v142 protects /workspace, the working directory, its link and the clone directory, and allows any in-tree removal, so removing the clone's .git or emptying its top level still loses the run at the next checkpoint. The clone's .git directory and the whole non-hidden top level are now protected, and ordinary in-tree removals stay allowed. dpkip6: a sandbox agent's signal to PID 1 killed the sandbox the engine still needed. Signals that reach PID 1, every process, a protected process group or the ACP agent adapter are now refused, and signals to processes the agent started still run. Scenarios 197 and 198 are added. tests/heading-coverage.json and tests/heading-coverage-debt.json are co-edited with owned TODO rows naming bd-ib-quzpge and bd-ib-dpkip6. Scenario 196 is taken by v157 (proposal stranded-claim-release, PR 3211), so this revision is v158.

## Modifications

Relative to the filed proposal, after three rounds of independent gpt-6-astra ratification review. Round 1 (2026-10-18T06:14:05Z, three blockers): (B1) the filed allowances licensed other segments, so each paragraph now states only a refusal condition met by an executed segment. v142's allowance sentence is rescoped to its own condition. A new paragraph, 'One decision covers the run's protections.', refuses the command when any executed segment meets any of the three conditions; a segment meeting none never exempts another, and data-only mentions exempt nothing. (B2) The filed process clause carried competing 'would send a signal' and 'pattern matches' tests. It now applies conservative pattern refusal regardless of parent, user, ancestor or session filters. kill targets are defined after the signal options and --, so kill -1 <pid> is a signal option. The adapter is identified in the PID namespace. An unreadable protected command line refuses pattern selection, and run-time-produced targets are a declared boundary. (B3) Scenario fixtures were added: Scenario 197 names .git, src, build and README.md and adds a mixed-operand refusal; Scenario 198 adds adapter id and pattern refusals, a filter-does-not-exempt case and a mixed-segment refusal. Advisories adopted: whole-tree boundaries are measured at submission, aggregated across segments, include moves, and have an empty-top-level rule; the contents of .git and other hidden entries are excluded; the manifest-launch exception is preserved explicitly. Round 2 (06:17:23Z, one blocker): Scenario 198's allowed-pattern fixture now gives the adapter's exact command line, states that both protected command lines are readable, and states that neither matches http.server 8765. The kill 0 advisory is adopted for the caller's own process group. Round 3 (06:18:53Z): NO BLOCKERS. Recorded corrections: the filed Motivation's evidence that pkill -f "sleep 3600" matched PID 1's command line containing "sleep infinity" is not established by those strings, and the incident attribution on bd-ib-dpkip6 needs re-verification; the clause stands on the class of failure. The v142 implementation test test_a_glob_that_empties_the_repository_tree_is_not_refused on feat/bd-ib-jgedjo is intentionally superseded by Scenario 197 and must change when bd-ib-quzpge implements it. Round 4 (2026-10-18T07:01:27Z, rebase re-review on the v157 base, digest 968dc04f): NO BLOCKERS; the 120 change lines are identical to round 3 and nothing v157 introduced conflicts with them.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-18T07:01:27Z
verdict: NO BLOCKERS
proposal_stem: sandbox-agent-run-survival
content_digest: 968dc04f0c7ba48c9866fac53182e03fc136fbea13dc8888e8b18e8ccb0c8ca4
