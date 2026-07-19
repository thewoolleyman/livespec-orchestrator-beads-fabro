# Plan handoff — codex-yolo-sandbox

**READ THIS FIRST. Status as of 2026-07-19.** This file is the ONLY thing a fresh session
inherits. Everything from "## Goal" down is the ORIGINAL 2026-07-15 analysis, kept as
background — its "First steps for the new session" list is **OBSOLETE**; use
"Next action" below.

## What this track is

Make every Codex sub-session launched through the codex-companion plugin run in full-access
"YOLO" mode (`danger-full-access`: full disk + network, no OS sandbox), so a dispatched Codex
reviewer can actually run `pytest`/`gh` instead of silently passing code it never executed —
and make that permanent for fleet members and official adopters, **without forking**
`openai/codex-plugin-cc` (the maintainer ruled the fork out).

## DONE and landed — do NOT redo

- **The fix is already LIVE in this repo** (PR #730, `737f562`): a one-line chokepoint rewrite
  in the codex plugin cache — `buildThreadParams` / `buildResumeParams` in `lib/codex.mjs`
  resolve to `danger-full-access`, with `CODEX_COMPANION_SANDBOX` as a downgrade escape-hatch —
  plus `.claude/hooks/codex-yolo-reapply.sh` re-applied from `hooks.SessionStart` (ordered AFTER
  `just ensure-plugins`, because a plugin refresh clobbers the cache), and
  `sandbox_mode = "danger-full-access"` in `~/.codex/config.toml` (host-local, not in git).
  Proven end-to-end: patched default → `NET=200` + out-of-workspace write;
  `CODEX_COMPANION_SANDBOX=read-only` → `NET=000`. **Network is the discriminator** —
  `read-only` AND `workspace-write` are both network-OFF, so `NET=200` proves
  `danger-full-access` specifically.
- **Upstream research** (PR #739, `bb845ec`): this is NOT new ground — 12+ issues and 5+ PRs
  upstream, **none merged**, and the sharpest root-cause issues have zero maintainer comments.
  Full survey + the "why" analysis: [`research.md`](./research.md). Consequence: do NOT wait on
  upstream; self-carry.
- **Design**: [`permanent-fix-design.md`](./permanent-fix-design.md) — options A/B/C, the two
  distinct failure surfaces, the mandatory drift canary, and the spec-ratification path.
- **Adopter gate DECIDED** (PR #742, `0184180`): **ON** for fleet members + official adopters,
  **opt-in** for everyone else — keyed on the core fleet manifest
  `.livespec-fleet-manifest.jsonc` (`members` ∪ `adopters`) parsed by
  `livespec_dev_tooling.fleet.contract.parse_manifest`; project identity via the fleet
  contract's `resolve_owner`.
- **AGENTS.md orientation note** (PR #731).
- **S5's spec proposal LANDED** (`61363e7` + `e968bb4`); item `.2` sits at `acceptance` — the
  maintainer may want to accept/close it.

## The ledger — epic `bd-ib-1jye`

| ID | Slice | Status |
| --- | --- | --- |
| `bd-ib-1jye.1` | **S1** — re-apply hook → tested Python module + drift canary | `ready` ← **THE BLOCKER** |
| `bd-ib-1jye.2` | S5 — propose-change ratifying the codex-full-access contract | `acceptance` (work merged) |
| `bd-ib-1jye.3` | S2 — manifest-gating helper + wire hook to it (needs S1) | `ready`, blocked-on-dependency |
| `bd-ib-1jye.4` | S3 — ship the gated hook FROM the orchestrator plugin (needs S2) | `ready`, blocked-on-dependency |
| `bd-ib-1jye.5` | C1 — orchestrator-owned full-access `codex exec`, Surface 2 (needs S2) | `ready`, blocked-on-dependency |

Each item's full spec lives in its beads record — `with-livespec-env.sh -- bd show <id>`.

## Next action — S1 is the blocker, and the factory has failed it TWICE

S1 was dispatched twice. Both runs ended `failed / workflow_error` **after reaching
`just check` GREEN**, and a run event flagged *"stages running beyond token expiry may need to
be retried."* Diagnosis: ~6h runtime under an oversubscribed factory (3–4 concurrent fleet
loops) blew the model-auth token TTL. **The implementation was fine — this is an infrastructure
failure, not a code defect.**

**Recommended: hand-implement S1 in a supervised session.** Two factory failures is the
carve-out to the standing "prefer factory dispatch" directive. It is small and fully specified:

- **NEW** `.claude/hooks/codex_yolo_reapply.py` — PURE importable
  `classify_state(*, content) -> "stock" | "patched" | "drift"` plus a patch function, and a
  `main()` that globs `~/.claude/plugins/cache/openai-codex/codex/*/scripts/lib/codex.mjs`,
  rewrites stock chokepoints, and writes a LOUD stderr WARNING for any file in the `drift`
  state (neither stock string nor our sentinel) — that warning IS the canary. Idempotent;
  fail-open when python3 or the plugin cache is absent.
  - `STOCK   = 'sandbox: options.sandbox ?? "read-only"'`
  - `PATCHED = 'sandbox: process.env.CODEX_COMPANION_SANDBOX || "danger-full-access"'`
- **REWRITE** `.claude/hooks/codex-yolo-reapply.sh` into a thin wrapper, mirroring
  `.claude/hooks/beads-access-guard.sh` (`command -v python3 >/dev/null 2>&1 || exit 0; exec
  python3 "$(dirname "$0")/codex_yolo_reapply.py"`).
- **NEW** `tests/` unit tests for the pure functions covering all four states
  (stock→patched, already-patched→no-op, drift→warn, absent→no-op). Pure — NO subprocess spawn.
- **Scope discipline:** preserve the current always-on repo-local behavior. Manifest-gating is
  S2, NOT this slice.

*Alternative* — re-dispatch, but only when the factory is quiet (check `fabro ps` first; if 3+
runs are already going, expect the same token-expiry death):

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  python3 .claude-plugin/scripts/bin/dispatcher.py loop \
  --repo /data/projects/livespec-orchestrator-beads-fabro \
  --item bd-ib-1jye.1 --budget 1 --parallel 1 --json
```

After S1 merges, S2 (`.3`) unblocks; after S2 merges, S3 (`.4`) and C1 (`.5`) unblock.
Dispatch each **supervised, in-session**.

## Hard rules and gotchas — each of these cost real time

- **NO detached / `setsid` / `nohup` watchers.** The maintainer explicitly objected to a
  background process auto-dispatching with no session attached and no oversight. If you want a
  watcher, use a harness-owned background task (tracked, killable, dies with the session).
- **`.overseer-state` holds EXACTLY ONE token** on its first line — `ready`,
  `blocked: <one-line reason>`, or `winding-down`. It is NOT a handoff surface; durable notes
  belong in THIS file. A long note there is reported fleet-wide as a malformed state file.
- **Dispatcher readiness ≠ `bd ready`.** The board lane IS the stored status, so an item must be
  stored status `ready`. Raw `bd create` files items as `open`, and the dispatcher then rejects
  them ("not in the ready set") — fix with `bd update <id> -s ready`. A killed dispatch can also
  leave an item stuck `active`; reset it to `ready` before re-dispatching.
- **`dispatcher loop --budget N`**: `N` is a dispatch COUNT, not dollars.
- **`loop --item <id>` validates readiness UP FRONT** and rejects a still-blocked item, so it
  cannot be used to "wait until it unblocks."
- Run every `bd` / dispatcher command under
  `/data/projects/1password-env-wrapper/with-livespec-env.sh -- …`. The beads-access guard also
  false-positives on the bare word "bd" appearing in unrelated shell (e.g. inside an `echo`), so
  write notes with a file tool rather than `echo`.
- **`.claude/hooks/` is a `source_tree_prefixes` entry**: touching a hook file requires a paired
  `tests/` change (`check-commit-pairs-source-and-test`), and `check-tests-no-subprocess-spawn`
  forbids testing the `.sh` by spawning it — which is exactly why S1 must become a tested Python
  module with a thin shell wrapper.
- Repo mutation protocol: worktree → PR → merge → cleanup; never commit on the primary checkout.
  Docs/shell/config changesets use `chore(...)` / `docs(...)` and skip the Red-Green ritual, but
  S1's new product `.py` DOES require the Red→Green pair.

## Deferred / explicitly not doing

- **Forking `openai/codex-plugin-cc`** — the maintainer ruled it out.
- **Upstreaming a sandbox toggle (option B)** — good citizenship, but the research shows upstream
  is a graveyard (nothing merged, no maintainer engagement); do not block this track on it.

## Goal

Make every Codex sub-session launched through the `codex:codex-rescue` subagent /
codex-companion runtime **always run in full-access "YOLO" mode** — full disk +
network, no OS sandbox, no approval prompts — so Codex is **never blocked by
sandbox restrictions** and can run tests (pytest/uv), `git`, and `gh`.

**Why this matters (the trigger):** a Codex adversarial review of work-item
`bd-ib-98c.3` (F1) ran read-only with **no network and no writable temp**, so it
could not run `pytest` ("uv failed on read-only cache init") or `gh pr diff`
("could not reach GitHub"). It reviewed statically and **passed the code as
correct**. A parallel Fable reviewer that *could* execute ran the parser against a
real event stream and caught **two real bugs** (a `review.verdict` mislabel and a
non-fail-soft emission leg). A crippled reviewer that can't execute is worse than
no reviewer — it gives false confidence. Same limitation degrades every
rescue/diagnosis Codex run.

## Root cause (code-verified, file:line)

The codex-companion plugin does **not** run `codex exec` with CLI flags. It spawns
`codex app-server` and drives it over JSON-RPC (`scripts/lib/app-server.mjs:190`,
argv is literally just `["app-server"]`). Sandbox + approval are set as **per-thread
JSON-RPC params** on every `thread/start` / `thread/resume`, and the plugin
**hardcodes restrictive values and never emits Codex's third, unrestricted mode
(`danger-full-access`) anywhere in its source:**

- **`task` (the rescue path):** `scripts/codex-companion.mjs:491` —
  `sandbox: request.write ? "workspace-write" : "read-only"`. So `task` = read-only;
  `task --write` = workspace-write. **Neither enables network** (see below), and
  neither is full-access.
- **`review`:** `scripts/lib/codex.mjs:1012` — literal `sandbox: "read-only"`,
  no caller override.
- **`adversarial-review`:** `scripts/codex-companion.mjs:414` — literal
  `sandbox: "read-only"`. Its arg parser (`codex-companion.mjs:713-719`) does not
  even recognize `--write`, so there is **no flag to escape read-only** for reviews.
- `approvalPolicy` is unconditionally `"never"` (`scripts/lib/codex.mjs:63-83`) —
  approvals are NOT the blocker; the sandbox is. (`codex exec`/app-server headless
  never prompts anyway.)

**Two critical wrinkles that defeat the "obvious" fixes:**

1. **`~/.codex/config.toml` is moot here.** It has no `sandbox_mode` set, but even
   if it did, the plugin sends an **explicit per-thread `sandbox` param that
   overrides config**. Setting `sandbox_mode = "danger-full-access"` in config.toml
   will NOT change these runs. (Confirmed: Codex's config-vs-explicit precedence
   makes the explicit param authoritative.)
2. **Network is off even under `workspace-write`.** Codex's `workspace-write`
   defaults `network_access = false`; only `danger-full-access` bakes in network.
   So even `task --write` cannot reach GitHub/PyPI without more.

The restriction is **Codex's own Landlock/seccomp/bubblewrap sandbox** acting on the
`sandbox` value it is told — verified NOT a host limit (host `/tmp` is writable and
`curl api.github.com` returned 200 from the same environment).

The plugin files live in the **cache**:
`/home/ubuntu/.claude/plugins/cache/openai-codex/codex/1.0.6/scripts/{codex-companion.mjs, lib/codex.mjs, lib/app-server.mjs}`.

## Codex's actual capability (the target state)

- Sandbox modes: `read-only` / `workspace-write` / `danger-full-access`. Only
  `danger-full-access` = full disk + network, no restrictions.
- CLI flag (**use this** — explicit and documented):
  `codex exec --dangerously-bypass-approvals-and-sandbox` → forces
  `DangerFullAccess`. (`--yolo` is an accepted but UNDOCUMENTED shorthand alias in
  0.144.3 — hidden from `--help`/completion, but the parser accepts it identically
  to the full flag; prefer the explicit form. `--full-auto` maps to
  workspace-write; do NOT use it for full access.)
- app-server transport equivalent of `--dangerously-bypass-approvals-and-sandbox`
  = sending `sandbox: "danger-full-access"` on the thread — which is exactly the
  value the plugin never sends.

## Options (for the new session to decide)

| # | Approach | Durability | Notes |
| --- | --- | --- | --- |
| 1 | Patch the 3 cached sandbox sites → `danger-full-access` directly | ❌ clobbered on plugin update | Fastest, but silently reverts on any `codex plugin` refresh. Only acceptable with a re-apply hook or version pin. |
| 2 | Fork `openai-codex` (thewoolleyman fork): make the 3 sites resolve to `danger-full-access`, gated behind an env/config toggle (e.g. `CODEX_COMPANION_SANDBOX=danger-full-access`) + add a `--sandbox`/`--full-access` flag to the review parser; install the fork | ✅ durable | Maintenance: track upstream. Fits the repo's existing fork-carry discipline (cf. the fabro `factory-integration` pattern). |
| 3 | Upstream a PR to `openai-codex` making the companion sandbox configurable (respect a per-call `sandbox` option + a default-full-access toggle) | ✅ durable, best long-term | Slow — depends on upstream merge. |
| 4 | **Bypass the plugin for execute-needing reviews:** call Codex directly via `codex exec --dangerously-bypass-approvals-and-sandbox "<prompt>"` (or an app-server client sending `sandbox: "danger-full-access"`) instead of the hardcoded-read-only `review`/`adversarial-review` path | ✅ fully under our control | Fast interim; a small wrapper the orchestrator invokes for reviews. Does NOT fix the `task`/rescue path (still workspace-write). |

**Recommendation:** (4) as an immediate interim so review runs can execute *today*,
plus (2) or (3) for durability so the standard rescue *and* review paths are YOLO
and survive plugin updates. The user wants the whole sub-session always-YOLO (the
`task` ternary at `codex-companion.mjs:491` included), so the durable fix must cover
all three sites, not just reviews.

## Risks (surfaced, user has accepted always-YOLO)

`danger-full-access` removes Landlock/seccomp confinement and enables unrestricted
network with **no per-command gate** (exec mode never prompts). A prompt-injected or
hallucinated destructive/exfil command runs immediately against the operator's full
filesystem + network. In this dark-factory context Codex is **already** the sole
implementer agent with in-repo git/gh/pytest access, so the marginal increase is:
losing cwd-confinement (writes anywhere on host) + always-on network. A middle
ground exists if full-access is more than wanted — `workspace-write` +
`[sandbox_workspace_write] network_access = true` (network on, writes confined to
cwd) — but the stated ask is YOLO. Whatever the fix, it MUST survive plugin updates
(option 1 alone does not).

## First steps for the new session

1. **Reproduce:** run a `codex:codex-rescue` review and confirm read-only/no-network
   (it will fail to `pytest`/`gh`). Baseline.
2. **Pick the option** (recommend 4 interim + 2/3 durable).
3. **Implement the interim (4):** a review wrapper that shells
   `codex exec --dangerously-bypass-approvals-and-sandbox` and returns the result;
   verify it can run `pytest` + `gh` inside a repo.
4. **Implement the durable fix (2/3):** the 3 sandbox sites →
   `danger-full-access` (env/config-gated), + a review-parser `--full-access` flag.
5. **Survives-update guard:** pin the plugin version, add a post-install re-patch
   hook, or carry the fork — so a marketplace refresh can't silently re-sandbox.
6. Formalize as a proper plan thread (`/plan codex-yolo-sandbox`) + anchor a ledger
   epic if driving it to completion.

## Evidence / references

- Companion runtime (cache): `scripts/codex-companion.mjs` (`:414` adversarial-review,
  `:491` task ternary, `:461-495` executeTaskRun, `:713-719` review arg parser);
  `scripts/lib/codex.mjs` (`:63-83` buildThreadParams — approvalPolicy always
  "never", sandbox defaults "read-only"; `:1002-1015` runAppServerReview, `:1012`
  literal read-only); `scripts/lib/app-server.mjs:190` (spawns `codex app-server`).
- Codex CLI `codex-cli 0.144.3`: `--dangerously-bypass-approvals-and-sandbox`
  → `SandboxMode::DangerFullAccess`. It also accepts an **undocumented `--yolo`
  alias** (hidden from `--help`/completion, but the parser accepts `--yolo`
  identically to the full flag while rejecting near-miss typos like `--yo` — so it
  is a real hidden alias, not inference; prefer the explicit flag). `codex exec`
  hardcodes
  `AskForApproval::Never`; CLI flag > config precedence
  (`resolve_permission_config_syntax`); config keys `sandbox_mode`,
  `[sandbox_workspace_write] network_access`, `default_permissions=":danger-full-access"`
  (mutually exclusive with `sandbox_mode`); no `CODEX_*` env forces sandbox
  (`CODEX_HOME` only relocates config dir).
- Verified host is not the limiter: host `/tmp` writable, `curl api.github.com` → 200.
