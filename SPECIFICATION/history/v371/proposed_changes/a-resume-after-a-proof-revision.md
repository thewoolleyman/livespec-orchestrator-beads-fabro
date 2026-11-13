---
proposal: a-resume-after-a-proof.md
decision: modify
revised_at: 2026-11-13T17:11:49Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratified under delegated decision. The coordinator graded proposal PR #5150 PASS (2026-11-13); legacy-coordinator-agent graded it PASS and gave the GO for this revise (2026-11-13 about 17:0xZ, the orchestrator slot after v370 = 447bc06c6). It changes no heading. The proposal anchors its paragraph after "the paragraph that begins 'The *resumed-at stage* is the node ...'". On master that text continues the "**What it resumes.**" paragraph rather than opening its own, so the paragraph is placed exactly where both of the proposal's anchors agree: directly after the text ending "only an unanswered or errored query is unobservable." and directly before "**What a resume does.**". This is the same location, so the text is unchanged. It releases bd-ib-bwwkne's spec-change-tier hold; the coordinator approves bwwkne after ratification. The revise applies decisions in created_at order, so each later decision's resulting files carry every earlier decision's edits and the last full-file write keeps all four.

## Modifications

One consistency repair from the independent ratification review: the fallback sentence "When the factory answers that it no longer holds the earlier run, or cannot be read, this anchor does not apply" drops ", or cannot be read". The section already says an unanswered or errored factory query is unobservable, and that a factory which cannot report the earlier run's liveness makes the resume refuse and MUST NOT proceed on an unobservable answer. As proposed, an unreadable factory would have both refused the resume and fallen back to the verdict. With the repair, only an authoritative not-held answer falls back to the verdict, which is what the proposal's own second scenario states, and an unreadable factory keeps the existing refusal. The placement note above also stands.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T17:10:16Z
verdict: NO BLOCKERS
proposal_stem: a-resume-after-a-proof
content_digest: 5cde601fa0d0a0d5dbe34c01d2ab43f9c737c8e36143dc348b5fe5cacd166c43
