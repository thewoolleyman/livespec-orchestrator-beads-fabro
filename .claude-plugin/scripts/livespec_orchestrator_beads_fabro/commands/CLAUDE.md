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
- The OPT-IN host Codex credential identity observation — the passive
  measurement behind `codex-cred-status --observe-identity-state <path>` —
  lives in FOUR cohesive modules, and the dependency direction reads bottom-up:
  `_dispatcher_codex_identity_claims` (PURE: the access token's session and
  token identifier claims, each as a truncated domain-separated SHA-256
  fingerprint, via `_dispatcher_projection.decode_codex_access_token_claims`)
  → `_dispatcher_codex_identity_state` (the mode-600 private state file, read
  and atomically written) → `_dispatcher_codex_identity_observation` (PURE: the
  per-identifier comparison, the rendered payload and human lines, and the
  `IDENTITY_CONTINUITY_LIMITATION` statement) →
  `_dispatcher_codex_identity_command` (the `codex-cred-status` argparse
  surface plus the leg that wires the three together).
  Seven properties an editor must not invert. NO raw claim value or token ever
  leaves the claims module or reaches the state file — the comparison only ever
  asks whether two readings are EQUAL, which a one-way digest answers exactly
  as well. `unknown` is a first-class verdict and never collapses into
  `unchanged`, because a failure to observe and an identifier that genuinely
  held are indistinguishable at the surface and support opposite conclusions;
  the same reason an EXISTING-but-unparseable prior record reports `unreadable`
  rather than `absent`. The observation NEVER invokes a provider, never
  initiates a refresh, and never mutates `auth.json`; and it never moves the
  command's exit code, which still follows the lifetime alarm alone, because
  external monitoring is wired to that code and an observation moving it would
  change what a page means. And an UNREADABLE reading is WITHHELD rather than
  written: recording it would overwrite the last comparable fingerprints, so one
  momentarily unreadable credential would leave every later reading comparing
  against the blip — which is why `state_write` names four outcomes
  (`recorded` / `withheld` / `refused` / `failed`) instead of carrying a boolean
  that cannot tell a deliberate withholding from a broken state path.
  A DESTINATION resolving to the host credential is REFUSED before anything is
  read or written — by exact path, `.`/`..` alias, symlinked parent, or hard
  link, and on the `<destination>.tmp` staging path too, which the writer
  unlinks before opening. The comparison uses the resolved source path threaded
  down from `host_codex_auth_path`, never one derived here: a guard comparing
  against a separately-derived path guards a guess, and the defect this fixes
  overwrote a credential with observation state. And an identifier the CURRENT
  reading could not see is `unknown` even on a first reading — the
  current-absence test runs BEFORE the prior-state test in `_change`, because
  `first-observation` asserts that an identifier was seen and recorded.
- The repository-declared proof credentials of
  `SPECIFICATION/contracts.md`'s proof-credential-projection clause live in
  FOUR cohesive modules, and the dependency direction reads bottom-up:
  `_dispatcher_proof_credential_management` (the `dispatcher.proof_credential_
  management` argv pair a repository declares per credential, when its provider
  exposes a management interface, plus the environment the mint and revoke
  commands are addressed through) → `_dispatcher_proof_credentials` (the
  `dispatcher.proof_credentials` parse and its refusal ladder, the resolution
  across both keys, the minted-or-copied provisioning verdict, and the
  per-declaration journal record) → `_dispatcher_proof_credential_projection`
  (the overlay env lines an admitted declaration renders) and
  `_dispatcher_proof_credential_gate` (the selection-level gate the two
  dispatch paths call) → `_dispatcher_proof_credential_lease` (the ONLY place
  either provider command is executed: the mint before the overlay is written,
  and the revoke once the run has ended).
  The lease carries NO state between its two legs on purpose — both are
  addressed by the per-run SCOPE, which is the dispatch id — because a handle
  threaded from the mint could only reach a revoke on the path the mint's
  return value took, and that is the shape that loses a revoke on every early
  return between them. A mint failure refuses the dispatch; a revoke failure
  cannot (the run has ended, so no decision is left) and is JOURNALED under its
  own stage instead, because a credential outliving its run is otherwise
  nothing anyone is looking for.
  That scope-keyed revoke still has to be REACHED, which makes the ORDER of the
  pre-launch refusals in `_dispatch_one_locked` load-bearing: the revoke is the
  run's own teardown, so a refusal returning between the mint and the launch
  leaks a live credential plus the mode-600 overlay carrying it. Every refusal
  whose inputs the overlay does not supply therefore belongs ABOVE
  `materialize_overlay` — which is why the goal preflight sits there rather than
  beside the goal render it guards — and the only in-between return left,
  an unmaterializable run config, revokes inside the materializer itself.
  The DECLARATION-versus-GATE split is deliberate, and the gate's own docstring
  names it: the declaration module grades COMMITTED CONFIGURATION and is pure
  over a block handed to it, while the gate reads the target repository off
  disk, grades the Dispatcher's LIVE ENVIRONMENT — which no committed
  declaration can decide — and WRITES the dispatch journal.
  Two orderings inside the declaration module are load-bearing and are
  asserted by its tests. The WITHHELD grade runs before the credential-shaped
  marker scan,
  because every withheld name is itself credential-shaped and a
  value-shape-first ladder would make the withheld refusal unreachable; and a
  name the Dispatcher MINTS per run is exempt from the `name` arm of that scan
  and from the absent-value grade, because it is credential-NAMED by
  construction and its value is one the Dispatcher itself supplies. The
  projection is fail-closed in both arms: a declaration the parse refuses, or a
  name whose value is absent, renders NO overlay line.
- `_dispatcher_pre_dispatch_wall.py` — the ONE wall both dispatch paths run,
  holding every refusal that must land after selection and BEFORE admission:
  the variant-aware acceptance-criteria wall, the proof-assets gate, the
  proof-credential gate, the Codex credential gate, and last the
  publish-branch reclaim, which refuses nothing and MUTATES a remote ref, so
  it must sit after everything that can still refuse. `_dispatcher_run_commands`
  hands it a one-item selection and `_dispatcher_loop_command` hands it the
  whole wave; nothing in it branches on which caller it is. It was two
  byte-identical private functions, one per command module, which is what made
  "both paths refuse" a claim about two sequences that could drift and required
  every new refusal to be wired twice. Do NOT re-inline it into either command
  module: that is the duplicate returning, and it is also what put the
  single-dispatch module over its file LLOC ceiling.
- `_dispatcher_codex_credential_gate.py` — the fourth refusal in that wall,
  and the pre-CLAIM half of the host Codex credential decision
  (`SPECIFICATION/scenarios.md` Scenario 19). Three properties an editor must
  not invert. It is the only wall that spends a PROVIDER REQUEST — the one
  bounded in-place renewal `project_codex_auth` makes — so its POSITION is
  load-bearing rather than tidy: a bounded renewal is the one thing that can
  turn an insufficient credential into a sufficient one, so that question has
  to be settled while the item is still unclaimed, because the answer decides
  whether there is anything to claim. It renders NO refusal of its own; the
  decision and its diagnostics stay in `_dispatcher_codex_auth`, which is where
  the two unchanged-expiry observations are kept apart, and a gate that
  re-worded them would be a second account of one measurement. And the snapshot
  `project_codex_auth` returns on success is DISCARDED here, because the
  overlay re-reads the credential as it then stands through
  `project_host_codex_auth` — the post-claim projection, which GRADES but never
  renews, since a second renewal would spend provider work on a question whose
  answer can no longer refuse before a claim.
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
- `_acp_structured_text` renders a structured entry written as TEXT into
  adapter bytes, and is shared by the two layers that spell one as a string:
  the WORKFLOW layer (a TOML scalar) and the PER-DISPATCH `--acp-node`
  argument. The REPOSITORY layer deliberately does not use it — its entries
  arrive from JSONC already decoded, so it hands `_acp_structured_render` a
  mapping and a JSON round trip here would invent a serialization step. A
  value is structured iff it opens with `{`, which is a complete
  discriminator rather than a heuristic, and a `{` that does not parse
  REFUSES rather than falling through to a command line: POSIX tokenization
  strips the quotes, so it would reach the sandbox as a plausible argv whose
  first token is not an executable.
- `_acp_workflow_defaults` renders the WORKFLOW layer's own structured entries
  into the manual form, and it runs as the inputs are READ
  (`_dispatcher_acp_nodes.workflow_layer`) rather than at the merge — the
  workflow layer is the least specific of the three, so rendering it at the
  merge would be rendering it in the middle of one. Two consequences an editor
  must not undo. The built-in identity table keys on EXACT RENDERED BYTES, so
  raw structured JSON reaching it would key on text no resolved node can equal
  and every built-in identity would silently stop attaching. And the closed
  grammar binds here too: the workflow layer is the hardest one to notice a
  typo in, because nothing in a repository mentions it.
- `_acp_capability_gate` and `_acp_factory_capabilities` are the PURE and
  IMPURE halves of one rule: a chain carrying `config_options` refuses before
  claim unless the resolved factory advertises
  `acp.candidate_config_options.v1`. The split is the usual one — the decision
  is a pure function of a capability set, and a decision that reached for the
  network itself could not be exercised without one. Two properties an editor
  must not invert. The gate FAILS CLOSED when the capability list is
  unreadable, because a gauge that passes when blinded turns a refusal into a
  pass and leaves a record that reads healthy. And the reader is a CALLABLE,
  consulted only when some chain actually carries options, so the ordinary
  dispatch — every dispatch in this fleet today — pays no round trip.
  `_dispatcher_acp_nodes._resolve_chains` is where it is called, before the
  attach.
- The **TDD order calibration** modules (plan `factory-test-first-enforcement`
  slice S3, `bd-ib-3h5vfq`) put seven `tdd.*` fields plus the implement
  adapter on the terminal `dispatcher.calibration` span, so "is the factory
  writing tests first, or producing the commit SHAPE afterwards" becomes a
  Honeycomb query. The split is pure-from-impure, and the dependency
  direction reads bottom-up:
  `_dispatcher_tdd_commits` (PURE: commit messages → Red/Green/suite-green
  counts and the Red-to-Green gap median) and `_dispatcher_tdd_order_sink`
  (the persisted per-dispatch aggregate of slice S2's guard decision spans,
  fed at ingest by `_otel_receive`) → `_dispatcher_implement_adapter` (PURE:
  the journaled implement adapter classified against the committed agent
  catalog) → `_dispatcher_tdd_signals` (PURE: the ONE place the eight
  projected keys are named, plus their source semantics, and the two
  projections — all keys with nulls for the journal, observed keys only for
  the span) → `_dispatcher_tdd_probe` (the IO gather: the `gh pr view --json
  commits` probe and the per-run selection).
  Three properties an editor must not invert. Absence is `None`, NEVER zero:
  a zero gap with zero refusals is exactly the post-hoc signature, so
  manufacturing one from a dropped signal would invent the finding the span
  exists to measure. The correlation is per DISPATCH, not per item — the
  dispatch id is both the `dispatch-id` journal record and the
  `Factory-Run-Id` commit trailer, which is what makes the commit-series
  filter an exact per-run selection. And `tdd.assertion_count` comes from
  `effective_criteria`, the segmentation the acceptance evaluator grades; the
  legacy description-regex `acceptance_count` beside it is slice S4's to
  repair and is deliberately untouched.
  **One docstring in that tree is narrower than the behaviour, and it is
  recorded here rather than left to be rediscovered.**
  `_dispatcher_tdd_commits` and `_dispatcher_tdd_signals` describe
  `tdd.suite_green_count` as "product code with no Red at all" — the plan
  research's framing. `red_green_replay` actually reaches its
  `TDD-Suite-Green-*` leg from TWO branches: product impl `.py` with no open
  Red, AND a passing TEST-ONLY change under a non-`feat:`/`fix:` subject,
  which touches no product `.py`. Measured on this slice's own series
  2026-10-02 (8 commits, 6 Red, 6 Green, suite-green 2 — both test-and-docs
  commits). The correct wording is in `orchestrator-image/README.md`; the
  docstrings were not amended because the S2 order guard refuses a
  docstring-only write to an existing product path outside an open Red, which
  is the separate finding that README records.
- Three small modules carry rules that are ABOUT the structured form without
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
