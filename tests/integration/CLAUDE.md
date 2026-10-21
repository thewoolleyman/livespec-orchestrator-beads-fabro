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
- `test_acceptance_parking_record_scenario138.py` — binds the ACCEPTANCE half of
  `SPECIFICATION/scenarios.md` "Scenario 138": the parking-verdict ledger comment
  and its one-per-distinct-(verdict, pending-leg set) idempotence, the honest
  non-green dispatch result (`stage: acceptance`, the verdict, and
  `status: needs-attention` with exit 1 for a cannot-judge park), `stage: done`
  reserved for an item the pass closed, the reconcile-merged re-accept arm with
  its pointer repair, and the missing-pointer `needs-attention` fact. Drives three
  REAL entry points — `dispatcher.main(argv=["dispatch", ...])`,
  `dispatcher.main(argv=["reconcile-merged", ...])` and
  `needs_attention.main(argv=[...])` — against the in-memory tenant; only
  `run_dispatch`, each surface's `CommandRunner`, and the spec-side `spec_next`
  read are stood in. The comment is asserted LINE BY LINE rather than by
  containment, because a body that merely mentioned the verdict would satisfy an
  `in` check while naming neither the leg that failed to observe what nor the
  action that would move the item — and those are the two things the clause
  requires of it. The comments are read back through the store's
  `bd comments --json` seam and indexed on `text`: `bd show --json` carries no
  bodies at all, so verifying the write through it reports every successful append
  as lost. The dispatch id is pinned at its ONE source
  (`_dispatcher_self_update.run_id`, which the pre-run claim mints) rather than at
  `dispatch_one`'s re-export, because the proof leg's own reason names every
  identifier it would accept and an unpinned one makes the comment unassertable.
  Two sequences are deliberately ONE case each rather than split: the
  reconcile-merged journey, because "no second comment" proves idempotence only
  beside a run that DOES append and "the pointer was written" proves repair only
  beside the park that had none; and the missing-pointer journey, whose three
  controls (a `captured`-only pull request, a sibling already carrying a pointer,
  and the fact clearing after the repair) each disqualify a cheaper lane that
  would satisfy the positive case alone.
- `test_proof_record_dispatch_id_attribution.py` — the proof-evidence leg's
  run-identifier attribution (`SPECIFICATION/contracts.md` §"Post-merge
  acceptance (`acceptance -> done`)" → "The proof evidence leg", v115) read
  against the VERBATIM comment payload of PR #2538, committed at
  `fixtures/proof_records/pull-request-2538-comments.json` in the
  `gh pr view --json comments` shape the pass itself issues. The real payload is
  what makes the case worth anything: every synthetic fixture stamped its record
  with whatever identifier it also fed the pass, which is exactly why a reader
  asking only for the Fabro run id looked correct while no real record has ever
  carried one. The control is the measured FAILURE — the same bytes with the
  dispatch id withheld, which is all the pre-repair build could see — so "the
  record graded" is evidence of the repair rather than of a reader that would
  always have graded it. A third case asserts the fixture is the forge shape,
  reading the argv off the seam, since every other claim rides on the payload
  being what the production read returns. The module also recorded, as an
  assertion rather than as prose, that PR #2538's fourth assertion stayed
  unevidenced once correctly attributed, because the body splitter opened a new
  section at the `# just.log:` lines inside its fenced code block — a section
  SEGMENTATION defect, not an attribution one. That defect is repaired, so the
  assertion now reads all four passing; the segmentation claim itself lives in
  the module below.
- `test_proof_record_fenced_section_segmentation.py` — the body splitter's
  fence-awareness (`SPECIFICATION/contracts.md` §"Post-merge acceptance
  (`acceptance -> done`)" → "The proof evidence leg"), read by the real
  proof-evidence leg against BOTH of this repository's committed payloads, PR
  #2561 and PR #2538. Real payloads are the whole point: a hand-written record
  body carries no fenced proof, and the hazard arrives only when a proof PRINTS
  something — shell comments, Python comments, the printed headings of a
  Markdown file — which is what every real proof does. Pre-repair, PR #2561's
  verified record graded `[None, None, True, True]` and PR #2538's graded
  `[True, True, True, None]`, so five of eight assertions across two correctly
  attributed, correctly published records read as unobserved and both items
  parked on NEEDS_ATTENTION. Three controls carry the module, because "all four
  passed" has three independent ways to be vacuous: a fabricated fifth assertion
  rides in the SAME criteria and must stay unevidenced, so a reader answering
  `True` for everything cannot pass; each record's surplus of heading-like lines
  over its four assertion headings is counted off the committed bytes, since a
  payload with no fenced hash line would have graded identically before the
  repair; and PR #2561's live `not_reproduced` record — whose first assertion
  says `Reproduced: NO.` while its other three say yes — is graded in the same
  breath, so a reader that had stopped reading the load-bearing line is excluded
  too. A fourth case asserts both fixtures are the forge shape and a fifth reads
  the production argv off the seam.
- `test_reconcile_merged_acceptance_pointer.py` — the reconcile-merged arm for an
  item RESTING IN ACCEPTANCE (`SPECIFICATION/contracts.md`'s reconcile-merged
  clause, v115): re-run only the acceptance pass against the records now on the
  pull request, apply the ordinary disposition, and write the missing Proof of
  Done pointer. The real `dispatcher.main(argv=["reconcile-merged", ...])`
  supervisor runs over the real store/client seam and a real on-disk journal, and
  resolves the merging dispatch's identifiers out of that journal; only the two
  seams that leave the process are stood in — the valve's shell runner and the
  acceptance pass's. The clause's FIRST requirement is a negative one, so it is
  read off the seam rather than off an exit code: the valve's runner is handed
  exactly the two commands this arm may issue and its full call list is asserted,
  since a janitor that ran and passed would exit 0 too. The pointer is checked
  against a BYTE-IDENTICAL Definition of Done prefix rather than by containment,
  which a build that rewrote the section while appending would also satisfy. The
  control is a verified record belonging to another dispatch of the same item,
  listing the assertion as reproduced: without it, "the pointer was written" is
  equally consistent with a valve citing whatever record the pull request carries.
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

- `test_workflow_dod_gate_scenario131.py` — binds `SPECIFICATION/scenarios.md`
  "Scenario 131 — The Definition of Done gate admits a coherent item, refuses a
  malformed one host-side, and rests an incoherent one at needs-human" and the
  `SPECIFICATION/contracts.md` clauses it realizes (ratified v114): the reserved
  workflow's `dod_gate` node and its position, its own adapter input and
  built-in default, its worst-case timeout budget, its routing, and the
  registered variant's declare-but-do-not-reach parity. The graph and run config
  are read as committed bytes, and every derived claim goes through the
  PRODUCTION derivation rather than a restated literal — the timeout budget is
  read off `derive_fabro_timeout_seconds` (a node absent from that derivation is
  budgeted at ZERO, so asserting the visit table directly would pass for a
  budget the Dispatcher never applies), and admission-requiredness is read off
  the dominator derivation, which is also what proves the widened graph is a
  shape that derivation still understands rather than one it refuses. The
  adapter default is compared to the review input's own line instead of to a
  model name written here, because a default pinned by copying a literal drifts
  silently the moment the review pin moves. The needs-human rest state and the
  prompt's verification duties are bound in the sibling cases of the same
  module; the `fabro validate` leg belongs to `check-fabro-graph-validity`,
  which reads this same payload.

- `test_implement_amendment_scenario131.py` — binds the FIFTH gherkin scenario
  of that same heading, the one whose subject is the stage AFTER the gate: an
  implement node that determines the Definition of Done is wrong ends through
  the structured needs-human ending carrying the proposed amendment, the item
  rests at `blocked / needs-human` with that amendment as the recorded
  question, and no code differing from the section is published. It realizes
  the kept-current clause of `SPECIFICATION/contracts.md` §"Effective
  acceptance criteria" (v114), which requires ONE rest state for a wrong
  Definition of Done whichever stage notices it and says in as many words that
  the implement prompt must state the rule. The journey is ONE case rather than
  four because each of its four mechanisms already worked before the slice — the
  claim under test is that they COMPOSE, and split apart every one of them
  passes against a build that drops the amendment somewhere between the run and
  the valve, since no case would carry the same string through two layers. Only
  the `fabro` CLI is stood in, at the runner seam the port publishes; the
  committed graph, the terminal mapper, the question reader, the valve summary
  and the blocked ledger write are production code over the real store seam. The
  publication half is asserted as REACHABILITY from the terminal (empty) with
  the real publishing route from the implement node's other successor as its
  control, because an absent `implement -> pr` edge would equally satisfy a
  graph that reached `pr` through `implementation_diff`, and because an empty
  reachable set alone is indistinguishable from a misspelt node name. The
  prompt's own duties are a sibling case, whose needles are chosen so each can
  only be present if the prompt carries that duty — the structured-ending needle
  is deliberately not the bare failed-outcome shape, which the generic
  needs-human protocol already carries.

- `test_proof_chain_end_to_end_scenario132.py` — binds
  `SPECIFICATION/scenarios.md` "Scenario 132 — A factory-captured proof is
  captured on a draft pull request, reviewed, replayed and published" as ONE
  journey, and carries the heading's registry row. The COMMITTED graph is
  DRIVEN rather than read: the drive takes the graph off the dispatch plan's own
  materialized run config — the file this dispatch would have handed Fabro — and
  follows that file's edges and edge CONDITIONS from `start` to its `Msquare`
  terminal, so no node order is written down in the module. Every other layer is
  production code over the real store/client seam: `dispatcher.main(argv=
  ["dispatch", ...])`, the plan build, `run_acceptance_pass`, the proof-evidence
  leg, the disposition, the pointer write and every ledger write. Two seams are
  stood in — `run_dispatch`, replaced by the drive itself, and the acceptance
  pass's `CommandRunner`, which IS the hermetic forge double, so the pull request
  the driven nodes published onto is the pull request the pass reads. That single
  seam is the whole point of the module: every host-side case before it fed the
  pass a record the TEST wrote, so "the pass graded the record the run published"
  was true by construction and could not have failed. Both record bodies are read
  VERBATIM from `fixtures/proof_records/pull-request-2538-comments.json`, the
  committed payload of the first `factory_captured` dispatch that ever ran this
  chain live, and the item's Definition of Done is BUILT from that record's own
  assertion headings with the run id read off its own header — nothing is
  transcribed, because a synthetic record stamped with whatever identifier the
  test also fed the pass is exactly how a reader that could never match a real
  record looked correct for weeks. The journey walks ONE reviewer-requested fix
  round, which is not decoration: `publish_draft`'s idempotence and the
  append-only rule are both claims about a SECOND entry, and the round drives the
  reviewer's own disposition loop out of the committed graph rather than around
  it. The pointer reaches the captured record through the pull request and run it
  NAMES rather than by a second link, because the pointer clause fixes the
  section's contents as a closed set and forbids copying proof content; the reach
  is asserted by resolving that pair against the forge, with a pull request the
  forge does not hold as the control that the resolution can return the other
  answer. The merged diff's vocabulary overlap with every assertion is COMPUTED
  and asserted empty over a deliberate SUPERSET of the production matcher's terms
  (no stop-word subtraction), since a superset finding nothing is the
  conservative direction and a diff carrying an assertion's words would make a
  PASS ambiguous about which evidence leg produced it. Four siblings carry what
  one journey cannot. Every condition the committed graph declares is driven
  through the evaluator under every state the workflow's nodes can report, with
  the condition set cross-checked against an independent scan of the committed
  text, because the journey short-circuits past most of those clauses and both
  answers must occur. The append-only instrument is shown to REPORT a rewritten
  record through the forge's one forbidden verb, because an instrument that has
  never failed is not known to be able to. One extra assertion the records never
  name must stay unevidenced and park while the four real ones still grade off
  the verified record, which is the control against a proof leg that answers
  `True` for everything. And the drive is asserted to REFUSE a context term
  outside its closed vocabulary, an unresolved workflow input, an operator it
  does not evaluate, an all-conditional node with nothing matching (the
  `all_conditional_edges` shape the pinned engine rejects outright) and a graph
  with no terminal — a walker that guessed would report a green journey through a
  route the graph does not describe. The heading's other gherkin scenarios stay
  bound in the four modules this journey composes rather than replaces:
  `test_workflow_proof_capture_scenario132`,
  `test_workflow_proof_verify_scenario132`,
  `test_proof_of_done_acceptance_scenarios132_133` and
  `test_needs_attention_proof_facts`.

- `test_proof_credential_projection_scenario134.py` — binds
  `SPECIFICATION/scenarios.md` "Scenario 134 — A declared proof credential is
  projected by name and a withheld, absent, credential-shaped or over-scoped
  declaration is refused" and the `SPECIFICATION/contracts.md` section it
  realizes, "Proof credential projection". The projection is read out of the
  overlay FILE the production `materialize_overlay` writes, in the same
  `[environments.<id>.env]` table as the dispatch credential set, which is the
  section's own same-channel requirement — a builder asserted in isolation would
  pass just as well while nothing threaded it into the overlay. Its control is
  the identical repository with the declaration removed and the value still
  present in the environment, so the name's presence is evidence rather than a
  property of every overlay. Each of the four refusals drives the real
  `dispatcher.main(argv=["dispatch", ...])` CLI with only the launch seam stood
  in, and is read off that seam rather than off an exit code, because "before any
  run exists" is a claim about what did NOT happen and a dispatch can exit
  non-zero having already created one. Every refusing case also asserts the
  journal carries no `proof-credential` record, since a record beside a refusal
  would describe a credential reaching a sandbox that never launched; and the
  admitted case is the control for all four, because four refusals alone are
  equally consistent with a gate that refuses every declaration. The drain leg is
  here too: the two dispatch paths reach the gate through separate call sites.
  The same module binds the clause's MINTING half against a HERMETIC PROVIDER
  DOUBLE — a script standing in for one provider's credential-management
  interface, which appends a line per call to a ledger and prints what it minted
  on stdout. Three cases carry it. The projection case reads the minted value out
  of the overlay the real materializer writes while the HOST holds a value under
  the same spelling, because a projection preferring the environment would be
  byte-identical to the pre-minting build on exactly the repositories an operator
  is most likely to have. The lifecycle case drives the real dispatch CLI and
  asserts the double's ledger as a SEQUENCE — mint, the run, revoke — since
  "revoked after the run ends" is a claim about order that a set cannot carry,
  with both legs' scope read back off the journal's own dispatch id rather than
  supplied by the test, and the copied sibling declared beside the minted one so
  "journaled minted" cannot be a build reporting every declaration as minted. The
  refusal case gives the double a twin that writes nothing and exits non-zero, and
  asserts the dispatch refuses rather than sliding onto the host's credential —
  the quiet failure where everything stays green and the only thing lost is the
  per-run bound the clause exists to establish.

- `test_ai_only_entry_path_refusal_scenario133.py` — binds the two ENTRY-PATH
  gherkin scenarios of `SPECIFICATION/scenarios.md` "Scenario 133 — A mixed item
  is refused ai-only from every entry path …", which the unit module
  `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_acceptance_eligibility.py`
  had bound against the shared decision primitive. ONE seeded mixed item — three
  `factory_captured` assertions and one under a `Human-attested` sub-heading with
  its `Reason:` line — runs through BOTH real dispatch entry points,
  `dispatcher.main(argv=["dispatch", "--item", …])` and the drain command's
  `dispatcher.main(argv=["loop", "--item", …])`, with only the launch seam stood
  in, and the two refusals are compared BYTE FOR BYTE rather than needle by
  needle: the clause's requirement is that the two AGREE, and two independently
  drifting messages that each mention the assertion satisfy a containment check
  just as well. "Before any claim or run exists" is read off the recording seam,
  off the ledger row's status and assignee, and off the absence of any
  `ledger-admit` or `dispatch-id` journal record, never inferred from an exit
  code. Two siblings carry the rest. The UNNARROWED autonomous pass consumes the
  same decision by DROPPING the row from the enumeration rather than refusing the
  wave, so it is asserted to leave no claim, no run AND no refusal — without that
  case the module reads as though an unnarrowed drain would print this message.
  And the parked-policy control is the identical item under `ai-then-human`,
  graded on the seam being ENTERED, because the refusals alone are equally
  consistent with a wall that refuses every human-attested item outright and
  makes the ratified remedy unreachable. The fixture commits its own spec tree so
  the item's reference RESOLVES: the mechanical findings arm runs first and its
  refusal shadows this one, and an unreadable tree makes that arm skip the
  reference check, leaving the fixture passing for a reason it stopped measuring.

- `test_acp_fallback_journey_scenario127.py` — binds `SPECIFICATION/scenarios.md`
  "Scenario 127 — Ordered ACP fallback preserves primary resolution, failure
  honesty, and one node visit". One two-candidate structured chain, declared in a
  `.livespec.jsonc` on disk, carried from the capability gate through to both
  ledgers: the configuration read, the catalogs, the chain resolution, the gate,
  the event scan, the hold and warning ledgers and the journal writes are all
  production code. Exactly two sockets are stood in, each at a seam the product
  publishes for the purpose — the factory's `GET /api/v1/system/info` answer
  through `FabroHttpTransport`, and the run's own event stream through
  `CommandRunner` — so the request path, the server qualification and the
  `fabro events` argv remain the real ones. The agent is `glm-acp-agent`
  deliberately: its `protocol` mechanism makes BOTH candidates carry
  `config_options`, so one fixture owes both capability strings and can isolate
  each gate arm by advertising the other. Every assertion is chosen to be DERIVED
  rather than echoed, because a recorded stream can prove nothing a fixture
  supplies: the hold's `expires_at` comes from occurrence time, the hold keys the
  candidate that FAILED while the warning keys the one that RESCUED the node (no
  single echoed field yields both), and the `primary_generation` the events carry
  is computed from this repository's own resolved chain rather than transcribed,
  so a configuration change that moved it makes the stream stop matching instead
  of silently agreeing. `cleared` is asserted ZERO against a run that SUCCEEDED,
  which is the scenario's own control that run success does not clear the primary.
  The version gate is bound on both halves — the FACTORY half in all four
  advertised states, including an unreachable server that must refuse rather than
  pass, and the RELEASE half read from this repository's own committed
  `dispatcher.minimum_release` floor with an at-floor control, since a refusal
  alone is equally consistent with a floor that refuses everything. The two
  negative controls carry the rest: an absent run reads as unobservable cost, and
  a factory advertising neither capability refuses before any journey is
  reachable. "Unchanged run and sandbox identity" is asserted as what the
  orchestrator can actually observe — one run id, reached through exactly one
  events read against the pinned factory, inside one node visit — because this
  repository holds no per-attempt container surface and an assertion about one
  would be an assertion against the fixture. The live controlled run on `hp` is a
  separate operational artefact of the same work-item; this module is what makes
  its transcript checkable.

- `test_filing_definition_of_done_scenario140.py` — binds
  `SPECIFICATION/scenarios.md` "Scenario 140 — Filing displays
  Definition-of-Done findings and withholds ready only on a mechanical one" and
  the "Authoring at filing time" sub-clause it realizes. All six of the
  heading's gherkin scenarios are asserted over one governed fixture
  repository: the display primitive, both halves of the host-side wall, the
  intake router with its ledger writes, and the needs-attention snapshot are
  production code over the REAL store/client seam, with only the spec-side
  `spec_next` read stood in. Two legs are worth keeping in view. The mechanical
  and advisory filings are the SAME filing differing only in whether the
  reference line resolves, because "the advisory item reached `ready`" is
  otherwise equally consistent with a build that graded nothing and "the
  mechanical one did not" with one that withholds `ready` from everything. And
  the carrier-relation pair is asserted together — a bullet inside the section
  is a finding, the same statement as prose above the heading is not — since
  either half alone passes for a build that reports neither or both. The four
  filing front-ends are PROSE with no CLI, so the authoring rules and the shared
  display call are asserted against the shipped prose, read whitespace-collapsed
  because the prose is hard-wrapped and a needle straddling a line break fails
  silently while the prose says exactly the thing. The hygiene leg runs through
  the REAL `needs_attention.main(argv=[...])` entry point rather than the lane,
  because a lane nothing composed would satisfy a per-lane assertion while the
  snapshot an operator reads carried no such row.

- `test_plan_result_reader_scenario146.py` — binds
  `SPECIFICATION/scenarios.md` "Scenario 146 — Authoritative result readers
  distinguish fulfillment from observation failure" and the
  shared-authoritative-result-reader clause it governs. Every case drives
  `read_result` itself over the REAL store/client seam and one recording
  `CommandRunner`; no adapter is stood in under the reader, so the parse, the
  repository resolution, all five adapters and every observation are production
  code. The scenario outline's five rows are asserted in BOTH directions against
  the SAME fixtures — each fulfilled target satisfied with its repository,
  target identity, UTC observation time and evidence identity, and each unmet
  target not satisfied — because a reader that reported satisfaction
  unconditionally would pass the first half and one that could never report it
  would pass the second. The three "cannot satisfy" controls the scenario names
  each get their own case: a comment saying verified against a typed verified
  proof, a stale local file that genuinely EXISTS in the working tree against a
  differing remote blob, and a shell predicate against the closed kind set.
  `_status` is the one accessor the negative controls read through, so they stay
  true as the `unsatisfied` and `unobservable` statuses land in their own
  Red-Green cycles rather than having to be rewritten by a later one.
  ONE case in the module does NOT use the recording stand-in, and that is
  deliberate: the remote-target-identity case issues the adapter's own endpoint
  over a real HTTP request to a loopback forge, because an argv assertion cannot
  see what a transport then does with a well-formed endpoint string. The defect it
  guards is that `?ref=proof#variant` is legal argv whose `#` a client reads as a
  FRAGMENT DELIMITER, so the forge was asked for `ref=proof` and the blob that
  OTHER branch holds satisfied a result naming this one. `urlopen` stands in for
  `gh` rather than the binary itself — a fragment is dropped by URL parsing, so
  the stdlib client reproduces it byte for byte while the tier stays hermetic —
  and the loopback forge answers one blob for the exact requested (path, ref) pair
  and a different one for every corruption of it, so the case discriminates in
  both directions instead of merely failing.

- `test_fabro_currency_admission_scenario130.py` — binds
  `SPECIFICATION/scenarios.md` "Scenario 130 — Dispatch admits only a current,
  identifiable Fabro base" and the Fabro-currency-admission clause of
  `SPECIFICATION/contracts.md` through the REAL pre-dispatch wall,
  `pre_dispatch_wall_exit`: the real committed factory block, the real
  `JournalFile` on disk, the real release-observation cache under a tmp
  `XDG_STATE_HOME`, and the real forge and engine argvs. Only the
  `CommandRunner` that shells out to `gh` and `fabro`, and the clock the
  observation is aged against, are stood in. Driving the WALL rather than the
  gate is what makes "refused BEFORE claim" observable: a refusal returning
  from the wall is one that reached no `admit_and_select`, so nothing moved
  `ready -> active`, no assignee was set and no Fabro run was created — a
  gate-level assertion that a verdict carries a refusal cannot show that. The
  currency gate is FIRST in the wall, which is why these cases need no fixture
  for the criteria wall, the proof-assets prerelease, the proof-credential
  declaration or the host Codex credential; that ordering is itself
  load-bearing, since the proof-assets gate CREATES a repository prerelease and
  the Codex gate SPENDS a bounded provider renewal. Every fixture parameter is
  REQUIRED rather than defaulted, because a default is an arm no case takes and
  this tier's per-file coverage gate reads a never-taken branch in a fixture
  exactly as it reads one in the product.

- `test_needs_human_preservation_push_hookless.py` — binds work-item
  bd-ib-3vn3mu against the SPECIFICATION/contracts.md rule that a factory run
  never awaits a human (ratified v093, Scenario 103): the `needs_human`
  terminal's own script, extracted from the committed graph and unescaped, runs
  in a throwaway repository with a real bare origin and REAL `.git/hooks`, and
  its preservation commit and push must complete without executing the governed
  repository's check suite. Every case that asserts a hook did NOT run first runs
  a CONTROL — a plain `git` write of the same kind in the same fixture — that
  MUST record the hook and MUST be refused, because an absent marker is
  otherwise equally consistent with "the node skipped the hook" and with "no
  hook was ever wired", and nothing in the output distinguishes them. The
  content assertion is what makes the commit leg worth anything: a hook-refused
  commit still leaves the push creating the ref, so "the ref exists" passes for
  a preservation that saved the last checkpoint and lost the work. The
  `publish_draft` counterpart is driven in the same module against the same
  refusing-hook fixture and MUST still be hook-gated, since the two nodes'
  pushes are one line apart in intent and only the measured difference keeps
  them apart.

- `test_needs_human_push_failure_is_reported.py` — binds work-item bd-ib-s6bowj
  against the same Scenario 103 rule, one layer on: when the preservation push
  FAILS, the terminal's output after `LIVESPEC_NEEDS_HUMAN_PUSH_FAILED` must
  carry the push's own error text, bounded and with any credential embedded in a
  remote URL redacted, and the ending must be unchanged. The node's own script is
  extracted from the committed graph, unescaped and run by `sh` in a throwaway
  repository, as in the sibling module. Every fixture is a REAL `git push`
  failure rather than a stand-in for one, because the text under test is the
  push's OWN output and a fixture that fed the node a string would assert only
  that the node can echo a string: an origin path that does not exist, the same
  with a ~3 kB path whose diagnosis overruns the bound, and a `git://` origin
  carrying userinfo, which git echoes verbatim (git 2.43 anonymizes its own
  `unable to access` line, so an https URL cannot produce the shape under test).
  Each case runs a CONTROL push of the same kind in the same repository first and
  compares the report against what that control actually printed — which is what
  makes the token's absence evidence of REDACTION rather than of the whole-text
  discard this node used to perform, and the bound's assertion a byte comparison
  against the control's leading bytes rather than an encoding of this git
  version's message lengths. The successful-push case is the control for all of
  them: "the failure arm reports an error" is otherwise satisfied by a node that
  prints a diagnosis on every ending.

- `test_fix_stage_failure_routes_to_needs_human.py`,
  `test_open_red_needs_human_reason.py` and
  `test_completed_red_green_pair_still_proceeds.py` — bind the three
  Definition-of-Done assertions of work-item `bd-ib-qhv7qs` against
  `SPECIFICATION/scenarios.md` Scenario 103: a `fix` or `review_fix` stage whose
  agent turn times out with a Red commit open at the branch head ends through
  the needs-human terminal with the tree preserved, the dispatch result and the
  item's DURABLE record name both the timed-out stage and that open Red, and a
  stage that ends normally with a completed pair still proceeds. The split is by
  the layer each assertion lives in. The first reads the committed graph's EDGES
  and nothing else, because routing a node failure is entirely an edge property.
  The second DRIVES the terminal's own script — extracted from the graph and
  unescaped — by `sh` in a throwaway repository whose HEAD really carries Red
  trailers, then feeds that real stderr through the production terminal mapper
  and the durable-record writer over the real store/client seam, because the
  reason comes from the SANDBOX while the failed stage comes from the ENGINE's
  outcome map and neither can supply the other. The third is the preservation
  assertion, which has nothing to implement and is therefore the one most easily
  lost: each of its three facts is also a control in a sibling module, and what
  it adds is the ORDINARY JOURNEY none of them asserts — a route onward, a
  checkpoint no repository gate can refuse, and silence about an open Red. Two
  controls are load-bearing. A completed Red-Green pair must produce the
  unchanged generic reason, since the discriminator is the GREEN's absence and
  not the Red's presence, and a completed pair is what every healthy stage
  leaves. And each routed node must keep exactly ONE unconditional out-edge,
  because an edge added by consuming the fallthrough routes the timeout
  correctly and publishes a graph `fabro validate` rejects outright — the
  `all_conditional_edges` defect that took the whole factory down twice.

- `test_needs_human_stage_cause_and_open_red_gate.py` — binds work-item
  bd-ib-rv7g4z against the same Scenario 103, one layer on from the module
  above: the terminal reported an OPEN RED where the real cause was a
  `pr_refresh` failure, and the Red it reported was not open. Both halves are
  measured on run 01M51D4RYHCB. The shipped `pr_refresh`, `refresh_repair` and
  `needs_human` bytes are taken through the canonical parser and EXECUTED by
  `sh` in throwaway clones with real bare origins, because every arm under test
  is shell and a substring assertion cannot tell a precedence arm that RUNS
  from one sitting behind an earlier `elif`. The carry is asserted END TO END
  across all three nodes in one clone, since the classifier ALREADY claimed to
  route "with that stage own cause" and the terminal's precedence is satisfied
  by a record no stage ever writes — only the composition can show the carry.
  The publication is real: the branch is pushed to origin and then DELETED, so
  the stage meets the genuine origin-unobservable failure a merged-and-deleted
  pull request produces rather than a stand-in for one. FOUR CONTROLS CARRY THE
  MODULE, and each one asserts the open-Red clause is PRESENT, because the
  defect is a reason that fires too often and the cheapest wrong fix is one
  that never fires at all. The path discrimination is the subtle half: a
  genuine open Red stages the TEST ALONE, so its head commit touches `tests/`
  and nothing else, while the measured false positive carries non-`.py`
  IMPLEMENTATION beside its test — so the exempt case is keyed on
  `red_green_replay`'s own `_stages_non_python_implementation` premise rather
  than on "changes a product `.py`", which reads naturally and would retire the
  clause for the one shape it was built for. The control for that case adds a
  product `.py` to the SAME three paths, which is a genuinely half-authored
  commit and must still report. The POSITIVE case for that test-alone shape is
  deliberately NOT duplicated here: it is
  `test_open_red_needs_human_reason.py::test_the_terminal_reason_names_the_open_red_commit_at_the_branch_head`,
  whose head commit changes exactly one `tests/*.py`, and it is the guard that
  makes the narrowing honest rather than a quiet retirement. Measured by
  mutation on 2026-10-18: replacing this module's any-`.py` reading with a
  product-`.py` one reds that case and two siblings in the same module, so a
  future narrowing cannot pass while only this module's cases are consulted.

- `test_needs_human_preservation_ref_identity.py` — binds work-item
  bd-ib-zddbkq against Scenario 103's requirement that a needs-human outcome
  preserve the tree on a RUN-SCOPED ref, which holds only while the name the
  terminal chooses cannot be shared by two runs. The node's OWN script is
  extracted from the committed graph, unescaped and driven by `sh` in a
  throwaway repository with a real bare origin, provisioned with the dispatch
  correlation id in the same LOCAL git config key the Dispatcher's prepare step
  writes. Both engines were wrong in OPPOSITE directions and both read healthy:
  the Petri-era engine sets `context.internal.run_id` to the literal `petri`, so
  the push SUCCEEDED and every needs-human outcome landed on one shared ref and
  overwrote the last run's work, while the pinned engine supplies no stdin to a
  script node and preserved nothing. The ordering under test is therefore
  guaranteed-unique-first — the dispatch id, then the engine's value — rather
  than a grammar guessing which stdin values are real ids, and the module says
  why: a guess admits the first placeholder of a shape it had not anticipated,
  silently, which is the same defect again. Each case carries a control that
  rules out the cheap vacuous pass: the fallback naming the ref is only
  meaningful beside a clone carrying NO marker, which must push nothing, since a
  node answering with a constant of its own would pass otherwise; and the
  placeholder's refusal is only meaningful beside a genuine engine run id that
  still names the ref on that same marker-less arm, since a node that had
  stopped reading stdin would satisfy the refusal exactly as the correct one
  does. The preserved BLOB is read back off the ref rather than the ref alone,
  because a ref created at the last engine checkpoint is present, plausible, and
  missing exactly the work the node exists to save. The key name is asserted
  against `FACTORY_RUN_ID_MARKER` itself: the terminal spells it inside a shell
  string no import graph can see, and a rename on either side drops the node
  onto the stdin fallback — the placeholder on one engine, nothing on the other.

- `test_sandbox_clone_git_identity.py` and
  `test_needs_human_preservation_committer_identity.py` — bind work-item
  bd-ib-lsr3vf against Scenario 176: on the Petri engine the sandbox clone
  carries no `user.name` and no `user.email`, because the engine applies its
  configured `git_identity` to its OWN per-node checkpoint commits only, so a
  SCRIPT node that creates commits itself has no committer. The first module
  runs the ACTUALLY RENDERED identity prepare steps in a real clone and then the
  shipped `publish_draft` script against a default branch that advanced after
  the clone was taken, which is what gives the refresh rebase a commit to
  create; the second runs the shipped `needs_human` terminal and reads the
  preserved commit's author AND committer off the pushed ref. Both execute
  rather than match text, because a step that writes the right keys in the wrong
  scope, or after the node that needs them, renders identically to one that
  works. Three things are load-bearing. The fixtures leave the clone with NO
  identity in ANY scope — `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` at
  `/dev/null`, no `GIT_AUTHOR_*` or `GIT_COMMITTER_*` in the child environment,
  and every provisioning commit supplying its identity per invocation with
  `git -c` — since the host's own `~/.gitconfig` would make every case pass and
  an agent-set identity is exactly what made the defect intermittent in
  production (canary 12 passed only because a tool call had run `git config
  user.name` first). The expected pair is read back off the rendered overlay's
  OWN env table rather than off a constant, because a renderer projecting one
  pair into the config and another into `LIVESPEC_GIT_AUTHOR_NAME` would
  attribute one commit two ways. And each module's control is the measured
  failure with only the identity steps withheld: for `publish_draft` that is
  exit 128 on "Committer identity unknown", and for `needs_human` it is the
  expensive shape rather than a visible one — `PRESERVED` is still reported and
  the ref still exists, at the last commit the clone already had, so only the
  preserved BLOB discriminates.

- `test_watchdog_bound_run_poll_scenario173.py` — binds
  `SPECIFICATION/scenarios.md` Scenario 173 and the `contracts.md` paragraph it
  exercises (the Dispatcher progress watchdog's "Observing the run"): once the
  run id is bound every poll reads THAT run by id and the factory's run history
  is never listed again, while discovery before the bind is unchanged. The
  journey runs through the PRODUCTION launcher — real `WatchedFabroLauncher`,
  real `FabroPort`, the real per-poll observation seam and real threading — with
  only the fabro subprocess stood in, and stood in AT THE ARGV, because the rule
  is about which call each poll ISSUES and no returned run can distinguish a
  per-run read from a listing that happened to contain the same row. Three
  things about the cases are worth knowing before editing. The bound node id is
  the listing-then-read case because it carries BOTH halves of one rule on one
  dispatch; split apart, a bound-poll-only fixture passes against a build that
  never discovered its run at all. The ps listing deliberately carries a SECOND
  row belonging to another work-item, so the discovery leg is a real attribution
  rather than a single-row lookup. And the no-longer-held and failed-read cases
  assert against EACH OTHER's reason rather than on `matched` alone: a vanished
  run, a run the factory still holds but is no longer running, and a read that
  observed nothing all report `matched: False`, so a boolean-only assertion is
  satisfied identically by the one outcome the clause forbids — a confident
  claim that the factory dropped the run, earned from a read that saw nothing.
  Every case asserts a poll-count FLOOR and the shape of the tail rather than an
  exact count, because the floor is what each clause is about. That used to be a
  concession to a race as well — a poll could still land while the launch thread
  unwound — and it is not any more: the fixture releases the run through
  `end_run_and_await_launcher_return`, which waits on the LAUNCHER's own thread
  rather than on the fake runner's too-early signal (bd-ib-spc6xr).

- `test_workflow_refresh_repair_scenario176.py` — binds
  `SPECIFICATION/scenarios.md` Scenario 176 and the two `contracts.md`
  paragraphs it exercises, v134's "Refresh repair" and "Refresh-repair
  accounting": a `publish_draft` or `pr_refresh` stage that cannot refresh the
  run onto an advanced default branch restores its pre-refresh head, records a
  brief and routes to the existing `fix` node instead of ending the run at
  `needs_human`. Every behavioural case EXECUTES the shipped script bytes —
  taken through `parse_dot_graph`, never retyped — against a real throwaway
  origin, because every guard in both stages is shell and a substring assertion
  cannot tell a restoration arm that RUNS from one sitting behind an earlier
  `exit`. Only the two engine template tokens are bound, and the
  `sandbox_check_suite` substitution stands in for a per-repository
  DECLARATION rather than for the stage. Two claims are read off the graph
  instead, because no execution can establish them: the ROUTE (every acyclic
  path from the classifier to `pr` visits janitor, then publish_draft, then
  proof_capture — reachability alone would be satisfied by a repair routed
  straight back to publication) and the BUDGET the accounting paragraph grants.
  Three controls are load-bearing. The authentication-failure case is what
  forces the push-failure classification to be a POSITIVE reading rather than a
  residual category: without it, "a failed push enters the fix node" passes for
  a build that repairs an unreachable origin, which is the one cause v134
  forbids this route. The exhaustion case asserts the brief is ABSENT as well as
  the reason file present, since the classifier routes on the brief and a third
  round that wrote one would re-enter `fix` while reporting exhaustion. And the
  `review_fix`/`disposition` budgets are asserted UNCHANGED beside the widened
  `fix` budget, because "the repair took nothing from review-fix" is otherwise
  equally consistent with a graph that widened nothing at all.
  The same module carries v146's narrowing of the divergent-prior-run guard
  (work-item bd-ib-c435hh) and Scenario 144's mirrored "with no refresh-repair
  round before it" sub-scenario: a repaired visit republishes a non-ancestor tip
  EQUAL to the head this run published, under an explicit lease, while a foreign
  tip, an unestablishable published head and a visit following no repair round
  each still fail closed. Its fixture DRIVES the real conflict through the
  shipped `pr_refresh` bytes and then performs the fix turn's own instructed
  integration, because the premise — a published head that is a NON-ANCESTOR of
  the repaired head — cannot be arranged by hand without assuming it, and the
  non-ancestry is ASSERTED rather than trusted. Two controls are load-bearing.
  The brief-absent case is the republication world with ONLY the brief removed,
  which is exactly the state a review-fix round reaches the stage in, so the
  refusal is evidence about the brief rather than about anything else the
  fixture carries. And the two plain-fast-forward arms run with the exact-head
  push helper WITHHELD from the sandbox plugins root: both arms move the ref to
  the same sha a lease would, so the absent helper is the only instrument that
  can tell a fast-forward from a rewrite.

- `test_tenant_client_backup_lane_scenario181.py` — binds the `Given` of
  `SPECIFICATION/scenarios.md` Scenario 181 and the `contracts.md` §"Beads
  connection model" bullet "Client backup lane disabled": this repository's
  committed `.beads/config.yaml` sets `backup.enabled: false` and the comment
  attached to that key names `dolt-backup.service` and
  `DOLT_BACKUP('sync','s3')` as the hourly server-side lane the client lane
  would duplicate. The subject is THIS repository's own committed file rather
  than a fixture, which is what puts the case at this tier: `bd` opens the
  committed file at the repository root on every call, so a fixture would grade
  bytes no `bd` invocation ever reads. Two things are worth knowing before
  editing. The comment is asserted as well as the key, because a bare disabled
  backup setting on a ledger reads as "backups switched off" rather than
  "backed up centrally, client lane redundant", and the second reading is the
  correct one; the assertion is on the comment block ATTACHED to the key, since
  a rationale parked elsewhere in a flat key-value file does not travel with
  the line it explains. And the scenario's `When`/`Then` — a live `bd` write
  whose stderr carries no `auto-backup failed` warning, and the next hourly
  `dolt-backup.service` run reporting every tenant synced — is deliberately NOT
  here: it needs the credential wrapper, the shared Dolt server and the backup
  timer, so work-item `bd-ib-rxf` carries it as a HOST-CAPTURED assertion
  instead. This file never connects to a tenant.
- `test_janitor_check_venue_row_scenarios190_191.py` — binds
  `SPECIFICATION/scenarios.md` Scenarios 190 and 191 and the
  `SPECIFICATION/contracts.md` subsection they exercise, "Post-merge janitor
  check-suite venue": which machine the post-merge janitor's check suite runs
  on, how the delegated gate's verdict reads, and what the `janitor-post-merge`
  journal row says about both. Every case drives the production `post_merge`
  over a real on-disk `JournalFile` and reads the row back off that file,
  because the row IS the clause's subject and a projection asserted in
  isolation would pass while nothing wrote it into the record an operator
  reads; the venue itself comes off a real `.livespec.jsonc`, which is where
  the production reader takes it from, so no argument of the module can put a
  venue into the flow. Two seams are not canned, and each is load-bearing. The
  SUBMITTED-TREE reading runs for real through the production
  `ShellCommandRunner` against a real git checkout the fixture commits into,
  with the expected value measured through a DIFFERENT git invocation
  (`git show -s --format=%T` against production's `rev-parse HEAD^{tree}`), so
  the assertion compares two readings of one repository rather than the row
  against a constant the module also fed the flow — and it asserts the row
  names the TREE and not HEAD's commit id, which is equally plausible in a
  journal and names an object no gate Job label holds. And the start-instant
  case RUNS the check suite, one leg of it sleeping a known two seconds, since
  a canned result returns instantly and would make a stamp taken before the
  launch indistinguishable from one taken beside the journal append; its quick
  leg is the control that the measured duration came from the sleep.
  Three further pairings must not be split. The cluster row's three NULL
  `gate_state` arms (a state word on standard output alone, a `state` that is
  not a string, and no state-bearing line at all) sit beside the host-local
  case that carries NO gate field, because a null on a host-local row and a
  null on a cluster row are the two states the field exists to tell apart. The
  Job-key case pairs a verdict line carrying an explicit `job_started_at: null`
  and no `job_finished_at` with a line naming no Job at all on a row that DOES
  carry the tree hash — every ingredient the gate's own naming convention
  needs — so "nothing was derived" is observable rather than assumed. And the
  no-verdict cases name `_gate(state="FAILED")` as their control, since a
  janitor that called every non-pass reading a lost verdict would satisfy all
  three of them.

- `test_pre_push_deletion_only_scenario188.py` — binds
  `SPECIFICATION/scenarios.md` Scenario 188 and `constraints.md` §"Pre-push
  gate refinements": a push whose every ref update is a deletion (an all-zero
  local object id on the pre-push hook's standard input) skips the green-token
  probe and the `just check` aggregate, and every other input shape — a
  create, an update, a deletion travelling beside one, and no input at all —
  still runs the full gate. The subject is this repository's own committed
  `dev-tooling/just-check-pre-push.sh`, `lefthook.yml` and `justfile` rather
  than a fixture, which is what puts the case at this tier: the script is
  executed as the SHIPPED BYTES with `uv` and `just` stubbed on `PATH`, so what
  it INVOKES is the observable — the only thing that can tell a real skip from
  a gate that ran and happened to pass. Three halves are asserted because any
  one alone leaves the skip dead: the script's own branch, lefthook's
  `use_stdin: true` (lefthook forwards a hook's standard input ONLY to a
  command declaring it), and the recipe passing that input through. The
  always-run `02-ledger-conformance` step is asserted to stay a separate
  pre-push command the skip cannot reach. This file never connects to a tenant
  and never pushes.

- `test_delegated_pre_push_gate.py` — this repository's OPT-IN to the delegated
  pre-push gate (work-item bd-ib-idp5g7), whose contract is
  livespec-dev-tooling's `SPECIFICATION/contracts.md` §"Delegated pre-push
  gate" and whose client is the pinned `gate_remote_delegate`. Only two facts
  live in this tree — `delegated_gate = true` in this repository's own
  `[tool.livespec_dev_tooling]` block, and the branch
  `dev-tooling/just-check-pre-push.sh` takes on the client's answer — so the
  subject is this repository's own committed files rather than a fixture, as in
  the sibling module above, and the script is likewise executed as the SHIPPED
  BYTES with `uv` and `just` stubbed on `PATH`: what it INVOKES is the only
  observable that can tell a delegated gate from a local one, since both
  complete and a completed push looks identical afterwards either way.
  DELEGATION IS SELECTED BY TWO FACTS and only one of them is in the tree, so
  the host half is driven through `GATES_KUBECONFIG` — the single override the
  client and the shipped `with-gates-kubeconfig` wrapper BOTH resolve the
  credential from — rather than read off whatever host the suite runs on: the
  real credential is absent in a sandbox and PRESENT on the VPS, so a test
  asserting on it would pass here for the very reason it would fail there. Both
  host answers are asserted. The credential-holding arm is the positive control
  without which the credential-less one proves only that nothing is switched
  on, since a repository that never opted in ALSO fails that probe, and
  silently. Three script cases carry the branch: its POSITION (after the
  green-token skip, before the local fall-through — ahead of the token it would
  re-gate a tree already proven green, behind the aggregate it would be
  unreachable), the selected-delegation case asserting the local aggregate is
  NOT also run, and the fail-closed case asserting a delegated run that reaches
  no verdict refuses the push instead of falling through, which is what the
  `exec` buys. No `gate_check_suite` is declared and a case asserts that
  absence, because a declaration would gate the tree on recipes chosen in
  `pyproject.toml` rather than the ones this repository's pre-push actually
  runs. This file never connects to a tenant and never pushes.

- `test_exhaustion_record_credential_identity_scenario186.py` — binds
  `SPECIFICATION/scenarios.md` Scenario 186 and the credential-identity clause
  of `contracts.md` §"Dispatcher admission, WIP cap, and post-merge
  acceptance": a provider-exhaustion record observed on one credential account
  does not refuse dispatch on another account of the same vendor. The six
  gherkin blocks map 1:1 to the six cases, each through the surface the
  scenario names — `post_run_dispositions` for the mint, over a terminal built
  by `fabro_run_terminal_outcome` from a Fabro payload so the vendor is
  classified by production code; `live_provider_exhaustions` for "the records
  the Dispatcher reads"; and `filter_eligible_candidates` for the four
  admission cases, against a real repository checkout and a real on-disk
  journal. What makes it a scenario binding rather than a unit test is the
  JOIN: the account the valve compares against is taken from the verdict's own
  journaled session-headroom assessment, so the label one dispatch's admission
  wrote is the label another dispatch's admission reads, which is the only
  thing the incident turned on. Two cases are controls for the rest and must
  stay: the provider-only record, because narrowing an account-named record is
  equally consistent with a gate that stopped reading the journal, and the
  absent-account case, because that one arm WIDENS a record's reach and is the
  direction every other case argues against.

- `test_janitor_environment_scrub_scenario189.py` — binds
  `SPECIFICATION/scenarios.md` Scenario 189 and the post-merge and reconcile
  janitor environment clause of `SPECIFICATION/contracts.md`: the janitor's
  check run carries neither `LIVESPEC_FABRO_FACTORY` nor `LIVESPEC_INVOKER`,
  keeps every other value the Dispatcher's environment held, and the
  `janitor-post-merge` journal row names what it removed. The check aggregate
  is a REAL child process that EXITS NON-ZERO when it can see the variable
  under test, which is the measured defect rather than a contrivance: this
  repository's own factory-resolution and operator-default tests read those
  variables, so a janitor that inherits them reds a merge whose
  default-branch CI was green and strands the item `active`. The child dumps
  its environment NUL-framed, the only framing in which a value's own newline
  cannot be mistaken for a record boundary, and every value is read back by
  NAME so no assertion renders the rest of the host's environment. Each case
  carries the SAME probe run through the same production `ShellCommandRunner`
  with an unscrubbed overlay as its control, because "the child saw no
  variable" is evidence only beside a child that WOULD have seen it — a probe
  that could not read its environment at all would otherwise satisfy every
  assertion here. The retention case is deliberately an INVARIANT that holds
  before the scrub and after: the obvious wrong implementation hands the child
  a curated environment built from scratch, and a check reaching for a
  credential or for `PATH` in that environment fails for a reason no journal
  row would name. The empty-removal-list case and the names-what-it-removed
  case are each other's control, since an omitted field is what every row
  written before the scrub looks like. The reconcile case drives the REAL
  `dispatcher.main(argv=["reconcile-merged", ...])` with the probe taken off
  the repository's own committed `dispatcher.janitor.check_suite` declaration,
  because the valve builds its own plan and no argument could put a probe into
  it; its runner is keyed on the SUBCOMMAND rather than on call order, so the
  case does not encode the valve's stage sequence, which is not the subject.

- `test_agent_hook_unparseable_manifest_scenario194.py` — binds
  `SPECIFICATION/scenarios.md` "Scenario 194 — A conflicted pyproject.toml does
  not make the repository's agent hooks refuse every tool call": both of that
  heading's sub-scenarios, driven against the launcher
  `.claude/hooks/livespec_uv_hook_launcher.py` that each `uv run`-started
  PreToolUse hook command is invoked through. This tier is the exception to the
  `livespec_orchestrator_beads_fabro`-package framing above — the scenario is
  about this repository's own committed agent hooks, and the heading taxonomy
  still requires an integration-tier binding. Every case resolves those hook
  commands from `.claude/settings.json` itself rather than retyping them, so a
  rewiring that dropped a guard cannot keep the binding green; the committed
  shape of that wiring is pinned one tier down, in
  `tests/hooks/test_livespec_uv_hook_launcher.py`. The conflicted case is
  parameterized across all four guarded tools AND every committed command,
  because the claim is about the whole guarded surface rather than one call.
  Nothing is spawned: the launcher's own `subprocess.run` is stood in for, which
  is what makes "the guard was not launched" assertable at all.

- `test_sandbox_path_guard_scenario180.py` — binds `SPECIFICATION/scenarios.md`
  Scenario 180 and the `contracts.md` paragraph "The run's working tree survives
  the agent." (v142): the committed PreToolUse hook
  `.claude/hooks/livespec_sandbox_path_guard.py` refuses a command whose
  executed segment would remove, move or replace the sandbox root, the run's
  working directory, its working-directory link or the run's clone, while
  scratch removals, in-tree removals and data-only mentions still run. One case
  per gherkin scenario, each driven through `main()` IN-PROCESS — a payload on
  stdin, a deny payload on stdout — over a REAL layout built under `tmp_path`:
  a root holding a symbolic link to a clone under a sibling `repos/` tree, which
  is the layout the 2026-10-15 incident ran in. The real filesystem is what puts
  this at the integration tier rather than beside the policy's unit cases: the
  protected set is DISCOVERED from that layout — the working-directory link is
  identified by what it points at, and the clone sits OUTSIDE the root — so a
  stubbed filesystem would exercise the decision ladder and leave the discovery
  unexercised. The production root is `/workspace`, redirected here through the
  guard's own documented override. Two things are worth knowing before editing.
  The sandbox-root case asserts the link and the clone still EXIST after the
  hook has spoken, because the clause's "before any part of it executes" is
  exactly what a deny decision buys and an exit code cannot show it. And the
  Background premise — that the agent's ACP adapter runtime offers a hook
  running before each shell command — is a property of the RUNTIME, so it is
  bound here only as the half this repository controls, namely that the guard is
  registered on the `Bash` PreToolUse matcher in the committed
  `.claude/settings.json`; that a dispatched run's agent actually reaches it is
  work-item bd-ib-jgedjo's HOST-CAPTURED assertion, proved on the factory
  against a released build.

- `test_factory_registry_resolution_scenario182.py` — binds
  `SPECIFICATION/scenarios.md` Scenario 182 and the host-factory-registry clause
  of `SPECIFICATION/contracts.md`: a `dispatcher.factories` entry declaring
  `"registry": true` names no machine, and its server and container-daemon
  addresses are resolved by the entry's own name from the host factory registry.
  Every case starts from a `.livespec.jsonc` and a registry JSON file on disk
  and runs the production configuration, resolution, pre-claim declaration grade
  and plan seams; the only things stood in are the two CLIs (a recording runner,
  so the `fabro run` and `docker --host` argvs are observable without a server
  or a daemon) and the ledger, through the hermetic `FakeBeadsClient`. Three
  things an editor must not weaken. The address is asserted at the ARGV and at
  the LEDGER as well as at the resolver, because a dropped address does not fail
  — it resolves to None, which every surface reads as "this factory declares no
  server" and therefore as the ambient LOCAL factory, so the run is created on
  the wrong machine with nothing in the record saying so, and a registry-backed
  entry is exactly the case where no committed `server` exists downstream to
  fall back to. Every refusal is taken off `dispatch_preamble` with the item
  SNAPSHOTTED before and compared after, because "refused before any claim,
  ledger write of any kind, or Fabro run creation" is two claims and a refusal
  string proves only the first. And the `env unset` registry-path case asserts a
  NEGATIVE beside the constant — the resolution must not return the override
  file's address — since asserting the default path alone is an echo of the
  constant, while the negative is what an implementation reading the override
  unconditionally cannot satisfy. That negative reads the real host
  `/etc/livespec/fabro-factories.json`, which is unmanaged state this suite does
  not own, so what keeps it hermetic is `_REGISTRY_SERVER` being a
  RESERVED-domain sentinel no inventory can render — NOT an assumption about
  what that file holds. Spelled as a machine this fleet provisions, the
  assertion is false on exactly the host the registry maps `petri` on: measured
  2026-10-18, writing the production pair into that path reds the case while the
  code is correct, which is a false FAIL on every `just check` run there.
  Every refusal row also asserts the FAULT it is refused FOR, which is what
  makes the nine rows nine cases: all nine name the factory and the path and
  exit alike, so a names-only assertion holds for any of them and a row whose
  staging landed on an adjacent arm would report a real refusal for the wrong
  reason and still pass. The `unreadable` registry is therefore staged as a
  DIRECTORY at the registry path and discriminated on the `OSError` TYPE
  (`IsADirectoryError`), NEVER by clearing the mode bits. Mode bits do not
  refuse root and every dispatch and sandbox here runs as root: the read
  succeeds, the file parses, and what follows is the `no-entry` refusal wearing
  the `unreadable` label — the adjacent arm, a different remedy, and nothing in
  the output saying so. Measured 2026-10-18 against both this suite and a Proof
  of Done capture of the same arm: with a mode-bit staging the directory
  assertion reds, and without it the mode-bit staging passed while establishing
  `no-entry` twice and `unreadable` never. The rule binds any CAPTURE or REPLAY
  demonstrating that arm as much as it binds this module. The consumer surfaces the
  clause also names belong to `test_factory_registry_consumers_scenario182.py`
  beside it; what this module establishes for them is that `FactoryTarget.server`
  and `FactoryTarget.docker_host` already carry the registry's addresses, so no
  consumer learns that an address came from a file.

- `test_factory_registry_consumers_scenario182.py` — the CONSUMER half of
  Scenario 182 and of the same clause: "Every surface that turns a declared
  factory into an address MUST use this one resolution, and every surface whose
  behaviour depends on whether a factory is remote MUST treat a registry-backed
  entry as naming a server", together with the failure behaviour each of those
  surfaces owes an unresolvable one. Every case writes a `.livespec.jsonc` and a
  registry file and drives the production surface: the reconcile survey and its
  claim lane through `reconcile_runs` over `reconcile_factory_targets`, plan
  liveness through `observe_target_run`, the merge-hold guard through
  `arm_refusal_for_release`, the projection through
  `resolve_projection_factory`, the availability evidence through the production
  `FactoryRunReader`, the valve through `needs_human_question_summary`, the
  container sweep through the pass's own daemon lane, and the telemetry
  classification through `factory_run_turn_observation`. Three things an editor
  must not weaken. THE SURFACES NEED CASES OF THEIR OWN EVEN THOUGH THE
  RESOLUTION IS SHARED, because an unresolvable registry answers with
  `FactoryTarget.server` of `None` — the same value an unconfigured repository
  carries, which every one of these surfaces already reads as the ambient LOCAL
  Fabro — so a consumer that opened a port on it surveys whichever engine the
  dispatching host runs, answers cleanly, and reports a factory as holding no
  runs from a reading taken on the wrong machine. Measured on the pre-fix build:
  the plan gauge asked the local engine about a run living elsewhere, and the
  merge-hold guard read the empty listing it got back as "no run of this item is
  live" and fell through to arm the pull request. EVERY LIVENESS CASE THEREFORE
  ASSERTS THAT NO PROCESS WAS LAUNCHED for that factory, which is the only place
  the right unobservable verdict is distinguishable from the wrong one — both
  return the same value, and only one of them has already contacted a machine
  the factory never named; the merge-hold case carries the mirror control, the
  same guard over a sibling that DOES declare an address, because a guard that
  had simply stopped asking anything would satisfy the refusal and the
  nothing-launched assertion together while refusing every release this fleet
  makes. And THE UNDECODABLE-REGISTRY CASE BELONGS HERE rather than beside the
  resolution's own refusal rows: `Path.read_text(encoding="utf-8")` raises
  `UnicodeDecodeError`, which is a `ValueError` and not an `OSError`, so such a
  file escaped the reading entirely and reached every consumer as a traceback —
  including the needs-human valve lane, whose absorbed set is `OSError` and the
  beads family, so one byte of host state cost the whole valve list instead of
  one item's enrichment. It is written as RAW BYTES, the only way to express a
  file that never reaches the JSON reader, and driven through the survey rather
  than through the reading, because the reading returning a detail proves only
  that it no longer raises while the claim is that the pass completes and
  reports the factory.

- `test_factory_overflow_selection_scenario203.py` — binds
  `SPECIFICATION/scenarios.md` Scenario 203 and the factory-overflow-selection
  clause of `SPECIFICATION/contracts.md`: an unpinned dispatch goes to whichever
  declared factory's own scheduler is least utilized and has a free slot. Every
  case starts from a `.livespec.jsonc` on disk and drives the production
  configuration read, capacity read, selection, ledger stamp and launch argv;
  only the `fabro` CLI is stood in — at the runner, so the real
  `FactoryRunReader` and the real `FabroPort` stay in the path and each
  factory's run board and scheduler ceiling are scripted per SERVER URL — plus
  the ledger, through the hermetic `FakeBeadsClient`. Four things an editor must
  not weaken. The chosen factory is asserted at the ARGV and at the LEDGER as
  well as at the resolved target, because a dropped name does not fail: the
  dispatch proceeds to the default, which is the ordinary outcome of a healthy
  ranking, of an unreachable overflow factory and of a build that ranked
  nothing, with nothing in the record saying which. The PINNED case asserts the
  capacity argv list is EMPTY rather than checking the answer, since a pinned
  dispatch resolves to its own factory whether or not the reads were spent — the
  unpinned cases are the positive control that the same runner IS reached. The
  no-free-slot cases assert a launch ARGV beside the journal reason, because
  "neither refused nor deferred" is a negative and a refusal leaves no argv at
  all. And the equal-utilization row is what makes the comparison a RATIO: at 5
  of 10 against 1 of 2 the default holds more runs by every absolute measure and
  only utilization ties them, at which point the clause's earlier-candidate rule
  keeps the dispatch on the default — an implementation comparing free slots or
  remaining capacity sends that row to the overflow factory while passing the
  row above it. The `ps` fixture carries a TERMINAL row beside its live ones,
  since `max_concurrent_runs` bounds non-terminal runs and a reader counting
  every row would report a long-lived factory as permanently saturated (hp
  listed 1626 rows on 2026-10-12, nearly all terminal). The registry cases are
  asserted at the capacity argv's SERVER, because a registry-backed entry
  commits no address and a resolution that skipped the registry would read a
  factory with no server and report the candidate unmeasured — which looks
  exactly like a saturated one.

- `test_run_wall_budget_scenario175.py` — binds `SPECIFICATION/scenarios.md`
  Scenario 175 and the `contracts.md` paragraphs it exercises (the Dispatcher
  progress watchdog's "The whole-run wall budget", and the whole-run wall budget
  key of "ACP node timeouts"): a run whose slot-holding time passes the resolved
  `dispatcher.run_wall_budget_seconds` has its preserve-by-reference pointer
  written and read back, is then cancelled, and rests for a human. The journey
  runs through the PRODUCTION launcher — a real `WatchedFabroLauncher`, a real
  `FabroPort`, the real per-poll observation seam, the real export-then-terminate
  precondition and real threading — with only the fabro subprocess stood in, and
  stood in AT THE ARGV, because every sub-scenario is about which call a poll
  ISSUES and in which ORDER and no returned verdict can tell a cancel that
  exported first from one that did not.
  THE OPEN-COMMAND-NODE CASE IS THE ONE A NARROWER TEST CANNOT REACH, and it is
  what makes the two bounds independent rather than one deferring the other: the
  stall watchdog deliberately widens its window to an open command node's own
  timeout, so the fixture scripts a REAL `janitor` start event with no
  completion AND a 36000-second `janitor` timeout, which means the production
  stall decision genuinely would not cancel for hours — and the budget cancels
  anyway. Three further things an editor must not weaken. The pointer is read
  back off the tenant's own comment surface and indexed on `text`, never through
  `bd show --json`, which carries no bodies at all and reports every landed
  write as lost; a pointer read out of the journal alone is satisfied by a write
  nobody confirmed. The queue-time case keeps the wall clock advancing a FULL
  BUDGET PER POLL while the factory reports the run `runnable` throughout, so
  the absence of a cancel is evidence the clock was never fixed rather than
  evidence the clock never advanced. And the layer is asserted beside the
  budget, because 3600 seconds is a deliberate repository override in this
  fixture and only the layer separates that from a target that inherited the
  fleet default.
  ONE SUB-SCENARIO THE LAUNCHER CANNOT REACH is driven through the production
  `gather_resume` instead: "A budget cancel between publication and capture can
  anchor resume" is a claim about what a LATER invocation reads off the row this
  watchdog wrote. The two halves are joined HERE rather than in two unit
  modules — the journal that case reads is rendered by the production
  `run_wall_budget_exceeded_record`, so a respelling of the stage on either side
  fails the case instead of leaving two self-consistent modules that never meet,
  and without the join "the budget record anchors" is a claim about a row a test
  author typed. The entered stage is asserted as `proof_capture` rather than
  merely "an anchor exists", because the pull request's proof record is ANOTHER
  run's and its `captured` verdict implies `review`: the stage is the only thing
  that separates the budget row's reading from the record's. Its control
  rewrites that same row's `executing_stage` to `janitor` and asserts the anchor
  falls BACK to the proof record, since "the budget record anchored" is
  otherwise equally consistent with a reader that anchors on any budget row —
  including a rework round whose head would not carry the rework.

- `test_implement_completion_field_scenario204.py` — binds
  `SPECIFICATION/scenarios.md` Scenario 204 and the v165 clause "An implement
  turn that ends incomplete does not succeed": the implement stage's outcome is
  decided from a structured completion field the turn states, and an incomplete
  or UNSTATED one fails the stage with a partial-progress cause on the same
  failure edge any other implement failure takes. The measured incident is run
  01M58QNY3ZNM2YCVVB9G2383M0, whose turn ended "Partial progress only" with one
  declaration and one test committed and was recorded SUCCEEDED, after which
  janitor, publication and capture were all spent before the feature was found
  absent. Two layers, neither establishing the other: the committed GRAPH
  decides the gate's position, routing and cost, and the gate's own SCRIPT BYTES
  decide what counts as a stated completion — so the three sub-scenarios take
  those bytes through `parse_dot_graph` and execute them against a real
  throwaway clone, because every arm is shell and a substring assertion cannot
  tell an arm that RUNS from one sitting behind an earlier `exit`. Three
  controls carry it. The stated-complete case is the control for the two
  failures, since a script that always exited non-zero satisfies both and stops
  every conforming run at the gate. The EMPTY record is asserted beside the
  absent one, because an emptied file is what a half-written record leaves
  behind and a `test -f` guard would admit it. And the stale-cause case asserts
  a passing gate leaves no cause standing, since the terminal reads that file
  whichever stage ended the run — an inherited value would be reported as the
  question for a failure somewhere else entirely. The budget case asserts the
  EXACT visit count the gate is billed at rather than "more than nothing": a
  node absent from that table is billed at ZERO and is one the Dispatcher can
  kill the engine out from under, while a budget of one is reachable by a second
  attempt of the turn it guards and would read as correct. The prompt half of
  the clause is `tests/prompts/test_implement_completion_field.py`.

- `test_session_recovery_receipt_scenario162.py` and
  `test_session_recovery_reconciliation_scenario163.py` — bind
  `SPECIFICATION/scenarios.md` Scenarios 162 and 163 and the consumed-recovery
  half of `SPECIFICATION/contracts.md` §"Launch obligations and consumed
  recovery". Both drive the PUBLIC consumer pass — `consume_recovery_obligation`
  over a real on-disk attempt store — rather than the grades in isolation,
  because every claim here is about what a real pass LEAVES BEHIND and a
  hand-built record satisfies each assertion while establishing nothing about
  the path a daemon takes. Nothing is stood in but the two seams the product
  publishes for it: the sanctioned command and the durable-effect lookup.
  Four pairings must not be split. 162's unconsumed leg is a REAL deferred pass
  behind a valid HOLD and its executed leg CONTINUES THE SAME ATTEMPT, so
  consumption becoming observable is attributable to the execution rather than
  to a second fixture — a separate attempt for the executed leg agrees with a
  build that marks every claimed recovery consumed. 163's convergence case
  shares ONE command object across a first pass, a duplicate and a replacement
  consumer at a new generation, so "one effect" is a count of real invocations
  rather than an inspection of three returned values. Its gate control is the
  identical evidence with the gate SUCCEEDING, asserting the same operation,
  because the failed-gate case alone is equally consistent with a build that
  redispatches on any gate failure and happened to be handed a merge — the
  fixture is the measured 2026-10-09 case, where a gate reported FAILED at
  05:19:06Z for a pull request that merged at 05:18:03Z. And the ambiguous leg
  asserts the lookup was CONSULTED and the command was NOT, across both the
  unobservable round and the recovering one, since `uncertain` twice over is
  equally consistent with a pass that never asked. The ambiguous leg uses its
  own attempt, because a recorded effect short-circuits the very lookup it
  exists to exercise. 162 asserts fulfillment as an ABSENCE OF VOCABULARY — the
  consumption grade's state set cannot express it and the required-result
  identity survives untouched — which is what leaves that question with the
  relay authority that owns it.

- `test_sandbox_history_preparation.py` — the FIRST `[[run.prepare.steps]]` entry
  of the shipped implement-work-item run config, EXECUTED under `/bin/sh` against
  real complete and shallow clones (work-item bd-ib-ukht2p). It executes rather
  than matching the command line because the assertion is what the step does to a
  clone, and a conditional that inspects the wrong thing — or swallows a failure
  behind a successful fallback — reads as correct and is not. Three things carry
  the module. The measured failure is its own case: the retired unconditional
  `git fetch --unshallow --quiet` must still be refused by the SAME complete
  fixture, so the positive reading is evidence of the repair rather than of a
  fixture that was shallow all along. The two fail-closed controls are separate
  cases, one per command that can fail, each reading the recorded `git` argv to
  say WHICH command was reached, since one exit code cannot distinguish them. And
  `GIT_CEILING_DIRECTORIES` is pinned at the fixture root: this suite's pytest
  basetemp carries a `.git` of its own, which is an ANCESTOR of every `tmp_path`,
  so without the ceiling the inspection-failure control walked out of its fixture
  and answered confidently for the suite's own repository.

- `test_check_suite_plugin_gate_reentry.py` — every graph node that runs the
  declared check suite re-enters the materialized plugin-cache gate BEFORE the
  suite (work-item bd-ib-3f79, the recurrence of bd-ib-cewr.3). Its docstring
  carries the MEASURED CAUSE the two earlier readings never established, taken
  from this repository's own live Fabro sandbox: the Claude Agent SDK's session
  start is a registry SYNC and not an installer, so it writes a record whose
  `installPath` is a COMPUTED cache location and leaves materialization to the
  loader — which rules the atomic-install fix shape out, since the write happens
  inside the closed-source engine. The janitor cases EXECUTE the shipped node
  bytes against a prepared plugins root under `tmp_path`, never the enclosing
  run's own; the unrepairable case asserts the stand-in suite's marker is ABSENT,
  which is the ordering proof and the one assertion the pre-repair bytes could
  not satisfy. One case isolates cache completeness from pin enforcement by
  pinning the build first and breaking its cache afterwards, and asserts the
  advanced-build marker is absent so the drop is attributable to the
  `required_paths` reading alone. `publish_draft` carries no re-entry of its own
  and the last case measures WHY — `janitor` is its only in-edge — rather than
  trusting it.

Coverage rules: 100% line + branch on every covered module, as everywhere in
this repo. Build state through the public store/client seam (or a small
read-only stub for shapes the fake's public surface never produces); never read
or write a live tenant DB.
