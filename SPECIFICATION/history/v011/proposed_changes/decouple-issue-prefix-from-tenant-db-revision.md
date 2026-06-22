---
proposal: decouple-issue-prefix-from-tenant-db.md
decision: accept
revised_at: 2026-06-22T07:12:05Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: prefix-decouple
---

## Decision and Rationale

th53uv decoupled the beads issue-ID prefix from the tenant DB name; config and dolt-server contract already reflect it. Accepting aligns this repo's own dogfooded SPECIFICATION with the decoupled model: the tenant DB name (== database == server_user) is the <=32-char identity, the issue-ID prefix is bd's server-stored create-prefix (a short alias, here bd-ib) decoupled from the DB name.

## Resulting Changes

- spec.md
- constraints.md
- contracts.md
