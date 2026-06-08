# livespec_impl_beads/commands/

The implementation modules behind the thin-transport wrappers. One
public module per query-only skill:

- `detect_impl_gaps.py` — mechanical spec→impl gap detection via the
  Spec Reader; pure read-and-emit (never mutates the JSONL, never
  prompts).
- `list_memos.py`, `list_work_items.py` — JSONL store listing.
- `next.py` — the ripeness ranker; a pure function of work-items
  JSONL state plus the cross-repo manifest at
  `<project-root>/.livespec.jsonc`.

Each public module exports `main(argv=None) -> int` (the supervisor
the wrapper calls) plus its named helpers, all enumerated in
`__all__`.

Private helper modules (underscore-prefixed) carry shared plumbing:

- `_config.py` — store-path / project-root resolution
  (`resolve_store_config`).
- `_cross_repo.py` — cross-repo manifest loading and the
  `is_item_ready` readiness predicate; consults
  `livespec_runtime.cross_repo.resolve_ref` for `depends_on` gating.
- `_jsonc.py` — JSONC parsing for `.livespec.jsonc`.

Rules an agent editing this tree must follow:

- `main()` is the only place `sys.stdout.write` / `sys.stderr.write`
  are permitted, and only for the documented CLI output contract
  (the `--json` envelope, human lines, usage errors to stderr with
  exit 2). `print()` is banned. Do NOT scatter writes into helpers.
- These are QUERY-ONLY skills by contract. Do NOT add mutating CLI
  flags (`--update`, `--write`, etc.) to `list-*` or `next` — that
  is a contract violation per `SPECIFICATION/constraints.md`
  §"Forbidden patterns".
- Catch the EXPECTED `livespec_impl_beads.errors` exceptions at
  the `main()` boundary and map them to exit codes; never let an
  expected error escape as an uncaught traceback.
- Keyword-only arguments (`*` separator) on every helper; the
  `main(argv)` positional is the argparse-convention exemption.
- `next`'s readiness gating MUST exclude any candidate with a
  `depends_on` entry resolving to `RefStatus.OPEN`; excluded items
  are absent from the ranked list, not surfaced at lower urgency.
