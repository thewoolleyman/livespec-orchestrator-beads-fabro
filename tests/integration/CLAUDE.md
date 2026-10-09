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

Coverage rules: 100% line + branch on every covered module, as everywhere in
this repo. Build state through the public store/client seam (or a small
read-only stub for shapes the fake's public surface never produces); never read
or write a live tenant DB.
