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

Conventions:

- Read the prompt as COMMITTED BYTES. Never render it through a template engine
  here; the rendering seam has its own tests.
- Prompt prose is hard-wrapped, so a needle must sit within one physical line,
  or the probe can only fail silently while the prose says exactly the thing.
- Derive the set of prompts under test from the graph, never from a literal
  list, and carry a control proving the derivation reached them all.
