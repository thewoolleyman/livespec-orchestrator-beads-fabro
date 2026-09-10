---
name: livespec-orchestrator-beads-fabro-drive
description: "Execute exactly one operator action id against the target repository — a dispatch action, a human valve or policy action, or a config action. Use when the user has selected an action id from the attention surface and wants it executed. Mutating: it drives dispatch and policy writes."
allowed-tools: bash
---

# livespec-orchestrator-beads-fabro-drive — pi binding

This file is the thin pi binding of the `drive` operation of the
**livespec-orchestrator-beads-fabro** plugin, per
this repository's `SPECIFICATION/contracts.md` (the pi skill surface contract). It carries pi-runtime
mechanics ONLY. The behavior lives in the plugin's reference wrapper
`scripts/bin/drive.py`; this binding resolves the plugin root and
dispatches to it, adding no operation behavior of its own.

pi's skill namespace is flat — a skill name admits no colon — so this
plugin's namespace is carried by the unabbreviated `livespec-orchestrator-beads-fabro-` name
prefix rather than by the `/livespec-orchestrator-beads-fabro:drive` form the Claude and Codex
surfaces use. The operation, its flags, and its output are identical
across all three runtimes.

## Resolving the plugin root (`$PLUGIN_ROOT`)

The ordered algorithm is realized ONCE, by this package's
`lib/resolve-plugin-root.sh`, and MUST NOT be restated inline here.
Twelve independently-maintained inline copies of a resolution rule are
kept in agreement only by copying, and that is exactly how one
positional defect came to live in every binding of a sibling Driver at
once.

`<skill-dir>` below is the directory holding THIS `SKILL.md` — you read
this file from disk, so you know its absolute path; the resolver sits
two levels up, beside the bindings tree.

```bash
PLUGIN_ROOT="$(bash "<skill-dir>/../../lib/resolve-plugin-root.sh" .)" || exit 1
echo "$PLUGIN_ROOT"
```

The resolver searches, in order: the `LIVESPEC_ORCH_PLUGIN_ROOT`
override; the governed project's own plugin directory when that checkout
IS this plugin (dogfooding); the project-scope pi package clone under
`.pi/git/github.com/thewoolleyman/livespec-orchestrator-beads-fabro/`; and the user-scope clone
under `~/.pi/agent/git/github.com/thewoolleyman/livespec-orchestrator-beads-fabro/`.

On failure the resolver writes its own diagnostic to stderr and exits 1.
STOP and surface that diagnostic verbatim. Do not improvise a path, and
do not run an install command the diagnostic did not ask for — under a
non-interactive pi run (`-p`, `--mode json`, `--mode rpc`) a failure is
frequently pi's project-trust gate silently ignoring project packages
rather than a missing install.

## Invocation

```bash
python3 "$PLUGIN_ROOT/scripts/bin/drive.py" "$@"
```

The supported flags are the wrapper's own; pass through whatever the
user supplied and let the wrapper validate them. A usage error exits 2
and a precondition failure exits 3 — surface either verbatim rather than
retrying with guessed arguments.

## Launching a long-running action — use the detached gate runner

An `impl:<work-item-id>` dispatch is NOT a short command. One invocation
spans the Fabro run, the pull request, the merge, the post-merge janitor,
and acceptance, so it routinely outlives the agent turn that launched it.

**Do NOT launch it as an agent-harness background task.** Such a task can
be killed mid post-merge: measured 2026-09-10, two `impl:` dispatches
launched that way from one session died 37 ms apart at ~34m55s with the
harness line `exited with code 144`, AFTER both their pull requests had
merged. Both work-items were left `active` with no merge audit — merged
work the ledger still showed as in flight. **A background task's death is
NOT the dispatch's verdict**; the Fabro run and the merge can already have
succeeded, and `drive` prints its result only on exit, so its `--json` log
is empty either way.

Launch it through the detached gate runner instead. `gate-start` runs the
command in its own session that survives the tool call and returns
immediately with a run id; `gate-wait` blocks until that run is terminal
and reports a durable `PASSED` / `FAILED` / `RUNNING` /
`DIED_WITHOUT_VERDICT`:

```bash
run_id=$(mise exec -- just gate-start -- python3 "$PLUGIN_ROOT/scripts/bin/drive.py" --action impl:<work-item-id> --json)
mise exec -- just gate-wait "$run_id"
```

Prefix the gate command with whatever the invocation ordinarily needs (the
governed project's `with-<project>-env.sh` credential wrapper, for
instance) — `gate-start` runs the argv it is given, unchanged. `gate-wait`
exits with the gate's own exit code (75 for `DIED_WITHOUT_VERDICT`, which
is neither a pass nor a fail); killing the waiter does not touch the gate,
so it is safe to background and safe to re-issue.

The `gate-*` recipes come from the livespec-dev-tooling
worktree-discipline pack, imported optionally and installed by
`just install-worktree-pack` (which `just bootstrap` runs).
`Justfile does not contain recipe gate-start` therefore means the pack is
not installed in that checkout — install it rather than falling back to a
background task.

## Recovering a merged item left `active`

A merged item still sitting at `active` with no merge audit is the
signature of a killed dispatch. The recovery is `dispatcher.py
reconcile-merged`, driven per item — the `reconcile-runs.timer` does NOT
close cleanly-merged work. It runs a fresh checkout plus baseline checks
and routinely exceeds a foreground timeout, so launch it through
`gate-start` for the same reason:

```bash
run_id=$(mise exec -- just gate-start -- python3 "$PLUGIN_ROOT/scripts/bin/dispatcher.py" reconcile-merged --repo <path> --item <work-item-id> --invoker <role:name>)
mise exec -- just gate-wait "$run_id"
```

## Output

Surface the wrapper's stdout verbatim. Do NOT re-interpret,
re-summarize, or re-rank it: every listing, ranking, filtering, and
formatting decision belongs to the wrapper, which is the same code the
Claude and Codex surfaces call.
