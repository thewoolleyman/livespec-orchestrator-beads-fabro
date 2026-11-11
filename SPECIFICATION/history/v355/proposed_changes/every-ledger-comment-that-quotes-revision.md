---
proposal: every-ledger-comment-that-quotes.md
decision: modify
revised_at: 2026-11-11T20:31:51Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-2
---

## Decision and Rationale

Accepted on the fleet coordinator's decision given in advance (legacy-coordinator-agent, 2026-11-11): orchestrator writers that quote specification text verbatim into a ledger comment pass each quoted span through the one shared goal-template opener rewrite before the write, so the ledger record carries no opening delimiter for any reader. It is defence in depth beside the v330 goal-render rewrite. Work item bd-ib-engf4h owns the scenario.

## Modifications

Layout: the scenario takes this repository's un-numbered heading form and its Feature line equals the heading; the paragraph gains a closing sentence naming the scenario. Wording from the independent review: the first sentence speaks of quoted spans; a sentence states the obligation governs a comment not yet written and never rewrites a stored comment; scenario case 2 speaks of the digest carried by each record that carries one. Two clarifications ruled by the coordinator: a writer the specification elsewhere requires to use comment_safe_external_text is unchanged, and a reader MUST NOT derive a clause digest from a recorded quote. The proposal's instruction about tests/heading-coverage.json is carried out in the revise commit, not written into the specification.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T20:30:21Z
verdict: NO BLOCKERS
proposal_stem: every-ledger-comment-that-quotes
content_digest: a55a199804a206fe18ff6a0b863ae0a0eb324ff02bd8e06174c3ec5a8ed3f825
