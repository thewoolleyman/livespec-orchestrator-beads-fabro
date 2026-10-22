# livespec_orchestrator_beads_fabro/commands/

The implementation modules behind the thin-transport wrappers. One
public module per query-only skill:

- `detect_impl_gaps.py` — mechanical HEADING-COVERAGE enumeration via
  the Spec Reader: one gap per H2 heading of the governed spec tree that
  no test exercises. Pure read-and-emit (never mutates the store, never
  prompts). Despite the `-impl-gaps` name it performs no spec↔impl
  comparison and never reads implementation state. The enumeration and
  the stable heading-derived gap-id live in the private
  `_heading_gaps.py` sibling, which the dispatcher's
  `no-stale-gap-tied` invariant reads too — so the detector and that
  invariant can never drift onto two derivations.
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
  when no epic carries the slug), the missing typed `next_action` +
  `last_session` pointers, and — as the SECOND of the two writes relay
  research note 007 permits to start a plan epic's authority chain — the
  missing GENESIS token of every live plan epic that carries no chain
  (`_plan_record_genesis.py`, through `create_genesis_token`). It then
  reports what it wrote, skipped and refused; a second run reports zero
  writes. Every ledger write goes
  through the existing store bridge (`tag_epic_plan_slug`,
  `set_next_action`); the decisions — slug derivation, collision
  refusal, whether an anchor already stands, what a handoff seeds —
  live in `_plan_record_migration.py`. It writes the working tree only:
  the anchor files land through the repository's ordinary worktree →
  pull-request → merge discipline, and the fleet-wide run across
  tenants is an operator follow-up.
  THE GENESIS LEG RUNS LAST, so every epic one run touches reaches the
  same starting state: the pointer the seeding leg writes is the
  migration's GUESS at a next action and carries no obligation, so
  letting it commit the chain's first transition would start the
  authority history with a record of nothing and would leave a
  freshly-seeded epic at epoch 1 while an epic whose pointer already
  stood sat at epoch 0. Its two findings are routed by CODE and not
  interchangeably: an already-named chain is a SKIP, because running the
  migration twice is an ordinary operator act whose whole claim is that
  it changed nothing, while an unconfirmed genesis is REFUSED carrying
  its remedy, because another writer may have migrated the epic in the
  same minute and that is state a human resolves.

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
- `_dispatcher_sandbox_worktree_pack.py` — the gitignored worktree-discipline pack
  a fleet-default sandbox installs before anything reads it (`bd-ib-tlmq3m`,
  Scenarios 30 and 96), plus the premise that decides whether it is owed. PURE,
  and the repair of a defect that only a run making NO COMMIT could reach: the
  pack arrived as a SIDE EFFECT of the hook-manager's pre-commit hook, so every
  ordinary run had it by the time its janitor ran, and a seeded re-dispatch —
  which reuses already-reviewed commits — reached the janitor with none and exited
  127 on a pack member. Four properties an editor must not invert. The invocation
  is read from the fleet-defaults module and never composed here, because
  `constraints.md`'s fleet-toolchain-literal ban admits this fleet's recipe runner
  in no other module. The step is rendered in the OVERLAY rather than written into
  `workflow.toml`, for the two reasons `_dispatcher_default_branch_fetch` records —
  that file is forked per repository, and the same ban SCANS it. It is rendered
  AFTER the committed chain, which is a requirement rather than a position: the
  recipe runs through the virtual environment the committed `uv sync` populates, so
  the "as early as possible" instinct fails the prepare step and kills the run. And
  the premise is read off the sandbox check-suite field's resolution ARM, never its
  value — the same discipline `fleet_toolchain_is_the_host_janitor_premise` keeps
  one venue over, because a repository may declare exactly the fleet convention and
  a value comparison would read that deliberate declaration as an inheritance. It
  renders NO worktree exclusion, and that is deliberate: every pack member is
  already in the governed repository's own tracked `.gitignore`, which is the same
  fact that makes the pack absent to begin with.
- FACTORY OVERFLOW SELECTION — where an UNPINNED dispatch is placed, in THREE
  cohesive modules, and the dependency direction reads bottom-up:
  `_dispatcher_overflow_factories` (the committed-only
  `dispatcher.overflow_factories` array, its three outcomes and the pre-claim
  refusal) and `_dispatcher_factory_capacity` (ONE candidate's reading: its own
  server's non-terminal run count and its own `max_concurrent_runs`, or which
  measurement stopped it) -> `_dispatcher_overflow_selection` (the ranking, and
  the one journal record per selection). `_dispatcher_factory_ledger._placement`
  is the one caller; `_factory_default` is the leaf both the overflow grading
  and `_config.resolve_fabro_factory` read the configured default from.
  Seven properties an editor must not invert. The comparison is a RATIO and
  never a count, a free-slot tally or remaining capacity: hp reports a
  `max_concurrent_runs` of 10 against petri's 2 (measured 2026-10-19), which is
  the asymmetry the rule exists for, and the ratio is also the only reading
  under which 5-of-10 and 1-of-2 TIE — at which point the clause takes the
  EARLIER candidate, which is the default. Selection NEVER refuses, defers or
  counts on capacity grounds, so the no-free-slot arm is a PLACEMENT on the
  default whose scheduler then queues the run, and nothing in these modules has
  a refusal to return. A candidate that could not be MEASURED has no free slot,
  and its reason rides the record: a saturated candidate reaches the ranking
  identically, so without the reason the journal cannot say which measurement
  stopped it. NEITHER figure is ever coerced to a zero — a run count of zero is
  an idle factory and a ceiling of zero is a stopped scheduler, so a coerced
  zero is indistinguishable from a measurement, and in the run-count direction
  it is the one coercion that sends work to a server nobody could reach. A
  ceiling below 1 is NOT an unreadable read: its effect is identical (no free
  slot) and its evidence is the opposite, so it is carried as a reported figure
  and the journal shows `0 of 0` rather than a reason that sends an operator to
  debug a read that worked. The registry is resolved BEFORE either read and
  graded here, so an unresolvable one names the registry instead of surfacing as
  a factory that declares no server — the same `None` value an unconfigured
  entry carries and a completely different remedy. And the committed array is
  graded against `_factory_default.configured_factory_name` and never
  `resolve_fabro_factory`, which reads `LIVESPEC_FABRO_FACTORY` first: an
  operator who exported the overflow factory's own name would otherwise see the
  array that names the committed default ADMITTED — the one shape the clause
  forbids — and would see the candidate list open with the overflow factory,
  where a utilization tie makes it win.
  ONE ASYMMETRY BETWEEN THE TWO LEDGER CALLERS IS LOAD-BEARING. Both
  `_unrecorded_pin` (the pre-claim gates and the admission stamp) and
  `resolve_dispatch_factory_target` RANK; only the second JOURNALS, because it
  is the one that records the chosen factory. A record per gate would make the
  clause's "one record" several, each describing a reading no dispatch acted on.
  THE RANKING IS TAKEN ONCE PER INVOCATION, through `_ranking`, and `_placement`
  takes it rather than performing it. Every unpinned item of one wave resolves
  to the same ranked choice, so a ranking reached inside the gate's per-item
  loop spends four engine round trips per ITEM — and is several independent live
  readings, which can disagree, while the `dispatcher.minimum_release` floor is
  graded only against the targets that one gate call returns.
  AND THE PIN PRECEDENCE CARRIES ITS OWN ENVIRONMENT LAYER, in `_pinned_factory`
  rather than in `resolve_fabro_factory`. An unpinned placement hands that
  function the RANKED name, which suppresses its `LIVESPEC_FABRO_FACTORY`
  layer, so a dispatch pinned only by the variable ranked anyway — spending the
  reads the clause forbids a pinned dispatch, and stamping the claim with a
  factory the dispatch never reaches, since the resolution does honour the
  variable. That variable is the only routing mechanism `drive.py` has, and it
  is used precisely when the recorded factory identity is the point.
  THE LAYER SITS ABOVE THE RECORDED PIN, not below it, which is the ratified
  order of the selection clause and one place where it is spelled. A pin is the
  item's OWN dispatch history and the variable is this invocation's routing
  decision, so an item an operator re-routes is exactly one that has been
  dispatched elsewhere before — measured 2026-10-19, an item carrying fifteen hp
  journal rows was dispatched with the variable naming `petri` and had its claim
  stamped `hp`, after which reconcile held that claim against hp for a run living
  on gmktec. `explicit_dispatch_factory` therefore reads the `--factory` FLAG
  alone: the variable is one layer below it in `_pinned_factory`, and reading it
  in both places is what gave a namespace-carrying caller its own copy of the
  order and let the two copies drift apart.
  THAT FLAG READER IS PUBLIC BECAUSE ADMISSION NEEDS IT AND HOLDS NO NAMESPACE.
  The valve writes the pending claim stamp, and the flag is the one precedence
  layer the variable cannot stand in for, so each of the three dispatch paths
  reads it and hands `admit_and_select` the NAME through `explicit_factory`. A
  valve reaching for `args.factory` itself would be the second reader this
  entry's first half exists to retire.
- `_dispatcher_journal_file.py` — the append-only dispatch journal and the
  attribution stamp it owns, split out of `_dispatcher_io` for the same reason
  `_dispatcher_shell_runner` was: that aggregate's import closure reaches the
  watched Fabro launcher, which reaches the factory-ledger resolution, so a
  module that writes the journal AND resolves a dispatch factory closes a cycle
  — and the overflow-selection record is exactly such a writer.
  `_dispatcher_io` still RE-EXPORTS `JournalFile` and `utc_now_iso`, so every
  existing caller is untouched; only a module inside the launcher's own import
  reach needs the leaf directly, which is also why `_acp_factory_run_reader`
  now takes `ShellCommandRunner` from `_dispatcher_shell_runner` rather than
  from the aggregate. The stamped-once refusal moved WITH the append that
  applies it: a copy left behind would be a second authority on which fields no
  writer may supply.
- `_dispatcher_item_run_target.py` — the factory ONE item's dispatch went to,
  resolved from the item's own recorded `dispatch_factory` stamp and falling
  back to the repository default, plus `ACP_EVENTS_TIMEOUT_SECONDS`, the bound
  on a single `fabro events` read. Both names lived in the `agent.acp.failover`
  event projection that v127 retired (`bd-ib-qm6r1`) and neither belonged to
  it: the per-attempt cost read `_dispatcher_cost_chain` performs asks the same
  two questions. Three properties an editor must not invert. It answers `None`
  and never a `FactoryTarget` carrying `server=None`, because that value is
  what an UNCONFIGURED repository holds and every consumer reads it as the
  ambient LOCAL engine — so answering with one surveys whichever Fabro the
  dispatching host runs and reports a clean reading taken on the wrong machine,
  the trap `AGENTS.md` catalogues. Every arm fails SOFT onto that `None`,
  because each caller runs after the work it follows has already finished and
  an unreachable tenant must not raise through a caller with nothing left to
  do. And the item's stamp wins over the repository default, for the reason
  `targeted_factories` gives: an item dispatched to one factory must not have
  its run looked for on another, where the clean answer is a run that does not
  exist. It is a LEAF of its own rather than a member of the cost chain, so a
  later retirement of some other consumer cannot take the cost read's bound
  with it — a removal whose only symptom is an unbounded subprocess against a
  slow factory.
- `_fabro_port_workflow.py` and the credential half of `_fabro_port_auth.py` —
  the two invocations whose bodies left the `FabroPort` class when the facade
  reached its file LLOC ceiling and the `settings` verb needed room. Both stay
  inside the `_fabro_port` facade FAMILY, which is what keeps every engine
  invocation behind the one seam `check-fabro-port-seam` enforces, and both are
  named in that check's `DISCOVERY_ANCHORS` — a family member holding an engine
  invocation must be, or the check's SEAM control fails rather than certifying
  an exemption over a module it does not account for. `fabro auth login` sits
  beside `resolve_bearer_token` because it WRITES the `~/.fabro/auth.json` that
  resolution reads, so the write and the read of one file are stated in one
  place. `FabroPort.settings` is read for ONE figure — the server's own
  `scheduler.max_concurrent_runs` — and hands back the whole payload, because
  the nesting differs between builds and
  `_fabro_port_records.scheduler_max_concurrent_runs_from_payload` is where
  this family's readings of a payload live. That reader SEARCHES for a
  `scheduler` block rather than reading a fixed path, and the reason is
  measured: the ratifying revision named `server.scheduler.max_concurrent_runs`
  while the 2026-08-22 retention spike recorded the block under
  `server.server`, so a fixed-path read answers one build and returns `None` for
  the other — and `None` reads downstream as "no free slot", which retires
  overflow selection silently while every surface still reports a healthy
  dispatch.
- `_dispatcher_minijinja_escape.py` — the shared MiniJinja literal escaper every
  untrusted-prose renderer routes through, so arbitrary item prose cannot alter
  graph semantics when Fabro renders the goal. It lived in `_dispatcher_overlay`
  until `bd-ib-tlmq3m` and was always a guest there: that module renders a run
  config and renders NONE of its own output through the escaper, which is why the
  cut is clean. It moved by COHESION rather than by line count when the sandbox
  worktree-pack prepare step needed room under the overlay's LLOC ceiling, and it
  deliberately left NO re-export shim — AGENTS.md §"Refactoring for size" bans
  one, and a shim would have bought the overlay none of the room the split was
  for. Every caller imports from here.
- `_dispatcher_goal_recovery.py` — what a SEEDED dispatch's goal brief says about
  the tree its sandbox starts on (`bd-ib-kn7ktk`, Scenario 185): "The new sandbox
  MUST check out the recorded SHA, and the goal brief MUST name that commit as an
  interrupted prior attempt whose current state the agent inspects before
  continuing." PURE. It is its own module rather than a branch inside
  `_dispatcher_goal` because that module assembles the ITEM's own brief — ledger
  fields, riders, ratified lessons, every line of it untrusted prose bound for the
  escaper — while this section is authored by the Dispatcher from the invocation's
  resume attributes, so the two share neither input nor provenance; keeping them
  apart is also what keeps the brief assembler free of a dependency on
  `_dispatcher_resume_entry`, which owns the attribute names. Three properties an
  editor must not invert. BOTH `resume_head` AND `resume_fetch_ref` are required,
  and that pair is the whole discriminator: a `resume` route sets the head alone
  and its tree is that dispatch's OWN publication, entered at the node it stopped
  at, so a renderer keyed on the head would narrate every resumed run's own branch
  as somebody else's interrupted attempt and send a run entering at `pr` off to
  audit work it had already proved. The two attributes are read DEFENSIVELY
  through the shared constants, exactly as `resume_checkout_for` reads the same
  pair, because only a recovery route sets them and a respelling at either end
  resolves absent, renders the plain brief, and says nothing about the section it
  dropped. And an attribute that is PRESENT but empty narrates nothing, because an
  empty head reaches `git checkout --detach ''` and fails the run in preparation —
  a brief that had already told the agent to inspect that commit would be
  describing a placement which never happened. The section travels to the one call
  site through the `_dispatcher_plan` façade beside `render_goal`, its paired
  input, rather than being imported at the dispatch path separately.
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
- `_dispatcher_credential_rotation.py` — the re-resolution the loop's bounded
  credential re-probe takes each round, so a credential ROTATED in that wrapper
  reaches a wait that is already parked (`bd-ib-o6aeji`, Scenario 121). The wait
  used to assess `os.environ` — the value injected when the loop was LAUNCHED —
  which made it unretirable by the one event it exists to wait for: measured
  2026-10-08, four loops on this host journaled `exhausted` from 08:54Z and
  11:42Z through 23:10Z while other repositories' dispatches ran on the same
  factory minutes after the rotation, and the only remedy was to kill and
  re-dispatch all four. Four properties an editor must not invert. EVERY name
  the wrapper injects is emptied for the child — the whole per-wrapper
  credential set plus the caam pool slot this dispatch projects, which
  `_dispatcher_credential_wrapper.wrapper_injected_child_env` owns — because the
  wrapper caches the DIFF
  between its caller's environment and what it injected and replays it to every
  caller on the host: a nested invocation that already holds those values
  produces
  a near-empty diff, which both hides the rotation from this reading and poisons
  that shared cache (`AGENTS.md`'s wrapper-cache entry, measured 2026-10-01).
  Emptying only the name under read is NOT a smaller version of that
  protection: the cached diff covers everything the wrapper injected, so three
  of the four names stayed inherited and the entry replayed to the rest of the
  host was near-empty for those three. A
  wrapper fault is NEVER reported as an absent credential — it yields the
  launch-time value with `rotatable` False — because the two have opposite
  remedies and a wait retired by a refusal about a misconfigured wrapper reports
  the wrong fault; a PERSISTENT fault is SURFACED through the `source` label
  every refused-probe record carries, and never by ending the wait, because the
  provider limit the wait governs clears with the credential unchanged and the
  probe's own next result is its only retirement signal. A repository declaring
  no wrapper spawns
  nothing, since there is no second source to read and a `sudo` re-exec per
  round would learn nothing. And the journal names the credential by a ONE-WAY
  identity rather than a value, with the empty token fingerprinting to null:
  the only question two rows are asked is whether the value CHANGED, and "no
  credential was resolved" must not read as a changed one.
  A FIFTH property, and it is what makes the other four reach a run:
  `publish_rotated_credential` puts each round's RESOLVED value into the
  process environment, because the dispatch the wait admits does not consult
  this re-resolution at all — `_dispatcher_credentials` renders the sandbox
  overlay from `os.environ[<selected name>]` and the pre-launch
  `assess_credential_status` re-reads the same entry. A wait that retired on
  the wrapper's rotated value while leaving that environment holding the
  launch-time one reports a resume and then admits a run carrying the exact
  credential it had been parked on. It publishes BEFORE the assessment and on
  every round including the returning one, so one round's reading is both the
  value assessed and the value projected; and a round that resolved NOTHING
  publishes nothing, since every fallback reading is the launch-time value and
  on an ABSENT name that is the empty string — which the dispatch path reads as
  a credential to project rather than as the absence an operator must fix.
- `_dispatcher_git_credential_helper.py` — the git credential helper every
  dispatch configures in the sandbox clone, so an in-sandbox push to
  github.com obtains an App installation token minted AT PUSH TIME from the
  refreshing `gh` wrapper `_dispatcher_gh_refresh` materializes
  (`bd-ib-52zt3o`, Scenario 29). Three properties an editor must not invert.
  It configures a COMMAND and never a token value: an installation token
  outlives neither the run nor the `pr` stage, so a stored one would be both
  a durable copy of a credential and expired by the time it was read. It is
  rendered UNCONDITIONALLY — with the App inputs present `gh` on PATH is the
  refreshing wrapper, and without them gh answers from the ambient
  `GITHUB_TOKEN` the credential projection always carries — because rendering
  it inside the App condition would leave the other arm with no credential at
  all on an engine that supplies none. And it is scoped to the
  `https://github.com` URL rather than installed as a blanket helper, which is
  what leaves the PINNED engine's path untouched: git consults no helper for a
  URL already carrying a username and a password, so the token Fabro embeds in
  the origin URL still wins there. That precedence is git's own, not something
  arranged here, which is why both cases are asserted as a pair.
- `_dispatcher_sandbox_worktree_exclude.py` — the ONE renderer that makes a
  Dispatcher-materialized sandbox path invisible to the run's own git worktree,
  shared by ALL FOUR projections that write a fixed `/workspace` path:
  `_dispatcher_gh_refresh` (the bundle and its base64 payload, `bd-ib-dud2ww`),
  `_dispatcher_credential_use_projection` (the guard script, `bd-ib-ccywva`),
  `_dispatcher_codex_auth_projection` (the projected Codex home) and
  `_dispatcher_tmux_socket_root` (the tmux socket root) — the last two found by
  a static audit (`bd-ib-5qxa5q`) rather than by a run, which is the shape this
  defect class takes once the first two have been repaired: the remaining
  instances are latent until a dispatch happens to reach them. PURE. The defect
  it closes belongs to the LAYOUT rather than
  to any one artifact: the Petri-era engine runs each prepare step as a graph
  node and checkpoints after it, and on that engine the repository clone IS
  `/workspace`, so every `/workspace` path a prepare step writes is committed
  into the run branch — while on the pinned engine the clone is
  `/workspace/<repo>` and the same path sits outside it. That is why the
  mechanism is one shared renderer and not a rule each projection re-implements.
  Four properties an editor must not invert. The entry is written to the clone's
  own `info/exclude` and never to a tracked `.gitignore`, because a rule added to
  a tracked file would itself be a change every checkpoint commits. EVERY path
  the chain writes is listed, not only the artifact it ends with — an
  intermediate a later step deletes is committed by the checkpoint of the step
  that wrote it. Callers name paths NARROWLY, a file rather than its directory,
  because the entry lands in a GOVERNED repository's clone and excluding a
  directory that repository could legitimately track would hide its own content
  from git — and the narrowness rule is about WHAT THE CALLER WRITES rather than
  about path shape, which is what admits the two directory-naming callers: the
  Codex home is a credential HOME the telemetry projection and the codex-acp
  child both populate, and the tmux root is a socket root the tmux SERVER
  populates, so in neither case is there a file the projection could name that
  would cover what later lands beside it. And every arm that cannot MEASURE
  where a path sits is passed over
  WITH a labelled line on stderr: a failing prepare step kills the run before any
  work, so the pass-over is right, but a silent one is indistinguishable from a
  successful exclusion until `publish_draft` refuses at the end of a full run.
  Every call site renders the exclusion as its FIRST prepare step for the same
  checkpoint reason; the credential-use caller may do so and still install the
  guard at the path `guarded_acp_command` execs, and the Codex and tmux callers
  may do so and still have the adapter resolve `$CODEX_HOME` and tmux resolve
  `TMUX_TMPDIR`, since hiding a path from git is not hiding it from the sandbox.
- `_dispatcher_tmux_socket_root.py` — the sandbox-local tmux socket root, as
  ONE projection: the path, the exclude-then-create prepare steps, and the
  `TMUX_TMPDIR` env line. Split out of `_dispatcher_overlay` by cohesion when
  the root gained its worktree exclusion (`bd-ib-5qxa5q`) — that file ASSEMBLES
  the overlay, while this is a peer of `_dispatcher_codex_auth_projection` and
  every other materialized `/workspace` projection. Keep the three together:
  the exclusion, the creation and `TMUX_TMPDIR` must all name the same
  directory, and splitting them across modules is how two of them come to name
  different ones. The root is projected UNCONDITIONALLY, because it is what
  keeps a sandbox-local `tmux kill-server` away from the host default
  under `/tmp`.
- `_dispatcher_harness_shell_policy.py` — the Claude harness's own shell-tool
  policy, as the TWO projections it needs: the `[environments.<id>.env]` lines
  that put its keys in the sandbox PROCESS environment, and the
  exclude-then-write prepare steps that put the SAME keys in the sandbox's own
  `<clone root>/.claude/settings.local.json`. Split out of `_dispatcher_overlay`
  by cohesion once the policy stopped being one env table (`bd-ib-rv2jk4`);
  `harness_shell_env_lines` is re-exported from the overlay because that is
  where every caller already reaches for it. Five properties an editor must not
  invert. The settings path is ASKED OF GIT (`git rev-parse --show-toplevel`)
  and never spelled, because the harness resolves the `local` source against the
  PROJECT DIRECTORY and the clone root is not a fixed path on any layout this
  fleet runs: `/workspace/<repo>` on the pinned engine, `/workspace` itself on
  the Petri-era engine, and `/repos/<owner>/<repo>` with `/workspace/<repo>` a
  symlink to it in a live hp sandbox measured 2026-10-16 — where a
  `/workspace/.claude/settings.local.json` holding 3600000 sat on disk from
  before harness start while a shell tool call still reported the committed
  1200000, so the first shipped path wrote correct bytes somewhere nothing
  loads. The WRITE fails closed when git cannot answer, where the paired
  exclusion passes over, because a write nobody can place is this projection
  failing silently while an exclusion nobody can write concerns a path git was
  never going to stage. BOTH projections render from the ONE `_HARNESS_SHELL_ENV` tuple,
  which is the whole repair: the env table alone was NOT the effective ceiling,
  because the sandbox agent starts the harness with `settingSources: ["user",
  "project", "local"]`, so the governed repository's committed
  `.claude/settings.json` is loaded and a settings-file `env` value overrides
  the same variable inherited from the process environment — measured on run
  01M4XWYERJEZ15GNMGHV66CSBY, whose `run.created` environment carries
  `BASH_MAX_TIMEOUT_MS=3600000` and whose two final Green amends were ended at
  1202366 ms and 1203117 ms by the committed file's 1200000 ms. It writes the
  `local` source and never the committed `project` one, because `local`
  outranks `project` (measured on the operator host) and because the committed
  file is the interactive host sessions' setting. The write MERGES the `env`
  members into whatever document the sandbox already carries, which at the clone
  root is REQUIRED rather than defensive — the harness writes its own permission
  approvals into that same file while the run is driving (39 `permissions.allow`
  entries in the measured sandbox), so an overwrite would discard live session
  state — so a `settings.local.json` an image, an earlier step or the harness
  itself left keeps its other keys;
  a file holding no JSON object cannot be merged into, so that one arm writes a
  fresh document and SAYS SO on stderr rather than failing the prepare step,
  which would kill the run at launch over a per-sandbox file that no longer
  parses. And the merge is shipped as the SANDBOX'S OWN BYTES with no host-side
  twin — a twin would be a second account of one merge, and only the copy the
  sandbox runs decides anything. This raises NO ceiling; it makes the ceiling
  the overlay already declared the effective one.
- `_dispatcher_default_branch_fetch.py` — the DISPATCH BASE every dispatch
  fetches into its sandbox clone, so `origin/<default_branch>` exists for the
  `implementation_diff` node and for every check that diffs the default branch
  (`bd-ib-xlblgr`, Scenario 61). A source-staged clone is SINGLE-BRANCH: its
  `remote.origin.fetch` refspec names only the disposable
  `livespec/source/<id>` branch, so the committed `git fetch --unshallow`
  deepens that branch and brings in no other ref. Four properties an editor
  must not invert. The DESTINATION half of the refspec is load-bearing rather
  than decoration: measured 2026-10-14, a bare `git fetch origin <branch>` in
  such a clone writes `FETCH_HEAD` and creates no
  `refs/remotes/origin/<branch>`, exiting 0 with no warning — a fetch that
  reports success while the ref the next node reads still does not exist. The
  branch is PROJECTED through `CONTRACT_INPUT_NAMES` rather than spelled, so an
  adopter whose default branch is not this fleet's gets the same step; a
  renderer keyed on its own spelling of the name would render for no dispatch at
  all. It lives in the OVERLAY because the committed run config is forked per
  repository (`_dispatcher_paths.workflow_toml` prefers a dispatch target's own
  copy), so only the overlay reaches every dispatch — the same reason
  `_dispatcher_factory_provenance` gives. And it carries NO `|| true`: without
  the ref a run spends its whole implement stage and then loses it at
  `implementation_diff`, so a fetch that could not be taken is cheaper to report
  in preparation than to discover afterwards. It is rendered FIRST among the
  materialized blocks, immediately after the committed unshallow it completes.
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
- `_dispatcher_janitor_check_venue.py` — WHERE the post-merge janitor's check
  suite EXECUTES (`bd-ib-26deyw`): the dispatching host, or the maintainer-owned
  k3s cluster through the shared delegated gate. Do not confuse it with
  `_dispatcher_janitor_venue.py`, which answers WHICH REF the fresh checkout is
  made at. Five properties an editor must not invert. The two venues are not
  symmetrical in what an exit code MEANS — a host-local suite's exit code IS its
  verdict, while a delegated gate has THREE outcomes, so the lost-verdict case
  has to stay distinguishable from a red tree. A lost verdict is RED at
  `janitor-post-merge` and never the `janitor-env-degraded` outcome, which
  reports `green` at its own stage: a gate that was asked and did not answer is
  not a venue that failed to provision, and an item must not close on a reading
  nobody took. The gate client is INVOKED as a subprocess in the janitor
  checkout rather than imported, because the shared dev-tooling package is a
  governed repository's development dependency and not part of this plugin's
  vendored runtime — the installed plugin root carries no virtual environment,
  so a module-level import would resolve under this repository's own test run
  and raise on every real dispatch. The verdict is read off the client's own
  JSON log line rather than its exit code, which answers a PUSH question (0 only
  when the gate passed AND a green token was written) that a post-merge gate is
  not asking. And every doubt resolves to the HOST-LOCAL venue — an absent
  block, an absent key, a wrong type, an unrecognised word — the mirror of the
  fail-closed verdict, landing in the same place: both defaults reduce to "run
  the checks".
  It also owns the `janitor-post-merge` ROW'S ACCOUNT of that venue
  (`bd-ib-nsrgxl`, Scenario 191), named here beside the selection it reports so
  the row's words and the selection's words cannot drift. Five further
  properties an editor must not invert. The row names the RESOLVED venue, never
  the declared value: a row echoing `cluster` — or any other unrecognised word
  — would report a machine the suite never ran on, which is the reading the
  fail-closed selection exists to prevent anyone making. On the HOST-LOCAL
  venue the gate fields are OMITTED and never nulled, because the cluster arm
  writes `gate_state: null` where the client reached no verdict and a
  host-local null would read as that same state. ONE parse of the verdict line
  serves both the state word and the Job keys, which is why `_verdict_line`
  yields the LINE rather than the state. No Job key is ever DERIVED — the
  gate's convention is `gate-<repository>-<first twelve of the tree hash>` in
  the `gates` namespace and the row already carries that tree hash, so a name
  COULD be constructed, and a constructed one reads exactly like a reported one
  while being wrong in precisely the case an operator reads the row to
  investigate. And the START instant is taken by the CALLER immediately before
  the launch: the row is built after the command returns and already carries
  its own append instant, so a start stamped there would report every stage as
  instantaneous. The submitted-tree reading (`gate_tree_hash`) is the module's
  one impure function, taken directly on the runner exactly as the venue
  resolution's own merge-containment probe is, and answers `None` rather than
  the empty string for a reading that could not be TAKEN. The `suite_source`
  word names the RULE rather than the venue: `dispatcher.janitor.check_suite`
  on the host, and `gate_check_suite` on the cluster, where the committed
  declaration is not applied at all, so naming it there would send an operator
  to edit a declaration the run never consulted.
- `_dispatcher_open_command_node.py` — which COMMAND node of the phase graph a run
  is inside, read off one `fabro events` output (`bd-ib-qsk4o5`). PURE, and the
  repair of a measured false-kill: a command node (`janitor`, `publish_draft`,
  `implementation_diff`, `verify_pr`, and the three terminal sentinels) emits a
  start event and a completion event and nothing between them, so BOTH liveness
  layers are flat for its whole duration however healthy the run is — the
  heartbeat because it beats only while an agent turn runs, the event stream
  because there is no further event. Three of the six stall cancels on hp between
  2026-10-08 and 2026-10-12 killed healthy runs that way, one of them inside
  `publish_draft` seven minutes after its janitor went green.
  Four properties an editor must not invert. The open set is COUNTED (starts
  against endings) rather than sequenced, because `parse_last_event_epoch` records
  that events may arrive out of order, so a reader keying on the last lifecycle
  event it saw would answer differently for one reordering of the same stream —
  and counting is also what reads a RETRY correctly. A tie is broken by the
  LONGEST bound, because no two command nodes run at once in this graph, so a tie
  is a reading artifact and the bound has to cover whichever node is genuinely
  still running. The ACP nodes are deliberately OUT of `COMMAND_NODES`: a healthy
  run inside one emits agent events throughout, so widening every node's bound to
  its own timeout would retire the backstop rather than relax it — and the tuple
  is asserted against the committed graph's `script` nodes, because a set that
  drifted away from the graph would report "nothing open" for a node that is
  open, which is exactly the cancellation this module prevents. And the reading
  is taken from the SAME `fabro events` output as the wall-clock timestamp, in
  `_dispatcher_io_liveness_probe`, so the two cannot disagree about the stream
  they describe and no dispatch pays a second probe per poll.
  `decide_stall` applies it as the MAXIMUM of the configured stall window and the
  open node's timeout, taken across the WHOLE quiet window rather than the newest
  reading — a command node cannot complete without emitting a completion event,
  and that event would open a new window, so within one window a node once
  observed open is still open and a later reading that misses it has failed to
  observe it (the events reader tolerates a stream truncated mid-record).
- The `_dispatcher_run_wall_*` family — the WHOLE-RUN WALL BUDGET
  (`bd-ib-sdxfsn`, Scenario 175, `contracts.md` §"Dispatcher progress watchdog"
  and §"ACP node timeouts", v133). The stall window above bounds a run's QUIET
  TIME and cannot bound a run that keeps emitting events while heading for
  `needs_human`; measured on hp, such a run holds a factory slot for hours and
  no layer reclaims it. The budget is the second, orthogonal bound: past it the
  run is exported and cancelled whatever its event stream says.
  The family splits by what each piece can fail on, and the split is not
  cosmetic — the clock is the half that is easiest to get silently wrong, so it
  carries no I/O at all.
  - `_dispatcher_run_wall_budget.py` — the budget VALUE and its three-layer
    resolution (per-dispatch argument, then `dispatcher.run_wall_budget_seconds`,
    then the workflow default of 21600 seconds), plus the pre-dispatch refusal
    `node_timeout_conflict`. The resolved `RunWallBudget` carries its own LAYER,
    which is what makes every downstream record able to name where the number
    came from; a bare float would make the record say what the bound was and not
    which surface an operator must edit to change it. The refusal names both keys
    and both values and fires BEFORE any run exists, because a budget smaller
    than a node's own timeout cancels a healthy node every time and the cancel
    reads exactly like a legitimate one.
  - `_dispatcher_run_wall_clock.py` — the SLOT-HOLDING clock. PURE, and the
    module whose key tuple is the whole claim: `RUNNING_SINCE_KEYS` deliberately
    EXCLUDES `start_time` and `start_record`, which include the time a run spent
    `runnable` in the factory's queue. A run charged for queue time is cancelled
    for a slot it never held, and the record would read identically. When no
    running instant can be read and no poll has yet observed the run running the
    start is UNFIXED, `slot_holding_seconds` answers `None`, and
    `budget_exceeded` is `False` — unmeasured means no cancel, never a cancel on
    a default. The start is fixed ONCE per run (the watch's `RunWallBudgetWatch`
    holds it), so a later poll whose record has lost the instant cannot restart
    the clock.
  - `_dispatcher_run_wall_budget_preserve.py` and
    `_dispatcher_run_wall_budget_watch.py` — the EXPORT-THEN-TERMINATE
    precondition and the per-poll verdict. The pointer is written AND READ BACK
    before `fabro rm -f`, and a read-back that fails yields `HELD` rather than
    `CANCELLED`: the run keeps its slot for one more poll and the export is
    re-attempted. The `HELD` arm must stay an explicit `continue` in the watch
    loop and never a fall-through — a quiet run past its budget satisfies the
    stall rule as well, so a fall-through cancels it as stalled, with the wrong
    record, the wrong disposition, and the pointer the hold exists to secure
    still unwritten.
  - `_dispatcher_run_wall_budget_records.py`,
    `_dispatcher_run_wall_budget_comment.py` and
    `_dispatcher_run_wall_budget_disposition.py` — the two journal records, the
    durable ledger comment, and the rest state. The `exceeded` record composes
    the shared `watchdog_cancel_fields`, so a budget cancel and a stall cancel
    describe one run the same way; the `held` record deliberately carries NO
    stage, pull request or head, because nothing was cancelled and a record
    naming a publication would read as a completed cancel. The disposition
    writes the comment BEFORE the blocked transition and rests the item at
    `blocked` / `needs-human` carrying the remedy `resolve-blocked:<id>:ready`;
    it has no release arm, since a budget cancel is not a non-convergence
    observation and must not bounce the slice to `backlog`.
  THE `exceeded` RECORD ALSO ANCHORS A RESUME, and that reader is
  `_dispatcher_resume_cancel_anchor` rather than anything in this family — the
  clause says the record "anchors resume ... exactly as a
  `watchdog-stall-cancel` record does", so the anchor's stage test is MEMBERSHIP
  in its `_CANCEL_SOURCES` map and every other bound reads one shape. Two
  properties an editor must not invert, and both are about failing in the
  expensive direction. A reader recognising only the stall stage REFUSES
  NOTHING: the budget row is well-formed, the anchor returns nothing, the resume
  reports a headless pull request, and the re-dispatch reclaims the publish
  branch and spends another whole budget rebuilding implement, janitor and
  publish_draft — the waste the budget exists to stop, re-entered through the
  recovery path. And the two stages name DIFFERENT sources
  (`SOURCE_CANCEL_RECORD` / `SOURCE_BUDGET_CANCEL_RECORD`), each the journal
  stage an operator can grep for, so the source rides the `CancelAnchor` rather
  than being read from a constant at the call site; one shared value would send
  an operator reading a budget-anchored resume after a row that run's journal
  does not carry. A third cancel class means one more row in that map and
  nothing else.
  The extractions that made room for it are leaves with no budget knowledge of
  their own: `_fabro_record_instant.py` (the nested-record instant reader, moved
  verbatim out of `_dispatcher_reconcile_runs_grace.py`),
  `_dispatcher_journal_rows.py`, `_dispatcher_watchdog_run_probe.py`,
  `_dispatcher_stale_item_reap.py`, `_dispatcher_watch_poll.py` (one poll's
  whole observation — its `stamped_attribution` call is an explicit statement
  BEFORE the `WatchPoll` construction, because field-order evaluation would
  otherwise put the reap row ahead of the dispatch stamp rows in the journal),
  and `_dispatcher_shell_runner.py` (`ShellCommandRunner` and `child_env`, split
  out of `_dispatcher_io.py` to break the import cycle the budget's preserve leg
  closed; `_dispatcher_io.py` still RE-EXPORTS both, and only a module inside the
  launcher's own import reach needs to import the leaf directly).
- `_dispatcher_sandbox_image_source.py` — WHICH of the three sources supplies one
  dispatch's sandbox image (`bd-ib-jy7fuh`, Scenario 169). PURE and a leaf; the
  decision is resolved ONCE in `_dispatcher_loop_plan`, rides
  `DispatchPlan.sandbox_image`, and is read from there by both consumers — the
  launch overlay renders from it and the `dispatch-id` record names it through
  `sandbox_image_source_journal_record` — for the same resolve-once reason the
  integration contract gives. Four properties an editor
  must not invert. The CATALOG arm wins over `dispatcher.fabro_sandbox_image`
  unconditionally, because the configured key is a repository-wide pin and the
  catalog environment is the placement this dispatch was ROUTED to. It wins by
  the overlay DECLARING NOTHING rather than by declaring the catalog's image:
  the catalog lives on the factory server and the Dispatcher reads it at no
  point, so there is no value it could render on the catalog's behalf — and the
  submitted config's own `environments.<id>` overlay still applies on top of the
  server's environment selection, so suppressing only the SUBSTITUTION would
  leave the committed pin overriding the catalog instead (the measured defect,
  hp-candidate run 01M4PBFW4MP8, where `sandbox.plan.image` named the catalog's
  image while the started container ran the override). And `catalog_governs` is
  a question about the SOURCE rather than an inference from an absent
  `overlay_image`, which the committed-run-config arm also carries: those two
  arms need opposite handling, and collapsing them would make a repository that
  configures nothing withhold a declaration nothing is competing with. And the
  journaled `sandbox_image` is NULL on the catalog arm rather than filled in:
  the only values available to fill it with are the committed and configured
  images, which are exactly the ones that arm keeps out of the launch — while
  all three keys are written on EVERY launch, nulls included, because an
  omitted key is what a record from a build predating this decision looks
  like, so a reader could not tell "named no environment" from "was never
  asked". The record's `sandbox_image` argument is REQUIRED for the mirror
  reason: a default is how one dispatch's record silently reports the
  no-declaration answer for a dispatch that had a declaration.
- `_dispatcher_proof_budget.py` — the declared size budget every proof record is
  measured against before it is posted (`bd-ib-555xcd`). PURE, and the ONE place
  the three figures are named: the MEASURED forge comment ceiling, the record
  budget below it, and the per-assertion inline allowance a capture agent plans
  its proof recipe against. Three properties an editor must not invert. The
  ceiling is a MEASUREMENT with its provenance recorded beside it
  (`plan/archive/definition-and-proof-of-done/research/005-forge-comment-ceiling-measurement-2026-10-07.md`),
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
- The TRANSPORT a projected credential reaches the worker through lives in three
  cohesive modules, split pure-from-impure the usual way:
  `_dispatcher_secret_channel` (PURE: the two transports a factory may declare,
  the stable vault key each credential is stored under, the reference token, the
  bundle rewrite and every refusal), `_dispatcher_overlay_write` (routing plus
  the mode-600 write, which are ONE act) and `_dispatcher_secret_vault`
  (dispatch policy, rejection scrubbing and per-store journaling). The store is
  injected as a `VaultSecretSink`, which is what keeps the whole transport
  exercisable without a factory; its engine call remains the specialized
  `FabroPort.secret_set` verb inside the existing `_fabro_port` facade.
  Two properties of the sink an editor must not invert, both about SURFACES
  rather than about correctness. The value travels on the child's STANDARD
  INPUT, from an UNLINKED temporary file's descriptor — never an argument, which
  is visible in the host process table, is what a runner echoes into a log, and
  is what a timeout or not-found diagnostic quotes back verbatim. And the
  server's own rejection text is SCRUBBED BEFORE its bounded excerpt is taken:
  the dispatch journals that refusal, so an echoing message would put the
  credential into the one record written to say it could not be stored. It is
  a specialized `FabroPort` verb so every engine invocation remains behind the
  one facade, while the unlinked-file ownership and rejection policy stay out
  of the value-free verbs. `_dispatcher_codex_overlay_leg` is the
  neighbouring extraction that keeps the materializer inside its size ceiling:
  the run budget, the graded host Codex snapshot, the credential-use enforcement
  inputs and the launch-route guard, in that order, as one unit.
  Six properties an editor must not invert. The INLINE overlay is the default
  only when the declaration is ABSENT; an unrecognised, empty, null or non-string
  declaration REFUSES — the pinned engine resolves no
  reference, so routing on it breaks every dispatch, while guessing the inline
  transport on a Petri-era server persists a literal credential in an immutable
  server-side workflow version, which is the exposure the whole transport exists
  to close (`fabro inspect` returned the projected `CLAUDE_CODE_OAUTH_TOKEN`
  unredacted on hp run 01M058955QQ5). The vault key is STABLE from the environment
  variable name: the reference lands in an immutable workflow version, so a
  dispatch-derived name would make every credential rotation require a new
  bundle instead of refreshing the value the existing bundle names. Factory
  dev-token login happens BEFORE materialization can perform its first vault
  store, so a fresh host does not fail before the later launch-time login. A
  host-global per-factory launch lock spans the first stable-key write through
  the worker's `running` transition: the candidate records that transition only
  after it has loaded and snapshotted the vault, so overlapping dispatches from
  independent operator-host clones cannot interleave a multi-secret batch or
  replace one launch's values before its snapshot. `runnable` is deliberately
  too early to release because it reports queue admission, not a started worker.
  Routing finishes BEFORE
  anything is stored, so a refusal leaves the vault untouched rather than
  seeding credentials for a dispatch the next line declines. A store failure
  REFUSES rather than being ignored: the bundle is unchanged either way, so an
  ignored failure launches the run against an absent, incomplete or stale stable
  entry. And the routed name list is read back off the lines each
  projection ACTUALLY rendered — never re-derived from a declaration — because
  `contracts.md` section "Proof credential projection" requires that a change of
  transport leave the declaration, its refusals and its journal rows alone.
  The routed set is EXPLICIT (`REQUIRED_CREDENTIAL_ENV_NAMES` plus
  `OPTIONAL_CREDENTIAL_ENV_NAMES` plus the rendered proof-credential names)
  rather than discovered by a marker scan, for the reason that module's own
  comment gives: the same env table carries `CODEX_REFRESH_TOKEN_URL_OVERRIDE`
  and the credential-use deadline keys, none of which is a credential. A
  credential renderer added later must add its env name there.
  WHICH of those names are REQUIRED is scoped by the dispatch's own ROUTING,
  through `required_credential_env_names(routes_codex=)`, and the parameter is
  threaded from the one resolution `_dispatcher_credentials` takes rather than
  re-read — because `_dispatcher_codex_overlay_leg` scopes itself by the SAME
  answer, and the two disagreeing is the measured defect: the channel demanded
  `CODEX_AUTH_JSON` of every bundle while the leg correctly projects none for a
  dispatch that routes no node to `codex-acp`, so every native-channel dispatch
  without a Codex node was refused at the `run-config-overlay` stage naming a
  credential it was right not to carry (canary dispatch
  3239702d96d246b28af019dd63dc151f, 2026-10-18). A family this routing does NOT
  require is demoted to an OPTIONAL name rather than dropped, so a value some
  projection nonetheless rendered is still routed off the vault instead of
  being left inline in an immutable workflow version; and neither
  `credential_env_names` nor `route_dispatch_secrets` defaults the parameter,
  since each default is silently wrong for half the dispatches.
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
- `_acp_dispatch_coverage` is the DISPATCH-scoped half of the legacy
  provider-record coverage rule: `_acp_hold_coverage` answers it for one
  candidate, and this answers it for the whole set a dispatch's resolved node
  adapters render. PURE, and the repair of a measured fail-wide
  (`bd-ib-4nlb5s`): the legacy admission gate iterated a hard-coded
  `("anthropic", "codex")` tuple, so a record for either vendor refused EVERY
  dispatch including one routed wholly to the other, and a record for any
  third provider was unreadable. Both halves are now derived — the readable
  providers from the journal's own records
  (`_dispatcher_provider_exhaustion.live_provider_exhaustions`), the
  refusable ones from the rendered candidates
  (`covering_provider_exhaustion`). Three properties an editor must not
  invert. `builtin` TRAVELS WITH the candidate and is never re-derived from
  an identity, because it is read from the rendered-bytes table and an
  operator who spelled their own `availability_key` with a vendor's word has
  not opted into that vendor's blanket. A node's FALLBACKS are in the set: a
  legacy record carries no scope, candidate key or node, so it cannot support
  a judgement about which chain position it reached, and reasoning about
  chain viability belongs to `_acp_candidate_preflight`. And an UNREADABLE
  resolution is `None` rather than the empty tuple — the empty tuple is an
  answer about candidates, `None` is the absence of a measurement, and the
  gate owes them opposite treatments. `_dispatcher_acp_preflight.
  resolve_dispatch_candidates` is the one place the resolution is read off
  disk, and `_dispatcher_admission_eligibility` spends it ONCE PER PASS.
- `_fabro_executed_candidate` attributes a classified provider-limit failure to
  the candidate that RAN, from the `livespec.acp.<node>.*` labels the dispatch
  stamped (`contracts.md` §"Provider-limit permanence and root-cause
  surfacing": "The provider is attributed from the recorded executed candidate
  identity, never inferred from a shared message literal"; Scenario 65). PURE,
  and the repair of a misattribution that is wrong in BOTH directions at once:
  Claude and Codex both say "You've hit your usage limit", the measured hint
  maps that sentence to `codex`, so a failing Claude attempt wrote a record
  under a vendor nothing spent — refusing later dispatches on an intact
  allowance while the exhausted one stayed unheld. Four properties an editor
  must not invert. RECOGNITION IS NOT TOUCHED: whether the failure is a ceiling
  stays with `_fabro_port_permanent_failure`'s cause-text classification, and
  only WHOSE ceiling it was moves here, which is what lets one message literal
  recognise a ceiling for either vendor without naming one. The typed flag is
  the GATE, because a dispatch stamps these labels on every run while a ceiling
  is rare, so an attribution firing on any failure would name a vendor for an
  ordinary transport fault. An ABSENT identity keeps the v107 cause-text
  attribution rather than refusing — `dispatch_run_label_pairs` emits a pair
  only for a node that resolved one, so an identity-less legacy adapter leaves
  its node unlabelled, and the contract keeps that adapter on the conservative
  legacy posture with no entitlement a typed hold could be scoped by. And the
  label keys are IMPORTED from `_dispatcher_run_labels` rather than respelled:
  a reader spelling a key its writer does not would find nothing and report an
  absent identity, which is the same misattribution arriving silently. The node
  key is normalized because the two engines spell it differently — the pinned
  engine keys its outcome map `implement`, the Petri-era engine keys its stage
  map `002-implement@1` — while the label is keyed on the graph node id alone.
  `_dispatcher_fabro_reattach.inspect_run` is where it is APPLIED, and the
  venue is forced rather than chosen: MEASURED on both engines, an `inspect
  --json` record carries no `labels` key at all (the pinned build answers
  `run_id`, `status`, `checkpoint`; the candidate build answers nine keys, none
  of them labels), while the `ps --json` run row carries them on every row. So
  the attribution costs a SECOND read, and it is taken at the one function
  every dispatch and every reconciliation reads a run through rather than at
  each terminal mapper that consumes the failure. Three properties of that
  read. It is spent ONLY on a failure already carrying the typed flag, because
  `ps -a --json` lists every run the factory holds. The row is selected BY RUN
  ID and never taken from the head of the list, since a factory serves every
  repository on its host and another repository's row carries a well-formed
  entitlement belonging to somebody else's dispatch. And it is journaled under
  its own `fabro-run-labels` stage, because its SILENCE changes an answer — a
  refused listing leaves the legacy attribution standing, which at the outcome
  is indistinguishable from a dispatch that recorded no identity to read.
- The HOST-WIDE AVAILABILITY EVIDENCE of `contracts.md`'s "Holds are per
  provider domain and discoverable host-wide from factory-native run records"
  paragraph (`bd-ib-hyuqv6`, Scenario 127) lives in FOUR cohesive modules, split
  record-from-read the way `_acp_hold_records` / `_acp_hold_ledger` are one
  level down, and the dependency direction reads bottom-up:
  `_acp_factory_hold_records` (PURE: ONE derived FAILED attempt — its six
  identifying fields, its bounded expiry, the typed hold it stands for and the
  journal line that audits it) and `_acp_factory_success_records` (PURE: ONE
  derived SUCCEEDED attempt, the retirement counterpart) →
  `_acp_factory_hold_evidence` (the read: every factory under
  `dispatcher.factories`, each one's `fabro ps -a --json` listing, and ONE
  `fabro inspect --json` per row either arm's window reaches) →
  `_acp_hold_retirement` (PURE: the two non-expiry retirement routes, applied to
  the UNION of that read with the repository's own journal fold).
  `_dispatcher_acp_preflight.resolve_acp_preflight` is the one consumer; the
  reader is an injected seam defaulting to ABSENT, exactly as `probe` and
  `headroom` beside it, so wait attention and idle-factory compose a verdict
  that reaches no factory.
  FOUR PROPERTIES OF THE RETIREMENT HALF (`bd-ib-bmbmlt`, Scenario 94) an editor
  must not invert. The two routes are applied at the UNION and nowhere else,
  because neither producer can reach both halves: the factory read cannot be
  handed a journal — that absence is what makes observations reconstructible
  after the journal is removed — so it can neither see an operator's clearance
  line nor filter itself by one, and the journal fold cannot see a factory, so
  it can neither derive a later success nor apply one. A confirmation is dated
  from its run's START rather than its completion, which is the conservative
  bound: a run that began after an observation cannot contain a node attempt
  that began before it, while a run already executing when the outage was
  observed would finish afterwards and clear a hold the contract says it proves
  nothing about. A derived confirmation claims ONLY the allowance its labels
  recorded, never a broader domain set, because a peer candidate's declared
  domain overrides are the declaring repository's configuration. And the
  confirmation arm no longer short-circuits on a non-failed row, because a run
  still RUNNING can already carry a succeeded node attempt; what stays scoped to
  a FAILED row is the occurrence-unreadable surface, since an undatable success
  retires nothing and so is not a failure to measure anything a decision rests
  on.
  SEVEN PROPERTIES AN EDITOR MUST NOT INVERT. No module of the READ group —
  `_acp_factory_hold_records`, `_acp_factory_success_records` and
  `_acp_factory_hold_evidence` — reads, writes, or
  can be HANDED a repository-local dispatch journal, which is how "Hold
  observations ... MUST remain reconstructible after any repository-local
  dispatch journal is removed" holds structurally — there is no parameter a
  journal could arrive in, and the journal copy is an AUDIT reference carrying
  the factory run it is re-derivable from. The scan is bounded by the LISTING
  ROW, before any per-run read is spent: a factory serving this fleet listed
  1626 rows on 2026-10-12, and a failure older than `HOLD_INTERVAL` can only
  re-derive an already-expired record. The occurrence time is the run's own
  COMPLETION instant (`start_time` advanced by `wall_time_ms`) and a row
  missing either figure is UNOBSERVABLE rather than dated from its start — a
  run that began four hours before it failed would mint holds born expired, so
  the mechanism would report a clean empty answer on exactly the outage it
  exists to catch, which is the same reason `_dispatcher_reconcile_runs_grace`
  excludes `start_time` from its own park measurement. Expiry is computed from
  that occurrence and from no other input, so a re-derivation cannot push a
  hold forward. Every read that could not be TAKEN is surfaced as unobservable
  and rides the verdict ALONGSIDE the entitlements it leaves unconfirmed, which
  is what lets the candidate filter act on it rather than merely report it,
  because "An unreadable or incomplete evidence source
  is unavailable, not an empty hold set" — while a failure the cause chain does
  not classify, and a failing node the run recorded no entitlement for, are NOT
  surfaced: both were measured, and the second is the conservative legacy
  posture where no entitlement exists for a typed record to be scoped by. The
  derived record is DOMAIN-scoped on the spent allowance, as Scenario 127
  requires. And an entitlement key that arrives DIGESTED is read as it stands,
  exactly as `_fabro_executed_candidate` reads it: the digest is one-way, so
  such a record covers only a candidate whose own key the engine would have
  recorded the same way, and broadening it would name an entitlement nobody
  declared.
- The FACTORY-NATIVE OPERATOR CLEARANCE of the same paragraph's "an operator
  clearance by a minimal factory-native record whose recorded outcome carries
  the clearance's exact identity, actor, time, and reason" (`bd-ib-dtfv2p`,
  Scenarios 116 and 127) is split pure-from-impure the usual way:
  `_acp_clearance_records` (PURE: what one clearance IS, the one label a reader
  recognises its run by, the single line its recorded outcome carries, and the
  parse of that line) → `_acp_clearance_factory_record` (the write: one
  deterministic single-script-node run, launched through the existing
  `FabroPort` facade) and `_acp_factory_clearance_evidence` (the read: where in
  a run's own `inspect` record that line is found). `_acp_hold_clear` is the
  write's one caller; `_acp_factory_hold_evidence`'s clearance arm is the
  read's, and it REPORTS the ids rather than applying them, because a clearance
  may name an observation this read derived, one the reading repository's own
  journal carries, or one neither holds any more — and only the union has all
  of them in hand, which is the same reason the other two retirement routes are
  applied there.
  Eight properties an editor must not invert. The FACTORY record is the
  AUTHORITY and the journal line is its AUDIT REFERENCE — the
  provider-exhaustion clause says so in as many words — so the valve writes the
  journal only once the factory write has succeeded, and a repository that
  cannot record on a participating factory is REFUSED rather than falling back
  to its own journal: a journal-only retirement clears the hold for that
  checkout while every peer, which has no access to that journal by
  construction, keeps dispatching into a record its operator believes is gone.
  Every pre-existing refusal returns BEFORE the write, which is what keeps a
  record a peer reads as a clearance from describing a clearance the valve went
  on to reject. The LABEL carries nothing a reader decides on, because an
  `availability_key` is opaque by contract and a `--reason` is operator prose,
  so neither fits the engine's label alphabet — the label says which rows are
  worth a per-run read and the OUTCOME carries the clearance. The engine
  version is MEASURED rather than assumed, because the two engine generations
  take their workflow argument differently and a Petri-era engine refuses a
  config file before any run exists. And the payload rides the script through
  TWO deterministic encodings in one order only — shell-quote the line, then
  DOT-escape the result — so the recorded outcome is the line itself, plainly
  readable by an operator looking at the run, rather than an encoded form only
  this package can decode. The PARSE lives beside the RENDER so one record
  format cannot drift across two files, and it is STRICT in the destructive
  direction: a line missing the marker, or carrying a field of the wrong type,
  reads back as NOTHING rather than as a clearance assembled out of whichever
  fields happened to parse — a retirement cannot be undone, so a half-read
  record would retire an observation nobody cleared. And the read scans BOTH
  engines' outcome maps (the Petri-era `stages` map and the pinned
  checkpoint's `node_outcomes`) without consulting the node id, because the two
  spell that id differently — `record` against `002-record@1` — while the
  record carries at most one clearance line and that line carries its own
  marker; reading one map only answers `None` on the other engine, which at the
  evidence surface is indistinguishable from a run that recorded no clearance.
  And the clearance ARM is bounded by the run's START, exactly as the
  confirmation arm is and for the same reason — a clearance recorded longer ago
  than `HOLD_INTERVAL` can only retire a record that has already expired on its
  own — so a clearance row outside that window costs no per-run read at all.
  AT THE UNION (`_dispatcher_acp_preflight._unioned`) the two clearance SOURCES
  are UNIONED rather than preferred between: a clearance this repository's own
  operator performed is a line in its journal and one a PEER's operator
  performed is a record on the factory, both name observation ids, and an id is
  a digest of the evidence plus the scope it lands on — so an id either side
  names is naming the same record, and a repository that cleared one hold
  locally while a peer cleared another must see both retired rather than
  whichever source it happened to read. The merged set is carried ON the ledger
  value and not merely consumed, so a later reader of
  `retired_observation_ids` cannot answer a different question from the filter
  above it. What this delivers at the wave is the clause's own scheduling rule:
  the next loop-wave evaluation re-derives the chain, finds the cleared record
  retired, and proceeds — instead of parking again for the instant the previous
  evaluation scheduled, however long ago the operator cleared the outage.
- The ADMISSION SESSION-HEADROOM FILTER of `contracts.md`'s "Admission filters
  candidates by projected Claude session headroom" paragraph (`bd-ib-jwuxs4`,
  Scenario 60) lives in SEVEN cohesive modules, split pure-from-impure the usual
  way, and the dependency direction reads bottom-up: `_acp_session_headroom`
  (PURE: the reading value, its validation, the coverage predicate and the skip
  predicate, plus the projection RESULT value and the per-evaluation policy type)
  → `_acp_session_headroom_drain`
  (PURE: the five-hour drain rate — the inclusive age window, the earliest-prior
  selection and the rate itself) → `_acp_session_headroom_projection` (PURE: what
  that rate IMPLIES — the projected exhaustion instant, the horizon comparison
  that decides a projection skip, and the three closed results) and
  `_acp_session_headroom_
  records` (PURE: the journal projections — the per-item assessment record, the
  per-node selection fields, and the fields a headroom-governed refusal adds) and
  `_dispatcher_session_headroom_io` (the ONE bounded usage request plus the
  opaque credential fingerprint) and `_dispatcher_session_headroom_baseline`
  (the dispatch-journal read that projects one credential's prior readings) →
  `_dispatcher_session_headroom_gate` (the
  committed floor and horizon, the per-evaluation policy its memo lives in, and
  the journal
  writer). The filter itself is the LAST of the five filters of
  `_acp_candidate_preflight`, below the unavailable-evidence filter the
  retirement work added (`bd-ib-bmbmlt`) and below the credential probe, which
  is the ordering the headroom clause requires — "a successful credential-
  usability probe MUST NOT override a headroom skip";
  `_dispatcher_admission` is the only caller that
  supplies a policy, and it hands the policy the SAME journal path it resolves
  the verdict against, because `dispatcher.py` accepts a `--journal` override
  and a re-derived path cannot be proven to name the file this pass appends to.
  SIX PROPERTIES AN EDITOR MUST NOT INVERT. This is NOT the credential probe:
  `claude-cred-status` answers "can this credential call the provider" and
  reported `usable` two minutes after a run was refused mid-implement on the
  session limit (hp, 2026-10-14), which is why the clause exists at all. An
  UNOBSERVABLE reading is its own field and is never coerced to a number —
  every sentinel available (0, 100) is also a valid reading, so a coerced one
  is indistinguishable downstream from a measurement. COVERAGE FOLLOWS
  PROVENANCE: the resolved `claude-acp` agent id, or a built-in identity keyed
  on exact rendered bytes, never an `availability_key` that happens to spell a
  vendor. EQUALITY PASSES the floor and a floor of ZERO disables both kinds of
  skip while RETAINING the reading and its journal row — the unobservable arm
  is the only one the zero-floor guard reaches, since no remaining headroom is
  strictly below zero. The filter sits BELOW the credential probe, because "a
  successful credential-usability probe MUST NOT override a headroom skip". And
  a reading creates NO observed availability record and retires none, which
  holds structurally rather than carefully: nothing in the filter is handed a
  journal.
  A SEVENTH PROPERTY LIVES ONE MODULE OVER, in `_acp_preflight_verdict.
  _no_fallback_graded`, and it is the repair of a gap that hid for the mirror
  reason the one below hid: a repository DECLARING NO FALLBACK-ENABLED CHAIN is
  still assessed, because the clause covers "built-in single-candidate nodes
  without fallback metadata". The assessment used to be short-circuited by the
  enabled-chain test that runs strictly earlier, so it was gated on a repository
  declaring fallback metadata rather than on the clause's own coverage rule —
  measured 2026-10-17, a fresh dispatch in a sibling repository that declares no
  chains journaled ZERO assessments while this repository's own evaluations
  journaled one apiece, which left every repository without chains dispatching
  with no headroom brake at all. Three things about that path an editor must not
  invert. It is keyed on the POLICY's absence and never on a falsy floor, so
  wait attention and idle-factory still pay the whole short-circuit and issue no
  usage request. It filters on HEADROOM ALONE — the inputs are rebuilt and no
  hold ledger reaches it — because the other three filters need no external call
  and a verdict that applied them only when a policy happened to be supplied
  would answer differently per consumer, which "Idle-factory and wait attention
  consume this identical verdict" forbids; the headroom clause ratifies that one
  asymmetry and nothing else may acquire one. And it FAILS OPEN on the two
  graph-derivation refusals, which a dispatch does not need, while the
  CONFIGURATION refusal stays fail-closed in `_dispatcher_acp_preflight` where
  `prepare_acp_nodes` would refuse the dispatch for the same fault anyway.
  ONE GAP IS WORTH KNOWING BEFORE EDITING THE CHAIN LAYERS, because it produced
  a clean, plausible, entirely wrong green. A node's FALLBACKS are parsed as
  candidates and keep their resolved `agent_id`; its PRIMARY is REBUILT in
  `_acp_chain_resolution._attach_one` from the already-resolved adapter, so
  `agent_id` has to be carried across `AcpNodeChain` explicitly — exactly as
  `config_options` is. Without that, coverage saw `None` on every primary and
  the filter assessed nothing this repository's own eight ACP nodes run.
  `test_acp_session_headroom_primary_coverage.py` keeps the live control that
  caught it. The two gaps are siblings: that one made the filter assess nothing
  on a repository WITH chains, this one made it assess nothing on a repository
  WITHOUT them, and each produced a healthy-looking green on the other's
  population.
  THREE PROPERTIES OF THE DRAIN RATE an editor must not invert, and each is a
  different kind of claim. A PRIOR READING and a BASELINE are deliberately
  different types: the baseline carries the elapsed hours MEASURED during
  selection, which is the only place both instants are in hand, so the rate
  divides by a span that cannot be zero or inverted rather than by one guarded
  on an arm no dispatch could reach. The baseline is the EARLIEST in-window
  prior and never the newest — the earliest gives the longest span the window
  supports, while the newest reports the last few minutes, which is the quantity
  the level already tells you — and it is selected on the PARSED instant, never
  on journal position, because the journal is appended to by concurrent passes
  and `_dispatcher_io.JournalFile` stamps its envelope `at` at APPEND time. And
  the rate is NULL and never 0.0 wherever it cannot be measured: a drain of zero
  is what an unspent credential genuinely reads as, so a coerced zero is
  indistinguishable at the record from a measurement — the same argument the
  reading's own `unobservable` field rests on, one level down.
  THREE PROPERTIES OF THE PROJECTION an editor must not invert, and each is the
  clause's own wording rather than a preference. The record carries EXACTLY ONE
  result under ONE key, with the result KIND as a field inside it: three
  parallel optional blocks would let a record carry two, and a reader joining on
  whichever it found first would report the wrong one with no way to notice.
  `not-projected` and `unavailable` stay DISTINCT — the first means the dial or
  the floor settled the reading before any history was consulted, the second
  means a projection was attempted and an input could not be measured — and both
  end at a null rate, so a build that collapsed them would report an operator's
  disabled dial and a fresh checkout's missing history as one state. And every
  unavailable arm FAILS OPEN, because the floor already governs the level of an
  unprojected reading while a projection that refused when blinded would refuse
  every first dispatch on every credential in every fresh checkout — the common
  case rather than an edge. Note also that the baseline is read ONCE in
  `_dispatcher_session_headroom_gate._assessed` and spent twice: the rate and the
  projection are two readings of ONE history, and a second journal read would
  let a rate measured against one baseline sit beside a projection naming
  another.
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
- The DISPATCH-TIME FABRO CURRENCY ADMISSION of `contracts.md`'s
  Fabro-currency-admission clause and `constraints.md`'s
  exact-upstream-base-and-bounded-currency clause (`bd-ib-j9x`, Scenario 130)
  lives in FIVE cohesive modules, and the dependency direction reads bottom-up:
  `_dispatcher_fabro_currency` (PURE: the release and observation values, the
  calendar-day arithmetic, the decision ladder and the evidence block every
  refusal carries) → `_dispatcher_fabro_currency_sources` (the engine and forge
  reads: the target's own serving integration commit, the paginated releases
  parse and the bounded ancestry walk) and `_dispatcher_fabro_release_cache`
  (the mode-ordinary JSON record under the per-user state root) →
  `_dispatcher_fabro_release_observation` (the cache-versus-refresh decision,
  which is where the seven-calendar-day age test lives) →
  `_dispatcher_fabro_currency_gate` (the selection-level gate the pre-dispatch
  wall calls).
  EIGHT PROPERTIES AN EDITOR MUST NOT INVERT. Every arm that could not MEASURE
  fails CLOSED, because a gauge that admitted when blinded turns the refusal
  into a pass and leaves a journal record that reads exactly like a healthy one.
  Publication time is the ONLY ordering evidence — `constraints.md` says so in
  as many words — so nothing here may read a semantic version or a commit
  timestamp, and `releases_by_publication` exists to be the single place that is
  true rather than a convention each caller re-applies. It is NOT the forge's
  enumeration order, which is by CREATION: measured on the release-class
  fixture, reading the list head as newest ADMITTED a base 35 calendar days out
  of window, because that head was a stable release published five weeks before
  the nightly that was actually newest. That sort also runs BEFORE the ancestry
  walk's candidate bound, so the cap cannot truncate by creation order and leave
  the answer outside the population the refusal then reports on. The one
  TRANSITION is `transition-admitted` rather than `current` and states the gap
  it is excusing, because an admitted transition reporting only "admitted" is
  indistinguishable at every surface from an in-window base — the one
  description the clause forbids it — and its three literals are RATIFIED, not
  configured: a deadline an operator could move is the indefinite 0.254 freeze
  `constraints.md` forbids. The serving commit is asked of the
  TARGET'S OWN SERVER through `FABRO_SERVER`, never of the local client, which
  on this fleet is routinely a different build (the hosts are re-pinned one at
  a time). The ancestry walk is BOUNDED BY THE OBSERVATION — one round trip per
  release it was handed, no narrower candidate cap — and its refusal STATES THE
  SCOPE IT SEARCHED, because an absence asserted over an unstated population is
  what turns a bounded search into a false impossibility. The bound being the
  observation is a CORRECTNESS requirement and not a preference: a smaller cap
  does not merely miss a base, it MISDIAGNOSES one, because the 30-day rule
  exists to refuse an OLD base and a base must be found before it can be judged.
  Measured 2026-10-11 against the live forge, `v0.254.0` is `identical` to the
  carrier commit `497aaba6` and sits at publication index 80 of 147 published
  releases, so a 40-candidate cap refused the very carrier the ratified
  transition must ADMIT, reporting `no-release-tag-ancestor` — a different
  condition, with a different corrective route. The cost scales with staleness in
  the right direction: the walk stops at the first ancestor in publication order,
  so a current build costs one or two round trips and only a build with no
  release-tag ancestor at all pays the full observation. A stale cached observation
  whose refresh failed is carried FORWARD rather than discarded, because the
  clause requires the refusal to name it — and it is still never SERVED, since
  an expired reading proves nothing about currency. And a target that declares
  NO SERVER is recorded under the gate's own unevaluated stage rather than
  refused or passed over in silence: every condition the clause enumerates is a
  fact about a build some server is SERVING, so refusing there would impose an
  admission condition on every repository that has not declared a factory,
  while silence would read as a reading that was taken and succeeded. Do NOT
  turn that last one into a configurable exemption — the discriminator is the
  structural absence of a server to ask.
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
  required result through. Nine cohesive modules, and the dependency direction
  reads bottom-up: `_plan_result_targets` (PURE: the closed five-kind grammar,
  each target's own identity rendering, the reference, and the parse refusal) and
  `_plan_result_observation` (PURE: the observation value plus its constructors
  and the named sources) → `_plan_result_reference` (PURE: the parse and its
  whole refusal ladder) → `_plan_result_repository` (the named repository
  resolved to ONE clone plus that clone's own tenant connection) →
  `_plan_result_proof_grade` (PURE: what a pull request's records PROVE — the
  factory leg's attribution, its publish-head build declaration and its
  requested-build containment, and the reading order that keeps
  `unsatisfied` and `unobservable` apart) → `_plan_result_ledger` /
  `_plan_result_forge` / `_plan_result_proof` (the five adapters, grouped by the
  source each reads) → `_plan_result_reader` (the ONE public entry point: parse,
  resolve, then exactly one source).
  THE PROOF ADAPTER IS SPLIT PURE-FROM-IMPURE for the reason that split exists
  everywhere else in this tree: `_plan_result_proof` resolves the subject through
  the ledger, reads the pull request and builds the containment reader, while
  `_plan_result_proof_grade` decides what the records mean. The grading is a pure
  function of a record set plus three answers about it, and a decision that
  reached for the forge itself could not be exercised across every state the
  clause distinguishes without a double for one.
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
  semantics, a verified-class verdict, the build the record declares, and every
  requested assertion reading as reproduced — never text; the installed build
  identifier is deliberately not compared, because the host-leg clause records
  it without verifying it.
  THAT THIRD THING IS READ FROM A DIFFERENT PLACE PER LEG, and the two shapes are
  not interchangeable. A HOST record declares a `Build identity` section, whose
  `containment_ref` is the release tag or, where no release applies, the
  default-branch commit. An ordinary FACTORY record declares a `Publish-branch
  head:` prose line and carries no such section AT ALL, because that section names
  a release and the capture and verify stages run on the draft pull request, before
  the merge any release could contain — so `published_head` is what recovers its
  candidate. Asking every record for the host section refused every ordinary
  factory proof of its own exact candidate, and the refusal read exactly like a
  record that proves nothing (measured 2026-10-09 against `overseer-s32tdk`'s
  `verified` record on pull request 2376).
  THE CONTAINMENT THE TWO LEGS OWE ALSO DIFFERS, which is why
  `_authoritative_containment` returns a `_Containment` carrying ONE READER PER LEG
  rather than one composed reader. Both legs ask whether the declared candidate
  carries the REQUESTED build; only the host leg additionally asks whether it
  carries the SUBJECT'S RECORDED MERGE, which is the post-merge requirement on a
  released build. A pre-merge factory candidate is the head that merge was made
  from, so it cannot contain it: imposing the host relation there produced a
  confident negative no re-dispatch could ever turn into satisfaction. Do not
  collapse the two readers back into one — a single parameter is one edit away from
  re-imposing it, and neither leg's refusal announces which relation refused it.
  The ORDER of the reader's three steps is load-bearing and is the fail-closed
  order: an unparseable reference names no target to read, and every adapter
  needs the clone it executes from, so a reversed pair would spend a read on a
  question that had not been established and then attribute the failure to the
  wrong source — which is the one thing the clause requires naming correctly.
  EVERY STATUS IS EARNED ON THE ARM THAT ESTABLISHED IT, and the two
  non-satisfied statuses are not interchangeable. `unsatisfied` is a CONFIDENT
  NEGATIVE and is returned only where the source WAS read and the target found
  wanting; an arm that could not read answers `unobservable` and names the
  source that failed. Moving a read-failure arm onto `unsatisfied` reports a
  diagnostic as a measurement, and moving an unmet arm onto `unobservable` hides
  a real negative behind one — the clause forbids both directions, so neither
  default is safe.
  ONE READ INSIDE THE PROOF ADAPTER IS THE EASIEST PLACE TO RE-COLLAPSE THAT
  DISTINCTION, so it is named here. `_recorded_merge` yields the merge a verified
  build must contain, and it answers THREE ways, not two: a merge, an ABSENCE, or
  `_MalformedAudit`. An absence is a subject whose work has not closed, which
  leaves the merge-containment relation VACUOUS; audit evidence that is PRESENT
  holding a value of the wrong type is malformed, which refuses from the LEDGER.
  Do not fold the third answer back into the second. `omitempty` omits a field and
  never retypes one, so a `metadata` holding a string, an `audit` holding a list,
  or a `merge_sha` holding a number is unreadable evidence rather than a sparse
  record — and folding it onto the vacuous arm skips the containment relation
  entirely, so the reading SATISFIES on the requested build alone. That is this
  adapter's most forbidden direction reached from its most innocuous-looking
  simplification: satisfaction earned on evidence nobody could read, which no
  `unsatisfied`-versus-`unobservable` reasoning catches because the verdict is
  neither of them.

- `_plan_next_action_admission.py` — the WRITE-TIME half of that reader's
  repository identity (`bd-ib-eebjcl`): whether the repository a candidate
  pointer's `required_result` names is one `resolve_result_repository` can
  actually resolve for this project. It is the impure companion of
  `_plan_next_action_validation`, which grades the pointer's SHAPE and is pure
  over the value handed to it, and `_plan_tracked_write` calls it in that
  module's place so every sanctioned writer takes one admission. Three
  properties an editor must not invert. It calls the READER'S OWN RESOLVER
  rather than restating what resolves, so the two sides cannot drift: the parse
  admitted any non-empty `repo` string while the resolution accepts four
  identities, and a value the writer accepted could therefore be one no
  observation could ever resolve — which `resume_directive` answers by
  withholding dispatch, while replacing an unobservable obligation is refused by
  design, so ONE malformed field locked a plan for its whole budget (measured
  2026-10-18 on plan epic `bd-ib-6tcjfx`, whose pointer named this project's own
  repository as `<owner>/<repo>`). A forge-path identity is REFUSED with the
  bare identity it was reaching for, never normalized onto it, because stripping
  the owner would make `<any-owner>/<this-repo-name>` resolve to THIS checkout —
  the exact inference `_plan_result_repository._origin_repository_name` refuses,
  since it reads another repository's result as this project's and reports it
  satisfied. And a reference the PARSE refuses passes through with no refusal of
  its own: the shape grade has already named the parse fault, and a `human` or
  `none` pointer names no repository at all, so an opinion here would either
  restate another module's refusal or invent one for a correct pointer.

- RELAY DELIVERY of `contracts.md`'s "Relay delivery" clause (`bd-ib-t3znvw`,
  Scenario 149) — the plan primitive that records a relay, and the one thing
  that discharges it. FIVE cohesive modules, split pure-from-impure the usual
  way, and the dependency direction reads bottom-up: `_plan_relay_record`
  (PURE: the three delivery legs, the record, and the two selections a retry
  and a recheck resolve a relay through) and `_plan_relay_admission` (PURE:
  every refusal, plus the explicit supersession that admits a conflicting
  target) → `_plan_relay_payload` (PURE: the canonical payload and the
  `plan-relay-event` body, render and parse together) →
  `_plan_relay_projection` (the one write and the one read of those epic
  comments) → `_plan_relay_delivery` (the primitive: grade, observe through the
  shared authoritative result reader, then record what was observed).
  SIX PROPERTIES AN EDITOR MUST NOT INVERT. `delivered` is written from ONE
  input — a `satisfied` reading taken in this call — and never from anything a
  caller supplied, which is why the caller's type (`RelayAcknowledgements`)
  carries only `receipt_ack` and `peer_recorded` while the recorded type
  (`RelayLegs`) carries all three: a caller-writable evidence leg would be the
  sender certifying its own delivery, and a record holding all three reads as
  discharged whoever wrote the third. The DEADLINE a record carries is read back
  off the relay's own history and never off the request — the SENDER is the
  party recording, so a stored request deadline lets it roll its own clock
  forward on every recheck, with every record well-formed either way; the
  request's deadline is used only where the relay has no history. A RETRY is
  answered from the record and never by observing again, and the operation
  identity is matched WITHIN the relay: matched epic-wide it would answer a
  fresh relay's first recording with another relay's record, naming a target the
  caller never named. A CONFLICTING target is refused rather than recorded, the
  supersession that admits one must carry its own relay id (reusing the
  displaced id makes the successor the latest record for that id and shadows the
  disposition the clause requires preserved), and a supersession of an UNCHANGED
  target is refused too — without that arm the deadline rule is launderable by a
  fresh relay id plus a record that reads as the sanctioned path. The epic's
  relay comments are read ONCE per call and the resolved records handed down, so
  no two grades can disagree about what the ledger holds. And every malformed
  payload parses to `None` rather than to a partial record — a half-read one
  would answer a retry with an observation the READER assembled, satisfaction
  included.

- The PLAN-AUTHORITY EPOCH CHAIN of `contracts.md`'s "Required result, budget
  and progress epoch" clause (`bd-ib-wdl577`, Scenario 147) — how a plan epic's
  authority transitions serialize when several writers commit from one epoch at
  once. Seven cohesive modules, and the dependency direction reads bottom-up:
  `_plan_epoch_payload` (PURE: the receipt ring, the authority state, the
  transition payload and its canonical JSON) and `_plan_epoch_findings` (PURE:
  every reportable condition plus the remedy each names) → `_plan_epoch_tokens`
  (the single-use token records, through the public `bd` surface only) and
  `_plan_epoch_projection` (the metadata cache and the `plan-progress-event`
  comment, with their reads) → `_plan_epoch_chain_head` (the forward walk) →
  `_plan_epoch_chain` (the ONE surface a plan writer calls: commit, recover a
  retry, or refuse as stale), `_plan_epoch_reconcile` (grade the projections,
  repair them, withhold a dispatch) and `_plan_epoch_genesis` (the one write
  that may start a chain).
  THE EXCLUSION IS NOT IN THIS PLUGIN, and that is the whole design. Writers
  may run on different hosts, containers or cloud instances that share nothing
  but the Beads server (maintainer ruling 2026-10-12,
  `.ai/ledger-writers-are-multi-host.md`), so serialization comes from `bd
  close`'s own `UPDATE … WHERE status != 'closed'` compare-and-swap. Nothing
  here may acquire a lock, open a socket, touch a host directory or reach past
  `bd` into SQL — a fence on any of those is wrong for this fleet however well
  it tests on one host.
  SEVEN PROPERTIES AN EDITOR MUST NOT INVERT. The winner of a close is READ from
  `close_reason`, never inferred from the exit code: a loser exits 0 when its
  conditional update matched no row, or 1 with Dolt `Error 1213`, and 22 of 80
  closer exits were non-zero across relay research note 005's 20 trials. That
  read-back has THREE answers and not two — this writer's reason, a rival's, or
  no reading at all — and the third is reported as
  `close_outcome_unknown_finding` with the candidate LEFT STANDING. `token_reading`
  renders an unreadable record as `present=False` with no close reason, which
  compares unequal exactly as a rival's reason does, so a winner whose read-back
  failed would otherwise delete the candidate its own committed payload names as
  `next_token_id` — severing the chain permanently, since every later walk reaches
  that id and reports it unreadable. The `present` test therefore runs BEFORE the
  candidate delete and before any projection: a leaked token is recoverable and a
  severed chain is not. A
  token is created ONLY with a server-assigned id and never re-created,
  because a duplicate explicit-id create is an upsert that reopens a closed
  record and erases its close reason (note 007) — which would admit a second
  winner for a committed transition. The payload carries the FULL resulting
  state and never a delta, which is affordable only because the receipt ring is
  bounded, and safe only because the predecessor of the latest closed token is
  deleted (note 006 measured both over 60 transitions) — a delete the
  RECONCILER also performs, because a writer that stopped after its close never
  reached its own and every later commit discards only the predecessor of the
  token IT closed, so one partial write otherwise strands one record for the
  rest of the epic's life (measured on the live tenant 2026-10-13 against
  released build v0.194.0: three live records at every checkpoint of a
  60-transition run). The RING IS CHAIN
  HISTORY and no writer supplies it: `carrying_receipts` exists because taking
  the receipts from the requesting writer left a 24-transition chain holding
  one receipt. The progress event is projected BEFORE the cache, since a
  missing cache is reconciled by walking forward while a missing event is the
  only record a retry recovers its original transition from. And the
  projections are repaired FROM the chain, never the chain from a projection.
  `authorized_head` is the call a dispatch gate makes, rather than a convention
  each caller remembers: a caller that forgot to verify would still get a
  perfectly good head.

- The RESULT BUDGET AND TYPED CAUSAL RECOVERY of `contracts.md`'s "Required
  result, budget and progress epoch" clause (`bd-ib-zi5ygh`, Scenarios 147 and
  148) — how a plan's obligation survives every pointer rewrite. Six cohesive
  modules, and the dependency direction reads bottom-up: `_plan_obligation`
  (PURE: the obligation read out of the chain's `AuthorityState`, its two exact
  inclusive limits, and the pointer projection) and `_plan_recovery` (PURE: the
  typed attempt, the CLOSED executable-operation grammar, the cause-to-operation
  authorization table and every refusal) → `_plan_progress_decision` (PURE: what
  one write may do to the obligation) → `_plan_tracked_write` (the ONE path all
  three writers take through `_plan_epoch_chain`) and `_plan_progress_resume`
  (the read-only reading a resume takes before deciding to dispatch) →
  `_drive_plan_progress_diagnosis` (the `diagnose-plan-progress:<epic>` executor).
  THE AUTHORITY IS THE CHAIN, NEVER THE POINTER, and that is the whole design.
  `next_action` is one metadata object every sanctioned writer rewrites
  WHOLESALE, so a budget stored there is one any writer can grant itself a new
  value for — and the defect is invisible, because the rewritten pointer is
  well-formed whether it preserved the deadline or extended it. The pointer and
  the `plan-progress-event` comments are PROJECTIONS of committed transitions.
  SEVEN PROPERTIES AN EDITOR MUST NOT INVERT. The projection is DERIVED from the
  committed authority and never accepted from the candidate, which is what makes
  a writer's request unable to matter. It has TWO hand-back guards and both are
  needed — one keyed on the ACTION carrying null tracking, one on the AUTHORITY
  tracking nothing — because a `human` pointer written while an unmet obligation
  is RETAINED must carry explicit nulls while the authority keeps the
  obligation; a projection keyed only on the authority stamps it back onto the
  one pointer that must not carry it, and the result fails validation on its next
  read. Both limits are INCLUSIVE (`>=`), since "At the exact deadline or when
  accepted handoffs reach max_handoffs, the next continuation is expired", and
  the COUNT is reported ahead of a clock that also passed because the count is a
  settled fact while the clock keeps moving. `satisfied` is the ONLY observation
  permitted to replace a budget — an `unobservable` result is a failure to
  MEASURE, so letting it advance makes a broken reader the cheapest route to a
  fresh deadline. The recovery operation needs TWO independent gates, the closed
  grammar AND equality with what the measured CAUSE authorizes, and the DERIVED
  operation is itself grammar-checked: the draft this replaced derived it from
  the pointer's own `ref` and treated equality as authorization, so a caller who
  authored the ref authorized itself (measured: `"I will try a different
  approach."` with a host cause and `diagnose-this-is-not-a-supported-operation`
  with an unknown cause were both ACCEPTED). These writers NEVER create a chain
  genesis — research note 007 — so an epic without one takes the legacy path and
  every reader reports `plan-progress-tracking: missing` naming
  `migrate-plan-records`. A chain that READS CLEANLY while tracking no
  obligation reports that same code with a DIFFERENT remedy, and the two must
  never collapse (`bd-ib-paevjd`, live instance `bd-ib-lrik25`): the migration
  creates only a genesis token, so naming it for an epic that already has one
  names a remedy whose re-run creates nothing and can never clear the finding —
  only an executable-kind pointer write carrying `required_result` and `budget`
  creates the obligation. So that arm names the OPEN TOKEN too, since "the chain
  is present" has to be checkable. And the DIAGNOSIS reads the obligation from the chain
  rather than parsing the pointer, which is the repair rather than a guard in
  front of the old dereferences: the handler it replaces cast an optional parse
  to a `NextAction` and reached through a `ResultReferenceRefusal` for an
  identity, crashing on an epic with no pointer and on a legacy one — the two
  states it most needed to answer for.
  AN EIGHTH PROPERTY, AND IT IS ABOUT THE ORDER OF `_plan_tracked_write`'S
  SEQUENCE (`bd-ib-b5npv2`). The OPERATION IDENTITY is recognised FIRST, through
  the chain's public `recover_committed_operation`, and only then is the
  obligation decided. `commit_transition` carries its own retry guard and keeps
  it — that guard is the chain's last word, and a caller cannot be allowed to
  satisfy it on the chain's behalf — but a write refused BEFORE it is reached
  never gets the recovery the clause owes: the decision's expiry ladder reads the
  OBSERVED head, so the retry of the handoff that consumed the final
  `max_handoffs` unit is read as an expired continuation and refused, although
  the write it retries succeeded. Nothing duplicated, and the caller was told to
  register a causal recovery for an obligation it had just met. Asking early
  costs one comment read and can change nothing, because that reading performs
  no write; the CONTROL is that a DIFFERENT operation identity at the same
  exhausted budget is still refused, which is what keeps the repair from being
  "stop grading expiry". A twin committing in the window between that scan and
  the chain's own is still answered as a recovery, by the chain's guard, which is
  why `_persist`'s idempotent arm stays reachable rather than becoming dead.
- The CARRIER GATE that stops a plan deriving a plan-level step while a carrier
  of one of its assertions is still open (`bd-ib-evrynu`), split
  pure-from-impure the usual way and reading bottom-up: `_plan_carrier_map`
  (PURE: the `carriers:` block, written AND read — `last_carrier_map_carriers`
  is the read half) → `_plan_carrier_tenancy` (which repository one carrier id
  names, from each configured tenant's own create-prefix) →
  `_plan_carrier_gate` (the first carrier that is not closed) →
  `_plan_resume_advance`, the one caller. `_plan_ready_child` is the ledger
  half of that advance, extracted so the carrier question and the child
  question sit beside each other rather than one inside the other's module.
  Six properties an editor must not invert. The gate sits BETWEEN the child
  check and the plan-level leg: a ready child is the next step whatever the
  carrier map says, and every plan-level leg asserts something about the WHOLE
  Definition of Done, so asking the gate first holds a plan's own child behind a
  sibling tenant's carrier and asking it afterwards asks it too late. The LATEST
  carrier-map event governs and the events are never unioned, because such an
  event RESTATES the whole map — a union makes a plan wait on work its own
  maintainer re-assigned. A `plan-level proof` entry is NOT a work-item carrier
  and is discharged by the plan's own proof record, so it is dropped at the
  parse rather than refused downstream. The status comes from the SHARED result
  reader and never from a local `bd` call, because every carrier of a real plan
  is cross-tenant and a local call answers, for an id this tenant never minted,
  that the carrier is not closed — a confident negative on the wrong
  population. Only a `satisfied` reading establishes closure, so an
  `unobservable` one is OPEN: the other way round makes an unreachable tenant
  the cheapest route to a proof record asserting work nobody could look at. And
  the carrier wait is the ONE derived step whose obligation names a repository
  other than the plan's own, because its target is a work-item in the carrier's
  tenant rather than the plan epic — the exception that proves `_carried`'s
  rule rather than an exception to it.
  THE GATE HAS TWO READINGS AND NOT ONE VERDICT, and they pull in OPPOSITE
  directions, so neither may be collapsed onto the other. `first_open_carrier`
  passes a carrier nothing can place OVER, so it cannot hide the open carrier
  behind it; `unplaceable_carrier_ids` then reports exactly those passed-over
  carriers, because a carrier whose status nobody measured must not read as
  closed. The advance's rest state for the second is a `human` pointer NAMING
  the carriers — configuring the sibling, re-assigning the assertion, or
  recording that the carrier is done are all decisions, and none is one an
  unattended resume may take — with explicit null tracking so the unmet
  obligation stays in the progress history rather than being discharged by
  pointing elsewhere.
- The EVIDENCED CAUSAL SUPERSESSION of `contracts.md` §"Required result, budget
  and progress epoch" (`bd-ib-evrynu`, Scenario 211), split pure-from-impure the
  usual way and reading bottom-up: `_plan_supersession` (PURE: the ratified
  closed cause set, what one write must NAME, the evidence values and the whole
  refusal ladder) → `_plan_supersession_evidence` (the three ledger readings the
  `misderived` cause's verification needs) → `_plan_progress_unmet`'s
  `superseded_decision`, reached from `_plan_progress_decision` and carried by
  `_plan_tracked_write` as one more field of a sanctioned write. It is the ONE
  write that may rename an unmet obligation, and the derivation gate above is
  what stops new obligations needing it.
  Six properties an editor must not invert. The REPLACEMENT inherits the
  superseded obligation's original deadline and consumed handoff count unchanged
  and consumes nothing, so the candidate's own budget is DISCARDED — a
  supersession that adopted it is the laundering route the cause exists to
  close, and the pointer it produced would be indistinguishable from a
  legitimately advanced one. The EXPIRY RULES STILL BIND: the clause says a
  supersession of an already expired obligation "remains subject to the expiry
  rules above", so it is not a second route past a deadline. The cause set is
  the RATIFIED three and what this build can VERIFY is one of them, so a cause
  whose evidence it takes no reading for is refused under the clause's own rule
  that a cause whose evidence does not verify must be refused — fail-closed in
  the only direction available, since all three were refused before. The
  REPLACEMENT must be the closure of the carrier the evidence names, because the
  evidence for this arm IS a carrier and a replacement free to name anything
  else makes it a verified footnote attached to an unrelated rename. A carrier
  CLOSED when the derivation was recorded and one closed SINCE are two refusals
  with two reasons — the first means the step could legitimately have been
  taken, the second that the replacement is already satisfied — and every
  UNDATABLE closure routes to the first, which is the arm that refuses. And the
  deriving match is an identity AND an epoch: an identity alone resolves a real
  transition of the same plan, recorded by a real derivation actor, that wrote
  an obligation the supersession is not about.
  `_plan_progress_outcome` and `_plan_progress_unmet` are the cohesion split
  that made room for it, and the direction is one-way: the outcome leaf imports
  nothing from the family, the unmet module owns every arm that DEFENDS a
  standing obligation (the rename refusal, the expiry gate, the typed causal
  recovery and the supersession), and `_plan_progress_decision` is left as the
  DISPATCH plus the arms that ESTABLISH a budget. `_plan_write_identity` is the
  pure retry-identity derivation, split off `_plan_tracked_write` for the same
  pure-from-impure reason. None of the four leaves a re-export shim; callers
  import from the module that owns the name.
- `_plan_resume_reconcile.py` — the reconciliation half of the resume, split out
  of `_plan_resume` by cohesion once the durable progress check pushed that file
  past its size ceiling. `_plan_resume` keeps the TOP-LEVEL sequence (the
  progress check, the missing-Definition-of-Done pre-emption, the pointer parse
  and the picker reasons); this owns what follows them, at ONE public entry
  point. The progress check's POSITION in that sequence is load-bearing: a plan
  that is both expired and missing its Definition of Done must report the
  expiry, and settling the dispatch question first answers with the gap pointer
  and never reads the obligation.
- `_plan_result_plan_owned.py` — the ONE entry point every plan-level obligation
  is read through (`read_plan_owned_result`), and the repository an obligation
  naming THE PLAN EPIC ITSELF is read against (`bd-ib-woacnk`). A plan-level leg
  targets the epic, the epic lives in the plan's own tenant whatever the record
  says, and an unobservable
  obligation withholds dispatch while being unreplaceable by design — so one
  stale `repo` field locks a plan for its whole budget. Three properties an
  editor must not invert. It owns THE WHOLE READ and not merely the redirect,
  because one plan-level obligation is read THREE times on the way through a
  single resume and the redirect alone is a rule each call site has to remember —
  each read was added for its own reason, and settling any subset of them leaves
  the plan stopped a different
  way: `evaluate_resume_progress` reads the CHAIN-held authority and
  `decide_plan_resume` returns on that verdict BEFORE the pointer is consulted,
  so a redirect living at the pointer read alone is unreachable for every
  chain-tracked plan — which is every plan the progress gate can lock, including
  the measured one; `result_observation` reads the recorded POINTER, which is
  what decides the satisfied step is stale; and
  `_plan_tracked_write._prior_observation` reads the chain-held authority AGAIN
  for the sanctioned write that persists the derived pointer, where the reading
  DECIDES rather than reports — an unobservable prior obligation cannot be
  replaced, so the derived step is refused and the resume answers with no
  further step at all, which under an unattended resume is a plan silently
  stopping rather than one diagnosably locked. Of the three steps a caller
  composing them itself would repeat — resolve this project's root, redirect,
  read — only the root announces its own absence, so a forgotten redirect
  returns a well-formed `unobservable` reading of another repository's tenant;
  reaching `read_result` directly from a plan-level caller is that defect
  returning. The discriminator is the
  obligation's own TARGET and never the pointer's kind: the chain records no
  kind, and a kind test buys nothing either way, since an `impl` leg's target is
  a CHILD and an id equal to the epic's resolves in exactly one tenant. And the
  rewrite persists NOTHING — it is read-time on all three paths, each of them
  observing rather than recording (the write's own reading is of the PRIOR
  obligation, which it grades), and the ordinary advance is what replaces a
  recorded pointer.
- `_drive_cli.py` — the `drive` CLI's operator transport, split out of `drive.py`
  on the same seam `_session_wait_cli` sits on for `session_wait` once routing
  the diagnosis executor pushed that file past its size ceiling. `drive.py` keeps
  the two things that DECIDE — the action router and the supervisor sequence —
  while this owns the conversion between an operator's shell and a typed call:
  the argv surface going in, the payload rendering and exit code coming back.
  The exit codes live here, with `exit_code_for_status` as the one place a result
  status is mapped to one, and `EXIT_PRECONDITION_ERROR` is PUBLIC because the
  supervisor returns it directly for the two faults it detects before any action
  runs — a `--repo` that does not exist and an unattributed state-changing
  invocation. Do NOT keep one code private by splitting the set across the two
  modules: that is how the surface comes to disagree with itself.
- The DURABLE LAUNCH OBLIGATION of `contracts.md`'s "Launch obligations and
  consumed recovery" clause (`bd-ib-zejlae`, Scenarios 160 and 161) — the record
  a dispatch or a delegation persists BEFORE it may report a protected launch.
  Seven cohesive modules, and the dependency direction reads bottom-up:
  `_session_obligation_coverage` (PURE: the three coverage grades and every
  refusal rung) and `_session_obligation_records` (the two writes — intent, then
  attachment — plus the census) → `_session_obligation_launch` (PURE ordering:
  the launch boundary and the turn-completion gate) and
  `_session_obligation_reconcile` (the crash repair, keyed on the stable
  operation id) → `_session_obligation_host` (the host's installed coverage
  declaration and the obligation store root) → `_session_obligation_delegation`
  (the ONE place the product puts a real target through both: a detached gate
  run, which is how work is DISPATCHED, and a Herdr pane, which is how it is
  DELEGATED) → `_session_obligation_cli` (the `session-wait launch` and
  `session-wait complete` host commands, routed from `_session_wait_cli`).
  Six properties an editor must not invert. The coverage DECLARATION is read off
  the host and can be put in no parameter, because the clause makes it "runtime
  evidence, not a user-selectable exemption" — an argument would be exactly the
  exemption it forbids. The obligation store sits BESIDE the session-wait store
  and the declaration sits beside BOTH: an obligation discoverable only through
  a wait row cannot cover the incident, which is a coordinator that armed no
  wait, and a declaration filed under the store root is censused as an
  unreadable obligation. `unmonitored` and `unobservable` are never collapsed —
  one is a confident negative about the host, the other a failure to measure,
  and the clause keeps them apart in both directions. The REFUSAL writes no
  record and performs no effect, so `effect.calls == []` is what proves it. The
  reconciliation's reader has exactly ONE verb and it reads, so "never auto-kill
  a live target to repair tracking" holds structurally rather than carefully.
  And the retry RECONCILES rather than re-registering: a second call under one
  operation id completes the original obligation's attachment, preserving its
  epoch, deadline and authority, instead of opening a second obligation for one
  piece of work. The canonical result identity, epoch and original deadline are
  the relay contract's and arrive AS GIVEN; nothing here computes, defaults or
  refreshes any of them, because that would be the second result model the same
  clause forbids.
- The CONSUMED RECOVERY of the same clause (`bd-ib-dle6l3`, Scenarios 162, 163
  and 164) — the orchestrator-side consumer API a supervised scheduler drives
  over ONE recovery attempt, plus the sanctioned-action bridge it executes
  through. The overseer repository owns the daemon, the schedule and the
  takeover; what lives here is one PASS and its result. Nine cohesive modules,
  dependency direction bottom-up: `_session_recovery_shape` (PURE: what a
  version-1 attempt record IS, and the three ways bytes fail to be one) and
  `_session_recovery_lease_reading` (PURE: the standing lease, or the fact that
  it cannot be read) → `_session_recovery_records` (the attempt, the closed
  transition vocabulary, and the two writes: open, then append-once) →
  `_session_recovery_consumption` (PURE: consumed only on execution evidence,
  and the latency that took) and `_session_recovery_lease` (the
  generation-fenced claim, takeover and fence accounting) and
  `_session_recovery_effect` (the execution receipt and the two seams a caller
  supplies) and `_session_recovery_safety` (PURE: the three real barriers and
  the four facts that only look like one) and `_session_recovery_action` (PURE:
  the typed action current ledger/forge/remote-factory evidence sanctions) →
  `_session_recovery_execution` (run the command at most once) →
  `_session_recovery_outcome` (what the pass reports) →
  `_session_recovery_consumer` (the ORDER of the pass: receipt, claim, safety,
  action, execution, reconciled next action).
  Seven properties an editor must not invert. The transition vocabulary is
  CLOSED and holds no word for fulfillment, so no surface here can discharge
  the relay-owned required result — the consumption grade reports the identity
  it leaves outstanding instead. CONSUMPTION is execution EVIDENCE and nothing
  else: a receipt and a claim leave recovery unconsumed, which is the whole of
  Scenario 162. A DUPLICATE converges on the first observation and is COUNTED
  rather than appended, and a displaced consumer's refused mutation is counted
  too, because `duplicate_count` and `fenced_count` are measurements the clause
  asks for and a silently dropped event reports a clean zero. A LAPSED HOLDER
  reclaiming gets a NEW generation, which is the one arm where a duplicate
  effect otherwise survives — a paused process is still inside its own command
  when its newer self reclaims. A `started` transition with NO effect IS the
  ambiguity, so it routes the next pass into the durable-effect LOOKUP and an
  unobservable lookup writes nothing and runs nothing; this family claims no
  exactly-once arbitrary shell execution and there is no shell string anywhere
  in it — the command is a protocol the caller supplies. The LOCAL GATE OUTCOME
  is carried and never consulted: the measured 2026-10-09 case had a gate
  reporting FAILED at 05:19:06Z for a pull request that merged at 05:18:03Z, so
  the forge rung precedes the ledger rung and a failed gate selects the same
  action a green one would. And a SAFETY DEFERRAL writes exactly one
  transition: the original deadline, the epoch and the required result are read
  BACK off the record and reported, which is how "retaining the original
  obligation/deadline history" is checkable from the outcome rather than from
  this family's care. The stable attempt id, the epoch, the original deadline
  and the executable-operation grammar are the relay contract's and arrive AS
  GIVEN — `sanctioned_operation` reaches the relay's own
  `is_executable_operation` and adds exactly ONE consumer-side form, the
  per-item `reconcile-merged`.
- The PROOF CARRY-FORWARD DECISION a changed-head `pr_refresh` takes
  (`contracts.md` §"Definition-of-Done and Proof-of-Done stages" → "Proof
  carry-forward across a refresh", "The observation scope" and "The decision";
  `bd-ib-v4exlm`, Scenario 178). FOUR modules, and the dependency direction
  reads bottom-up: `_dispatcher_carry_forward_grammar` owns the closed
  direct-read grammar and the two record lines the proof prompts write;
  `_dispatcher_carry_forward_record` owns the SANDBOX's one account of the
  Proof of Done record — the header and publish-head reader the publication-head
  program now composes too, plus the reproduction-step parse;
  `_dispatcher_carry_forward_decision` owns the condition ladder, the decision
  record's rendering and its posting; and `_dispatcher_carry_forward_program`
  assembles all four into the ONE stdlib-only program the Dispatcher
  materializes into the sandbox, beside the publication-head reader and for the
  same reason. The ASSEMBLY ORDER is load-bearing and is not alphabetical: each
  fragment uses names the earlier ones define, so a reordering raises
  `NameError` at import rather than deciding something wrong in a sandbox.
  `pr_refresh` records the four decision inputs — the previous head, the
  previous base, the new base and the new head — beside its changed marker, and
  `pr_refresh_head` is where the program is entered; its EXIT CODE is the
  decision, because that is all the engine gives a command node.
  Five properties an editor must not invert. The decision is taken ENTIRELY
  inside the sandbox, so these modules ship a PROGRAM FRAGMENT and no host-side
  implementation: a host-side twin would be a second account of one grammar
  with no caller, which is the duplication `_dispatcher_publication_head`
  records the cost of, and the paired tests therefore load the shipped bytes
  rather than re-deriving them. Every arm that cannot MEASURE answers
  `reproof_required` naming the input, because the decision's whole claim is
  that the incoming commits CANNOT have affected the proof, and a blinded gauge
  can make no such claim. The grammar's character test runs BEFORE its
  production test, since POSIX splitting has already discarded the
  metacharacters by the time words exist. And a REJECTED path operand is kept
  apart from a command OUTSIDE the grammar even though both route identically:
  the distinction buys the record, which must point its reader at the `..`
  segment rather than at the command's shape. And an UNREADABLE decision input
  still POSTS a record naming it, rather than failing closed in silence: the
  clause requires exactly one decision record on every changed-head refresh,
  and the condition hardest to reconstruct afterwards is exactly the one a
  silent refusal would leave no artifact for.

- The READ-ONLY SANDBOX-IMAGE ENUMERATION of `contracts.md`'s "Sandbox image
  enumeration" subsection (`bd-ib-nqmltq`, Scenario 212) — the answer to "which
  sandbox image would a dispatch to this factory pull RIGHT NOW", which the
  host's image-warm timer needs before the first run that needs the tag. FOUR
  cohesive modules, and the dependency direction reads bottom-up:
  `_dispatcher_plugin_install_registry` (the ONE read of
  `~/.claude/plugins/installed_plugins.json`: which repositories this plugin is
  registered for, and at which build) and `_dispatcher_sandbox_images` (ONE
  repository's ordered entries) -> `_dispatcher_sandbox_image_builds` (which
  builds are executing host-wide) -> `_dispatcher_sandbox_images_command` (the
  scope, the one JSON array and the exit code).
  Six properties an editor must not invert. EVERY ENTRY IS DECIDED BY THE
  FUNCTIONS A DISPATCH CALLS -- `has_fabro_factory`, `resolve_fabro_factory`
  plus `factory_environment_id`, `resolve_fabro_sandbox_image`,
  `sandbox_image_source` and `workflow_toml` -- never by a copy of their
  ladders, because the whole point of the enumeration is that the warm timer
  and a real dispatch cannot disagree about the tag, and a second derivation
  produces a well-formed answer on each side with nothing announcing the
  divergence. The dispatch journal could not answer this: on the
  `committed_run_config` arm it writes `sandbox_image` null, deliberately.
  The COMMITTED-versus-BUNDLED choice is read off `workflow_toml`'s own answer
  -- asked once per build, with the new `payload_root` keyword, and tested for
  whether the path it returned sits under that build -- rather than re-decided,
  which is what makes a target-local copy yield exactly ONE entry however many
  builds execute. An UNREADABLE source moves the EXIT CODE and nothing else:
  stopping at the first one would report a partial enumeration as a complete
  one, and reporting every entry at exit zero would hand the warm timer a tag
  list with a silent hole in it; a run config that was READ and declares no pin
  is image-less rather than unreadable, which is why `_WorkflowUnreadable` is
  its own type and not a None. LEASE LIVENESS is the existence of the recorded
  pid's `/proc` entry and never a comparison against the start time the lease
  also records -- that file's encoding is Claude Code's, not a contract this
  read may assume -- and the weaker reading errs in the harmless direction,
  since a recycled pid can only warm one extra tag. The EXECUTING-BUILD set is
  keyed on a running Dispatcher's own ARGV rather than on
  `LIVESPEC_RETAINED_PAYLOAD_ROOT`, because the launcher exports that variable
  only when it has copied a release aside, so an environ scan reports a host
  with no running Dispatcher while several are executing. And the command
  CHANGES NOTHING, which holds structurally rather than carefully: `rglob`,
  `iterdir`, `read_bytes` and `read_text` are the whole host surface, and
  nothing in the four modules reaches the ledger, the dispatch journal or a
  factory.

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
