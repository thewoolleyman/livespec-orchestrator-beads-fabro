---
proposal: drive-close-duplicate-id-successor.md
decision: accept
revised_at: 2026-11-01T22:27:25Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

ACCEPT. Adds the human-only, status-independent close-duplicate:<work-item-id>:<successor-id> drive valve beside release-spec-tier: it closes an item that duplicates a work item already carrying its behaviour, in any non-closed status and whatever spec-change-tier hold it carries, records superseded_by, writes a ledger comment and one journal record naming successor and invoker, and refuses writing nothing on an unresolvable or self successor, an already closed item, or a live run or unreleased dispatch claim. The done door rule names it as a second owner; the superseded_by mapping states the cross-tenant form (metadata.superseded_by) since no dependency edge crosses tenants; Scenario 31 gains two scenarios; no H2 change. Motivation: bd-ib-jbbzxn, measured case livespec-dev-tooling-ipcm33 duplicating bd-ib-tqzazn (v254, Scenario 274), which no existing valve or plan disposition can close, blocking epic livespec-dev-tooling-dfixhe. Handed to plan spec-implementation-lockstep (epic bd-ib-ax3rds) under coordinator legacy-coordinator-agent ruling R301. Contradicts no design record. Delegated decision; independent read-only sonnet review NO BLOCKERS on these exact bytes. Nit left for a separate pass: the human-valve grammar counts and lists (contracts.md ~lines 381, 447, 1505) already omit release-spec-tier and now also omit close-duplicate. Re-cut as v270 after 69da40bce took v269; the hunks are unchanged and a fresh independent sonnet review returned NO BLOCKERS on the v270 bytes, with one more nit for the implementing item: the valve should close with resolution: duplicate, the existing enum value that needs no AuditRecord.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-01T22:26:44Z
verdict: NO BLOCKERS
proposal_stem: drive-close-duplicate-id-successor
content_digest: 770617bcd11af5a23297bd2d5cf8aa7692b80fc26f68efca06e75c26cab5f8fc
