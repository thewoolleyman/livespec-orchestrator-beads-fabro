---
proposal: rendered-goal-reach-and-size-advisories.md
decision: modify
revised_at: 2026-10-21T16:55:02Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 4). The file carries two proposals, both adopted as filed. (1) Work-item bd-ib-n1kn: ten open rows in the livespec-overseer tenant pointed their implementer at a predecessor's comments as their evidence, which the sandbox cannot read; the host-side wall now reports such a reference as an ADVISORY finding naming the referenced work-item, and an unflagged item is never reported as clear, because the item's own analysis records that any mechanical discriminator is high-precision and low-recall. (2) Work-item bd-ib-40vz: item overseer-6s3pk6.6 grew to 10,862 bytes from recorded measurements with nothing warning; when the committed dispatcher.goal_size_warning_bytes is set, an item whose rendered goal exceeds it carries an ADVISORY finding on the filing displays, the Dispatcher's stderr and journal, and needs-attention, never refusing or delaying a dispatch, with no default and a configuration finding for an invalid value. Both insert after the advisory-finding sentence of "Authoring at filing time." and before "Either kind MUST be recorded". The only other change normalises scenarios.md's trailing extra blank line, left by the v191 revise, to a single final newline. Scenarios 218 and 219 were confirmed free on master and in every pending proposal. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes in round 1, and confirmed that defining the new key in place is consistent with the policy-settings sections and the needs-attention envelope. Scenario 218 gains coverage and debt entries owned by bd-ib-n1kn, and Scenario 219 by bd-ib-40vz. The stale-branch precondition was skipped with --skip-stale-branch-check because its only finding, spec/reprove-merged-item-v2 (another thread's WIP proposal file, e942de03e), was verified unrelated: it adds only proposed_changes/reprove-merged-item.md.

## Modifications

contracts.md, section 'Effective acceptance criteria', paragraph 'Authoring at filing time.': both filed proposals' sentences inserted after 'because only the gate can judge it.' and before 'Either kind MUST be recorded'. scenarios.md: Scenarios 218 and 219 as filed, and the trailing extra blank line left by the v191 revise normalised to a single final newline.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T16:54:19Z
verdict: NO BLOCKERS
proposal_stem: rendered-goal-reach-and-size-advisories
content_digest: 34b0327abd237393547605ff8a1e6533cadd4757801b1e222a706518fdcfc0d8
