---
proposal: generated-record-file-regeneration.md
decision: accept
revised_at: 2026-10-22T07:26:28Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:fabro-currency
---

## Decision and Rationale

Accepted under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by plan session fabro-currency (plan bd-ib-6tcjfx), which filed the proposal (PR 3493) for bd-ib-ze7xxj under coordinator rulings R570/R576 and ratifies it as a single-proposal pass under R202. It lets a dispatcher.record_files entry name a generator; a conflicted generated record file is resolved by running its generator after every other conflicted path, never by merging its text, on both the entry-wise merge route and the refresh-repair route; a refreshed head's generated files must equal their generator's output before the repository-declared gate, a mismatch failing as gate target generated-record-file:<path>; and the refresh-repair brief carries regenerate lines. Measured: three chase-master re-runs on 2026-10-22 lost default-branch rows of tests/heading-coverage-debt.json to a hand merge. It departs from no design record: the entry-wise merge of Scenario 200 stands for declarations without a generator, successful regeneration consumes no refresh-repair round, and a pre-gate mismatch takes the existing refresh-repair route under the existing two-round budget. Scenario 238's heading sits outside the gherkin fence (house format). The configured ratification reviewer, gpt-6-astra, in a separate read-only Codex session, returned NO BLOCKERS in round 1 on the exact resulting bytes (digest 8e7f9726425f2a8d2bf6e2367da067efd8092f88f32ef28bef08a1167a9a0d51) on master after v199 and independently recomputed that digest.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-22T07:23:48Z
verdict: NO BLOCKERS
proposal_stem: generated-record-file-regeneration
content_digest: 8e7f9726425f2a8d2bf6e2367da067efd8092f88f32ef28bef08a1167a9a0d51
