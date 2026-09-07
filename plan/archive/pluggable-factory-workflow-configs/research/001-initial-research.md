# pluggable-factory-workflow-configs — initial research

## Goal

Let `.livespec.jsonc` name which Fabro workflow config (graph, steps,
per-step models) a dispatch uses — mirroring the existing
`dispatcher.factories` / `default_factory` pattern (named registry +
default + env override + CLI override + ledger-recorded retry
consistency) — entirely client-side in the orchestrator's Dispatcher.
Zero changes to the Fabro server or its API contract.

## Why this is a pure client-side change (verified, not assumed)

Confirmed live 2026-08-17 against `fabro run --help` and this repo's
`commands/_dispatcher_paths.py`:

- `fabro run <WORKFLOW>` already takes an arbitrary client-supplied
  `.fabro`/`.toml` file path per invocation. The server has no
  persistent notion of "which config" — every run is fully
  self-describing at submission time.
- Per-step model overrides already live *inside* a workflow.toml's own
  `run.inputs` block — confirmed by inspecting a live run's `run_spec`:
  `disposition_adapter` and `review_adapter` each carried their own
  `ANTHROPIC_MODEL=...`-prefixed adapter invocation string, independent
  of the top-level `run.model`.
- So "different steps, different models" is already fully expressible
  in a workflow.toml today. The only gap is *selecting between multiple
  named variants from `.livespec.jsonc`* — nothing about the feature
  requires touching Fabro itself.

## What already exists to mirror

`commands/_config.py::resolve_fabro_factory(cwd, factory=None)` is the
exact shape to copy for workflow-config resolution. Its precedence:
explicit CLI arg → non-empty `LIVESPEC_FABRO_FACTORY` env → 
`dispatcher.default_factory` in `.livespec.jsonc` → implicit `"default"`.

`commands/_dispatcher_factory_ledger.py::resolve_dispatch_factory_target()`
adds retry consistency on top: explicit arg → the factory a PRIOR
dispatch of the same work-item already resolved to (read via
`dispatch_factory_for()`) → the resolved default → records the choice
back to the ledger via `record_dispatch_factory()` so a retry reuses it.

## What's missing (the actual gap)

`commands/_dispatcher_paths.py::workflow_toml()` resolves the workflow
file by a DIFFERENT, narrower precedence: explicit `--workflow <path>`
(a raw path, no registry) → the dispatch target repo's own committed
`<repo>/.fabro/workflows/implement-work-item/workflow.toml` → the
plugin's bundled default. The workflow NAME is hardcoded as a literal
in `_WORKFLOW_SUBPATH = (".fabro", "workflows", "implement-work-item",
"workflow.toml")` — there is no config-driven registry of multiple named
variants, no default-selection key, and no ledger-recorded retry
consistency the way factory selection has.

## Scoped implementation pieces (from design discussion, not yet filed as work items)

1. Parameterize `_WORKFLOW_SUBPATH` in `_dispatcher_paths.py` so the
   workflow NAME is a variable, defaulting to the literal
   `"implement-work-item"` for zero-disruption backward compat.
2. Add `resolve_workflow_config(cwd, name=None)` in `_config.py`,
   mirroring `resolve_fabro_factory()`'s precedence: explicit arg →
   `LIVESPEC_FABRO_WORKFLOW` env → `dispatcher.default_workflow_config`
   in `.livespec.jsonc` → implicit default name `"implement-work-item"`.
3. New `.livespec.jsonc` schema: `dispatcher.workflow_configs.<name>`
   (a relative path under `.fabro/workflows/<name>/`, mirroring how
   `factories.<name>.server` is just a URL) plus
   `dispatcher.default_workflow_config`.
4. New `_dispatcher_workflow_ledger.py`, mirroring
   `_dispatcher_factory_ledger.py`'s retry-consistency shape, plus
   `record_dispatch_workflow_config()` / `dispatch_workflow_config_for()`
   in `store.py` mirroring the existing factory pair.
5. `--workflow-config <name>` CLI flag alongside the existing raw
   `--workflow <path>` escape hatch (keep both — the raw path stays
   useful for one-off overrides and the CI preflight check that already
   uses it, per `_dispatcher_master_ci_preflight.py`).
6. Spec update: `SPECIFICATION/contracts.md` §"Dispatcher policy
   settings" needs the new config keys and CLI flag documented, plus at
   least one new scenario (mirroring how factory selection has its own
   scenario) and a `tests/heading-coverage.json` entry for any new
   heading. Land via `propose-change` → `revise`, not a hand-edit.

## Design principle to hold

Each named variant must be a COMPLETE, independently-valid
`workflow.toml` — never a partial overlay merged with the default. This
already matches how the repo-local override works today: a consumer
repo's committed file fully REPLACES the bundled default, it doesn't
patch it. The reason, per the existing code comment: different variants
can need genuinely different sandbox image pins, not just different
prompts/models — partial-merge semantics would be a much murkier surface
than "pick one of N complete files by name."

## Scope not yet cut

No scope event recorded yet. This research captures the shape of the
change; the next planning pass should record requirement carriers (which
of the six pieces above are in scope for a first cut vs. deferred) and
explicit deferrals (e.g. whether a `list-workflow-configs` discovery
/enumeration surface is in scope now or deferred) before any
implementation child work-item is filed.

## Unrelated prior work

This plan is independent of the now-archived `plan/archive/fabro-on-hp/`
(hp-xubuntu provisioning) — that plan is closed and must not be reopened
or modified by this one.
