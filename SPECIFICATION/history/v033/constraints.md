# constraints.md — livespec-orchestrator-beads-fabro

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
- The tenant DB name is the load-bearing tenant identity (`database ==
  server_user == tenant`, one ≤32-char Dolt name serving all three);
  skills MUST resolve those three from the single `connection` block
  value. The beads `prefix` is DECOUPLED from the tenant DB name: it is
  bd's server-stored issue-ID create-prefix — a short, readable alias
  that MAY differ from the DB name (here it is `bd-ib`) — and skills MUST
  read it from its own `connection.prefix` value rather than assume it
  equals the tenant.
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
  capture-work-item, implement, groom, plan) carry their orchestration logic
  as a SHARED, harness-neutral prose artifact at
  `.claude-plugin/prose/<op>.md` — the consent flow, the multi-step
  dialogue, the `livespec_orchestrator_beads_fabro.*` package calls, and
  the JSON / handoff semantics. Each per-runtime SKILL.md is a THIN
  binding that resolves the plugin root, reads `prose/<op>.md` in full,
  and maps its harness-neutral vocabulary to the runtime's tools —
  adding no operation behavior of its own. This mirrors livespec CORE's
  prose + thin-Driver-binding decomposition
  (`livespec/SPECIFICATION/spec.md`). Thin Python helpers MAY exist for
  utilities (record-formatting, schema validation); no dialogue logic is
  duplicated across the Claude and Codex bindings.
- Thin-transport skills (list-work-items, next, detect-impl-gaps,
  list-plan-threads) carry ZERO orchestration in SKILL.md beyond a
  one-line invocation of the wrapper script. All logic lives in
  `.claude-plugin/scripts/bin/<skill>.py`. This is the upstream
  thin-transport doctrine, enforced here.
- The operator skill (`drive`) carries only harness binding prose
  in SKILL.md. Selected-action execution and outcome summarization live
  in the shared `drive.py` wrapper and command module so Claude Code and
  Codex bindings call the same logic.
- Codex support is REQUIRED as a first-class agent-runtime consideration. Codex adapters MUST be thin runtime bindings over the same wrapper CLIs, beads tenant semantics, and consent rules as the Claude Code skills; they MUST NOT copy Claude-specific `SKILL.md` bodies. Thin-transport behavior remains zero-orchestration under Codex too: ranking, listing, and formatting logic stays in the wrapper scripts. The `drive` surface is likewise a thin runtime binding over `drive.py`, with the selected action executed by the shared CLI. The human Codex TUI discovery surface MUST be verified separately from model-visible plugin loading: `/skills` → `List skills` (or the `@` picker) searches the short skill name such as `drive` and renders the plugin context as `drive (livespec-orchestrator-beads-fabro)`. Claude-only hooks are NOT assumed to run under Codex; any Codex adapter or hook replacement MUST be manually verified before Codex support is claimed.
- Heavyweight skills that write to the work-items store MUST
  obtain per-operation user consent before each store write, in one
  of the recognized consent forms, unless the user explicitly waived
  consent for the named operation class (per `contracts.md`
  §"Store-write consent discipline"). Waivers are explicit,
  class-named, and invocation-scoped — never a default.
- The Dispatcher's machine-path dispositions of already-filed items
  (the lifecycle verbs admit / complete / accept / reject, the `backlog` bounce, and — only under full autonomous mode's collapsed `approve` gate — the auto-approve disposition, with `complete` carrying PR + merge-sha audit evidence) are the SOLE exemption from the store-write consent
  discipline; `--no-close-on-merge` disables the post-merge disposition
  writes entirely. The Dispatcher MUST
  NOT create net-new work-items.

## Full autonomous mode constraints

Full autonomous mode (`contracts.md` §"Full autonomous mode") is a
dangerous override; these are its mechanically-checkable safety rails.

- **Default-off, explicit, invocation-scoped.** `dispatcher.autonomous_mode`
  MUST default to `false`. Enabling the mode MUST be an explicit,
  invocation-scoped opt-in (`--mode autonomous`); it MUST NOT be a
  default, MUST NOT be inferred from context, and MUST NOT persist across
  invocations — modeled on the §"Skill orchestration constraints"
  operation-class waiver discipline.
- **Explicit dangerous-mode confirmation.** Enabling the mode MUST require
  an explicit dangerous-mode acknowledgement; a bare config-key flip or an
  ambiguous flag MUST NOT silently arm it.
- **Audit every resolution.** Every autonomously-resolved decision MUST be
  journaled and attributable (which gate — `approve` / `acceptance` / `needs-human` — which item, what the LLM decided); no silent auto-approve — extending the §"Forbidden patterns" no-silent-close rule to every collapsed gate.
- **Still escalate the unresolvable.** The mode MUST NOT auto-resolve a
  decision the LLM cannot confidently resolve, NOR a decision that is
  human-gated by design — drift acceptance, a spec-change slice, or a
  regroom / backlog bounce (`contracts.md` §"Full autonomous mode",
  `spec.md` §"Terminology"); every such truly-unresolvable decision MUST
  still block and surface to a human. The "no release with zero
  verification" floor of `contracts.md` §"Post-merge acceptance
  (`acceptance → done`)" MUST hold — every acceptance carries at least one
  AI pass even under the mode.

## Persistent Agent Knowledge constraints

- The `.ai/<topic>.md` files MUST be referenced from `CLAUDE.md` and/or
  `AGENTS.md` (orphaned files are forbidden).
- Authoring a `.ai/<topic>.md` topic MUST create the file AND add the
  reference if missing in one atomic operation. A partial state (file
  written, reference missing) is a bug.
- No productivity-heuristic hygiene invariant from `livespec` applies to
  the `.ai/<topic>.md` files; they are durable-pending, not transient.

## Forbidden patterns

- No mutating writes from `capture-spec-drift`'s ledger-intent scan. The
  scan MUST be read-only — it MUST NOT mutate, close, or re-rank any
  work-item — and MUST NOT auto-file a propose-change without per-finding
  user consent.
- No mutating CLI flags on `list-*` or `next` skills. These are
  query-only by contract; adding `--update` / `--write` / similar flags
  is a contract violation. (Their `bd` reads are non-mutating
  `bd list` / `bd show` calls.)
- No silent close of work-items. Every terminal issue (logical `done`,
  stored as beads-native `closed`) MUST carry
  a `resolution:<enum>` label and a non-empty `close_reason`; doctor
  catches violations.
- No off-substrate persistence. State that doesn't go in the tenant DB
  (and the Spec Reader's read-only view of the spec tree) MUST be
  re-derivable from the tenant DB. Skills MUST NOT store sidecar JSON,
  sidecar SQLite, JSONL work-item files, environment-variable state, or
  similar.
- No `CREATE DATABASE`, no direct SQL, no server-lifecycle management,
  no committed password, no per-write `DOLT_COMMIT` — restated here as
  forbidden patterns because each is an architectural boundary, not a
  tuning knob.
- No silent or unbounded autonomous mode. Full autonomous mode
  (`contracts.md` §"Full autonomous mode") MUST NOT be enabled by default,
  MUST NOT auto-resolve a truly-unresolvable decision, and MUST NOT create
  net-new work-items; every auto-resolution MUST be journaled.

## Closed-item integrity

A closed gap-tied work-item must mean "proven", not merely "status
flipped". This section codifies that completeness invariant, extending
the §"Forbidden patterns" silent-close rule with the scenario-binding
half specific to gap-tied items.

A gap-tied work-item marked `resolution:completed` MUST carry the `resolution:completed` label AND its acceptance scenario MUST be bound to a real integration-tier-or-above test in `tests/heading-coverage.json` (the entry's `test` field is a live test node id, never the `TODO` sentinel); a closed gap-tied item whose acceptance scenario is still `TODO`, or which lacks the `resolution:completed` label, is "closed but unproven" and is FORBIDDEN.

The acceptance scenario of a gap-tied item is resolved from the item's
`gap-id` label through the `clauses[]` gap-id→scenario map in
`tests/heading-coverage.json` (the same map livespec core's
`constraints.md` defines and the
`behavior_scenario_link` check consumes). The "real test, not `TODO`"
half is the same `tests/heading-coverage.json` `test`-field state the
existing `heading_coverage` check tolerates as `TODO` but this invariant
does not for closed gap-tied items. This invariant ADDS the
scenario-binding half on top of the §"Forbidden patterns" rule "No
silent close of work-items" (which forbids the label-half for ALL closed
items) and ties the two halves together as the single "closed but
unproven is forbidden" rule. The mechanical enforcement of this
invariant is the `closed_item_integrity` check codified in
`contracts.md` §"Closed-item-integrity check".
