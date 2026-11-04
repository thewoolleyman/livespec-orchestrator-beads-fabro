---
proposal: ledger-comment-file-transport.md
decision: accept
revised_at: 2026-10-28T02:01:57Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted, spec-first for bd-ib-jiwoij (routed URGENT by petri-factory-on-gmktec: on build 0.246.0 a pre-dispatch verdict comment over 131072 bytes kills the dispatcher with 'Argument list too long: bd' before claiming). A separate read-only Claude Sonnet reviewer, the configured ratification reviewer, returned NO BLOCKERS at 2026-10-28T02:01:56Z. An earlier read-only gpt-6-astra review raised one blocker in round 1 (stdin would satisfy the clause but not the file-transport assertion); its replacement was adopted verbatim, the proposal was re-filed, and its round 2 also returned NO BLOCKERS. Every ledger comment written through the live backend reaches bd through --file, never as an argv element, and reads back byte-identical, including a 196608-byte plan record.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-28T02:01:56Z
verdict: NO BLOCKERS
proposal_stem: ledger-comment-file-transport
content_digest: 62afb088d44c3e63ac06de5c61fe0d41ead594b10f432fdaf2b52631a331f1d8
