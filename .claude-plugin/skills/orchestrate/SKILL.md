---
name: orchestrate
description: Compose spec-side next and impl-side next, present operator-selectable actions, and dispatch selected factory-safe impl work through Dispatcher/Fabro. Invoke bare as `/livespec-orchestrator-beads-fabro:orchestrate` for the walkthrough, or explicitly as `/livespec-orchestrator-beads-fabro:orchestrate plan [--repo <path>] [--json]` / `... run [--repo <path>] --action <action-id> [--json]`.
allowed-tools: Bash
---

# orchestrate

Thin operator binding over the shared Python CLI:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/orchestrate.py" "$@"
```

## Operator-surface defaults

Three defaults shape the everyday path; each has an explicit override so
scripts, CI, and the Dispatcher keep a fully specified invocation. These
defaults are a property of the Python CLI itself, so every runtime
(Claude, Codex, direct invocation) inherits them.

- **Bare `orchestrate`** (no subcommand) is the ergonomic walkthrough
  entry point. It runs the read-only `plan` flow against the resolved
  repo and renders the `actions[]` — it does NOT error on a missing
  subcommand. The interactive select → `run` loop is the skill/harness
  layer over the CLI's `plan`/`run`: this binding presents the rendered
  `actions[]` and, on the operator's selection, invokes the equivalent
  `run` for that action id. The CLI introduces no new selection or
  ranking logic — it is a presentation layer over `plan` and `run`.
- **`--repo` is optional.** Omitted, it defaults to the current
  working directory's repo (the governed checkout the operator is in).
  `--repo <path>` overrides the default; an unresolvable path is a
  precondition error (exit 3) naming the path.
- **Markdown is the default output.** Console output renders
  human-readable Markdown. `--json` is the explicit opt-in to
  machine-readable JSON; the Dispatcher-facing and CI-facing
  invocations pass `--json` for stable parsing. The JSON payload shape
  is unchanged — only the default rendering flips to Markdown.

## Commands

- `plan [--repo <path>] [--json]` — run spec-side `next` and impl-side
  `next`, then emit selectable action records. This is read-only.
- `run [--repo <path>] --action <action-id> [--json]` — run one selected
  action. `impl:<work-item-id>` dispatches through Dispatcher/Fabro in
  `shadow` mode with `budget=1` and `parallel=1`. `spec:<action>:<n>`
  returns a human handoff such as `/livespec:revise --spec-target
  SPECIFICATION/`; it never mutates spec state directly.

## Operator Flow

1. Invoke bare `orchestrate` (or `plan [--repo <path>]`) to render the
   `actions[]`.
2. Present the returned `actions[]` to the user.
3. Invoke `run [--repo <path>] --action <id>` only for the action the
   user selected.
4. Summarize `status`, Dispatcher exit code, PR/run fields present in
   `dispatcher.stdout_json`, and any human handoff.

Machine callers (the Dispatcher, CI) SHOULD pass `--repo` and `--json`
explicitly to keep a fully-specified invocation.

This skill does not create work-items and does not duplicate ranking
logic from either `next` surface.
