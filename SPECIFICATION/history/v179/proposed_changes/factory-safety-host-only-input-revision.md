---
proposal: factory-safety-host-only-input.md
decision: modify
revised_at: 2026-10-21T09:58:40Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 10). Work-item bd-ib-fv4w: the closed factory_safety enum had no honest reason for an item whose authoritative input exists only on the host (overseer-pfpfty.8, 2026-08-12), so such an item stayed factory-eligible. The fourth reason needs-host-only-input host-routes it exactly as the other three do, and every enumeration of the reasons is updated. Modifications beyond the filed proposal: the factory_safety bullet's sharp-line sentence is scoped to the first three reasons, because reading host-only input is not applying host state; and two repairs from ratification review round 1: an input that is itself a secret is needs-host-secrets, which takes precedence, and Scenario 230's Given states a non-secret input that cannot be committed or fetched rather than only a gitignored file. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes in round 2. Scenario 230 gains coverage and debt entries owned by bd-ib-fv4w; the renamed #### set-factory-safety heading is not a tracked H2. Stale-branch precondition skipped with --skip-stale-branch-check: it tripped on spec/reprove-merged-item-v2 (e942de03e, another thread's WIP), whose diff against origin/master touches only SPECIFICATION/proposed_changes/reprove-merged-item.md and mentions neither factory_safety nor needs-host, so it is unrelated to this topic.

## Modifications

contracts.md: the factory_safety bullet's closing sentence now reads 'The sharp line for the first three: ...'; the needs-host-only-input definition adds 'an input that is itself a secret is needs-host-secrets, which takes precedence'. scenarios.md: Scenario 230's Given reads 'a non-secret review verdict held only in a gitignored host file' and adds 'And that input cannot be committed to the repository or fetched into the sandbox'.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T09:57:45Z
verdict: NO BLOCKERS
proposal_stem: factory-safety-host-only-input
content_digest: 3dccafe649bd92ee34b02f720f077493e94c0d5fc2c411806b3d0e0381645386
