---
proposal: idle-slot-audit.md
decision: accept
revised_at: 2026-10-16T19:28:46Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under the maintainer's delegation recorded on livespec-dev-tooling-dfixhe (scope event 2026-10-16T06:29Z: spec revises continue under delegation during the capacity-first halt), as directed by the stability-freeze driver gitops-fleet-capacity-monitoring. That driver asked this plan session (factory-idle-with-ready-work, epic bd-ib-opbzv3) to draft, review, and revise this clause. This session did not receive that authorization from the maintainer directly. Motivation: on 2026-10-16 nine hp slots sat idle for about five hours while priority work was dispatchable, and only a driver's journaled script measured it. This clause ships that measurement as a read-only audit and attention fact. Review history: two independent read-only Fable review rounds on the proposal. Round 1 returned APPROVE-WITH-AMENDMENTS with two blockers. The first was a collision with Host concurrency belongs to the Fabro scheduler; it was resolved by removing every ceiling and free-slot figure rather than amending that section. The second was classification totality over beads-native statuses. Round 2 returned NO BLOCKERS, and its four wording fixes were applied verbatim. The independent read-only ratification review (gpt-6-astra, codex session 01a1462e-49ec-7f60-92a5-dba807e5c034) returned NO BLOCKERS on these exact bytes and recomputed the digest. Scenario 187 gains a heading-coverage TODO row and a debt-register row owned by bd-ib-irh4js, the implementing work-item. That item is held at backlog under the halt and is dispatched when the maintainer lifts it. Step 3.5 note: the stale-branch precondition was skipped explicitly, because this proposal's own branch, spec/idle-slot-audit, is the branch carrying this revise.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-16T19:28:09Z
verdict: NO BLOCKERS
proposal_stem: idle-slot-audit
content_digest: 66e1335af512c6f01216ef3e36909ea51f2bacd3b9165560854f0db4a9dcdf64
