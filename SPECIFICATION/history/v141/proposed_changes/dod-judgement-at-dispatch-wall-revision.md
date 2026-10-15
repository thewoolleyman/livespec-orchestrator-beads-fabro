---
proposal: dod-judgement-at-dispatch-wall.md
decision: modify
revised_at: 2026-10-15T05:36:21Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5-plan-hp-factory-failure-follow-ups
---

## Decision and Rationale

Accepted with the two edits ordered by the Fable review #5 (APPROVE, 2026-10-15T01:04Z) plus one correction found by this revise's independent ratification review. Edit 1: the Dispatcher exit-codes entry for 5 now also names a pre-dispatch Definition-of-Done judgement refusal of a hand-picked dispatch, matching the sentence the proposal adds to 'The pre-dispatch wall'. Edit 2: a fourth Scenario 174 scenario covers a refused item that re-enters drain enumeration after its effective criteria or referenced headings change and is judged exactly once. Correction: gpt-6-astra round 1 (2026-10-15T05:34:39Z) returned BLOCKERS because that scenario required a verdict comment unconditionally while the clause requires one only for a refusing verdict. The scenario now carries the precondition that the changed criteria would still rest the item at needs-human, plus the refusal outcome; round 2 returned NO BLOCKERS on these final bytes. No H2 heading is added, so tests/heading-coverage.json is unchanged. Decision authority: the maintainer authorized the freeze driver (gitops-fleet-capacity-monitoring) to approve spec revises after a Fable subagent review. That authorization is recorded verbatim on livespec-dev-tooling-dfixhe (scope event, 2026-10-15T00:08Z). The driver relayed it to this session and directed this revise as v141 after v140. This session did not receive the authorization from the maintainer directly. Step 3.5 note: the stale-branch precondition was skipped explicitly. Its only finding was spec/plan-proof-release-rule-names-the-build-repository, owned by session k3s-on-gmktec-for-vps-usage, which adds a single proposed-change file, cuts no history and edits no spec file, so it cannot collide with this revision. The owner was notified. Implementation carrier: bd-ib-7f66ar (plan hp-factory-failure-follow-ups, epic bd-ib-qieqc6). Its dispatch-wall assertions are added to its Definition of Done after this revision lands.

## Modifications

contracts.md: the 'Judged again before dispatch' paragraph is inserted verbatim after 'Judged before admission'; the exit-code-5 sentence is appended to 'The pre-dispatch wall'; the dod_gate node sentence is replaced as proposed; and the Dispatcher exit-codes entry for 5 is widened (review #5 edit 1). scenarios.md: the three proposed Scenario 174 scenarios are appended verbatim, plus a fourth on re-entry after a criteria change (review #5 edit 2), whose precondition requires the changed criteria to still be refused (ratification round 1 correction).

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-15T05:35:59Z
verdict: NO BLOCKERS
proposal_stem: dod-judgement-at-dispatch-wall
content_digest: d78d15b6e388bac66be769963c25ae9e209cf33cd79c1994b5de85db608f271b
