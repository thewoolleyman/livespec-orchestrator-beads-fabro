# livespec_orchestrator_beads_fabro/commands/

The implementation modules behind the thin-transport wrappers. One
public module per query-only skill:

- `detect_impl_gaps.py` — mechanical spec→impl gap detection via the
  Spec Reader; pure read-and-emit (never mutates the JSONL, never
  prompts).
- `list_work_items.py` — JSONL store listing.
- `close_work_item.py` — the atomic close + `resolution:completed`
  wrapper (the "pit of success" for the closed-item-integrity
  invariant, SPECIFICATION/constraints.md §"Closed-item integrity").
  A MUTATING helper (like `gap-capture`, not a query-only `list-*`):
  `close_completed` reads the existing item and persists a closed copy
  carrying `resolution="completed"` through `append_work_item`, so the
  `bd close` + `resolution:completed` label land in ONE store
  operation and the two-step close recipe can never be half-done.
  `main` is the thin CLI (`close-work-item <id> [--reason …]`); the
  one EXPECTED misuse (a never-filed id) maps to `WorkItemNotFoundError`
  → exit 3.
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
  (Fabro sandbox run, guarded by a coarse wall-clock progress watchdog
  that `fabro rm -f`-es a sustained-no-progress run and reports a
  distinct `stalled-no-progress` outcome → auto-merge confirmation →
  post-merge janitor in a fresh detached worktree of merged master,
  with provisioning failures classified as janitor-env-degraded rather
  than work-item failures → Ledger close + journal). Bodies live in the
  `_dispatcher_*` private helpers (`_dispatcher_ledger_checks.py`,
  `_dispatcher_spec_checks.py`, `_dispatcher_spec_commitments.py`,
  `_dispatcher_janitor_checks.py`, `_dispatcher_plan.py`,
  `_dispatcher_engine.py`, `_dispatcher_io.py`, `_dispatcher_notify.py`,
  `_dispatcher_reflection.py`, `_dispatcher_watchdog.py`,
  `_dispatcher_cost.py` — the fail-closed cost-observability seam
  (work-item 5v9: `total_usd_micros` is null on every fabro run in
  v0.254.0, so autonomous mode refuses to keep picking on unobservable
  cost; the seam y0m's spend cap builds on). Its Ledger
  writes are machine-path dispositions of already-filed items
  (close-on-confirmed-merge).
- `rebalance_ranks.py` — the orchestrator-PRIVATE, on-demand bulk
  `rank` re-key (NOT a contract CLI and NOT a skill surface; never
  auto-fires). `rebalanced(items)` orders by the canonical
  `ready_sort_key` and assigns evenly-spaced fresh keys via
  `livespec_runtime.work_items.rank.n_keys_between` (order-preserving;
  compacts fragmented keys), and `main` walks the live (non-`done`)
  heads through it and writes each changed key back via the store's
  `update_work_item_rank`. `legacy_seed(rows)` is the one-time L2 backfill
  primitive (legacy `priority → captured_at → id` seed order); it is
  reused by the fleet's L2 migration, not by `main`.

Each public module exports `main(argv=None) -> int` (the supervisor
the wrapper calls) plus its named helpers, all enumerated in
`__all__`.

Private helper modules (underscore-prefixed) carry shared plumbing:

- `_config.py` — store-path / project-root resolution
  (`resolve_store_config`).
- `_cross_repo.py` — cross-repo manifest loading (`load_manifest`) and
  raw `depends_on` entry parsing (`parse_entry`). The readiness predicate
  (`is_item_ready`), the canonical `ready_sort_key` (= `(rank, id)`), and
  `lane_of` now live in the shared
  `livespec_runtime.work_items.lifecycle` (pure functions over an
  in-memory `index: dict[str, WorkItem]`); callers (`next`,
  `list-work-items`, the Dispatcher) import them from there.
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
- Catch the EXPECTED `livespec_orchestrator_beads_fabro.errors` exceptions at
  the `main()` boundary and map them to exit codes; never let an
  expected error escape as an uncaught traceback.
- Keyword-only arguments (`*` separator) on every helper; the
  `main(argv)` positional is the argparse-convention exemption.
- `next`'s readiness gating MUST exclude any candidate with a
  `depends_on` entry resolving to `RefStatus.OPEN`; excluded items
  are absent from the ranked list, not surfaced at lower urgency.
