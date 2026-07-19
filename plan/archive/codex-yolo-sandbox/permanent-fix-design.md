# Permanent-fix design — reach fleet + adopters without a fork

**Date:** 2026-07-18. Follows the shipped repo-local fix ([`handoff.md`](./handoff.md)
Resolution, PRs #730/#731) and the maintainer's direction: **no fork**, make it
permanent for *anything that uses the beads-fabro orchestrator* (fleet members AND
adopters). This doc is the actionable design; nothing here is built yet.

## Reach mechanism (why the shipped fix isn't enough)

PR #730's re-apply hook lives in this repo's **dev** `.claude/hooks/` + `.claude/settings.json`,
so it fires only for clones of *this* repo. Fleet members and adopters get it only if the fix
travels through the **orchestrator plugin's own distribution**. Confirmed feasible: Claude Code
plugins ship hooks via `hooks/hooks.json` referencing `${CLAUDE_PLUGIN_ROOT}` scripts (siblings
`livespec-driver-claude`, `honeycomb`, `ralph-wiggum` all do it). The orchestrator ships **no**
hooks today.

## Key refinement — A and C cover DIFFERENT surfaces (complete coverage, not redundancy)

Codebase investigation (2026-07-18) found **no orchestrator code that programmatically invokes
the codex-companion plugin's review/rescue paths**, and **no review step in the dispatch
pipeline** (`dispatcher.py`). Those paths are invoked *interactively* by agents
(`codex:codex-rescue` subagent, `/codex:review`, `/codex:adversarial-review`). The orchestrator's
only *programmatic* codex use is `codex exec`:
- `dispatcher codex-cred-refresh` (`_dispatcher_codex_cred_refresh_command.py`) — a guarded `codex exec`.
- The `codex exec <plugin>:<op>` dogfooding convention (rendered handoff strings in
  `needs-attention`; the Codex Driver `.claude-plugin/.codex-plugin/skills/*`).

Two distinct failure surfaces follow:

| Surface | What it is | Sandbox origin | Reached by |
| --- | --- | --- | --- |
| **1 — codex-companion PLUGIN (interactive)** | `codex:codex-rescue`, `/codex:review`, `/codex:adversarial-review`. **The original bug.** | Hardcoded in the plugin; ignores `config.toml`. | **A only** — no orchestrator code to redirect. |
| **2 — `codex exec` (orchestrator-owned)** | cred-refresh + `codex exec <plugin>:<op>` dogfooding. | Honors `config.toml sandbox_mode` / CLI flags. | **C** (flags/config). Already covered on the fleet host by the `config.toml sandbox_mode=danger-full-access` set in PR #730's rollout; adopters are not. |

So **A + C = complete coverage of both surfaces**, not redundant coverage of one. True
*redundancy* on Surface 1 only appears if C additionally ships an **orchestrator-owned review
wrapper** (`codex exec --dangerously-bypass-approvals-and-sandbox`) that agents use *instead of*
the plugin — a NEW surface to build (see Option C). That is the belt-and-suspenders overlap; it
is optional and the heaviest piece.

## Option A — orchestrator plugin ships the re-apply hook (covers Surface 1)

- Move the reapply logic into plugin-bundled files (`.claude-plugin/hooks/codex-yolo-reapply.sh`)
  and register a `SessionStart` entry in a plugin `hooks/hooks.json` using `${CLAUDE_PLUGIN_ROOT}`.
- Fires wherever the orchestrator plugin is enabled → fleet + adopters, automatically.
- **Gate it** behind an opt-in signal so it is a no-op unless enabled (see Adopter default):
  e.g. patch only when `LIVESPEC_CODEX_FULL_ACCESS=1` (or a `.livespec.jsonc` flag) is present.
- **Silent-drift risk:** it is a string-match rewrite of `codex.mjs`. If OpenAI restructures the
  chokepoint, the match misses, the hook no-ops (fail-open), and the plugin is quietly back to
  read-only — the exact false-confidence failure that started this. **Requires the canary** below.

## Option C — orchestrator-owned full-access `codex exec` (covers Surface 2, optionally Surface 1)

- Ensure the orchestrator's own `codex exec` calls run full-access independent of the plugin —
  via `--dangerously-bypass-approvals-and-sandbox` (handling the raw-`codex exec` **stdin/EOF
  trap** documented in `AGENTS.md` — redirect `< /dev/null`) or via `config.toml`.
- Optional (the belt-and-suspenders overlap): a small **orchestrator-owned review command**
  agents call instead of `/codex:adversarial-review`, so the factory's review capability never
  depends on OpenAI's plugin and is immune to A's drift.
- Self-contained: never modifies a third-party plugin — the *more defensible* thing to give
  adopters ("the factory runs Codex with full access to do its job").

## Option B — upstream a sandbox toggle (endgame; contribute, not fork)

- A clean, minimal PR to `openai/codex-plugin-cc` honoring an env/config (resurrect #241
  `CODEX_COMPANION_SANDBOX_MODE=inherit` or #226 `--sandbox`/`CODEX_SANDBOX`).
- If merged: everyone gets it natively, zero patching, zero drift, retire A's hook.
- **Merge is uncertain** (research.md: stalled 3+ mo, withdrawn PRs, no maintainer engagement).
  Value even if unmerged: a public, referenceable articulation of the fix.

## Adopter default — RESOLVED (2026-07-18)

Maintainer's decision: **ON** for the fleet's own repos and the maintainer's **official
adopters**; **opt-in** for any other (random external open-source) user. Grounded in the
existing fleet-membership contract — no new config format invented:

- **Source of truth = the "fleet config file in core":** `.livespec-fleet-manifest.jsonc`,
  committed on livespec-core master, already parsed by
  `livespec_dev_tooling.fleet.contract.parse_manifest` into `owner` + `members`
  (`FleetMember{repo, class}`) + **`adopters`** (`Adopter{repo, profile, posture}`).
- **Current project identity** = `owner/repo` from `git remote get-url origin`, via the
  contract's existing `resolve_owner` (no new identity scheme).
- **Gate:** `owner/repo` ∈ (`manifest.member_names()` ∪ `{a.repo for a in manifest.adopters}`)
  ⇒ **ON** (fleet member or official adopter — "MY OWN ADOPTERS"). Otherwise ⇒ **opt-in**
  (default OFF; the user flips a local `.livespec.jsonc`/env flag).
- **A's behavior under the gate:** patch the codex plugin only when the gate says ON *or* the
  local opt-in flag is set; otherwise no-op — a non-listed adopter's Codex and OpenAI's plugin
  are left untouched. This is what keeps us from silently YOLO-ing a random external user.

**Build-time implementation choices (not blockers):**
- *Fetch vs local marker:* fetching the manifest over `gh` at each SessionStart is a network
  cost + auth dependency. Cleaner: write a LOCAL membership/posture marker when a repo is wired
  as a fleet member / official adopter (`wire_fleet_member`) and have the hook read local state.
- *Per-repo opt-OUT:* today "listed ⇒ on". If some listed repo should NOT get full-access, add
  an explicit per-adopter/member field to the manifest (the `Adopter.posture`/`profile` seam is
  the natural home) rather than removing it from the list.

## Canary (mandatory if A ships) — defeat silent drift

A `SessionStart`/check that verifies the codex-companion chokepoint is actually patched (grep for
the `danger-full-access` sentinel in the active plugin version). If the opt-in is ON but the
sentinel is absent (string-match drifted after an OpenAI restructure), **emit a loud warning**
instead of failing silently. Turns A's worst failure mode from "silent read-only" into "visible
alert → fix the matcher".

## Spec lifecycle (how it becomes *permanent*)

`SPECIFICATION/` already governs Codex behavior (Scenario 21 names the orchestrator's Codex
plugin). The permanent contract lands via **`/livespec:propose-change` → `/livespec:revise`**,
with the mechanism/constraint recorded in `constraints.md` (like the fabro pin). File the
proposal **after** the adopter-default decision, since it encodes that default.

## Recommended sequence

1. ~~Maintainer decides **adopter default**~~ — DONE (2026-07-18; see "Adopter default" above).
2. Ship **A** (plugin-shipped hook, manifest-gated per above) **+ the canary** — covers Surface 1
   for fleet + official adopters; no-op for non-listed users.
3. Ship **C** for Surface 2 (force full-access on orchestrator `codex exec`; gated the same way).
   Add the review-wrapper overlap only if the drift-insurance is wanted.
4. Ratify the contract via propose-change → revise; record in `constraints.md`.
5. Pursue **B** as the endgame; retire A if/when it merges.

**Execution note:** steps 2–4 are factory-safe (in-repo Python/config/tests). Per the standing
"prefer factory dispatch" directive they should be **groomed into ready work-items and dispatched
through the dark factory**, not hand-built in-session. NB: `.claude/hooks/` is now a
`source_tree_prefixes` entry, so the canary + hook logic must live in a tested Python module
(the `beads_access_guard.py` pattern) with a thin `.sh` wrapper — a shell-only edit is rejected
by `check-commit-pairs-source-and-test` (and `check-tests-no-subprocess-spawn` forbids testing
the `.sh` by spawning it).

## Status snapshot

- DONE: repo-local hook + `config.toml` (PR #730), AGENTS.md orientation (PR #731). Fix is live
  in this repo + on the fleet host now.
- NEXT: this design; blocked only on the adopter-default decision for the outward-facing shape.
