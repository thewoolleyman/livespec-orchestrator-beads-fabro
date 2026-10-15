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

- `test_committing_stage_commit_runner.py` — bd-ib-sufca7: every ACP node prompt
  whose stage COMMITS routes each of its commits — Red, Green amend, any later
  one — through the Dispatcher-materialized sandbox commit runner and its
  bounded waits, and owes every commit run it started a terminal state or a stop
  before its final message. The committing set is derived by CONTENT (a prompt
  naming the `Red-Green-Replay` ritual), and the discriminator is measured rather
  than assumed: the token appears in exactly `implement.md`, `fix.md` and
  `review-fix.md` and in none of the other five ACP prompts, and it is
  vocabulary those three carried BEFORE the runner section existed, so the
  selection cannot be circular with what the cases assert. The runner PATH is
  imported from `_dispatcher_sandbox_commit_runner` rather than transcribed — a
  literal here would keep agreeing with itself while the prompt and the prepare
  step diverged, leaving the stage reaching for a program that is not there. Two
  controls carry the module: the derivation is asserted to have found exactly
  those three (a drifted scan would select none and every parametrized case would
  silently vanish), and every NON-committing ACP prompt is asserted NOT to carry
  the section, because the detached commit run is the ONE exception a committing
  stage makes to its rule against backgrounding a tool call and that carveout
  must widen by ruling rather than by copy-paste.

Conventions:

- Read the prompt as COMMITTED BYTES. Never render it through a template engine
  here; the rendering seam has its own tests.
- Prompt prose is hard-wrapped, so a needle must sit within one physical line,
  or the probe can only fail silently while the prose says exactly the thing.
- Derive the set of prompts under test from the graph, never from a literal
  list, and carry a control proving the derivation reached them all.
