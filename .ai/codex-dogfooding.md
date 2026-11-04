# Codex dogfooding

Moved word for word from `AGENTS.md` §"Codex dogfooding (OpenAI Codex CLI/TUI)" on 2026-10-30, when the maintainer
directed AGENTS.md split into a short core plus read-on-demand `.ai/` files
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Words such as "above" and "below" point into the AGENTS.md this text came from;
the sections they name now live in the `.ai/` files AGENTS.md routes to.

## Codex dogfooding (OpenAI Codex CLI/TUI)

This repo's `/livespec:*` and orchestrator surfaces can ALSO be dogfooded from
OpenAI Codex CLI/TUI, not just Claude Code. Unlike the Claude path (plugins
enabled PER PROJECT via a committed `.claude/settings.json`), Codex plugin
enablement is **HOST-WIDE**: each registration persists in `~/.codex/config.toml`
and applies to every project on the host. Codex offers no project-scoped plugin
enablement, so there is no committed-settings analogue for the Codex path.

Install the three plugins host-wide — livespec CORE (the artifact carrier that
ships the spec-side prose and wrappers), the `livespec-driver-codex` Codex Driver
(which supplies the `/livespec:*` operation surface over core's prose), and THIS
repo's own orchestrator plugin (whose name is declared in this repo's
`.claude-plugin/plugin.json` — e.g. `livespec-orchestrator-beads-fabro`,
`livespec-orchestrator-git-jsonl`; substitute it for `<orchestrator-plugin>`
below):

```bash
# livespec CORE (spec-side prose + wrappers; no skills of its own):
codex plugin marketplace add thewoolleyman/livespec
codex plugin add livespec@livespec

# The Codex Driver (supplies the spec-side /livespec:* operation surface):
codex plugin marketplace add thewoolleyman/livespec-driver-codex
codex plugin add livespec@livespec-driver-codex

# This repo's orchestrator plugin (ships its OWN cross-runtime Codex surface):
codex plugin marketplace add thewoolleyman/<orchestrator-plugin>
codex plugin add <orchestrator-plugin>@<orchestrator-plugin>
```

Once installed, Codex operations are driven via `codex exec` and NAME-selected as
`<plugin>:<op>` (e.g. `livespec:next`, `<orchestrator-plugin>:list-work-items`)
rather than as `/`-prefixed slash commands. The distributed Drivers resolve their
prose at runtime — no `AGENTS.md` skill→prose mapping is required. See
`livespec/SPECIFICATION/contracts.md` §"Plugin distribution" and
`livespec/SPECIFICATION/non-functional-requirements.md` §"Codex dogfooding
contracts" for the authoritative install and resolution contracts; each
orchestrator plugin's repository owns its own Codex Driver mapping. A temporary
local Codex marketplace registration used for testing MUST be removed afterward
unless you explicitly ask to keep it.

The Codex TUI picker displays skills by short name with the plugin as context.
In `/skills` → `List skills` (or the `@` picker), search `drive`; the
row renders as `drive (livespec-orchestrator-beads-fabro)` with kind
`Skill`. The colon-qualified form
`livespec-orchestrator-beads-fabro:drive` is still valid for prompt /
`codex exec` name selection and model-visible skill references, but it is not
the picker row operators should expect.

**A RAW `codex exec` invocation MUST redirect stdin from a source that reaches
EOF** — normally `< /dev/null` when the prompt is passed as an argument (or a
heredoc / file when using stdin-prompt mode). Never leave stdin inherited.
`codex exec` reads *additional* prompt text from stdin until EOF even when a
prompt argument is present (it prints `Reading additional input from stdin...`);
a background/detached or subagent-spawned call inherits an open **socket** that
never closes, so codex blocks on that read forever, before doing any work —
the process stays alive (a status check reports "running") while its output
never grows past that one line. A foreground call works only because it inherits
`/dev/null`. This trap hits ONLY raw `codex exec`; the plugin's own
`codex-companion.mjs` runtime spawns with `stdio: "ignore"` and is immune, so
prefer routing through the companion / `codex:codex-rescue`. When you must call
`codex exec` directly, use the redirect form, e.g.
`codex exec -s read-only -m gpt-5.5 "$(cat prompt.txt)" < /dev/null > out.log 2>&1`.
And NEVER treat "the process is alive" as proof of progress — verify the output
file is growing past the stdin line.

**The codex-companion runtime is patched to always run `danger-full-access`
(YOLO): full disk + network, no OS sandbox.** Upstream `openai/codex-plugin-cc`
hardcodes a restrictive sandbox on every plugin-launched thread (`read-only` /
`workspace-write`, both network-OFF), which silently cripples Codex reviews — an
adversarial review that cannot run `pytest`/`gh` passes code it never executed.
Upstream ships no toggle and has merged no fix (prior-art survey:
`plan/codex-yolo-sandbox/research.md`), so this repo self-carries a one-line
chokepoint rewrite in the plugin cache — `buildThreadParams` / `buildResumeParams`
in `lib/codex.mjs` resolve to `danger-full-access` — re-applied every session by
the distributed orchestrator plugin hook in `.claude-plugin/hooks/hooks.json`
(because a plugin refresh clobbers the cache).
To DOWNGRADE a single run, set `CODEX_COMPANION_SANDBOX` (e.g. `read-only` or
`workspace-write`) in the environment — that env var is the escape-hatch the
chokepoint honors. `~/.codex/config.toml` also carries
`sandbox_mode = "danger-full-access"` to cover the raw `codex exec` path.
Rationale, end-to-end proof, and the deferred fork / host-wide options are in
`plan/codex-yolo-sandbox/handoff.md`.
