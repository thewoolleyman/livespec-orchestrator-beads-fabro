# tests/livespec_orchestrator_beads_fabro/commands/

Tests for the thin-transport command modules under
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/`. One
`test_<name>.py` per module:

- `test_next.py` — the ranker. Asserts `rank_candidates` /
  `build_envelope` produce the correct ripeness ordering (priority,
  origin, captured_at, id), the `{candidates[], pagination}`
  envelope shape, `--limit`/`--offset` slicing, the empty-list
  no-work signal, and `depends_on` readiness gating (candidates with
  an OPEN dependency are absent from the ranked list).
- `test_list_work_items.py` — listing,
  filtering, and the `--json` vs human output contracts.
- `test_context.py` and `test_context_envelope.py` — the `context` read
  primitive. The first drives `main()` end to end over a fixture tenant
  carrying both child linkages (a dotted-id child and an edge-linked one)
  and asserts the `--json` envelope, the human rendering, the
  plan-slug-equals-epic-id resolution, the byte-identical re-run with an
  unmodified store, and the not-found refusal. The second covers the
  assembly decisions a well-formed tenant cannot reach: the `omitempty`
  sparse-record tolerances, the untagged epic still carrying a
  `plan:<slug>` marker, the archived plan directory, and the ancestor walk
  that skips a parent with no plan slug.
- `test_detect_impl_gaps.py` — mechanical gap detection emits the
  expected gap-id set; verifies it never mutates the JSONL.
- `test_config.py`, `test_cross_repo.py`, `test_jsonc.py` — the
  private helper modules (`_config`, `_cross_repo`, `_jsonc`):
  store-path / project-root resolution, manifest loading +
  `is_item_ready`, and JSONC parsing.
- `test_orchestrator.py` — the `orchestrator` contract CLI and its
  `_orchestrator_*` helpers: per-subcommand exit codes, the
  spec-reader category exposure, gap-capture Ledger writes (the one
  LEGITIMATELY mutating surface here — capture is its contract job),
  drift-capture routing through an injected propose-change CLI, and
  the injected-argv / payload wire-shape validation.

- `test_plan_result_targets.py`, `test_plan_result_reference.py`,
  `test_plan_result_observation.py`, `test_plan_result_repository.py`,
  `test_plan_result_ledger.py`, `test_plan_result_forge.py`,
  `test_plan_result_proof.py` and `test_plan_result_reader.py` — the eight
  modules of the shared authoritative result reader. The scenario itself is
  bound at the integration tier by
  `tests/integration/test_plan_result_reader_scenario146.py`; these cover what
  that tier cannot observe. Two of them are worth knowing about before editing:
  `test_plan_result_forge.py` asserts each adapter's ARGV on its own, because the
  argv is the only thing that decides which repository and which ref the answer
  is about and a stub that answers whatever it is asked cannot tell a correct
  query from a plausible one; and `test_plan_result_reader.py` asserts the
  fail-closed ORDER of the reader's three steps by counting the commands the
  runner received, with a positive control showing that same runner IS reached
  once the parse and the resolution both succeed — without it, a reader that
  never reached any adapter would satisfy both order cases.

- `test_plan_result_proof_subject.py` sits beside those eight and covers the
  subject-record read behind the verified-proof adapter's merge-containment
  requirement: the sparse audit shapes that record no merge and therefore leave
  that requirement vacuous. It is separate from `test_plan_result_proof.py`
  because those shapes were found by a coverage measurement taken after that
  module's Red was authored, and a Red's test bytes are fixed across its
  Red-to-Green pair. Its cases assert SATISFIED rather than merely "not
  unobservable", and assert that no second comparison base was named — which is
  what tells "the requirement was vacuous" apart from "the requirement was asked
  and happened to pass".

  It also owns the OTHER half of that read, and the two halves are what give each
  other meaning: audit evidence that is PRESENT holding a value of the wrong type
  is `unobservable` naming the LEDGER, because `omitempty` omits a field and never
  retypes one, so a present wrong type cannot be the sparse encoding of an
  absence. Those cases assert that NO command ran at all, which is what tells a
  ledger-side refusal apart from a comparison that was asked and failed. Keep both
  halves parametrized in this one module: the vacuous arm and the malformed arm
  differ only in the shape handed to the stub, and splitting them across files is
  how a later edit silently moves a shape from one verdict to the other — the
  defect these cases were added to close, where a merge nobody could read graded
  as a merge nobody recorded and the containment relation then did not run.

- `test_fabro_executed_candidate_attribution.py` — the attribution of a
  provider ceiling to the candidate that ran. Its two CONTROLS are the
  load-bearing cases and neither works without the other: an unlabelled failing
  node keeps the v107 cause-text provider, and a recorded identity cannot
  MANUFACTURE a ceiling on a failure that reports none. Without the second, an
  attribution that fired on every failure would satisfy the positive case while
  labelling ordinary transport faults with a vendor; without the first, one that
  fired only where an identity exists would strand the legacy posture. The
  positive case asserts the ARRIVING attribution is `codex` before asserting the
  attributed one is `anthropic`, which is what makes it able to fail — a fixture
  whose cause text already named Anthropic would pass against no implementation
  at all.

- `test_fabro_reattach_executed_candidate.py` — the same attribution through
  the run observation that WIRES it, which is a different claim: the reading is
  available either way, and these cases decide whether a real dispatch takes
  it. Its `ps` fixture carries TWO rows and the non-matching one is the other
  vendor's, so a reader that took the list head — or merged every row — fails
  here instead of landing on the right answer by luck. Its runner is keyed on
  the fabro SUBCOMMAND rather than on call order, which is what lets the
  ordinary-failure case assert that the labels read did not happen AT ALL; a
  reply list would make that absence look like an unconsumed element, which is
  also what a reordered pair looks like.

- `test_provider_exhaustion_executed_domain.py` and
  `test_fabro_message_only_executed_candidate.py` complete that attribution's
  grading, and both are CONTROLS: they pin consequences of the two cases above
  rather than behaviour of their own, so neither could fail before the
  attribution landed and both were committed on the suite-green leg. The first
  grades the hold's SCOPE — a provider value is only right in so far as the
  record written under it holds the right dispatches and admits the rest — and
  its negative case sits on the SAME journal as its positive, because a hold
  that refuses everything satisfies the positive edge exactly as well as a
  correct one does. The second grades the Petri-era shape, where the failure
  block is RUN-LEVEL and the failing attempt can only be read out of the
  `stages` map; its own control is the list-shaped `stages` that carries no
  per-stage state, which establishes no identity and is asserted to keep the
  v107 attribution so a later reader does not mistake that degradation for a
  defect.

- `test_dispatcher_fabro_currency.py`,
  `test_dispatcher_fabro_currency_sources.py`,
  `test_dispatcher_fabro_release_cache.py`,
  `test_dispatcher_fabro_release_observation.py` and
  `test_dispatcher_fabro_currency_gate.py` — the five modules of the
  dispatch-time Fabro currency admission. The scenario itself is bound at the
  integration tier by
  `tests/integration/test_fabro_currency_admission_scenario130.py`; these cover
  what that tier cannot observe. Three of them are worth knowing about before
  editing. The sources module asserts TWO claims off the SEAM rather than off a
  return value, because no return value can carry them: that the serving commit
  is parsed from the SERVER's section and not the client's (the two sections
  differ only in their label, and a whole-text scan matches the client line
  first), and that the ancestry walk is BOUNDED BY THE OBSERVATION (a claim about
  how many forge calls were spent, which a walk that re-asked or paged beyond
  what it was handed satisfies at every other assertion). That bound is asserted
  in BOTH directions, and the second direction is the one a cap defeats: a
  sibling case puts a genuine ancestor at index 44 of 60 and asserts the BASE
  rather than the call count, because a walk that spent the calls and still
  returned `None` is the failure being closed — the measured 40-candidate cap
  that refused the ratified 0.254 carrier for having "no release-tag ancestor".
  For the same reason the no-ancestor case reads its scope sentence off the
  observation's own SIZE rather than off a constant, which kept reading correct
  after the cap had made it false. The observation module reads the forge CALL COUNT in every case,
  since "served from the cache" is a claim about a read that did NOT happen and
  a reading that refreshed every time returns the same value. And the gate
  module asserts target-awareness with one CURRENT target beside one STALE one,
  which is the only shape that can fail for the right reason — a gate reading a
  single fleet-global surrogate returns one verdict for both, and both a
  both-current and a both-stale fixture would agree with it.

- The `test_plan_epoch_*.py` family covers the plan-authority epoch chain. Five
  of them are worth knowing about before editing. `test_plan_epoch_chain_
  serialization.py` injects the WINNER's whole transition at the one instant
  that reproduces a genuine race — after the loser has read the token and found
  it open, before its own close reaches the server — because that is the only
  interleaving that exercises the SERVER's conditional close rather than this
  plugin's own pre-check; a sequential second writer is refused earlier, by its
  own stale read, and a test that only did that would pass against a chain with
  no exclusion at all. `test_plan_epoch_chain_scaling.py` measures the live
  token count at EVERY step rather than at the end, since a chain that
  accumulated tokens and swept them at the close would satisfy an end-state
  assertion while holding an unbounded set in between; and it compares payload
  sizes only across transitions whose ring entries share one decimal width,
  because the width of the epoch counter is the one quantity that does grow and
  a window straddling a digit boundary reads that widening as unbounded growth.
  `test_plan_epoch_reconcile.py` produces each partial write through the TOKEN
  primitives, which is what a stopped writer actually leaves behind, and its
  first case is the positive control: without a healthy chain reporting
  NOTHING, a verifier that called every chain a partial write would satisfy
  every other case in the module. Its live-token-count case commits a
  transition BEFORE the one it stops, because the predecessor a stopped writer
  strands is the one its observed head already named — a stop taken against a
  genesis-only chain has no predecessor to leak and passes whether or not the
  reconciler sweeps one; and it reads the count after the reconcile AND after
  each later commit, since a reconciler that swept the right record while
  breaking the ordinary commit path would satisfy a single end-state reading.
  `test_plan_epoch_chain_close_readback.py`
  fails ONLY the read-back and lets the close itself land, which is the single
  interleaving that separates a won close from a lost one — its helper reads
  the head BEFORE installing the failure, because a patch covering the writer's
  own stale check refuses it before any close is attempted and the test then
  proves nothing about a read-back; and its second case is the positive
  control, since a guard returning the unknown outcome for EVERY unadmitted
  close would satisfy the first case while leaking a token on every lost race.
  And three modules
  (`test_plan_epoch_chain_retry.py`, `test_plan_epoch_genesis.py`,
  `test_plan_epoch_chain_close_readback.py`) spell their
  expected constants as LITERALS and bind them to the exported names with one
  `getattr` assertion, because each module's Red predates the constants it
  binds and a Red's test bytes are fixed across its Red-to-Green pair.

- `test_dispatcher_canary.py` covers the committed canary fixture
  (`orchestrator-image/canary-fixture.md`) and the four ways a committed
  fixture can be malformed, graded through the SAME ratified
  Definition-of-Done parse the gate's host-side wall reads — a second parse
  here is the drift that produced the two refused canaries this fixture
  exists to prevent. The recipe that files and dispatches from it lives at
  `tests/test_canary_dispatch_recipe.py`, one tier up, because its subject is
  the justfile recipe and the shell script rather than this module; the
  intake-refusal arms are HERE rather than there because they were found by a
  coverage measurement taken after that module's Red was authored, and a Red's
  test bytes are fixed across its Red-to-Green pair.

Conventions:

- Exercise both `main()` (supervisor: exit codes, stdout/stderr
  contract, usage-error exit 2) and the named railway helpers
  directly.
- Assert query-only behavior for the thin-transport modules
  (`list-*`, `next`, `detect-impl-gaps`) — they MUST NOT write to
  the store; a test that observes a store mutation there is a
  regression signal. The `orchestrator` gap-capture subcommand is
  the deliberate exception (capturing INTO the store is its job);
  its tests assert the writes instead.
- Use `tmp_path` for store + `.livespec.jsonc` fixtures, `capsys`
  for output capture; `monkeypatch.chdir(tmp_path)` for any
  `Path.cwd()`-default path.
