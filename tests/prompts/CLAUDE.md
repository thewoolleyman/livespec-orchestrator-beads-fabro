# tests/prompts/

Contract tests over the Fabro workflow PROMPT PROSE under
`.claude-plugin/.fabro/workflows/*/prompts/` — the agent-instruction bundle the
factory injects into each ACP node turn. The tier is declared in
`pyproject.toml` (`scenario_tiers`, and the coverage `omit` list, because the
prose is not executable product code), and its dotted node-id prefix is
`tests.prompts`.

What belongs here: an assertion about what a prompt SAYS, where the prompt is
the deliverable. Behavior that runs on the host — the Dispatcher's rendering of
`{{ inputs.* }}`, the graph's node attributes, the seam-equivalence gate — is
covered by `tests/livespec_orchestrator_beads_fabro/` and `tests/integration/`
instead.

- `test_acp_node_turn_end_discipline.py` — bd-ib-5qlr: every `backend="acp"`
  node prompt carries the turn-end instruction that forbids leaving a
  backgrounded tool call running, in ONE wording across all of them. The prompt
  list is DERIVED from `workflow.fabro`'s own node blocks rather than spelled in
  the test, because a hand-written list is blind to an ACP node added later; a
  sibling control asserts the derivation reached every prompt file on disk, so a
  scan that matched nothing fails rather than reporting clean.
- `test_proof_record_size_budget_discipline.py` — bd-ib-555xcd: every prompt that
  publishes a Proof of Done record states the declared size budget, measures the
  rendered body in BYTES, and refuses to post over budget. The two posting
  PRIMITIVES enforce this in code; the two factory STAGES hand-format their record
  and post it with `gh pr comment`, so for them the budget is prose — and the
  figures are IMPORTED from `_dispatcher_proof_budget` rather than spelled, so a
  constant changed without re-wording the prompts fails here instead of as a
  rejected comment in production. The publisher set is derived by CONTENT (a
  prompt carrying both the record title and the post call), with a control
  asserting it reached the two publishers known today.

- `test_proof_record_observation_scope_discipline.py` — bd-ib-v4exlm: both proof
  stages write the `Working directory: .` line ahead of their numbered steps,
  and only when every step ran from the repository root; `proof_verify` also
  writes one `Read: <path> <identity>` line per working-tree path operand, whose
  identity is the RAW bytes (`git hash-object --no-filters`) rather than the
  filtered hash. Both spellings are imported from
  `_dispatcher_carry_forward_grammar`, the module whose shipped program parses
  them, so a re-wording on either side fails here. A prompt test because neither
  line is rendered by any Python caller — and a reader whose writer never writes
  the line reports a correct observation while permanently retiring the
  carry-forward route.

- `test_proof_capture_record_run_id.py` — bd-ib-oa67lv: every record header the
  proof-capture prompt publishes — the `captured` record and the `not_captured`
  finding — resolves its run id from `livespec.factoryRunId` INSIDE the command
  that writes the header, and the capture stops with the needs-human protocol
  rather than posting a header with an empty one. The needles are scoped to the
  indented COMMAND BLOCK each `printf` sits in, because the defect was not a
  missing source: Step 4 already named `livespec.factoryRunId` correctly as its
  second source, and the posting command — a later and separate tool call —
  expanded the hook-only `$FABRO_RUN_ID`, which no agent shell holds. A
  whole-file probe reads that shape as satisfied. The hook-only variable is
  pinned by ORDER rather than by absence, so the prohibition explaining the
  hazard is still allowed to name it. A prompt test because the header is
  authored out of this prose and rendered by no Python caller, and because both
  mechanical halves that CAN observe the fault — the publication-head refusal
  and `proof_grade`'s — fire only after the capture has posted a comment that
  cannot be edited.

- `test_proof_capture_git_history_anchoring.py` — bd-ib-ltjrn: the proof-capture
  prompt's `Deterministic` bullet requires a reproduction step that reads git
  history to name a fixed commit sha or use a depth-independent predicate,
  never a fixed-size window counted from HEAD; it carries the reason (the
  engine appends a checkpoint commit after every node, so HEAD moves between
  capture and replay) and one worked example per verdict. The needles are
  scoped to that BULLET rather than the whole prompt, because the record's
  own "read the head from the forge, not the clone" paragraph would satisfy a
  whole-file probe over a bullet that said nothing. A prompt test because the
  steps are authored by the agent out of this prose and rendered by no Python
  caller: a HEAD-anchored step passes capture and surfaces one stage later as
  a `not_reproduced` verdict against a correct implementation.

- `test_review_proof_record_currency.py` — bd-ib-qnokup: the review prompt
  judges a captured record's currency by comparing TREES — a record is CURRENT
  when the tree of the commit it names equals the tree of the head under review
  — and it forbids the timestamp, sha-equality and commit-order readings
  outright, carries the moving-HEAD reason in the rule, keeps an absent record
  and an absent head declaration blocking, and routes its finding through this
  graph's `fix` label. A prompt test because the judgement is made by the
  `review` agent out of this prose and is rendered by no Python caller: a
  reviewer comparing timestamps emits a well-formed blocking finding, the run
  re-enters capture, and the defect surfaces only as a run that spends its whole
  firing budget rejecting correct records (measured 2026-10-20 on runs
  `01M5CE38SZJW` and `01M5CDH2FZSE`). The needles are scoped to the currency
  SECTION, since the prompt says `[BLOCKING]` a dozen times for a dozen
  unrelated conditions and separately tells the capture prompt where to read its
  head. The routing case is POSITIVE rather than a probe for the absence of
  v175's reverted `recapture` label: it enumerates the labels the prompt offers
  and requires exactly the two the shipped graph has, because an absence probe
  could never return a hit. The SEVERITY end of the same section stays bound in
  `tests/integration/test_workflow_proof_verify_scenario132.py`.

- `test_proof_record_self_contained_programs.py` — bd-ib-qnokup: the
  proof-capture prompt's `Self-contained` bullet scopes the publish-the-source
  duty by what the REPLAYER has — every program a step executes that is neither
  tracked in the repository at the commit the record names nor an installed tool
  invoked by its name goes into the record, inline or as a named proof asset —
  and it states both exemptions and the scratch directory that is untracked by
  construction. A prompt test for the reason its sibling modules record: the
  steps are authored out of this prose and rendered by no Python caller, so a
  record whose step runs an untracked helper publishes cleanly and surfaces one
  stage later as a `not_reproduced` verdict against a correct implementation.
  The needles are scoped to that BULLET, because the prompt's Step 5 body list
  separately requires the `COMPLETE SOURCE of any program it runs` and would
  satisfy a whole-file probe over a bullet that scoped nothing. The
  OUTPUT-IS-NOT-SOURCE clause and the round trip it pairs with stay bound in
  `tests/integration/test_proof_finding_work_order_scenario138.py`.

- `test_implement_coverage_before_green.py` — bd-ib-z6fmp: the implement-stage
  prompt requires the repository's per-file coverage check to be run over the
  FULL suite, with every gap closed, BEFORE any Green commit or amend — the hook
  runs the whole declared check suite and fails at that gate LAST, so a gap
  found there costs two full suite runs. The prompt is DERIVED from the graph's
  `implement` node rather than named, with a control asserting the derivation
  found exactly one such node whose prompt is on disk. The changed-files-only
  prohibition is pinned POSITIVELY (both physical lines of the sentence are
  required) because a probe for the absence of a narrowing phrase could never
  return a hit and would read clean over a prompt that said nothing. This tier
  reads the COMMITTED prompt; its DISPATCHED counterpart — the same instruction
  in the per-dispatch payload, with the check-suite input bound from the target
  repository's own declaration — is
  `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_payload_implement_prompt.py`,
  per the rendering-seam convention below.

- `test_implement_completion_field.py` — bd-ib-ahxcjx, the PROSE half of the
  v165 clause "An implement turn that ends incomplete does not succeed": the
  implement prompt directs the turn to end its final reply with a structured
  completion field stating whether the Definition of Done is complete on the
  committed branch, and enumerates all three verdicts — complete, incomplete,
  and stated nothing, which the clause reads as incomplete. A prompt test
  because the field is authored by the agent out of this instruction and is
  rendered by no Python caller, so nothing host-side can observe whether a turn
  was ever asked for it. The record PATH is derived from the completion gate's
  own script rather than spelled on both sides, because the two halves are
  useless apart and a rename of either reads as a turn that recorded correctly
  and a gate that found nothing — which the gate then reports as the agent's
  fault. The mechanism that reads the field is
  `tests/integration/test_implement_completion_field_scenario204.py`.

- `test_fix_check_suite_once_per_tree_scenario199.py` — bd-ib-k6dwyv, and the
  registry binding for `SPECIFICATION/scenarios.md` Scenario 199: the fix-stage
  prompt counts a commit whose repository pre-commit hook ran the FULL check
  suite green on the exact committed tree as that turn's run of the suite, and
  directs no second run on that same tree — while a changed tree and a partial
  hook run, such as a Red commit on the hook's fast path, both still owe a full
  run before the turn ends, and the refresh-repair steps are governed
  identically on the tree the repair produced. A prompt test because the
  obligation is discharged by the agent out of this prose and is rendered by no
  Python caller: nothing host-side can observe whether a turn chose to run the
  suite twice, and the engine reports the resulting timeout as an ordinary node
  failure. The bound node id is the DIRECTIVE-SITE enumeration, not a case
  reading the new section: the defect was never a missing paragraph — each site
  that directs a run said to re-run it until green with no exemption, so a rule
  stated in a section the directive never references leaves the directive
  saying the thing that cost run 01M56YAEWMS8 its turn. That case collects
  every list item carrying the check-suite workflow input and requires the rule
  AT each of them, so a third directive added later without it fails; its count
  control asserts the enumeration reached both known sites, because a splitter
  that matched nothing would otherwise report clean. Items are split at the
  list MARKER rather than at blank lines, since the refresh-repair steps are
  adjacent lines and a blank-line split would let a qualifier on step 1 satisfy
  an assertion about step 2.

- `test_commit_hook_outlasts_a_tool_call.py` — bd-ib-aaxsta: the implement and
  fix prompts carry ONE wording of the four commit-hook directions — how long
  the hook aggregate runs (minutes, measured at 142 and 553 seconds), that a
  tool call returning mid-hook is not a failed commit, that a running hook is
  waited out before any further commit without killing its processes and
  without a second live `git commit`, and that the turn does not end while a
  hook it started is still running. A prompt test because no timeout fired on
  the runs that lost their Green amend: the turns ran 32.6 and 27.6 minutes
  against a 14400-second node limit and both ACP turns ended `end_turn`, so
  nothing host-side could have intervened and the prompt is the whole
  mitigation. The two prompts are derived from the graph's `implement` and
  `fix` node blocks, with a control asserting one prompt per node on disk, and
  the fix prompt's compliance is asserted BOTH per-needle and as byte-identity
  with the implement section, because two paraphrases satisfy a needle list
  while drifting apart. Every needle is a sentence that must be PRESENT: an
  absence probe would read clean over the prompts as they stood, which is the
  state the item exists to end. Two needles pin compatibility with
  `contracts.md` §"A commit leg completes past one tool call" — the waiting
  direction admits a commit runner's bounded waits, and over-limit reaping is
  the run's job, not the agent's — so bd-ib-sufca7, which owns that clause and
  Scenario 179's registry binding, can ship the runner without contradicting
  this prose.

Conventions:

- Read the prompt as COMMITTED BYTES. Never render it through a template engine
  here; the rendering seam has its own tests.
- Prompt prose is hard-wrapped, so a needle must sit within one physical line,
  or the probe can only fail silently while the prose says exactly the thing.
- Derive the set of prompts under test from the graph, never from a literal
  list, and carry a control proving the derivation reached them all.
