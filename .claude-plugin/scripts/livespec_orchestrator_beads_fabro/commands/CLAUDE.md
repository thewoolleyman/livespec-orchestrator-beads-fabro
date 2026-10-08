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
- `_dispatcher_proof_budget.py` — the declared size budget every proof record is
  measured against before it is posted (`bd-ib-555xcd`). PURE, and the ONE place
  the three figures are named: the MEASURED forge comment ceiling, the record
  budget below it, and the per-assertion inline allowance a capture agent plans
  its proof recipe against. Three properties an editor must not invert. The
  ceiling is a MEASUREMENT with its provenance recorded beside it
  (`plan/definition-and-proof-of-done/research/005-forge-comment-ceiling-measurement-2026-10-07.md`),
  and it is NOT 65536 — that figure is what the forge's own rejection message
  says, and that message is wrong in both its number (the enforced ceiling is
  four times it) and its unit. Every measurement is in UTF-8 BYTES and never
  characters, which is the arm most easily simplified away because on ASCII the
  two agree: the discriminating probe was 131072 em dashes, half the character
  ceiling but 393216 bytes, and refused. And the refusal has TWO arms because the
  remedy differs — one enormous proof is attached, whereas many modest proofs
  summing over budget need a smaller recipe — so the aggregate arm says outright
  that no single proof overflowed, or the assertion it names reads as a culprit
  when it is innocent. The two posting primitives enforce it in code; the two
  factory stages hand-format their records, so for them it is a prompt
  instruction that `tests/prompts/test_proof_record_size_budget_discipline.py`
  binds to these constants.
- The DIGEST-NAMED ATTACHMENT a bulky proof travels as (`bd-ib-555xcd`) is split
  pure-from-impure across two modules, the usual split here:
  `_dispatcher_proof_attachment` (PURE: the digest, the digest-bearing slug, the
  four-line rendered reference, and the read-back) and
  `_dispatcher_proof_attachment_store` (the upload leg, which swaps each
  over-allowance proof for a stored asset). Four properties an editor must not
  invert. The record carries the asset's NAME, BYTE SIZE and DIGEST, and the
  digest is the load-bearing one — the other two say where the bytes are and how
  many to expect, while only the digest says WHICH bytes, which is what lets the
  acceptance pass and the replay stage verify the asset they fetch is the one the
  capture measured. The rendered block is PLAIN LINES and never fenced, because
  the record reader ignores fenced content (it cannot tell a verdict a verifier
  authored from one a proof printed), so a reference inside a fence would be
  invisible to the surfaces that must check it. The READER is fence-aware for the
  mirror reason: a replay whose proof `cat`s an earlier record prints these very
  labels, and matching them would attribute another assertion's asset to this one
  and then grade this one on whether those foreign bytes still hash correctly.
  And every partial read fails CLOSED — three of four labels, or an unparseable
  byte size, yields `None` — because a half-populated attachment sends the digest
  check after an asset with no digest to compare, and the natural coding of
  "nothing to compare" is "no mismatch found", a pass earned by missing data.
  The ORDER at the two call sites is load-bearing and identical in both: attach,
  then render, then measure. Attaching after the render would measure a record it
  then changed; measuring before the attachment would refuse records the
  attachment was about to rescue. An UNDER-allowance assertion is handed back as
  the very object it came in as, which is what makes an ordinary inline record
  render byte-for-byte as it did before any of this existed.
- `_dispatcher_proof_attachment_verify.py` — fetching an attached proof and
  deciding whether it IS the evidence it claims (`bd-ib-555xcd`). Pure decision
  (`attachment_is_evidence`) beside one impure seam (`attachment_digest_reader`),
  the usual split. Four properties an editor must not invert. The digest is taken
  over the DOWNLOADED FILE's bytes and nothing derived from the record — hashing
  the record's own stated digest, or the proof text it no longer carries, would
  compare a value with itself and pass every asset. The default reader
  (`unverified_attachment`) answers `None` for every asset, so a caller that wires
  none PARKS an attachment-bearing assertion instead of closing it on a digest
  nobody compared; the opposite default would make forgetting the wiring
  indistinguishable from verifying successfully. An unfetchable asset is `None`
  rather than an empty digest, because an empty string reaches the right verdict
  while asserting something false — that the asset WAS read and found different,
  which has a different remedy and is what the journal would carry. And a missing
  or mismatched asset is ABSENT EVIDENCE, never a FAIL: it says nothing about
  whether the behaviour holds, and a FAIL would route the item to rework and
  consume an `acceptance_rework_cap` attempt the unevidenceable-assertion clause
  forbids spending. `ProofRecord.attachment` resolves the asset through the SAME
  section walk `reproduced` uses, which is what keeps one assertion's digest from
  being checked against another assertion's verdict.
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
  the post-renewal observations are kept apart — whether the expiry advanced,
  held, or went unobserved, and whether a renewal response came back at all —
  and a gate that re-worded them would be a second account of one measurement. And the snapshot
  `project_codex_auth` returns on success is DISCARDED here, because the
  overlay re-reads the credential as it then stands through
  `project_host_codex_auth` — the post-claim projection, which GRADES but never
  renews, since a second renewal would spend provider work on a question whose
  answer can no longer refuse before a claim.
  A FOURTH property, and the one a reader is most likely to delete as dead
  weight: an EMPTY selection returns `None` before the credential is read at
  all. The drain reaches the wall on every pass that finds no ready work, so
  this is the common case, and grading there spent a bounded provider request
  on a pass that was never going to dispatch and then reported the shortfall as
  a refusal — an idle drain exited 3 instead of 0 (measured 2026-10-05). The
  guard is the gate's own precondition rather than the drain's, so every caller
  is covered; the wall's other refusals deliberately keep their empty-selection
  behaviour, including the proof-credential gate's grading of a repository
  declaration that is broken whether or not work is queued.
- `_dispatcher_codex_freshness.py` — the PURE diagnostics leaf behind both of
  those: the guarded freshness grade plus every refusal either position can
  render. Two properties an editor must not invert. `graded_freshness` returns
  `None` for an UNDECODABLE credential rather than letting
  `decode_codex_access_token_exp` raise, because `project_host_codex_auth` runs
  AFTER the claim and a bug-class escape from inside `dispatch_one` skips
  `release_pre_run_claim_if_needed` — which left the row `active` with no
  factory run, the exact stranded shape the pre-claim gate was adopted to
  retire. `tests/integration/test_codex_credential_claim_boundary.py` is the
  end-to-end control for that boundary and for the clock-ageing window beside
  it. And each refusal reports only what its own position MEASURED: the
  unparseable one names no lifetime (none was measurable) and no provider
  verdict, and the post-claim shortfall one reports no non-advancing expiry
  because it never asked for a renewal. `renewal_shortfall_refusal` is where
  that discipline is hardest to hold, because ONE refusal serves three
  post-renewal observations and the clause is the only thing that differs:
  `renewal_expiry_observation` compares the two EXPIRY INSTANTS — never the two
  `remaining_seconds`, which are measured against different clock readings, so
  an expiry that genuinely held reads as a smaller remainder afterwards — and
  returns `advanced`, `unchanged`, or `unmeasured` for the re-read that could
  not be taken. The clause was hardcoded to the `unchanged` wording until
  2026-10-05, when the proof capture measured a renewal advancing the expiry
  from 900 to 17970 seconds of remaining lifetime while the refusal still
  reported no advance: an expiry that demonstrably advanced reported as one that
  stood still, which points the operator at a broken refresh path rather than at
  the lifetime shortfall actually measured. The `advanced` clause reports that
  before/after CHANGE and nothing further — not the request as its cause, and
  not a token issuance — because two readings of one expiry instant are its
  whole evidence. `expiry` and `outcome.answered` are INDEPENDENT and neither
  implies the other — an expiry can advance while no renewal response came
  back, from a concurrent host refresh — so do not collapse them into one
  field. `CODEX_HOME_ENV` lives here, not beside
  `host_codex_auth_path`, because this module is the leaf and a constant
  imported upward would close a cycle.
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
  THREE PROPERTIES OF THE AGENT CATALOG'S OWN POPULATION, each the repair of a
  measured defect rather than a preference. It records TWO digests and they are
  not interchangeable: `agent_catalog_digest` is COMPUTED over the entries in hand
  and says which bytes this dispatch rendered, while `REGISTRY_SNAPSHOT_DIGEST` is
  TRANSCRIBED and says which upstream document they were seeded from — a question
  no self-digest can answer, and the one the record used to promise while carrying
  only the first. The transcribed literal is CHECKABLE: `REGISTRY_SNAPSHOT_COMMIT`
  plus the verbatim `agent.json` documents at
  `tests/fixtures/acp_registry_snapshot/` are what
  `test_acp_agent_catalog_registry_seed` re-derives it from, so the expected launch
  bytes come from the registry's own `distribution` block rather than from a
  literal that would pass for whatever the catalog happens to say. And a
  REGISTRY-SEEDED entry ships only while it names the run that LAUNCHED it
  (`verification_run`, filtered by `registry_entries_naming_a_verification_run`):
  a transcribed command resolves, renders, journals and prices correctly whether
  or not the program exists, so an unverified entry is indistinguishable from a
  working one at every surface except the exec — which is how three entries
  carried `@agentclientprotocol/<adapter>` package names no registry has ever
  published, plus a snapshot DATE where the version belongs, until 2026-10-06.
  `verification_run` is in the digest projection for that reason even though it
  changes no rendered byte. The two BUILT-IN ids
  (`BUILTIN_AGENT_IDS`) are exempt because ratification plus the live
  golden-master gate is their verification.
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
- `_plan_completeness_identity.py` — the identity each party to the plan
  archive's completeness leg is computed under, through the SAME primitive the
  proof-record surfaces publish under (`_dispatcher_proof_identity`). ONE
  resolver for both sides, because the leg's whole guarantee is that the two
  values are COMPARABLE: two resolvers reading different inputs would each look
  correct while making the comparison between them meaningless. Two properties
  an editor must not invert. There is deliberately NO parameter an identity can
  be put in — the leg used to compare a reviewer identity against the literal
  `plan-archive`, a constant no reviewer would adopt, so the check could only
  refuse a reviewer literally named that and an archiving session could author
  its own evidence under any other name (`bd-ib-3xsz`); an identity a caller
  could NAME is one a caller could RENAME, which puts the refusal one flag away
  from passing. And an UNRESOLVED identity REFUSES rather than falling back:
  `_dispatcher_invoker`'s `unattributed:<user>@<host>` mark compares EQUAL
  between two parties on one host, refusing a genuinely independent review, and
  DIFFERENT across hosts, admitting a genuine self-review.
- `_plan_completeness_evidence.py` — the completeness-review evidence record
  itself: the comment a reviewer writes, the parse that reads it back, and the
  grade that decides whether it satisfies the leg. Split out of
  `_plan_archive_review` (which keeps the plan-MEMBERSHIP concern) and
  deliberately keeping the RENDER beside the PARSE, so one comment format cannot
  drift across two files. Read its docstring before touching the grade: of the
  FIVE fields an evidence comment carries, only `reviewer-identity` and
  `reviewed-children` are cross-checked against anything their author does not
  control, while
  `separate-reviewer` and `attests-complete-requirement-coverage` are
  SELF-DECLARED attestations the gate records rather than establishes. Three
  properties an editor must not invert. The payload carries NO reviewer-identity
  field — the reviewer's identity is computed from the REVIEWING session's own
  environment, which is why the reviewer has to make the call itself and why a
  call made on its behalf records the caller — and the identity resolves BEFORE
  the append, because a record comment cannot be edited afterwards and one
  naming no reviewer would sit on the timeline permanently. A self-review is
  REMEMBERED rather than returned on sight, because two comments can carry one
  evidence id and refusing on the first read would refuse an archive a later
  independent comment satisfies. And the verdict carries TWO fields rather than
  one optional id, because "no evidence" needs a review performed while
  "self-review" needs a different PARTY — `_plan_archive` raises a distinct
  refusal for each, and the generic one would send the only session that cannot
  satisfy the leg back to author a second comment under the same identity.
- `_plan_completeness_recency.py` — whether a recorded completeness review still
  covers the plan it attested to (`bd-ib-0pf5`). PURE, and the repair of a
  fail-open measured BY EXECUTION on the live store: evidence written for plan
  epic `bd-ib-l3nptz` on 2026-08-17 still validated five days later, after seven
  further children had landed across four repositories. Three properties an
  editor must not invert. The binding takes TWO measurements because the first
  one's input is SELF-DECLARED — `reviewed-children` sits in the same comment as
  the two attestations, written by the same party, so a record that simply names
  the right ids satisfies the set test; each child's own STATUS INSTANT, read off
  the ledger record, is the part its author does not control. The instant is the
  LATEST of `created_at`, `updated_at` and `closed_at`, which OVER-reports (a
  mutation that changed no status moves `updated_at`) and that is the direction a
  terminal gate must fail in: a stale report costs one fresh review, a missed one
  archives a plan nobody reviewed and nothing re-examines a disposed thread. And
  a child reporting NO readable instant is reported rather than skipped, because
  an unreadable instant would otherwise be the cheapest way past the leg — while
  `latest_status_instant` returns `None` and never the empty string, which
  compares as earlier than every real instant and would make the same record read
  as one that last moved before the beginning of time.
- `_plan_completeness_leg.py` — resolving that leg end to end: grade the recorded
  evidence, commission one fresh reviewer when none is valid, and raise whichever
  of the three refusals is owed. Split out of `_plan_archive` (which keeps the
  ARCHIVE SEQUENCE) and cutting at ONE public entry point that either returns the
  accepted id or raises, so the refusal CHOICE stays beside the grade that
  distinguishes the three states. STALE evidence is commissioned around exactly as
  MISSING evidence is, because the ratified clause asks for a fresh reviewer
  whenever the timeline carries no VALID evidence; and when the commissioned
  reviewer records nothing the leg can read — the common case, since a review
  outlasts the attempt that asked for it — the FIRST read's stale account is what
  the refusal carries, because an attempt reporting "evidence is required" would
  hide the records it had just read and rejected.
- The SHARED AUTHORITATIVE RESULT READER of `contracts.md`'s
  shared-authoritative-result-reader clause (`bd-ib-77dipw`, Scenario 146) —
  the ONE reader both the relay-delivery and the plan-deadline callers observe a
  required result through. Eight cohesive modules, and the dependency direction
  reads bottom-up: `_plan_result_targets` (PURE: the closed five-kind grammar,
  each target's own identity rendering, the reference, and the parse refusal) and
  `_plan_result_observation` (PURE: the observation value plus its constructors
  and the named sources) → `_plan_result_reference` (PURE: the parse and its
  whole refusal ladder) → `_plan_result_repository` (the named repository
  resolved to ONE clone plus that clone's own tenant connection) →
  `_plan_result_ledger` / `_plan_result_forge` / `_plan_result_proof` (the five
  adapters, grouped by the source each reads) → `_plan_result_reader` (the ONE
  public entry point: parse, resolve, then exactly one source).
  Five properties an editor must not invert. The KIND SET IS CLOSED, and that is
  the entire mechanism for the clause's prohibition on arbitrary shell
  predicates — a predicate is refused for the same reason a typo is, so widening
  the parse to tolerate an unknown field re-opens it. EXACTLY ONE target is
  COUNTED rather than selected: a reference carrying two valid targets is a
  well-formed object, and picking the first in enumeration order would discharge
  the obligation on the weaker of the two while reporting the reference the
  caller wrote. The repository resolution answers BOTH the configuration
  question and the working-directory question from one value, because getting
  the first right and the second wrong reads the correct configuration while
  asking the wrong forge repository. The FILE result is compared against the
  REMOTE blob through the forge and never against a local checkout, because a
  local object for a path is whatever this host's last fetch left — an answer
  about fetch state reported as a fact about the branch. And the VERIFIED-PROOF
  read validates four things through the EXISTING typed reader — record
  semantics, a verified-class verdict, the build's containment ref, and every
  requested assertion reading as reproduced — never text; the installed build
  identifier is deliberately not compared, because the host-leg clause records
  it without verifying it.
  The ORDER of the reader's three steps is load-bearing and is the fail-closed
  order: an unparseable reference names no target to read, and every adapter
  needs the clone it executes from, so a reversed pair would spend a read on a
  question that had not been established and then attribute the failure to the
  wrong source — which is the one thing the clause requires naming correctly.

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
