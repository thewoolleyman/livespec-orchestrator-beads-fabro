---
proposal: client-backup-lane-disabled.md
decision: modify
revised_at: 2026-10-15T04:35:39Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Plan dolt-server-failures (epic bd-ib-etfwwx) assertion 5 needs a governing clause for bd-ib-rxf: this repository's connection model is silent on the client backup lane, while dolt-server spec v023 (thewoolleyman/dolt-server#121) requires every centrally backed Beads tenant to commit backup.enabled: false and forbids widening the tenant grant. The bullet mirrors that contract for this repository and Scenario 181 exercises it. Scenario 180 is reserved by the pending proposal sandbox-path-protection, so this revision takes 181. Revision number v139 follows the coordinator's ordering (v137 sandbox-commit-leg-completion, v138 pr-refresh-reproof-relevance, v139 this proposal).

## Modifications

Independent review (gpt-6-astra) should-fix #5: the proposed scenario's 'a bd write runs' could pass vacuously if the write failed (for example on an authentication error, which prints no backup warning). Scenario 181 now requires a bd write made through the plugin from the repository root that succeeds, a readback of the written change from the tenant, and asserts the absence of the warning on that write's stderr. The scenario title of the sub-scenario became 'A successful ledger write with the key committed'. The contracts.md bullet is unchanged from the proposal except that its cross-reference names Scenario 181.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-15T04:35:08Z
verdict: NO BLOCKERS
proposal_stem: client-backup-lane-disabled
content_digest: 630192b543990d28291608bbc0fa441572c55db381b01d87cf98900525761227
