---
proposal: plan-resume-surfaces-rulings-and-timeline-omissions.md
decision: modify
revised_at: 2026-10-21T14:07:16Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 2). The file carries two proposals, both adopted. (1) Work-item bd-ib-p38r: read_timeline returned 69 entries while epic overseer-hgq4wi held 104 typed plan comments across five kinds, so whole kinds were invisible through the reader named for the timeline, and an absence that reads as a failed write invites an unremovable duplicate comment. The timeline read path now returns every handoff entry and scope event and reports each other plan record kind it skips with its count. (2) Work-item bd-ib-ghijrt: a resume on epic bd-ib-fyozyd acted on its pointer without seeing two binding maintainer rulings recorded as scope events. Every resume now returns the epic's non-carrier-map scope events beside the typed next_action, and the plan operation surfaces them before acting. Modification beyond the filed text: Scenario 214's second case states checkably that ask, next_action and reason are unchanged by the rulings list, replacing "the same next_action decision as before". Scenarios 213 and 214 were confirmed free on master and in every pending proposal. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes. Scenario 213 gains coverage and debt entries owned by bd-ib-p38r, and Scenario 214 by bd-ib-ghijrt. The stale-branch precondition was skipped with --skip-stale-branch-check because its only finding, spec/reprove-merged-item-v2 (another thread's WIP proposal file, e942de03e), was verified unrelated: it adds only proposed_changes/reprove-merged-item.md.

## Modifications

contracts.md, section 'Ledger-held handoff persistence': after the scope-events sentence, the timeline read path returns every handoff entry and scope event oldest first with its kind, and reports each other plan record kind present with its prefix and count, never as absent. Section 'Typed next_action and last_session': after the ruling-identity clause, every resume returns every non-carrier-map scope event oldest first beside the typed next_action, the plan operation surfaces them before acting, and an epic with none returns an empty list. scenarios.md: Scenario 213, 'The plan timeline reports the record kinds it does not return', and Scenario 214, 'A plan resume returns the epic's rulings beside the typed next action', whose second case states that ask, next_action and reason are unchanged by the rulings list.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T14:06:52Z
verdict: NO BLOCKERS
proposal_stem: plan-resume-surfaces-rulings-and-timeline-omissions
content_digest: f6870420cf527fbb95522c91671efd2991f8bc44b56ad87e5f2f11c740657730
