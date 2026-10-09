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
