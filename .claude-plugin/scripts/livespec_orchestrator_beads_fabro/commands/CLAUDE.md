# livespec_orchestrator_beads_fabro/commands/

The implementation modules behind the thin-transport wrappers. One
public module per query-only skill:

- `detect_impl_gaps.py` — mechanical spec→impl gap detection via the
  Spec Reader; pure read-and-emit (never mutates the JSONL, never
  prompts).
- `list_work_items.py` — JSONL store listing.
- `context.py` — the item-context read primitive
  (SPECIFICATION/contracts.md §"`context`"): resolves one `plan_slug` or
  work-item id and emits the single deterministic envelope
  `_context_envelope.py` assembles for it — the record, its comments, its
  children (unioned across BOTH the dotted-id hierarchy and the
  `parent-child` edge), its dependency edges, the plan's typed
  `next_action`, the research directory its `associated_work_item_id`
  anchor resolves, and the spec clauses it and its children cite. Query-only
  like its `list-*` siblings; an absent key exits 3 naming it rather than
  emitting an empty envelope, because a front-end resuming from the envelope
  alone cannot tell an empty one from a plan that has not started.
- `close_work_item.py` — the atomic close + `resolution:completed`
  wrapper (the "pit of success" for the closed-item-integrity
  invariant, SPECIFICATION/constraints.md §"Closed-item integrity").
  A MUTATING helper (like `gap-capture`, not a query-only `list-*`):
  `close_completed` reads the existing item and persists a closed copy
  carrying `resolution="completed"` through `append_work_item`, so the
  `bd close` + `resolution:completed` label land in ONE store
  operation and the two-step close recipe can never be half-done.
  `main` is the thin CLI (`close-work-item <id> [--reason …]`); the
  one EXPECTED misuse (a never-filed id) maps to `WorkItemNotFoundError`
  → exit 3.
- `next.py` — the ripeness ranker; a pure function of work-items
  JSONL state plus the cross-repo manifest at
  `<project-root>/.livespec.jsonc`.
- `orchestrator.py` — the orchestrator-side contract CLI (per
  livespec contracts.md §"Orchestrator CLI contract — the three
  named CLIs"): subcommand parsing + expected-error → exit-code
  mapping; subcommand bodies live in the `_orchestrator_*` private
  helpers (`_orchestrator_shared.py`, `_orchestrator_spec_reader.py`,
  `_orchestrator_gap_capture.py`, `_orchestrator_drift_capture.py`).
  `gap-capture` is the ONE mutating command surface here (writing
  gap-tied work-items to the beads Ledger IS its contract job); the
  query-only rule below still binds every `list-*`/`next` module.
- `dispatcher.py` — the orchestrator-PRIVATE thin Dispatcher of the
  Beads/Dolt + Fabro reference orchestrator (NOT a contract CLI and
  NOT a skill surface): `ledger-check` runs the three dispatch-safety
  Ledger integrity checks; `spec-check` runs the three re-homed
  spec-context work-item invariants (no-stalled-epic /
  no-stale-gap-tied / unresolved-spec-commitment) against the tenant
  rows plus the spec tree; `janitor-check` runs the three re-homed
  stale-cleanup checks (no-stale-merged-branch /
  no-stale-merged-pr-branch / no-stale-worktree) against the repo's
  git/gh state; `dispatch`/`loop` drive ready work-items
  through the admission valve + the `.fabro/workflows/implement-work-item/`
  phase graph (admission: admit the highest-`rank` admission-eligible
  `ready` items up to the per-repo `dispatcher.wip_cap`, set the assignee,
  transition `ready → active`; a manual / unresolvable-assignee item is
  held + surfaced → Fabro sandbox run, guarded by a coarse wall-clock
  progress watchdog that `fabro rm -f`-es a sustained-no-progress run and
  reports a distinct `stalled-no-progress` outcome → auto-merge
  confirmation → post-merge janitor in a fresh detached worktree of merged
  master, with provisioning failures classified as janitor-env-degraded
  rather than work-item failures → the post-merge acceptance valve
  (`complete` → `acceptance`, then `accept` per the effective
  `acceptance_policy`: `ai-only` → `done`, else park in `acceptance`) +
  journal; a non-convergence terminal bounces the slice to `backlog`).
  Bodies live in the `_dispatcher_*` private helpers
  (`_dispatcher_ledger_checks.py`, `_dispatcher_spec_checks.py`,
  `_dispatcher_spec_commitments.py`, `_dispatcher_janitor_checks.py`,
  `_dispatcher_plan.py`, `_dispatcher_valves.py` — the pure admission /
  acceptance planning layer (WIP-cap read, `plan_admissions`,
  `acceptance_decision`, `reject_routing`), `_dispatcher_engine.py`,
  `_dispatcher_io.py`, `_dispatcher_notify.py`,
  `_dispatcher_reflection.py`, `_dispatcher_watchdog.py`,
  `_dispatcher_cost.py` — the fail-closed cost-observability seam
  (work-item 5v9: `total_usd_micros` is null on every fabro run in
  v0.254.0, so an unattended queue drain refuses to keep picking on
  unobservable cost; the seam y0m's spend cap builds on). Its Ledger
  writes (admit / complete / accept / reject / close-on-confirmed-merge)
  are machine-path dispositions of already-filed items.
- `rebalance_ranks.py` — the orchestrator-PRIVATE, on-demand bulk
  `rank` re-key (NOT a contract CLI and NOT a skill surface; never
  auto-fires). `rebalanced(items)` orders by the canonical
  `ready_sort_key` and assigns evenly-spaced fresh keys via
  `livespec_runtime.work_items.rank.n_keys_between` (order-preserving;
  compacts fragmented keys), and `main` walks the live (non-`done`)
  heads through it and writes each changed key back via the store's
  `update_work_item_rank`. `legacy_seed(rows)` is the one-time L2 backfill
  primitive (legacy `priority → captured_at → id` seed order); it is
  reused by the fleet's L2 migration, not by `main`.
- `migrate_plan_records.py` — the orchestrator-PRIVATE, one-shot
  plan-record migration contracts.md §"Plan-record conformance checks"
  requires per tenant BEFORE those checks arm (NOT a contract CLI and
  NOT a skill surface). It writes the missing `plan_slug` tags, the
  missing `plan/<slug>/associated_work_item_id` anchors (`unassigned`
  when no epic carries the slug), and the missing typed `next_action` +
  `last_session` pointers, then reports what it wrote, skipped and
  refused; a second run reports zero writes. Every ledger write goes
  through the existing store bridge (`tag_epic_plan_slug`,
  `set_next_action`); the decisions — slug derivation, collision
  refusal, whether an anchor already stands, what a handoff seeds —
  live in `_plan_record_migration.py`. It writes the working tree only:
  the anchor files land through the repository's ordinary worktree →
  pull-request → merge discipline, and the fleet-wide run across
  tenants is an operator follow-up.

Each public module exports `main(argv=None) -> int` (the supervisor
the wrapper calls) plus its named helpers, all enumerated in
`__all__`.

Private helper modules (underscore-prefixed) carry shared plumbing:

- `_config.py` — store-path / project-root resolution
  (`resolve_store_config`).
- `_cross_repo.py` — cross-repo manifest loading (`load_manifest`) and
  raw `depends_on` entry parsing (`parse_entry`). The readiness predicate
  (`is_item_ready`), the canonical `ready_sort_key` (`rank` first, then the
  equal-`rank` ready-age tiebreak, then `id`), and
  `lane_of` now live in the shared
  `livespec_runtime.work_items.lifecycle` (pure functions over an
  in-memory `index: dict[str, WorkItem]`); callers (`next`,
  `list-work-items`, the Dispatcher) import them from there.
- `_jsonc.py` — JSONC parsing for `.livespec.jsonc`.
- `_ready_aging_order.py` — the orchestrator-side ready-AGE inputs
  `ready_sort_key` needs, injected for the same reason
  `_sibling_status_lookup` is: the durable, clone-independent `ready_since`
  instant lives in the beads tenant, so reading it inside `livespec_runtime`
  would be a `runtime -> beads` back-edge. `ready_aging_order(project_root=)`
  resolves BOTH inputs — the lookup and
  `dispatcher.ready_aging_threshold_hours` — from ONE project root, which is
  what makes `next` and the Dispatcher's drain compose the identical ordering
  rather than two similar ones. The tenant read is lazy, memoized per pass, and
  fail-soft onto the ratified unknowable-instant path (`id` tiebreak, no age
  advantage); `unaged_ready_order()` is that path for a caller holding no
  project root. `rebalance_ranks` deliberately composes NEITHER input — stored
  `rank` keys must not absorb a transient dwell.
- `_dispatcher_credential_wrapper.py` — the dispatch target's committed
  `credential_wrapper` declaration, as read. Split out of
  `_dispatcher_credentials` by cohesion once the proof-credential gate became
  its third caller: that module PROJECTS credentials, while this one answers
  the narrower configuration question of what argv prefix the target declares
  as the thing that injects its credential environment. Every arm fails soft
  onto "not declared" rather than raising, because every consumer is building a
  DIAGNOSTIC naming the wrapper to fix and an exception there would replace an
  actionable refusal with a traceback about the file it was about to name.
- `_dispatcher_proof_credentials.py` — the repository-declared proof
  credentials of `SPECIFICATION/contracts.md`'s proof-credential-projection
  clause: the `dispatcher.proof_credentials` parse, the pre-dispatch gate the
  two dispatch paths call, the overlay env lines the sandbox reads, and the
  per-declaration journal record naming whether the credential was minted or
  copied. Two orderings inside it are load-bearing and are asserted by its
  tests. The WITHHELD grade runs before the credential-shaped marker scan,
  because every withheld name is itself credential-shaped and a
  value-shape-first ladder would make the withheld refusal unreachable; and a
  name the Dispatcher MINTS per run is exempt from the `name` arm of that scan
  and from the absent-value grade, because it is credential-NAMED by
  construction and its value is one the Dispatcher itself supplies. The
  projection is fail-closed in both arms: a declaration the parse refuses, or a
  name whose value is absent, renders NO overlay line.
- `_dispatcher_integration_schema.py` / `_dispatcher_integration_field.py` /
  `_dispatcher_integration_defaults.py` /
  `_dispatcher_integration_declaration.py` /
  `_dispatcher_integration_resolver.py` /
  `_dispatcher_integration_contract.py` — the typed repository-integration
  contract. `_schema` holds the CLOSED field set, `_field` holds the
  `IntegrationField` DESCRIPTOR TYPE plus the shape and venue dimensions,
  `_defaults` holds every fleet default the resolver can return — plus, because
  the fleet-toolchain-literal ban admits them in no other module, the fleet's own
  tool and recipe runner NAMES the defaults are composed from and this plugin's
  own release-repository identity, `_declaration`
  reads a governed repo's declaration, `_resolver` is the ONE generic resolver
  returning `Declared | FleetDefault | Defective` for ONE point, and `_contract`
  assembles the whole closed set into the frozen `RepoIntegrationContract` /
  `ResolvedIntegrationContract`. The dependency direction is load-bearing:
  `_field` imports none of the others and `_resolver` imports no field
  constants, which is what keeps the resolver generic and lets a per-family
  field group exist without the closed set importing it back. Adding a schema
  field means the obligation was RATIFIED first; do NOT add one for an
  unratified expectation.
  `_dispatcher_conformance_premises` owns the DISPATCH-TIME NOTICE for the three
  `dispatcher.conformance.*` premises: an ABSENT premise resolves to the same
  empty argv as an explicitly declared `no_op`, so it warns off the resolution
  ARM (never the value), names each key and all three modes, and never refuses
  the dispatch.
  The per-family modules (`_dispatcher_ci_pipeline_view`,
  `_dispatcher_check_suite_view`, `_dispatcher_core_provisioning_view`,
  `_dispatcher_hook_install_recipe`) are PROJECTIONS of that resolution — they
  shape it for one consumer and MUST NOT re-derive it from configuration.
  `_dispatcher_integration_validation` is the PRE-DISPATCH pass over that
  schema: it grades a governed repository's declaration against the schema
  version the executing build requires and refuses (exit 3, journaled)
  enumerating every `Defective` point in ONE message. It grades what the
  repository WROTE, never what it left unwritten — an absence is what a field
  added by a LATER build looks like in an EARLIER repository, so refusing on one
  would strand items already mid-pipeline.
  `_dispatcher_integration_projection` carries the projections that cross into
  a run — the `fabro run --input` pairs, the prompt variables, the prepare-step
  parameters — plus the dispatch record's contract projection and the `gh pr
  merge` method flag. The contract itself is resolved ONCE, in
  `_dispatcher_plan_build.build_plan`, and rides `DispatchPlan.integration`;
  every seam reads it from there. A seam that resolves an integration point of
  its own is the defect the resolve-once-project-everywhere clause retires.
- The ACP **agent and model catalogs**, and the STRUCTURED candidate form that
  resolves through them (`contracts.md` §"Agent and model catalogs" and §"ACP
  node adapter configuration"). The dependency direction is load-bearing and
  reads bottom-up:
  `_acp_agent_mechanism` (how one agent takes `model`/`effort` — exactly one of
  `protocol`, `env`, `json_env` or `arg`) → `_acp_agent_entry` /
  `_acp_model_entry` (one catalog entry each, closed grammar) →
  `_acp_agent_catalog` / `_acp_model_catalog` (the COMMITTED snapshots plus each
  one's digest and the per-repository merge) → `_acp_catalogs` (both as one
  frozen value plus the snapshot record) → `_acp_structured_render` (the pure
  render of one entry into the manual-form triple) → `_acp_candidate_forms` (the
  closed two-form grammar and the per-field identity override) →
  `_acp_structured_identity` (the derived triple) → `_acp_candidate_structured`
  (one structured candidate, end to end). `_acp_catalog_overrides` is the shared
  reader for both `dispatcher.agent_catalog` and `dispatcher.model_catalog`.
  Two rules an editor must not invert. The catalogs contain no network, HTTP,
  socket or subprocess import, because "the Dispatcher MUST NOT fetch a registry,
  a provider, or a catalog service at dispatch time" — a fetch cannot exist if
  the API to perform one is absent. And the DISPATCH between the two candidate
  forms lives in `_acp_node_chains`, downstream of both, because the structured
  path needs the identity type `_acp_candidate_schema` owns: making the manual
  parser dispatch closes an import cycle.
- `_config_acp` is the config-reading seam for the above — the dispatch target's
  catalogs and its per-node overlay layer, resolved from ONE read of the
  dispatcher block. `_dispatcher_acp_nodes.prepare_acp_nodes` resolves both ONCE
  per dispatch and passes them down for the same resolve-once reason the
  integration contract does: a second read of the same file cannot be proven to
  agree with the first, and the disagreement would be invisible because both
  reads produce a well-formed catalog.
- Two small modules carry rules that are ABOUT the structured form without
  belonging to any one stage of it, which is why each is its own file rather
  than a branch inside the renderer:
  - `_acp_codex_pin` names the agents whose candidates MUST carry both `model`
    and `effort` (`contracts.md` §"Built-in ACP node defaults"). It is a SET
    rather than a general rule because an entry declaring no `effort` is
    ordinarily admissible — it takes the adapter's own default — and making
    effort mandatory everywhere would refuse the un-pinned Claude disposition
    default this repository ships. It imports nothing, because
    `_acp_structured_render` is its caller and owns the entry type.
  - `_acp_codex_models_retired` turns the RETIRED `dispatcher.codex_models`
    key into a refusal carrying the equivalent per-node entries.
    `_acp_node_repository` consults it FIRST, before any `acp_nodes` parsing,
    so a repository carrying both keys is told about the retired one rather
    than about whichever `acp_nodes` fault it happens to hit. It holds the
    retired built-in tier values because they no longer exist anywhere else,
    and a migration that omitted them would silently re-point a node that had
    relied on a partial tier table.

Rules an agent editing this tree must follow:

- `main()` is the only place `sys.stdout.write` / `sys.stderr.write`
  are permitted, and only for the documented CLI output contract
  (the `--json` envelope, human lines, usage errors to stderr with
  exit 2). `print()` is banned. Do NOT scatter writes into helpers.
- These are QUERY-ONLY skills by contract. Do NOT add mutating CLI
  flags (`--update`, `--write`, etc.) to `list-*` or `next` — that
  is a contract violation per `SPECIFICATION/constraints.md`
  §"Forbidden patterns".
- Catch the EXPECTED `livespec_orchestrator_beads_fabro.errors` exceptions at
  the `main()` boundary and map them to exit codes; never let an
  expected error escape as an uncaught traceback.
- Keyword-only arguments (`*` separator) on every helper; the
  `main(argv)` positional is the argparse-convention exemption.
- `next`'s readiness gating MUST exclude any candidate with a
  `depends_on` entry resolving to `RefStatus.OPEN`; excluded items
  are absent from the ranked list, not surfaced at lower urgency.
