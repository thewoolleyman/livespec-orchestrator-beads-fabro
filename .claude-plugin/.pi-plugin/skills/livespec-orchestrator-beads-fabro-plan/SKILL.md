---
name: livespec-orchestrator-beads-fabro-plan
description: "Open or resume a durable plan and carry authorized work through child disposition, independent completeness review, a verified plan Proof of Done with required attestations, and archive. Use released-build proof where applicable. Use when the user starts, resumes, or closes a plan. Mutating: it writes plan state and ledger entries."
allowed-tools: bash read write edit
---

# livespec-orchestrator-beads-fabro-plan — pi binding

This file is the thin pi binding of the `plan` operation of the
**livespec-orchestrator-beads-fabro** plugin, per
this repository's `SPECIFICATION/contracts.md` (the pi skill surface contract). It carries pi-runtime
mechanics ONLY. The complete harness-neutral driving prose is the
plugin's shared artifact at `prose/plan.md`, the same artifact the
Claude and Codex bindings read.

Order of work, every time:

1. Resolve `$PLUGIN_ROOT` (next section).
2. Read `$PLUGIN_ROOT/prose/plan.md` **completely** with the `read` tool.
3. Execute that prose end-to-end, binding its harness-neutral vocabulary
   to this runtime via the Runtime bindings section below.

Never paraphrase, summarize, or act on a partial read of the prose, and
never restate its steps here — the prose owns the behavior, this file
owns the wiring.

pi's skill namespace is flat — a skill name admits no colon — so this
plugin's namespace is carried by the unabbreviated `livespec-orchestrator-beads-fabro-` name
prefix rather than by the `/livespec-orchestrator-beads-fabro:plan` form the Claude and Codex
surfaces use.

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

## Runtime bindings

- **"ask the user" / "confirm with the user" / "obtain consent"** —
  conversational turns in this pi session. pi has no structured-picker
  tool, so ask in plain prose, state the options explicitly, and WAIT
  for the user's reply before proceeding. Every store write this
  operation performs on the user's behalf is consented before it
  executes, per this repository's `SPECIFICATION/contracts.md` (the store-write consent
  discipline); a missing picker is never grounds to skip the turn.
- **"read `<file>`" / "list `<dir>`"** — the `read` tool, or the `bash`
  tool for shell work.
- **"invoke the `<name>` wrapper"** — the `bash` tool, invoking
  `python3 "$PLUGIN_ROOT/scripts/bin/<name>.py"` with explicit argv.
- **"invoke the sibling `<operation>` skill"** — this runtime exposes it
  as the pi skill `livespec-orchestrator-beads-fabro-<operation>`; drive that skill rather than
  reimplementing its behavior.
- **"hand off to a livespec core operation"** — core's operations reach
  pi through the livespec pi Driver as the skill
  `livespec-<operation>`. This plugin never binds core's prose or CLIs
  itself.
- **"surface the captured stdout" / "present the JSON verbatim"** —
  plain narration in this session, without re-interpretation or
  re-summarization.
