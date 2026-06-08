# constraints.md — livespec-impl-beads

Architecture-level constraints this plugin operates under. Each
constraint is a binary, mechanically-checkable rule; lint / type-check /
test failures are the enforcement mechanism.

## Inherited from livespec

Every constraint in
`livespec/SPECIFICATION/non-functional-requirements.md` applies to this
plugin without restatement. The list below captures only the
constraints that are PLUGIN-LOCAL refinements or that bear directly on
the beads substrate.

Inherited (verbatim, NOT re-stated here):

- Toolchain pins (mise + uv); `just` as the single dev-tooling entry
  point.
- Ruff rule set; Pyright strict mode plus the seven strict-plus
  diagnostics.
- 100% line + branch coverage; pytest discipline; hypothesis
  property-based test coverage on pure modules.
- Conventional Commits subjects; rebase-merge-only master.
- Lefthook pre-commit / commit-msg / pre-push step ordering.
- Comment discipline (Ruff ERA; no historical references inline).
- Keyword-only arguments and dataclasses (Python K4).
- Domain errors vs bugs split — Result-track for expected errors;
  raised exceptions for unexpected (Python K10).
- ROP-style composition of expected errors at the supervisor boundary.
- No relative imports; no banned-API surface (`abc.ABC`, `pickle`,
  etc.); typing.Protocol over abc.
- Vendored dependencies in `.claude-plugin/scripts/_vendor/`; no PyPI
  runtime dependencies.

## Beads substrate constraints

- The plugin reaches its tenant DB ONLY through the pinned `bd` CLI in
  server mode. No skill code MAY open a direct SQL connection, embed a
  local Dolt database, or speak the Dolt/MySQL wire protocol itself. The
  `bd` client is the sole substrate gateway. (A PyMySQL fallback, if
  ever introduced, is an implementation detail behind the same store
  API; it does NOT relax this gateway rule at the contract level.)
- The plugin NEVER issues `CREATE DATABASE`. The tenant DB is
  pre-created by the `dolt-server` operator (the root-run
  `onboard-tenant.sh`); a missing tenant DB is a precondition failure
  surfaced as a domain error, never an attempt to self-provision.
- The tenant password is supplied ONLY via the `BEADS_DOLT_PASSWORD`
  environment variable at `bd`-call time. It MUST NOT be persisted in
  `.livespec.jsonc`, in any committed file, in a sidecar, or in any
  process-spanning store.
- `bd` is invoked by a managed absolute path resolved from configuration
  (`LIVESPEC_BD_PATH` or a configured default). The plugin MUST NOT rely
  on the stale mise shim at `~/.local/share/mise/shims/bd`.
- Server-mode auto-commit stays OFF and `bd config dolt.auto-start` is
  `false`. The plugin MUST NOT re-enable per-write commits and MUST NOT
  start, stop, or otherwise own the externally-managed server lifecycle
  (the connection is established with `--external`).
- `bd init` is run non-interactively with `--skip-agents --skip-hooks`
  so it injects NO agent files and NO git hooks into the consuming repo.
- The beads `prefix` equals the tenant DB name (`prefix == database ==
  tenant`). This identity rule is fixed; skills MUST resolve all three
  from the single `connection` block value.
- A closure mutates the existing beads issue row IN PLACE (close-in-place
  per `contracts.md`). No skill code appends a second record to
  represent a state transition; the row is the single source of current
  state, with the tenant DB's own version history as the immutable
  backing log.
- File-system isolation: skills MUST NOT shell out to read or write
  GitHub APIs, Linear APIs, JSONL work-item files, or any tracking
  substrate other than the beads tenant DB reached through `bd`. The
  plugin's substrate is the tenant DB only.

## Process boundaries

- Each skill invocation is a single Python process; no daemons, no
  long-lived state, no in-memory caches that span invocations. The
  tenant DB (or the hermetic in-memory fake selected for CI / the
  no-live-connection fallback) is the only persistent state.
- Concurrency on the tenant DB is owned by the shared
  `dolt sql-server`'s transaction lifecycle (auto-commit OFF; the server
  serializes writes). The plugin adds no lockfile and no advisory lock;
  per-write `DOLT_COMMIT` under concurrent load is FORBIDDEN (it raises
  "database is read only").

## Spec Reader implementation constraints

- The Spec Reader is substrate-agnostic — it reads the spec tree, never
  the beads tenant DB — and is shared near-verbatim with the plaintext
  sibling.
- The initial implementation is a thin file pass-through; caching
  layers, indexes, embeddings, RAG adapters, and similar optimizations
  are explicitly OUT-OF-SCOPE for v001. Future revisions MAY introduce
  them so long as the four-capability API surface remains identical.
- The Spec Reader MUST be a Python module; the implementation language
  is not implementation-dependent at this granularity even though the
  upstream contract allows it — keeping all plugin code in one language
  reduces the toolchain surface.
- The Spec Reader MUST NOT mutate the spec tree. Read-only is the only
  mode of operation.

## Skill orchestration constraints

- Heavyweight skills (capture-impl-gaps, capture-spec-drift,
  capture-work-item, implement, capture-memo, process-memos) carry their
  orchestration logic in the SKILL.md prose; thin Python helpers MAY
  exist for utilities (record-formatting, schema validation) but the
  dialogue logic lives in markdown.
- Thin-transport skills (list-memos, list-work-items, next,
  detect-impl-gaps) carry ZERO orchestration in SKILL.md beyond a
  one-line invocation of the wrapper script. All logic lives in
  `.claude-plugin/scripts/bin/<skill>.py`. This is the upstream
  thin-transport doctrine, enforced here.

## Persistent Agent Knowledge constraints

- The `.ai/<topic>.md` files MUST be referenced from `CLAUDE.md` and/or
  `AGENTS.md` (orphaned files are forbidden).
- `process-memos`'s `persistent-knowledge` disposition MUST create the
  `.ai/<topic>.md` file AND add the reference if missing in one atomic
  skill operation. A partial state (file written, reference missing) is
  a bug.
- Doctor's `memo-hygiene` invariant from `livespec` does NOT apply to
  dispositioned-into-store content; the `.ai/<topic>.md` files are
  durable-pending, not transient.

## Forbidden patterns

- No mutating CLI flags on `list-*` or `next` skills. These are
  query-only by contract; adding `--update` / `--write` / similar flags
  is a contract violation. (Their `bd` reads are non-mutating
  `bd list` / `bd show` calls.)
- No silent close of work-items. Every `status: closed` issue MUST carry
  a `resolution:<enum>` label and a non-empty `close_reason`; doctor
  catches violations.
- No memo deletion. `disposition: discard` is the only path for "do not
  act on this"; the memo issue stays in the tenant DB.
- No off-substrate persistence. State that doesn't go in the tenant DB
  (and the Spec Reader's read-only view of the spec tree) MUST be
  re-derivable from the tenant DB. Skills MUST NOT store sidecar JSON,
  sidecar SQLite, JSONL work-item files, environment-variable state, or
  similar.
- No `CREATE DATABASE`, no direct SQL, no server-lifecycle management,
  no committed password, no per-write `DOLT_COMMIT` — restated here as
  forbidden patterns because each is an architectural boundary, not a
  tuning knob.
