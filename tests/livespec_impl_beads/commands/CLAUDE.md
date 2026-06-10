# tests/livespec_impl_beads/commands/

Tests for the thin-transport command modules under
`.claude-plugin/scripts/livespec_impl_beads/commands/`. One
`test_<name>.py` per module:

- `test_next.py` — the ranker. Asserts `rank_candidates` /
  `build_envelope` produce the correct ripeness ordering (priority,
  origin, captured_at, id), the `{candidates[], pagination}`
  envelope shape, `--limit`/`--offset` slicing, the empty-list
  no-work signal, and `depends_on` readiness gating (candidates with
  an OPEN dependency are absent from the ranked list).
- `test_list_memos.py`, `test_list_work_items.py` — listing,
  filtering, and the `--json` vs human output contracts.
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
