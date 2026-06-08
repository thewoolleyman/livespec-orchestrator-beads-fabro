# contracts.md — livespec-impl-beads

Wire-level surfaces this plugin exposes (slash commands and internal
APIs), plus the beads-issue mapping the skills read and write through
the pinned `bd` CLI. Every contract here concretizes a slot in
`livespec/SPECIFICATION/contracts.md`; nothing here overrides upstream.

## Plugin namespace

The plugin's slash commands live under `/livespec-impl-beads:`. That
namespace is fixed by `.claude-plugin/plugin.json` and may not be
changed without a coordinated rename across consumers (because doctor's
cross-boundary invariants in `livespec` invoke skills through this
namespace prefix per `livespec/SPECIFICATION/contracts.md`
§"Cross-plugin invocation"). Renaming is a major-version-bump
operation.

## The ten-skill surface

Every entry below is REQUIRED. The descriptions concretize each skill's
behavior on the beads substrate; cross-boundary semantics (handoffs,
JSON output schemas, user-consent rules) are defined by
`livespec/SPECIFICATION/contracts.md` §"Implementation-plugin
contract — the 10-skill surface" and apply uniformly.

### Heavyweight authored skills (6)

#### `capture-impl-gaps`

Detect spec → impl gaps by invoking the sibling
`/livespec-impl-beads:detect-impl-gaps --json` thin-transport skill (no
in-skill duplication of the detection logic; both this skill and doctor
consume the same canonical surface). The returned gap-ids are presented
to the user one at a time; on consent, a new work-item is created in the
tenant DB via `bd create` carrying the `origin:gap-tied` and
`gap-id:<stable-id>` labels. Detection state is in-memory and discarded
at skill exit — no persistent intermediate artifact. Re-running the
skill is idempotent: an already-tracked gap-id is detected as "already
filed" and not re-prompted unless the user explicitly asks for a
refresh.

**`--since-version <vN>`** (optional). When set, passed through verbatim
to both `detect-impl-gaps` invocations (the `--json`
authoritative-set call and the rich-display call). Validation is
delegated to the underlying skill — if the value is invalid,
`detect-impl-gaps` exits `2` or `3` and `capture-impl-gaps` surfaces the
error and aborts.

The flag is the surface that callers (notably `/livespec:revise`'s
post-step per the coordinating epic
`livespec#coordinating-epic-stale-revise-enforcement`) use to scope
per-revise gap detection. Direct user invocations MAY use it as well
for any "show me gaps for changes since this version" workflow.

#### `capture-spec-drift`

Detect impl → spec drift heuristically (LLM-driven). For each finding,
present it to the user with a recommended action; on consent, hand off
to `/livespec:propose-change` via the cross-boundary handoff (per
`livespec/SPECIFICATION/contracts.md` §"Cross-boundary handoffs"
entry 1). The handoff produces a proposed-change file under the
consumer's spec-side `<spec-root>/proposed_changes/`; this plugin never
writes to spec-side state directly.

#### `capture-work-item`

Freeform direct filing of a work-item. The user supplies title,
description, type, and priority; the skill creates a new beads issue via
`bd create` carrying the `origin:freeform` label and no `gap-id:` label,
plus the supplied fields. No gap detection runs; no closure-verification
rules attach. Closure is via the freeform path in `implement`.

The skill accepts an optional `--spec-commitment-hint <id_hint>` flag.
When supplied, the resulting work-item's `spec_commitment_hint` MUST
equal the verbatim `id_hint` (carried on the beads issue's native
`spec_id` field per §"Work-item beads-issue mapping"); when omitted, the
hint is absent (the freeform case). This is the surface livespec's
`unresolved-spec-commitment` doctor invariant queries via
`list-work-items --json` to verify each declared spec→impl commitment
maps to a filed work-item (per
`livespec/SPECIFICATION/contracts.md` §"Implementation-plugin
contract — the 10-skill surface" → "Work-item `spec_commitment_hint`
field").

#### `implement`

Drive Red → Green for a single work-item. The user picks the work-item
(or the skill defers to `next`'s recommendation). The skill walks the
user through:

1. Authoring a failing test (Red).
2. Implementing the change until the test passes (Green).
3. Closing the work-item.

Closure branches on `origin × disposition`. In every branch the closure
mutates the existing beads issue row IN PLACE (close-in-place): `bd
close --reason <reason>` sets terminal status and `close_reason`, `bd
update` sets the `resolution:<enum>` label, and — for resolutions that
imply a canonical-branch merge — the full `AuditRecord` is written into
the issue's `metadata` JSON column. No second record is appended.

- **gap-tied completion** — invoke `detect-impl-gaps --json`; confirm
  the `gap_id` is NO LONGER in the returned gap-id set; close with
  `resolution: completed` and an `AuditRecord`
  (`verification_timestamp`, `commits`, `files_changed`, `merge_sha`,
  optional `pr_number`) in `metadata`.
- **freeform completion** — close with `resolution: completed` and a
  user-supplied `--reason`.
- **non-completion administrative closure** — close with
  `resolution: <wontfix | duplicate | spec-revised |
  no-longer-applicable | resolved-out-of-band>`, carrying a
  user-supplied `--reason`.

#### `capture-memo`

Low-friction free-text deposit of an observation the user is not yet
ready to classify. The user supplies a one-paragraph text; the skill
creates a new beads issue via `bd create` carrying the `kind:memo` label
and the `state:untriaged` label, with `created_at` as the capture
timestamp. No dialogue branches; no classification.

#### `process-memos`

Per-memo handholding dialogue. Iterates over `state:untriaged` memos
(or a `--filter`ed subset) and for each:

1. Shows the memo content and timestamp.
2. Asks the user to pick a disposition (`spec-bound`, `impl-bound`,
   `persistent-knowledge`, `discard`).
3. Performs the disposition action (each updates the memo issue's labels
   in place — `state:untriaged` → `state:dispositioned` plus a
   `disposition:<value>` label — and records cross-references in the
   issue's `metadata` JSON column):
   - `spec-bound` — hand off to `/livespec:propose-change`
     (cross-boundary handoff entry 2) with the memo content as the
     proposed-change source material; set `disposition:spec-bound` and
     record the resulting `propose_change_topic` in `metadata`.
   - `impl-bound` — invoke `capture-work-item` internally to file a
     freeform work-item carrying the memo content; set
     `disposition:impl-bound` and record the resulting `work_item_id`
     in `metadata` for cross-reference.
   - `persistent-knowledge` — write the memo content into a
     newly-authored or existing `.ai/<topic>.md` file (the user picks
     the topic name in dialogue); add a reference to that file from
     `CLAUDE.md` and/or `AGENTS.md` if not already present; set
     `disposition:persistent-knowledge` and record the resulting
     `knowledge_file` path in `metadata` for cross-reference.
   - `discard` — set `disposition:discard`. The memo issue is preserved
     in the tenant DB (audit-trail discipline); only the state /
     disposition labels change.

### Thin-transport skills (4)

Each thin-transport skill is a short SKILL.md pass-through over a Python
`bin/` implementation (the wrapper-shape contract codified in
`livespec/SPECIFICATION/contracts.md` §"Wrapper CLI surface").
SKILL.md MUST NOT accrete logic — every behavior lives under
`.claude-plugin/scripts/bin/<skill>.py`.

#### `list-memos`

CLI surface: `list-memos [--filter <name>] [--json]`.

`--filter` flags supported:

- `--filter=untriaged` — show only memos whose `state` label is
  `untriaged`.
- `--filter=dispositioned` — show only memos whose `state` label is
  `dispositioned`.
- `--filter=all` — show every memo (default if no filter).
- Additional filters MAY be added in future revisions.

The skill reads the `kind:memo`-labelled issues from the tenant DB via
`bd` and filters in Python. `--json` output: an array of memo
materialized views (one per memo issue id); each view is the full
materialized record. Default human output: one-line summary per memo.

#### `list-work-items`

CLI surface: `list-work-items [--filter <name>] [--with-gap-id=<id>] [--with-spec-commitment-hint=<id_hint>] [--json] [--work-items-path <path>] [--project-root <path>]`.

`--filter` flags:

- `--filter=gap-tied` — `origin: gap-tied` only.
- `--filter=freeform` — `origin: freeform` only.
- `--filter=blocked` — `status: blocked` only.
- `--filter=ready` — `status: open` AND no unresolved `depends_on`
  edges.
- `--filter=closed` — `status: closed` only.
- `--filter=all` — default.

`--with-gap-id=<id>` — exact-match on the `gap_id` value (the
`gap-id:<id>` label).

`--with-spec-commitment-hint=<id_hint>` — exact-match on the
`spec_commitment_hint` value (the issue's `spec_id` field). Combinable
with `--filter` and with `--with-gap-id`.

`--project-root <path>` — override the cross-repo manifest and
connection-resolution base. Default: `Path.cwd()`. Used by doctor's
cross-boundary handoffs to invoke this skill from outside the consumer
project root.

`--work-items-path <path>` — repurposed connection-descriptor override.
The default substrate location is the beads tenant DB resolved from the
consumer's `.livespec.jsonc` `connection` block; this flag overrides the
resolved store descriptor (used by tests and by doctor invocations that
want to scope to a non-default store — e.g. the in-memory fake backend).
The keyword is retained for call-site parity with the plaintext sibling;
its value is no longer a filesystem path to a JSONL file.

The skill reads all issues from the tenant DB via `bd` and filters in
Python (mirroring the plaintext sibling's materialize-then-filter; no
SQL is issued by the plugin). `--json` output: an array of work-item
materialized views.

#### `next`

Cross-reference: cross-side composition of impl-side `next` with
spec-side `/livespec:next` is a Layer 3 (project-local orchestration)
concern per `livespec/SPECIFICATION/spec.md` §"Three-layer
orchestration architecture" → "Cross-side composition belongs at
Layer 3". This Layer 2 surface ranks impl-side state only; it MUST NOT
bake a cross-side weighting in.

CLI surface: `next [--limit <count>] [--offset <count>] [--json] [--work-items-path <path>] [--project-root <path>]`.
No `--filter` flag — the skill's job is to RANK rather than to filter.

`--limit <count>` — positive integer, default `5`. Maximum number of
candidates returned in the `candidates` array. Non-positive values MUST
cause the wrapper to exit `2` with a `UsageError`.

`--offset <count>` — non-negative integer, default `0`. Number of ranked
candidates to skip from the front of the ranked list before returning.
Negative values MUST cause the wrapper to exit `2` with a `UsageError`.

`--project-root <path>` — override the cross-repo manifest and
connection-resolution base. Default: `Path.cwd()`. Used by doctor's
cross-boundary handoffs to invoke this skill from outside the consumer
project root.

`--work-items-path <path>` — repurposed connection-descriptor override
(same semantics as for `list-work-items`): overrides the resolved beads
store descriptor; used by tests and by doctor invocations that want to
scope to a non-default store.

Ranking is a pure function of the materialized work-items read back from
`bd` (no LLM, and NOT delegated to `bd ready` — the cross-repo manifest
exclusion must run in Python). The reader populates each work-item's
`depends_on` from the issue's `blocks` edges so the ranker operates on
the same shape the plaintext sibling produces. The algorithm:

1. Identify ready items: `status: open`, `depends_on` either empty or
   all-closed.
2. Score by priority (lower number = more urgent) then by `gap-tied`
   ahead of `freeform` (gap-tied items have explicit spec backing) then
   by oldest `captured_at`.
3. Ties are broken deterministically by `id` lexicographic order.
4. Apply `--offset` and `--limit` to produce the returned slice.

Output schema (per `livespec/SPECIFICATION/contracts.md`
§"Implementation-plugin contract — the 10-skill surface" → `next` and
the upstream §"`/livespec:next` spec-side thin-transport skill" →
§"Output schema"): the output is a JSON object with two top-level keys,
`candidates[]` and `pagination`:

```jsonc
{
  "candidates": [
    {
      "action": "implement",
      "reason": "<one-line human narration>",
      "urgency": "high",
      "work_item_ref": "<id-of-ranked-item>"
    }
  ],
  "pagination": {
    "offset": 0,
    "limit": 5,
    "total": 12,
    "has_more": true
  }
}
```

Field semantics:

- `candidates[]` — array of candidate objects. `action` MUST be one of
  `"implement"` | `"none"`. The work-items-only scoping is principled:
  memos are a different slice of the store, and the canonical
  actionable-memo probe is `list-memos --filter=untriaged`;
  gap-detection and drift-detection are driver-side concerns the Layer 3
  driver invokes outside of `next`'s ranking. Each candidate MUST carry
  `action`, `reason` (non-empty human-readable narration), `urgency`
  (one of `high`, `medium`, `low`), and `work_item_ref` (the `id` of the
  ranked work-item, or `null` for `action: "none"`). Each candidate MAY
  include additional impl-beads-specific fields the wrapper emits (e.g.,
  `priority`, `origin`); the cross-plugin contract MUST NOT prescribe
  `additionalProperties` discipline per upstream.
- `pagination.offset` — echoed from `--offset`.
- `pagination.limit` — echoed from `--limit`.
- `pagination.total` — total count of ripe candidates BEFORE `offset`
  and `limit` are applied.
- `pagination.has_more` — `true` iff
  `offset + len(candidates) < total`.

`urgency` derivation per candidate: P0 → high; P1, P2 → medium; P3,
P4 → low.

When no items are ready, the wrapper MUST emit `candidates: []` with a
`pagination` echoing the inputs and `has_more: false`. An empty
`candidates` array IS the no-work signal; it does NOT degrade to any
legacy single-object shape. The Layer 2 surface MUST NOT bake a hygiene
fallback into the emission: emission of the empty array is purely
advisory, and any "what to do when both `/livespec:next` and
`/livespec-impl-beads:next` are quiet" handoff is a Layer 3
(project-local orchestration) concern (per `scenarios.md` Scenario 6's
empty-queue handoff sub-step).

When `offset >= total`, the wrapper MUST emit `candidates: []` and
`has_more: false`. The wrapper MUST always emit a valid (possibly
empty) `candidates` array.

##### Layer 3 discoverability nudge — not applicable under v089 recast

Under the v089 upstream recast (`livespec/SPECIFICATION/spec.md`
§"Three-layer orchestration architecture" → "Layer 3 — Cross-repo
orchestration (livespec-resident)"), the Layer 3 discoverability nudge
applies only to `/livespec:next`; impl-plugin `next` skills do NOT carry
the parallel-and-symmetric nudge contract because impl-plugin repos do
NOT carry their own Layer 3 driver. The wrapper at
`.claude-plugin/scripts/bin/next.py` MUST remain a pure thin-transport
pass-through per the upstream §"Thin-transport skill doctrine" and this
plugin's §"Thin-transport skills (4)" preamble.

#### `detect-impl-gaps`

CLI surface: `detect-impl-gaps [--spec-target <path>]
[--project-root <path>] [--since-version <vN>] [--json]`. No `--filter`
flag — the skill emits the complete current gap-id set.

The skill reads the live Specification via the Spec Reader, enumerates
every MUST/SHOULD rule per the gap-rule enumeration contract (per
upstream §"Spec Reader required-capability surface" capability 1), and
computes a stable `gap_id` per detected rule. Gap-id derivation is a
pure function of rule text + canonical heading path; the same rule text
always yields the same gap-id across runs. This skill is
substrate-agnostic — it reads the spec tree, never the work-items store.

**`--since-version <vN>`** (optional, default `null`). When set to a
historical version integer that exists under
`<spec-root>/history/v<NNN>/`, the skill restricts its scan to files
whose content differs between `<vN>` and the live spec (i.e., the file
appears in `SpecDiff(version_a=<vN>, version_b=<live>).per_file`). For
each such file, only MUST / SHOULD clauses present in the live version
are considered (clauses removed by the diff are not gaps — they were
spec content that no longer exists).

Validation:

- The value MUST be a positive integer. Non-integer / negative input
  exits `2` with a usage error.
- The version directory `<spec-root>/history/v<padded-N>/` MUST exist.
  Missing version exits `3` with `PreconditionError` naming the expected
  path.

When omitted, the behavior is unchanged — scan every file in the live
spec.

`--json` output: a top-level JSON object with one key, `gap_ids`, whose
value is an array of strings:

```json
{
  "gap_ids": ["gap-<stable-id-1>", "gap-<stable-id-2>", "..."]
}
```

Default human output: one line per gap-id, prefixed with the spec-file
path + heading the rule was sourced from.

The skill is the canonical gap-detection surface for the plugin.
Consumers:

- `livespec` doctor's `gap-tracking-one-to-one` and `no-stale-gap-tied`
  invariants subprocess this skill via the
  `<impl-plugin>:detect-impl-gaps --json` cross-boundary handoff (per
  upstream §"Cross-boundary handoffs" entry 5).
- The heavyweight sibling `capture-impl-gaps` invokes this skill as its
  detection step before walking the user through per-gap consent.
- The heavyweight `implement` skill invokes this skill at gap-tied
  work-item closure to confirm the `gap_id` is no longer detected before
  closing the record.

The skill MUST NOT mutate any impl-side store; it MUST NOT write to the
tenant DB; it MUST NOT prompt the user. It is a pure read-and-emit
pass-through over the Spec Reader's output and the gap-rule enumeration.

## Beads connection model

The plugin reaches its tenant DB exclusively through the pinned `bd`
CLI in server mode with a FLAGS connection. This model is the verified
v1.0.5 surface; its derivation lives in
`livespec/dev-tooling/implementation/research/beads-schema-mapping.md`
§2.1, and the contract-level commitments are:

- **Pinned binary.** `bd` is pinned to v1.0.5 (sha256-verified release
  tarball). The plugin invokes `bd` by a managed absolute path resolved
  from configuration (the `LIVESPEC_BD_PATH` environment variable, or a
  configured default); it MUST NOT rely on the stale mise shim at
  `~/.local/share/mise/shims/bd`.
- **Server mode, externally managed.** The connection is established via
  `bd init --server --external --server-host <host> --server-port
  <port> --server-user <tenant> --database <tenant> --prefix <tenant>
  --skip-agents --skip-hooks --non-interactive --quiet`. The
  `--external` flag declares the `dolt sql-server` externally managed:
  the plugin never starts, stops, or owns the server. `--server-socket
  <path>` overrides host/port when supplied; TCP is the default for
  sandboxed callers that lack `0750` socket-directory access.
- **FLAGS connection — one secret only.** Every connection input is a
  flag EXCEPT the tenant password, which is supplied at `bd`-call time
  via the `BEADS_DOLT_PASSWORD` environment variable. The password is
  NEVER persisted in `.livespec.jsonc` or any committed file. The
  superseded `BEADS_DOLT_SERVER_*` env-var connection surface is NOT
  used.
- **`prefix == tenant == database`.** The beads prefix equals the tenant
  DB name (the load-bearing identity rule), so issue ids read back as
  `<prefix>-<suffix>`.
- **Operator-pre-created tenant DB.** The tenant DB is pre-created by
  the `dolt-server` operator via the root-run `onboard-tenant.sh`. The
  plugin NEVER issues `CREATE DATABASE`.
- **`dolt.auto-start: false`; auto-commit OFF.** `bd config
  dolt.auto-start` is set `false` so `bd dolt status` reports
  `running (external)` truthfully. Server-mode auto-commit stays OFF
  (the default); the server owns the transaction lifecycle and the
  plugin MUST NOT re-enable per-write commits.
- **In-memory fake backend.** For hermetic CI and the
  no-live-connection runtime fallback, the plugin selects an in-memory
  fake backend (via `LIVESPEC_BEADS_FAKE=1` or the `connection.fake`
  config key). The fake satisfies the same store API; the live-tier
  path against a real tenant DB is opt-in and gated on
  `BEADS_DOLT_PASSWORD`.

## Work-item beads-issue mapping

A work-item is one beads issue in the tenant DB. The mapping below is
the contract-level outcome of the field-map derivation in
`livespec/dev-tooling/implementation/research/beads-schema-mapping.md`
§Part 1. The logical work-item field set is identical to the plaintext
sibling's; only the on-substrate home of each field differs. The
materialized work-item the skills read back carries the SAME logical
fields the plaintext sibling exposes, so cross-boundary consumers
(doctor, the ranker) see a consistent shape.

Logical field → beads home:

- `id` — beads issue `id`, supplied explicitly at `bd create --id` time.
  Format `<prefix>-<6-char-base32-suffix>` where `prefix` is the tenant
  DB name. The legacy `li-`-style random suffix is preserved as the
  beads suffix so cross-references survive.
- `type` — beads `issue_type`. Identity for `bug` / `feature` / `task` /
  `chore` / `epic`.
- `status` — beads `status`. Identity for `open` / `in_progress` /
  `blocked` / `closed` / `deferred`. (beads-only statuses are never
  emitted by a plugin write.)
- `title` — beads `title`. Identity.
- `description` — beads `description`. Identity.
- `priority` — beads `priority` (int). Identity; `0` = highest /
  critical on both sides, `4` = backlog.
- `assignee` — beads `assignee` (first-class field). Identity when
  present; absent when null.
- `origin` (`gap-tied` / `freeform`) — beads label `origin:<value>`.
- `gap_id` — beads label `gap-id:<id>`. Present iff `origin == gap-tied`;
  REQUIRED non-empty when present, absent when `origin == freeform`. The
  gap-id ↔ label exactly-once invariant is honored as exactly one
  `gap-id:` label per gap-tied issue.
- `priority`/`status`/etc. unchanged on read — materialization parses
  the `bd` JSON.
- `depends_on` — beads `blocks` dependency edges. For each blocker, a
  `bd dep add <this-issue> <blocker> --type blocks` edge exists; the
  reader populates `depends_on` from these edges.
- `superseded_by` — beads `supersedes` dependency edge (`bd dep add
  <superseding> <this> --type supersedes`). Present iff non-null.
- epic linkage — beads native `parent-child` (`bd create … --parent
  <epic>` / `bd update <child> --parent <epic>`). An epic is a
  `type: epic` issue whose members are its beads children.
- `captured_at` — beads `created_at`. On live create the value is read
  back from the server; on import the supplied timestamp is preserved.
- `resolution` (typed enum) — beads label `resolution:<enum>`, one of:
  `completed`, `wontfix`, `duplicate`, `spec-revised`,
  `no-longer-applicable`, `resolved-out-of-band`. REQUIRED present when
  `status == closed`.
- `reason` — beads `close_reason` (set via `bd close --reason`).
  REQUIRED non-empty for closure records.
- `spec_commitment_hint` — beads native `spec_id` field. When non-null,
  carries the verbatim `id_hint` from a spec-side
  `spec_commitments.impl_followups[]` declaration (per
  `livespec/SPECIFICATION/contracts.md` §"Implementation-plugin
  contract — the 10-skill surface" → "Work-item `spec_commitment_hint`
  field"). Absent for freeform items with no spec-side commitment.
- `audit` (the whole `AuditRecord`) — serialized losslessly into the
  beads issue's `metadata` JSON column. Present when `resolution` is one
  of `{completed, spec-revised, resolved-out-of-band}` (the resolutions
  that imply git activity landed on the canonical branch); absent
  otherwise. `AuditRecord` schema:
  - `verification_timestamp` (string, required). UTC ISO-8601 seconds of
    audit-record creation.
  - `commits` (array of strings, required, MAY be empty). SHAs of
    commits comprising the work. After squash-merge these SHAs may no
    longer exist locally; tooling MUST tolerate that case.
  - `files_changed` (array of strings, required, MAY be empty).
    Repo-root-relative paths touched by the work.
  - **`merge_sha`** (string, required, non-empty). SHA of the merge
    commit on the canonical branch that introduced this work. Tooling
    MUST verify it is reachable from `origin/<canonical_branch>` via
    `git merge-base --is-ancestor`.
  - **`pr_number`** (integer or null, optional). GitHub PR number for
    traceability; null when the merge did not originate from a PR.

  The audit MUST be present when `resolution` is one of `{completed,
  spec-revised, resolved-out-of-band}` — all three carry an implied
  canonical-branch merge that the audit attests. Resolutions in
  `{wontfix, duplicate, no-longer-applicable}` MUST carry no
  `AuditRecord` in `metadata`.

### Materialized view and close-in-place

Each work-item is exactly ONE beads issue row; there is no
latest-record-wins reduction (that is the plaintext sibling's concern).
A closure mutates the row IN PLACE: `bd close --reason` sets the
terminal status and `close_reason`, `bd update` sets the
`resolution:<enum>` label, and the `AuditRecord` (when required) is
written into `metadata`. A `status: closed` issue is terminal —
re-opening (`bd update --status open`) is ALLOWED but DISCOURAGED (the
right pattern is to file a new work-item with a fresh `id` that
references the closed one via `superseded_by` or `depends_on`). The
tenant DB's own version history is the immutable backing log behind the
in-place mutation; doctor's `no-orphan-blocker` invariant in `livespec`
reads materialized views, and readers of this plugin MUST do the same.

### `work_item_merge_evidence` static check

The check walks every materialized work-item from the configured store
descriptor (reading the `AuditRecord` from each closed issue's
`metadata` column) and applies the following rules.

For each work-item with `status == "closed"`:

- If `resolution` is in `{completed, spec-revised, resolved-out-of-band}`:
  - REQUIRE an `AuditRecord` is present in `metadata`.
  - REQUIRE `audit.merge_sha` is non-empty.
  - REQUIRE `git cat-file -e <merge_sha>` exits 0 (the SHA exists in the
    local repo).
  - REQUIRE
    `git merge-base --is-ancestor <merge_sha> origin/<canonical_branch>`
    exits 0.
- If `resolution` is in `{wontfix, duplicate, no-longer-applicable}`:
  - REQUIRE no `AuditRecord` is present (the negative-evidence case — a
    record that says "this was closed administratively" must not carry
    merge-evidence).
- If `resolution` is null AND `status == "closed"`:
  - FAIL with message "closed work-item without resolution is
    malformed."

Work-items with `type == "epic"` are EXEMPT from the merge-evidence
requirement. Epics close when their child work-items (beads
parent-child members) are all closed; the check INSTEAD requires that
every child resolves to a closed work-item.

All operations are local `git` invocations (`cat-file`, `merge-base`);
the check is network-free per the existing no-network-I/O constraint
(the `bd` reads it depends on go through the same local `bd` client, not
a separate network surface owned by the check).

The check is plugin-private to `livespec-impl-beads` (it depends on the
beads-issue mapping this plugin defines — specifically the `AuditRecord`
in `metadata` and the `resolution:` label). The plaintext sibling ships
its own JSONL-shaped equivalent; the two are not interchangeable.

## Memo beads-issue mapping

A memo is one beads issue carrying the `kind:memo` label. Logical
field → beads home:

- `id` — beads issue `id`, same `<prefix>-<suffix>` format as
  work-items; memos preserve the legacy `mm-`-style suffix
  distinguishing them in cross-reference text.
- `text` — beads `description` (the memo body; Markdown permitted).
- `state` (`untriaged` / `dispositioned`) — beads label `state:<value>`.
- `disposition` (`spec-bound` / `impl-bound` / `persistent-knowledge` /
  `discard`) — beads label `disposition:<value>`. Present iff `state ==
  dispositioned`.
- `captured_at` — beads `created_at`.
- `work_item_id` — recorded in the memo issue's `metadata` JSON column
  when `disposition == impl-bound`.
- `knowledge_file` — recorded in `metadata` when `disposition ==
  persistent-knowledge`.
- `propose_change_topic` — recorded in `metadata` when `disposition ==
  spec-bound`.

`kind:memo` is the discriminator `list-memos` filters on; a memo issue
is never returned by `list-work-items` and vice versa.

## Spec Reader internal API

Per `livespec/SPECIFICATION/contracts.md` §"Spec Reader
required-capability surface", every `livespec-impl-*` plugin MUST expose
four capabilities through an internal adapter. The shape is
implementation-dependent; this plugin's shape is a Python module with
these public functions:

```python
def read_current_specification(spec_root: Path) -> SpecSnapshot: ...
def read_specification_history(spec_root: Path, version: int) -> SpecSnapshot: ...
def current_specification_version(spec_root: Path) -> int: ...
def diff_specification_versions(
    spec_root: Path, version_a: int, version_b: int,
) -> SpecDiff: ...
```

`SpecSnapshot` and `SpecDiff` are dataclasses defined under
`.claude-plugin/scripts/<adapter>/spec_reader.py`. The Spec Reader is
substrate-agnostic — it reads the spec tree, never the beads tenant DB —
so its implementation is shared near-verbatim with the plaintext
sibling. The initial implementation is a thin file pass-through (no
caching, no indexing); cached or section-indexed implementations remain
valid future refinements without contract change.

The Spec Reader MUST:

- Consult the active template manifest's `spec_files` list rather than
  hardcoding the well-known file set (per upstream §"Spec Reader
  required-capability surface" capability 1).
- Surface the `version-directories-complete` pruned-marker exemption
  when reading history (capability 2).
- Return `int` for the current version (capability 3).
- Compute diffs as a structured change list (capability 4); the initial
  implementation returns a `SpecDiff` carrying per-file
  added/removed-line counts plus a unified-diff body.

The Spec Reader MUST exclude content from
`<spec-root>/proposed_changes/`. Only ratified canonical content is
exposed; pending proposals are not yet intent.

The Spec Reader is consumed by `detect-impl-gaps`, `capture-spec-drift`,
`implement`, and `process-memos`. It is NOT a slash command and NOT
exposed through the `/livespec-impl-beads:` namespace.

## Persistent Agent Knowledge realization

Per `livespec/SPECIFICATION/contracts.md` §"Persistent Agent
Knowledge realization", the per-plugin form is
implementation-dependent. `livespec-impl-beads` realizes the store as:

- A directory `.ai/` at the consumer project's root containing one
  markdown file per topic (`.ai/<topic-slug>.md`).
- Each topic file is referenced from the consumer project's `CLAUDE.md`
  and/or `AGENTS.md` via a one-line bullet pointing at the file path.
  Reference inclusion is REQUIRED — orphaned topic files MUST NOT exist.
- `process-memos`'s `persistent-knowledge` disposition writes the memo
  content to the chosen topic file (creating it if absent) and updates
  `CLAUDE.md` / `AGENTS.md` references if needed.
- Topic files MAY accumulate; pruning is the user's call (`process-memos`
  does NOT auto-trim). Doctor's memo-hygiene invariant in `livespec`
  does NOT apply to dispositioned-into-store content (per upstream
  §"Persistent Agent Knowledge realization" bullet 3).

The harness loads `CLAUDE.md` / `AGENTS.md` automatically into agent
context per Claude Code / Codex / other harness conventions; the linked
`.ai/<topic>.md` files are loaded on-demand by the agent following
bullet references when relevant. This realization is the same slot the
plaintext sibling implements — it is substrate-independent (the
Persistent Agent Knowledge store is markdown files, never beads issues).

## `compat` block

Per `livespec/SPECIFICATION/contracts.md` §"Cross-repo
coordination — pin-and-bump", every consuming project's `.livespec.jsonc`
declares a `compat` block for each active impl-plugin. For
`livespec-impl-beads`:

```jsonc
{
  "implementation": { "plugin": "livespec-impl-beads" },
  "livespec-impl-beads": {
    "format": "beads",
    "compat": {
      "livespec": ">=0.1.0,<1.0.0",
      "pinned": "master"
    },
    "connection": {
      "tenant": "livespec-impl-beads",
      "prefix": "livespec-impl-beads",
      "database": "livespec-impl-beads",
      "server_user": "livespec-impl-beads",
      "server_host": "127.0.0.1",
      "server_port": 3307,
      "socket": "/var/lib/doltdb/dolt.sock",
      "fake": false
    }
  }
}
```

`format: beads` is fixed for this plugin (the substrate marker — the
plaintext sibling declares `jsonl`). `livespec` is a semver range
matching every `livespec` release this plugin's pinned version is known
to be compatible with. `pinned` is the SPECIFIC `livespec` release tag
the consumer currently runs against (`master` during bootstrap, which
fires doctor's `contract-version-compatibility` `warn` as expected).
Both are REQUIRED per upstream.

The `connection` block is plugin-specific configuration. Its keys:

- `tenant` / `prefix` / `database` — all equal (the load-bearing
  identity rule; the prefix doubles as the tenant DB name).
- `server_user` — the least-privilege tenant user scoped to this DB.
- `server_host` / `server_port` — the TCP connection to the shared
  `dolt sql-server`.
- `socket` — the Unix socket path; OVERRIDES host/port when reachable.
  TCP is the default for sandboxed callers that lack `0750`
  socket-directory access.
- `fake` — selects the hermetic in-memory backend; `false` in the
  committed config (which describes the real connection). CI and tests
  set `LIVESPEC_BEADS_FAKE=1` to force the fake.

The tenant PASSWORD is deliberately ABSENT from this block. It is
supplied only via the `BEADS_DOLT_PASSWORD` environment variable at
`bd`-call time and is NEVER committed. The `LIVESPEC_BD_PATH`
environment variable (the managed absolute path to the pinned `bd`
binary) and `LIVESPEC_BEADS_FAKE` likewise overlay this block at
runtime and are not committed config keys.

There is no `work_items_path` / `memos_path` key — those are the
plaintext sibling's JSONL-file locations; this plugin's substrate is the
tenant DB resolved from the `connection` block.

**`canonical_branch`** (optional string). The canonical branch name
against which merge-evidence checks (see §"`work_item_merge_evidence`
static check") verify reachability. Default: the value of
`git symbolic-ref --short refs/remotes/origin/HEAD` (typically `master`
or `main`). Hard-coded fallback when symbolic-ref resolution fails:
`"master"`. The key is project-level (one value per repo), not
per-work-item — static checks resolve it once per invocation and apply
it uniformly.

The configuration block is read by every skill at invocation time. A
missing or malformed block MUST fire a `fail` finding from doctor's
`contract-version-compatibility` invariant (upstream §"Cross-boundary
doctor invariants").

## Cross-boundary handoffs

Per `livespec/SPECIFICATION/contracts.md` §"Cross-boundary handoffs",
this plugin participates in these red-edge handoffs:

1. `/livespec-impl-beads:capture-spec-drift` →
   `/livespec:propose-change` (drift findings).
2. `/livespec-impl-beads:process-memos` → `/livespec:propose-change`
   (spec-bound memo disposition).
3. `/livespec:doctor` →
   `/livespec-impl-beads:list-memos --filter=untriaged --json`
   (memo-hygiene invariant).
4. `/livespec:doctor` → `/livespec-impl-beads:list-work-items --json`
   (work-item structural invariants).
5. `/livespec:doctor` → `/livespec-impl-beads:detect-impl-gaps --json`
   (gap-detection invariants `gap-tracking-one-to-one` and
   `no-stale-gap-tied`).

The handoff mechanism is namespace invocation (per
`livespec/SPECIFICATION/contracts.md` §"Cross-plugin invocation") —
never direct CLI shelling-out to wrapper paths.
