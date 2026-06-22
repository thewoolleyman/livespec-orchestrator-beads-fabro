---
topic: decouple-issue-prefix-from-tenant-db
author: prefix-decouple
created_at: 2026-06-22T07:11:42Z
---

## Proposal: Decouple the beads issue-ID prefix from the tenant DB name

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/constraints.md
- SPECIFICATION/contracts.md

### Summary

The dogfooded SPECIFICATION still asserts the retired `prefix == tenant == database` coupling, but th53uv decoupled the beads issue-ID prefix from the tenant DB name. Rewrite spec.md, constraints.md, and contracts.md so the model is: the tenant name (== database == server_user) is the unique <=32-char Dolt identity, while the issue-ID `prefix` is bd's server-stored create-prefix, a short readable alias that MAY be distinct from the DB name (here `bd-ib` for the `livespec-orch-beads-fabro` tenant) and need NOT equal it.

### Motivation

Work-item livespec-th53uv decoupled the issue-ID prefix from the tenant DB name. The config (.beads/config.yaml + .livespec.jsonc) and the dolt-server contract already reflect this (PRs #118, #3, and master cdc6fcf). The repo's own dogfooded SPECIFICATION + code comments are the last surface still asserting the retired coupling; this propose-change aligns the spec prose.

### Proposed Changes

Rewrite each coupling assertion to the decoupled model:

- spec.md Terminology 'Tenant database': the tenant DB name (== database == server_user) is the load-bearing <=32-char identity; the beads `prefix` is bd's server-stored issue-ID create-prefix, a short alias DECOUPLED from the DB name (here `bd-ib`).
- spec.md Substrate properties bd-init example: `--prefix <tenant>` -> `--prefix <issue-prefix>` (keep `--database <tenant>` / `--server-user <tenant>`), with an inline note that `<tenant>` is the <=32-char DB name and `<issue-prefix>` is the short decoupled create-prefix (e.g. `bd-ib`).
- constraints.md Beads substrate constraints: replace the `prefix == database == tenant` identity bullet with one stating the tenant DB name is the load-bearing identity (database == server_user == tenant) and the `prefix` is the DECOUPLED create-prefix read from connection.prefix.
- contracts.md Beads connection model bd-init example + bullet: `--prefix <tenant>` -> `--prefix <issue-prefix>`; rewrite the `prefix == tenant == database` bullet to 'Tenant identity vs. decoupled issue-prefix'.
- contracts.md Work-item beads-issue mapping `id` clause: the prefix is the tenant's decoupled issue-prefix (e.g. `bd-ib`), NOT the tenant DB name.
- contracts.md `connection` block example + key descriptions: example `prefix` value -> `bd-ib`; split the `tenant`/`prefix`/`database` 'all equal' bullet into a tenant-identity bullet (tenant == database == server_user) plus a separate decoupled-`prefix` bullet.
