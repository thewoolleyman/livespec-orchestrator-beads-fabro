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
- `orchestrator.py` — the orchestrator-side contract CLI (per
  livespec contracts.md §"Orchestrator CLI contract — the three
  named CLIs"): subcommand parsing + expected-error → exit-code
  mapping; subcommand bodies live in the `_orchestrator_*` private
  helpers (`_orchestrator_shared.py`, `_orchestrator_spec_reader.py`,
  `_orchestrator_gap_capture.py`, `_orchestrator_drift_capture.py`).
  `gap-capture` is the ONE mutating command surface here (writing
  gap-tied work-items to the beads Ledger IS its contract job); the
  query-only rule below still binds every `list-*`/`next` module.
- `dispatcher.py` — the orchestrator-PRIVATE thin Dispatcher of the
  Beads/Dolt + Fabro reference orchestrator (NOT a contract CLI and
  NOT a skill surface): `ledger-check` runs the three dispatch-safety
  Ledger integrity checks; `spec-check` runs the three re-homed
  spec-context work-item invariants (no-stalled-epic /
  no-stale-gap-tied / unresolved-spec-commitment) against the tenant
  rows plus the spec tree; `janitor-check` runs the three re-homed
  stale-cleanup checks (no-stale-merged-branch /
  no-stale-merged-pr-branch / no-stale-worktree) against the repo's
  git/gh state; `dispatch`/`loop` drive ready work-items
  through the `.fabro/workflows/implement-work-item/` phase graph
  (worktree → Fabro run → auto-merge confirmation → post-merge
  janitor → Ledger close + journal). Bodies live in the
  `_dispatcher_*` private helpers (`_dispatcher_ledger_checks.py`,
  `_dispatcher_spec_checks.py`, `_dispatcher_spec_commitments.py`,
  `_dispatcher_janitor_checks.py`, `_dispatcher_plan.py`,
  `_dispatcher_engine.py`, `_dispatcher_io.py`). Its Ledger writes
  are machine-path dispositions of already-filed items
  (close-on-confirmed-merge).

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
