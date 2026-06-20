# livespec-impl-beads

The **beads/Dolt-backed implementation plugin** for
[livespec](https://github.com/thewoolleyman/livespec), and the livespec
family's current work-items backend. It is one realization of the
abstract implementation-plugin contract livespec publishes in its
`SPECIFICATION/contracts.md` §"Implementation-plugin contract — the
10-skill surface": a Claude Code plugin exposing the
`/livespec-impl-beads:*` skill surface that captures, ranks, and drives
impl-side work, with work-items stored as rows in a per-repo
beads tenant on a shared Dolt `sql-server`. The repo dogfoods livespec:
its own spec lives at `SPECIFICATION/` and evolves through the
`/livespec:*` lifecycle.

## Status

Active. This plugin is the dogfooded implementation backend across the
livespec family. Its substrate is a per-repo tenant database on an
externally-managed `dolt sql-server`, reached over TCP `127.0.0.1:3307`
through the pinned `bd` (beads) CLI in server mode — the plugin never
embeds a local database and never speaks SQL directly. The `compat`
pin against livespec is still `master` during bootstrap; the next
bump-pin PR will set a real release tag.

## Install

This is a Claude Code plugin distributed via a marketplace. It composes
with livespec core and the Claude Code Driver, so install all three:

```
/plugin marketplace add thewoolleyman/livespec
/plugin install livespec@livespec
/plugin marketplace add thewoolleyman/livespec-driver-claude
/plugin install livespec@livespec-driver-claude
/plugin marketplace add thewoolleyman/livespec-impl-beads
/plugin install livespec-impl-beads@livespec-impl-beads
```

After install, restart Claude Code (or run `/reload-plugins`). The
skills below become available with the `livespec-impl-beads:` namespace
prefix.

The beads backend also needs host-level runtime that the plugin install
does NOT provision: the pinned `bd` CLI, a running Dolt `sql-server`
reachable over TCP `127.0.0.1:3307`, the per-tenant password supplied
via environment at `bd`-call time (never committed), and the `.beads/`
pointer files. Without these, `bd` reports "no beads database found"
even though the plugin is present.

## Skill surface

The plugin ships seven skills — four heavyweight authored skills and
three thin-transport machine-query surfaces, per livespec's
`SPECIFICATION/contracts.md`:

- `/livespec-impl-beads:capture-impl-gaps` — detect spec→impl gaps and
  file gap-tied work-items with per-gap consent
- `/livespec-impl-beads:capture-spec-drift` — detect impl→spec drift and
  hand each finding to `/livespec:propose-change`
- `/livespec-impl-beads:capture-work-item` — freeform direct filing of an
  impl-side work item (`origin: freeform`, `gap_id: null`)
- `/livespec-impl-beads:implement` — drive Red→Green for a single
  work-item; verify gap-tied closure by re-running gap detection
- `/livespec-impl-beads:detect-impl-gaps` — emit the current gap-id set
  as JSON (pure read-and-emit; never mutates, never prompts)
- `/livespec-impl-beads:list-work-items` — list work-items from the
  beads store
- `/livespec-impl-beads:next` — rank the most-ripe impl-side action (pure
  function of store state; no LLM in the ranking path)

Each skill resolves livespec core's prose and config-named CLIs at
runtime and reads this repo's `.livespec.jsonc` for the beads tenant
connection block.

## Dispatcher and telemetry

Beyond the contract skill surface, this repo also carries the
orchestrator-PRIVATE self-machinery the livespec family dogfoods. Core's
contract sees only the three named `orchestrator.py` CLIs; everything
below is internal to this plugin.

- **The dispatcher** (`dispatcher.py` `dispatch` / `loop`) is the interim
  Dispatcher of the Beads/Dolt + Fabro orchestrator. It polls the beads
  Ledger for ready work-items, invokes the Fabro Loop once per item from
  the target repo's primary checkout (Fabro clones fresh inside its
  docker sandbox), confirms the PR merge, runs a post-merge janitor hard
  gate in a fresh detached worktree of merged master, and journals every
  step. This is the family's "dark-factory" cross-repo orchestration
  self-machinery.

- **The 29f telemetry pipeline** publishes the family's own telemetry. A
  host-local OTLP enrich/scrub stage (`_otel_enrich` + `_otel_scrub`) is
  the augment-and-scrub chokepoint between the dispatcher's local span
  files and Honeycomb — injecting the correlation triple, applying a
  fail-closed allowlist credential scrub, and batching egress. A live
  OTLP/HTTP receiver (`_otel_receive`) ingests spans from inside the
  Fabro sandbox, and a metrics-heartbeat liveness probe
  (`_dispatcher_heartbeat_probe`) feeds the stall watchdog so a
  live-but-stuck run is not mistaken for a dead one.

## Repo layout

| Path | Purpose |
|---|---|
| `.claude-plugin/` | Plugin manifest, skills (`skills/<name>/SKILL.md`), Python (`scripts/livespec_impl_beads/` + `scripts/bin/` shims), vendored libs |
| `SPECIFICATION/` | The live (dogfooded) spec for this plugin |
| `dev-tooling/` | Standalone enforcement-suite scripts (run via `just check`) |
| `tests/` | pytest suite mirroring the script trees |
| `research/` | Design and decision artifacts (e.g. the 29f telemetry pipeline architecture) |
| `.beads/`, `.fabro/` | Beads tenant pointer files and the Fabro workflow graph |
| `.livespec.jsonc` | Single wiring table — substrate marker, beads connection block, `compat` pin, the three orchestrator CLIs |
| `pyproject.toml`, `justfile`, `lefthook.yml`, `.mise.toml`, `.vendor.jsonc` | Toolchain configuration |

## Commands

```
just bootstrap   # one-time: primary-checkout guard hooks + lefthook + plugins
just check       # full enforcement aggregate (lint, types, tests, coverage, AST checks)
```

`just` is the single entry point for every dev-tooling invocation;
lefthook and CI delegate to `just <target>`. The primary checkout
refuses direct commits — work happens in `git worktree add`
secondaries. Product `.py` changes are committed through the
Red→Green-amend TDD ritual enforced by the `red_green_replay`
commit-refuse hook (see [AGENTS.md](AGENTS.md)).

## Observability

The livespec family dogfoods its own telemetry. CI runs, Red→Green commit-gate cycles, the beads+fabro dispatcher, sandbox runs, and harness sub-agents are published to a shared Honeycomb environment:

- **[livespec family — all activity](https://ui.honeycomb.io/thewoolleyweb/environments/livespec/board/krThv8DvcwS)** — the cross-repo activity board (Honeycomb, `livespec` environment).

## More

- See [livespec](https://github.com/thewoolleyman/livespec) for the core
  contract, prose, and templates this plugin realizes.
- See livespec's `SPECIFICATION/contracts.md`
  §"Implementation-plugin contract — the 10-skill surface" for the
  abstract contract this plugin concretizes for the beads substrate.
- See [AGENTS.md](AGENTS.md) for the commit protocol and repo orientation.
- See [SPECIFICATION/](SPECIFICATION/) for the live (dogfooded) spec.
</content>
</invoke>
