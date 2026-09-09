# tests/integration/

Integration-tier behavior journeys for the `livespec_orchestrator_beads_fabro` package —
tests that exercise a primitive through its REAL store/client seam against the
in-memory `FakeBeadsClient` (the hermetic CI backend and the
no-live-connection runtime fallback), rather than mocking the function under
test. This is the tier `SPECIFICATION/constraints.md` §"Heading taxonomy"
requires for a `scenarios.md` heading binding (integration-tier-or-above, never
a unit-tier test); its dotted node-id prefix `tests.integration` is in the
`heading_coverage` check's default allowlist.

- `test_regroom_state_machine_scenario9.py` — binds
  `SPECIFICATION/scenarios.md` "Scenario 9 — needs-regroom state and
  transitions": the three transitions of the `livespec_orchestrator_beads_fabro.regroom`
  state machine (enter on an intake Definition-of-Ready failure, enter on a
  Dispatcher non-convergence bounce, exit by filing `ready` replacement
  slices), plus the refuse-don't-drop guarantee and the expected-error
  surface. Each case owns its backend isolation via a local
  `reset_fake_singleton()` fixture; there is no shared conftest at this tier.
- `test_dispatcher_acceptance_needs_attention.py` — the ratified evidence rule
  of `SPECIFICATION/contracts.md` §"Post-merge acceptance (`acceptance -> done`)"
  and §"The NEEDS_ATTENTION verdict": an unobservable telemetry leg with a
  readable merged diff, and effective criteria that parse to zero gradeable
  assertions, each park the item in `acceptance` under the AI-dispositive
  `ai-only` policy instead of disposing of it. Only `run_dispatch` and the
  acceptance pass's `CommandRunner` are stood in; the verdict function, the
  disposition, and the ledger writes are production code.
- `test_reconcile_runs_ledger_gate_scenarios.py` — binds
  `SPECIFICATION/scenarios.md` Scenarios 104, 105 and 106: the run-inventory
  reconciler driven end to end through `reconcile_runs`, over work-items
  seeded and closed through the REAL store seam, a REAL preserve-by-reference
  ledger comment, and a real on-disk `JournalFile`. Only the two seams that
  leave the process — the `fabro` CLI and the factory's HTTP face — are stood
  in; the HTTP stand-in snapshots the item's ledger comments at each call, so
  the export-before-terminate ordering is OBSERVED rather than inferred from
  the end state.

- `test_ready_aging_tiebreak_scenario123.py` — binds
  `SPECIFICATION/scenarios.md` "Scenario 123 — The ready ordering breaks
  equal-rank ties by ready-age past the bound". All four of the heading's
  gherkin scenarios are asserted over ONE ordering of ONE tenant, because they
  are four properties of a single sort key and splitting them would let each
  pass against a key the others reject. The tenant is seeded through the REAL
  store seam, so every `ready_since` is the durable instant the store itself
  stamps on a transition into `ready` rather than a value poked into the
  ordering; and both ranked surfaces run as production entry points that
  resolve their own aging inputs — `next.main` and the Dispatcher's
  `ready_items` — so "the two agree" is an observation, not a consequence of
  the test handing both the same argument. Every id is chosen so the expected
  order DIFFERS from what the pre-aging `(rank, id)` key produced: the aged
  item of each pair carries the lexicographically later id, the below-bound
  pair's older member carries the later id, the unknowable-instant item carries
  an earlier id than its aged sibling, and the highest-`rank` item is the
  newest row in the tenant.

- `test_governed_repo_seams_scenario102.py` and
  `test_sandbox_exempt_hook_honor_scenario108.py` — bind
  `SPECIFICATION/scenarios.md` Scenarios 102 and 108 and the
  adopter-and-member-fixtures bullet of `SPECIFICATION/constraints.md`
  §"Governed-repository integration constraints". Every dispatch-path seam
  (preflight, contract resolution, plan build, input rendering, workflow
  validation, and the sandbox prepare parameters with the sandbox stubbed) runs
  through PRODUCTION code parametrized over the two committed
  governed-repository fixtures under `fixtures/governed_repos/`: a fleet member
  carrying the fleet toolchain and declaring no optional integration key, and an
  ADOPTER declaring every point through the contract schema while carrying none
  of this fleet's tooling. `governed_repo_fixtures.py` holds what the two
  fixtures are and what each seam owes each of them, so one parametrized test
  body asserts the SHAPE for both legs instead of branching on a fixture's name.
  The second module runs each fixture's commit-blocking hook in a sandbox-shaped
  checkout against the marker key the contract resolved, with a
  refuses-without-the-marker control and a deliberately non-honoring adopter
  variant that must fail.

- `test_seam_equivalence_contract_inputs_scenario100.py`,
  `test_schema_validation_refusal_scenario101.py` and
  `test_merge_mode_projection_scenario107.py` — bind
  `SPECIFICATION/scenarios.md` Scenarios 100, 101 and 107, each over BOTH
  governed-repository fixtures. The first loads the shipped
  `check-seam-equivalence` gate by path and runs it over throwaway repositories
  holding the REAL committed payload beside a fixture's declaration, one seeded
  per ratified disagreement (a token with no rendered input, a rendered input no
  position reads, a token where the pinned engine does not expand it), with the
  unseeded repository as the positive control that the gate can report clean.
  The second drives the REAL `dispatcher.main(argv=["dispatch", ...])` CLI over a
  fixture declaration carrying two unusable points and asserts the pre-dispatch
  precondition exit code, one message enumerating both committed keys, and a
  journal holding that refusal and nothing else; its control is the same
  invocation on the pristine declaration, discriminated by journal STAGE because
  every pre-dispatch precondition error shares one exit code. The third rewrites
  `dispatcher.merge_mode` inside each fixture's own declaration to reach all
  three resolver arms and reads each answer back off the auto-merge argv the
  dispatch would spawn. All three inject their variations into the COMMITTED
  fixture declarations rather than hand-writing a third repository, so the two
  legs stay the member's fleet-default posture and the adopter's fully-declared
  one.

- `test_declared_integration_points_scenario96.py`,
  `test_integration_validation_pass_scenario97.py` and
  `test_janitor_venue_merged_tip_scenario98.py` — bind
  `SPECIFICATION/scenarios.md` Scenarios 96, 97 and 98, each over BOTH
  governed-repository fixtures. The first walks the schema's own closed field
  set through the ONE generic resolver, asserting per point that a committed
  declaration resolves `Declared` carrying its value verbatim, that a truly
  absent key resolves `FleetDefault` where the schema declares one and
  `Defective` where none exists, and that a present-but-null key is `Defective`
  rather than a slide onto the convention; a sibling case asserts a committed
  check-suite outranks the per-invocation `--janitor` override, with the
  inheriting leg as the control that the override is reachable at all. The
  second drives the pre-dispatch validation pass's two-sided verdict — the
  committed declaration admitted unchanged, two unmet points refused once with
  both enumerated — and models a plugin upgrade by appending a field to the
  closed set, so an earlier repository's ABSENCE stays ungraded (nothing
  mid-pipeline is stranded) while a written-but-unusable point refuses fast. The
  third builds a REAL repository whose item merged before a later
  janitor-environment fix landed, resolves the venue and provisions there
  through production code, and controls the claim by provisioning the same
  repository at the retired historical merge sha, which cannot carry the fix;
  its sibling case asserts a tip that does not contain the merge degrades with
  the missing point and remedy, running the merge-presence check and nothing
  else.

- `test_context_envelope_scenario114.py` — binds
  `SPECIFICATION/scenarios.md` "Scenario 114 — The `context` read primitive
  assembles a deterministic item-context envelope" and the contract it
  realizes, `SPECIFICATION/contracts.md` §"`context`". The whole primitive
  runs as production code — argv parse, connection resolution, tenant read,
  child union, on-disk anchor read, JSON emission — against the REAL
  store/client seam over a tenant built through the client's public write
  verbs; nothing is stood in. The fixture defeats the two readings that would
  look right and be wrong: it carries a dotted-id child AND an edge-linked
  one, because either enumeration alone returns a plausible non-empty list
  while dropping the other linkage, and its epic's dependency array carries a
  `parent-child` edge beside a `blocks` edge, because a blocks-only
  projection would report the epic as unparented. The four cases are the
  every-field-populated epic envelope, the child-id shape parity, the
  byte-identical re-run with the store unmodified, and the not-found refusal
  that names the missing key.

- `test_discuss_work_item_scenario115.py` — binds
  `SPECIFICATION/scenarios.md` "Scenario 115 — `discuss-work-item` stands by
  over the context envelope and resumes without chat history" and the contract
  it realizes, `SPECIFICATION/contracts.md` §"`discuss-work-item`". The
  operation is a HEAVYWEIGHT AUTHORED skill — shared prose plus thin
  per-runtime bindings, no CLI wrapper — so the module keeps the behavior and
  artifact halves apart deliberately: the context assembly and the
  envelope-alone resume run the shipped `context` CLI over a fixture tenant
  built through the client's public write verbs, the maintainer ruling goes
  through the REAL `record_scope_event` and is READ BACK through
  `read_timeline`, and only the stand-by gate and the registered name are
  asserted against the shipped prose and bindings. Two traps are worth
  carrying forward. `plan` remains a live sibling operation, so "a skill named
  plan exists" is true and carries no information — the discriminator is that
  each runtime's discuss binding declares the discuss name and reads the
  discuss prose while the `plan` bindings still declare `plan` and read
  `plan.md`. And the prose is hard-wrapped, so `_prose()` collapses every
  whitespace run before matching: a needle straddling a line break otherwise
  fails while the prose says exactly the thing, which is a probe that can only
  fail silently.

- `test_plan_next_action_resume_scenario111.py` — binds
  `SPECIFICATION/scenarios.md` "Scenario 111 — Typed `next_action` drives an
  unattended resume and cannot be truncated by wrapping". The plan is created
  through `create_thread`, its pointer written through `append_handoff` (which
  updates the typed metadata in the same call that appends the entry) and
  `set_next_action`, and the unattended marker read off the real process
  environment through `is_unattended_session`; nothing is stood in. Two
  controls carry the module. The wrapped case asserts the prose marker IS
  still present and IS still readable — `recorded_next_actions` returns the
  truncated fragment — BEFORE asserting the directive took the typed route
  anyway, because otherwise "the resume took the typed action" passes just as
  well against a handoff carrying no marker line at all. And the attended case
  is the same epic with the same dispatchable pointer asking when the marker
  is absent, so a passing unattended case cannot be a directive that never
  asks.

- `test_migrate_plan_records_scenario112.py` — binds
  `SPECIFICATION/scenarios.md` "Scenario 112 — The one-shot anchor migration is
  complete and idempotent". The shipped `migrate-plan-records` entry point is
  invoked twice exactly as an operator invokes it, argv and all, over a tenant
  built through the client's public write verbs and a `tmp_path` repository
  holding live and archived plan directories. The fixture carries every shape
  the contract distinguishes — an already-slugged epic, one whose `plan:<slug>`
  hint supplies a slug, one whose title collides with a slug another epic holds
  (refused, never renamed), a closed epic under `plan/archive/`, a live
  directory no epic claims (anchored `unassigned`), a legacy handoff naming a
  work-item and an epic with no handoff — because a migration handling only the
  easy shape still reports a plausible non-empty run. Idempotence is asserted
  on three instruments rather than one: the zero write count says the second
  run DECIDED nothing, the anchor bytes say the filesystem was not rewritten,
  and the full record dump says no ledger row moved, including the
  `last_session` a re-seed would restamp while every other field stayed
  identical. The refusal recurring on the second run is deliberate — a refusal
  is a result, not a write.

- `test_plan_record_conformance_scenarios109_110_113.py` — binds
  `SPECIFICATION/scenarios.md` Scenarios 109, 110 and 113. The check lives in
  the fleet's shared checks package beside `plan_epic_parity` (the ratified home
  the contract names), so this repository's leg is the CONSUMER leg: `just
  check` wires `check-plan-record-conformance` beside `check-plan-epic-parity`
  under the same armed-only lever, and these cases drive the module that recipe
  runs over a fixture tenant — the arming gate, the tenant prefix read off the
  repository's own `.livespec.jsonc`, the ledger read through the shipped
  export path, every verdict, and the delegated lifecycle leg, all production
  code. Only the comment reader is injected, through the seam the module ships
  for it, because comments have no on-disk export shape and the alternative is
  the `bd` subprocess this tier does not spawn. Every case carries a control the
  check must leave alone — a correctly slugged and anchored epic, and a closed
  plan epic whose timeline holds real completeness-review evidence — because a
  check that reported everything would satisfy the offender assertion just as
  well. The arming gate is asserted in BOTH directions in one case, on the same
  fixture, since an unarmed run reporting nothing is otherwise
  indistinguishable from a fixture that produces nothing; and the delegated
  `plan_lifecycle_parity` leg is asserted to name its own lever and its verdict,
  since a half-armed family would otherwise read as a clean one.

- `test_named_workflow_variants.py` — binds the `SPECIFICATION/scenarios.md`
  named-workflow-variants scenario and the contract it realizes,
  `SPECIFICATION/contracts.md` §"Named workflow variants" plus the resolution
  order of §"Target-local workflow". Every case drives the real
  `dispatcher.main(argv=["dispatch", ...])` CLI over a real on-disk journal and
  the real store/client seam; only `run_dispatch` is stood in, so the registry
  parse, the ledger pin and the three refusals are production code. Each
  precedence case reads BOTH halves of the answer off the dispatch record — the
  selected `workflow_name` and the resolved `workflow_toml` — because neither is
  recoverable from the other, so asserting one alone would pass for a dispatch
  that reached the right directory under the wrong name. The
  default-versus-reserved case carries a control that drops the one
  `dispatcher.default_workflow` key, since "the dispatch resolved `slow`" is
  evidence the default outranks the reserved name only if the reserved name is
  what the same target resolves without it. The refusal cases key on the journal
  STAGE rather than the exit code, which all three faults share, and assert
  no-run on two independent instruments: the launch seam was never entered, and
  no `dispatch-id` record was written.

- `test_groom_variant_criteria_wall.py` — the variant-aware pre-dispatch
  acceptance-criteria wall, where `SPECIFICATION/contracts.md` §"Effective
  acceptance criteria" meets §"Consensus-gated automated groom cut": the wall
  refuses an AI-dispositive item with zero gradeable assertions, and a groom
  target has zero by construction because the groom run's own output is the
  draft that produces them. Every case drives the real
  `dispatcher.main(argv=[...])` CLI with only `run_dispatch` stood in, over ONE
  fixture repository registering both a groom-kind and an implement-kind
  variant; the legs differ only in the item's `dispatch_workflow` pin, written
  through the production writer. The pairing is load-bearing: the exempted leg
  alone would be satisfied just as well by a wall that had been disarmed
  altogether, so the implement-pinned control asserts the refusal still fires
  with the dedicated exit code (compared against the precondition code too,
  since a dedicated code is only useful if it is DISTINCT). The launch is read
  off the recording stand-in rather than the exit code, because a dispatch can
  exit 0 without creating a run and the wall's whole claim is about what happens
  before one exists. The implement leg declares no kind at all rather than
  declaring `implement`, because an undeclared kind is the shape of every
  variant registered before that key existed — the one the exemption must not
  open on. A fourth case runs the same groom-pinned item through `loop`, since
  the two dispatch paths reach the wall through separate call sites.

- `test_needs_attention_idle_factory_scenario120.py` — binds
  `SPECIFICATION/scenarios.md` "Scenario 120 — An idle factory with
  dispatchable work surfaces its first dispatch" and the contract it realizes,
  `SPECIFICATION/contracts.md` §"Orchestrator-owned attention facts" →
  "Idle-factory". The fact is composed through the real `build_attention` pass
  over the real store/client seam; nothing but the spec lane is stood in.
  Driving the whole snapshot is what makes the positive case mean anything: the
  scenario claims exactly ONE fact appears and that its handoff is one `drive`
  accepts, and a lane called in isolation could show neither. The three clearing
  cases each remove exactly ONE trigger condition from the SAME otherwise-idle
  fixture — a counted claim, an unexpired provider-exhaustion record, an empty
  admission-eligible set — because "the fact appeared" is otherwise
  indistinguishable from "the fact always appears". The positive case also
  asserts the mirror capacity fact is absent and that the journal is unchanged,
  since the fact's counted-claim read is the side-effect-free half of an
  accounting pair whose sibling writes as it reads.

- `test_credential_reprobe_scenario121.py` — binds
  `SPECIFICATION/scenarios.md` "Scenario 121 — A refused credential probe
  re-probes on a cadence instead of exiting, and no clock gates it" and the two
  clauses it realizes in `SPECIFICATION/contracts.md` §"Provider spend
  containment". The whole `loop` invocation is production code — the real
  `dispatcher.main(argv=["loop", ...])` CLI, the real store/client seam, a real
  on-disk journal, the real `.livespec.jsonc` cadence read and the real
  `time.sleep` — with only the two seams that leave the process stood in: the
  bounded Messages API probe and the factory launch. Driving the whole
  invocation is what makes the positive case mean anything, because "resumes
  WITHOUT HAVING EXITED" is a property of what the invocation does AFTER the
  wait returns; the run is therefore read off the recording launch stand-in
  rather than off an exit code, which a loop that admitted nothing would also
  produce. The control is a `revoked` credential through the same fixture and
  the same invocation: without it, the positive case is equally consistent with
  a gate that waits on EVERY refusal and so hangs a rotated-out token forever,
  and the discriminator is the journal, since the two legs differ in nothing
  else. The exhaustion-record case reads BOTH the re-probe stage and the
  provider-exhaustion refusal stage, because an empty launch list alone cannot
  separate "the record still governs" from "nothing happened at all". The
  fixture commits a one-second cadence and the wait sleeps for real, so elapsed
  time is evidence the committed dial was read — a stubbed sleep would prove
  only that some number reached some stand-in.

- `test_ledger_adoption_rank_scenario126.py` — binds
  `SPECIFICATION/scenarios.md` "Scenario 126 — Ledger normalization adopts a
  beads-native `open` row and assigns it a real rank" and the
  `SPECIFICATION/contracts.md` §"Work-item beads-issue mapping" adoption
  clause it realizes. All FIVE of the heading's gherkin scenarios are asserted
  over ONE seeded tenant run through ALL FOUR cadences, each a real
  `dispatcher.main(argv=[...])` invocation over the real store/client seam:
  the fifth scenario's "every cadence adopts the same row identically" is only
  meaningful if the other four are graded against what each cadence produced.
  The three adoptable rows are seeded through the client's own `create_issue`,
  which lands beads `open` with exactly the metadata handed to it, so "carries
  no real rank" is the absence the adapter really reports rather than a
  sentinel the test poked in. Every assertion carries a control the adoption
  must leave alone — a live already-ranked anchor, an adopted row that is
  ALREADY ranked, a parked `deferred` row that must stay unranked, and a
  `done` row whose key sorts after every live one, which is the discriminator
  for "bottom of the LIVE order": were `done` part of the bottom, every
  assigned key would land after it and the run would still look successful.
  The single-dispatch leg names an id the tenant does not hold, so it refuses
  at target selection — AFTER normalization — and launches nothing.

Coverage rules: 100% line + branch on every covered module, as everywhere in
this repo. Build state through the public store/client seam (or a small
read-only stub for shapes the fake's public surface never produces); never read
or write a live tenant DB.
