---
proposal: session-headroom-reads-the-seven-day-allowance.md
decision: modify
revised_at: 2026-10-21T10:59:43Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 7). Work-items bd-ib-u3jq5r and bd-ib-jtlyoj: the session-headroom admission filter read only the five-hour utilization, so a Claude account whose seven-day allowance was exhausted was still dispatched into a certain refusal (measured 2026-10-15: seven-day utilization 0.95 with status allowed_warning; 2026-10-20: this plan's preflight hit the weekly limit). Modifications beyond the filed proposal: an explicit exhaustion vocabulary (exhausted only when the provider explicitly reports the seven-day allowance refused, for Claude a status of rejected; a warning or any other value is not exhaustion), the seven-day skip declared a headroom skip with floor-skip semantics that a floor of 0 disables, distinct naming of the seven-day skip in refusal and per-node selection records, and the journal carrying the seven-day status beside its utilization. Scenario 231 gains a warning-or-absent case and a floor-0 case. The scenario number was renumbered twice before ratification (227, then 228, then 231) after other revisions took those numbers; 231 was confirmed free on master and in every pending proposal. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes in round 1. It confirmed no textual or semantic conflict with the pending proposal session-headroom-carried-drain-rate, which amends other sentences of the same paragraph, and no conflict with the rule that the Dispatcher MUST NOT read an outside account-selection process's readings, because the seven-day figures come from the provider's own response. Scenario 231 gains coverage and debt entries owned by bd-ib-u3jq5r. The stale-branch precondition ran unskipped unless the revise record says otherwise.

## Modifications

contracts.md, section 'Provider spend containment', paragraph 'Admission filters candidates by projected Claude session headroom': immediately after the sentence 'It MUST read the provider's five-hour session utilization using the exact credential snapshot that the dispatch would project.', new sentences requiring the seven-day utilization and status from the same provider response, defining exhaustion as an explicit provider refusal, skipping a covered candidate whose seven-day status is exhausted as a headroom skip with floor-skip semantics (disabled by a floor of 0, named distinctly in refusal and selection records), never skipping on an absent, unparseable or unrecognised reading, and journaling the seven-day utilization and status. scenarios.md: Scenario 231, 'Admission skips a Claude candidate whose seven-day allowance is exhausted', with three scenarios: a rejected status skips, a warning or absent reading does not, and a floor of 0 disables the skip.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T10:58:07Z
verdict: NO BLOCKERS
proposal_stem: session-headroom-reads-the-seven-day-allowance
content_digest: 88c15f846cc93722c47dfd4da3e3af0ffe8e3bf4990829f48a2a4b2041969472
