# spec.md — livespec-orchestrator-beads-fabro

This is the natural-language specification for `livespec-orchestrator-beads-fabro`,
the beads-backed implementation plugin for `livespec`. The plugin
dogfoods `livespec` — this `SPECIFICATION/` tree evolves through
`/livespec:seed` / `propose-change` / `revise` / `doctor` /
`prune-history` / `critique`, exactly the same lifecycle every consumer
project uses.

## Purpose

`livespec-orchestrator-beads-fabro` is one realization of the abstract
implementation-plugin contract that `livespec` publishes in
`livespec/SPECIFICATION/contracts.md` §"Implementation-plugin
contract — the 10-skill surface". Other realizations exist on paper
(`livespec-orchestrator-git-jsonl`, `livespec-orchestrator-gitlab`,
`livespec-orchestrator-gascity`, `livespec-orchestrator-darkfactory-kilroy`) and are
out of scope here. This plugin's substrate is a per-repo tenant
database on a shared, externally-managed `dolt sql-server`, reached
through the pinned `bd` (beads) CLI in server mode. Work-items are
beads issues in that tenant DB; the plugin never embeds a local
database and never speaks SQL directly — every read and write goes
through `bd`.

`livespec-orchestrator-beads-fabro` and `livespec-orchestrator-git-jsonl` are structurally
identical EXCEPT for this persistence substrate. The git-jsonl sibling
commits append-only JSONL files alongside the consumer project's other
source; this plugin keeps the same logical model (work-items, the
latest state of each by id) but stores it as rows in a beads tenant
DB. Everything above the store boundary — the 7-skill surface, the
Spec Reader, the cross-boundary handoffs, the `compat` block — is the
same contract.

## Scope boundary

The substrate is the only thing this spec describes that is unique to
the plugin. Everything else — the names of the seven skills, the
cross-boundary handoffs, the Spec Reader's required-capability surface,
the `compat` block format, the per-plugin Persistent Agent Knowledge
store realization slot — is FIXED by `livespec`'s published contract.
This `SPECIFICATION/` MUST NOT re-state `livespec`'s contract; it MUST
concretize the contract for the beads substrate and point upstream for
anything else.

When `livespec`'s contract changes, this plugin's `compat` block pin
moves forward in a discrete bump-pin PR (per `livespec`'s pin-and-bump
mechanism), at which point this `SPECIFICATION/` may require companion
revisions to honor the new surface. The current pinned `livespec`
reference is recorded in `.copier-answers.yml`
(`livespec_release_tag`) and in `.livespec.jsonc`'s
`livespec-orchestrator-beads-fabro.compat` block.

## Terminology

This spec adopts every term defined in
`livespec/SPECIFICATION/spec.md` §"Terminology" verbatim
(Specification, Specification History, Work Items,
Persistent Agent Knowledge, Gap, Gap-id, Origin, Spec Reader,
Transient, Durable-pending, etc.). The terms below are plugin-local
additions or refinements; they extend the upstream glossary, never
contradict it.

**Beads issue (work-item)** — One row in the tenant DB's `issues`
table, created and mutated through `bd`. Schema realization is defined
in `contracts.md` §"Work-item beads-issue mapping". A work-item is the
materialized state of one beads issue: id, status, title, description,
priority, assignee, the labels carrying `origin` / `gap_id` /
`resolution`, the `blocks` / `supersedes` / `parent-child` dependency
edges, and the `AuditRecord` carried in the issue's `metadata` JSON
column. There is exactly ONE row per id; state transitions mutate that
row IN PLACE rather than appending a second record.

**Tenant database** — The per-repo Dolt database on the shared
`dolt sql-server` that holds this consumer project's beads issues. The
tenant DB is pre-created by the `dolt-server` operator (the root-run
`onboard-tenant.sh`); the plugin NEVER issues `CREATE DATABASE`. The
tenant DB name (`== database == server_user`) is the load-bearing
≤32-char tenant identity. The beads `prefix` is bd's server-stored
issue-ID create-prefix — a short, readable alias DECOUPLED from the
tenant DB name (it MAY differ from it; here it is `bd-ib` for the
`livespec-orch-beads-fabro` tenant), so issue ids read back as
`<prefix>-<suffix>`.

**Close-in-place** — A closure mutates the existing beads issue row:
`bd close --reason` sets terminal status and `close_reason`, `bd
update` sets the `resolution:<enum>` label, and the full `AuditRecord`
is written into the issue's `metadata` JSON column. No second record is
appended; the row is the audit trail, with `bd`/Dolt's own
version history as the immutable backing log.

**Materialized view** — The current state of a work-item, read
back from `bd` (e.g. `bd show <id> --json` / `bd list --status all
--json`). Because beads is already one-row-per-id, materialization is a
near-identity parse of the `bd` JSON into the plugin's dataclasses
(no latest-record-wins reduction is needed — that reduction is the
plaintext sibling's concern). The reader populates `depends_on` from
the issue's `blocks` edges so the ranker operates on the same shape the
plaintext sibling produces.

**Persistent Agent Knowledge file** — A markdown file under
`.ai/<topic>.md` referenced from `CLAUDE.md` and/or `AGENTS.md` in the
consumer project. Per `contracts.md` §"Persistent Agent Knowledge
realization", `livespec-orchestrator-beads-fabro` realizes the upstream-mandated
Persistent Agent Knowledge store as these files plus the harness
instruction files that load them progressively. (This slot is
substrate-independent and identical to the plaintext sibling's.)

## Substrate properties

- The tenant DB lives on the shared `dolt sql-server`; connection
  parameters are configured in the consumer project's `.livespec.jsonc`
  under the `livespec-orchestrator-beads-fabro` section (`connection` block). The
  only secret — the tenant password — is supplied at `bd`-call time via
  the `BEADS_DOLT_PASSWORD` environment variable and is NEVER persisted
  in any committed file.
- The plugin connects in `bd` server mode via a FLAGS connection (per
  `contracts.md` §"Beads connection model"): `bd init --server
  --external --server-host … --server-port … --server-user <tenant>
  --database <tenant> --prefix <issue-prefix> --skip-agents --skip-hooks
  --non-interactive --quiet` (where `<tenant>` is the ≤32-char tenant DB
  name and `<issue-prefix>` is the short decoupled create-prefix, e.g.
  `bd-ib`). The server is externally managed
  (`--external`); the plugin never starts, stops, or owns the server
  lifecycle. `dolt.auto-start` is `false` and server-mode auto-commit
  stays OFF — the server owns the transaction lifecycle.
- The audit trail is the tenant DB's own version history plus the
  consumer project's git history of `.livespec.jsonc` and the spec
  tree. Work-item state is NOT git-tracked as files in the
  consumer repo (that is the plaintext sibling's model); it lives in the
  tenant DB.
- The materialized view of any work-item is read back from `bd`
  on demand; nothing on the consumer-repo filesystem mirrors the store
  state separately.

## What this spec is not

- Not a re-statement of `livespec`'s contract. When in doubt, defer to
  `livespec/SPECIFICATION/`.
- Not a Python implementation manual. Implementation details live in
  code under `.claude-plugin/scripts/` (the wrapper layer for
  thin-transport skills) and in the SKILL.md prose for heavyweight
  skills.
- Not a substitute for the upstream invariant catalog. Doctor
  invariants that span the spec ⇆ impl boundary (per
  `livespec/SPECIFICATION/contracts.md` §"Doctor cross-boundary
  invariants") apply uniformly across all impl-plugins; this spec
  describes what the plugin offers, not what doctor enforces.
- Not the canonical beads ⇄ livespec field-map authority. The field-map
  and connection-model derivation live in
  `livespec/dev-tooling/implementation/research/beads-schema-mapping.md`;
  `contracts.md` here records the contract-level outcome those
  derivations resolved to.

## Lifecycle and evolution

This `SPECIFICATION/` is governed by `livespec`. Changes land through
the standard livespec lifecycle:

- Propose: `/livespec:propose-change --spec-target SPECIFICATION/`
  drops a file under `proposed_changes/`.
- Critique: `/livespec:critique --spec-target SPECIFICATION/` surfaces
  issues before they ratify.
- Revise: `/livespec:revise --spec-target SPECIFICATION/` accepts,
  modifies, or rejects each pending proposal and snapshots a new
  `history/vNNN/`.
- Doctor: `/livespec:doctor --spec-target SPECIFICATION/` runs static +
  LLM-driven invariants.
- Prune: `/livespec:prune-history --spec-target SPECIFICATION/`
  collapses old history entries.

Every spec change MUST flow through this loop. Direct edits to the
top-level files outside a `revise` snapshot are out-of-process.
