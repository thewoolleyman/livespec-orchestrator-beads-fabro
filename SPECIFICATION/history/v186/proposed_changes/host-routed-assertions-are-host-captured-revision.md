---
proposal: host-routed-assertions-are-host-captured.md
decision: modify
revised_at: 2026-10-21T14:39:35Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 3). Work-items bd-ib-rowuou and bd-ib-gv6uwy: the deliverable policy presumes a factory run, but an item with non-null factory_safety is host-routed and no factory run ever executes it, so a factory_captured assertion on it can never be evidenced. 14 host-routed items in the livespec-dev-tooling tenant parked at acceptance with "merging run id unavailable" and were closed by hand, the latest livespec-dev-tooling-jvem (2026-10-17/18). For such an item the first provable mode is host_captured (or human_attested), the sandbox-capability refusal does not apply, and a factory_captured assertion on it is an ADVISORY host-side wall finding naming the assertion, the factory_safety reason and the remedy; it does not withhold ready, per the definition-and-proof-of-done owner's choice of a filing-time warning over a refusal recorded on bd-ib-rowuou. The run-id binding of factory records is unchanged. Modification beyond the filed proposal: the proof-mode definition of host_captured in the same section said a host-routed item's factory_captured assertions are captured and verified by the host-routed run, which contradicts the new rule; it now says no factory run executes a host-routed item, so such an assertion cannot be evidenced and is governed by the deliverable policy. Scenario 217 was confirmed free on master and in every pending proposal. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, found that contradiction as the one blocker in round 1, and after the fix returned NO BLOCKERS on the exact resulting bytes in round 2. Scenario 217 gains coverage and debt entries owned by bd-ib-rowuou. The stale-branch precondition was skipped with --skip-stale-branch-check because its only finding, spec/reprove-merged-item-v2 (another thread's WIP proposal file, e942de03e), was verified unrelated: it adds only proposed_changes/reprove-merged-item.md.

## Modifications

contracts.md, section 'Effective acceptance criteria': in the proof-mode definitions, the sentence promising that a host-routed run captures and verifies a host-routed item's factory_captured assertions is replaced by one stating that no factory run executes a host-routed item, so such an assertion cannot be evidenced and is governed by 'The deliverable policy'. In 'The deliverable policy.' paragraph, after the sentence ending 'is still captured mechanically.', the filed sentences: a host-routed item's first provable mode is host_captured or human_attested, the sandbox-capability refusal does not apply to it, a factory_captured assertion on it is an advisory host-side wall finding that does not withhold ready, and the run-id binding is unchanged. scenarios.md: Scenario 217 as filed.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T14:39:13Z
verdict: NO BLOCKERS
proposal_stem: host-routed-assertions-are-host-captured
content_digest: cf0f3d9675f436bcb87a151fed97b4ba121efc628e2727680b4f07250ac704ec
