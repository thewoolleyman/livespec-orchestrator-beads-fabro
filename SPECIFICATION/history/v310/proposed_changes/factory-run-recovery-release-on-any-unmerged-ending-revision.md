---
proposal: factory-run-recovery-release-on-any-unmerged-ending.md
decision: modify
revised_at: 2026-11-05T23:59:32Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Maintainer ruling 2026-11-05 (plan factory-run-work-preservation, epic bd-ib-nckst7, scope event frwp-ruling-recovery-release-2026-11-05): the maintainer chose "Any unmerged ending (Recommended)" from research note 006. The proposal implements that choice: an item whose latest dispatch ended without merging and whose livespec-preserved-tree receipt names that run's work-in-progress ref (or states its preservation could not be determined) is released for recovery once at ready, so restart, outside and returned wall-budget cancels are routed by recovery routing instead of fresh. Independent ratification review (sonnet): NO BLOCKERS.

## Modifications

Editorial normalization of the inserted contracts.md text only; meaning unchanged and the two Scenario 319 cases are as proposed. 'This sentence MUST NOT move' became 'This release MUST NOT move'; 'The release MUST read the ledger comment only, so deciding it takes no remote measurement' became 'Deciding this release MUST read the ledger comment only, so it takes no remote measurement'; 'Every sentence that follows' became 'Every sentence that follows in this paragraph'; 'an item this sentence releases' became 'an item this release covers'. The proposal's closing note on the pending proposal a-plain-re-dispatch-of is not spec text and is not carried into contracts.md.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T23:58:57Z
verdict: NO BLOCKERS
proposal_stem: factory-run-recovery-release-on-any-unmerged-ending
content_digest: 9891bfe1b16967728aa2195a44b37f644640a4cc3d7ff066efde4eeef0d34de3
