# Plan handoff — codex-yolo-sandbox

**Status: IMPLEMENTED + PROVEN (2026-07-17).** Authored 2026-07-15 from a read-only
investigation; picked up and driven 2026-07-17. The always-YOLO fix is live and
end-to-end verified. See "Resolution" below; the original analysis (still accurate)
follows unchanged for the record, and the upstream prior-art survey is in
[`research.md`](./research.md).

## Resolution (2026-07-17)

**Deep-research first (maintainer's ask):** this is *not* new ground — `openai/codex-plugin-cc`
has 12+ issues and 5+ PRs on exactly this, none of the sandbox-config PRs ever merged, and
the crisp root-cause issues (#482, #505) have zero maintainer comments. Full survey +
the "why no upstream fix" analysis: [`research.md`](./research.md). Consequence: "wait for
upstream" (option 3) is a weak bet, so we self-carry.

**Fix chosen (self-hosted, reversible — options 1+2 hybrid, NOT the fork):** force
`danger-full-access` at the *single* chokepoint both param builders share, with an env
escape-hatch to downgrade. `startThread`/`resumeThread` are the only two thread primitives
and every path (task, review, adversarial-review, resume) flows through
`buildThreadParams`/`buildResumeParams`, so two identical lines cover everything — the
handoff's original 3-site plan collapses to one:

```
lib/codex.mjs:68,81   sandbox: options.sandbox ?? "read-only"
                  ->  sandbox: process.env.CODEX_COMPANION_SANDBOX || "danger-full-access"
```

Also set `sandbox_mode = "danger-full-access"` in `~/.codex/config.toml` (defense-in-depth +
covers the raw `codex exec` path). Design note: we force at the chokepoint rather than the
upstream-flavored "inherit config.toml" because inherit *silently degrades* to read-only if
config.toml is ever reset — the exact false-confidence bug we are fixing.

**Durability vs plugin updates:** the cache is clobbered on refresh, so an idempotent
SessionStart re-apply hook restores the patch every session:
- `.claude/hooks/codex-yolo-reapply.sh` — string-match rewrite of the stock chokepoint in
  every cached plugin version; idempotent, fail-open.
- `.claude/settings.json` — registered under `hooks.SessionStart` **after** `just
  ensure-plugins` (which may re-resolve/clobber), so ordering restores it.

**Proof (end-to-end, same curl probe through the patched companion `task`):**

| Sandbox | `curl … api.github.com` | Verdict |
| --- | --- | --- |
| patched default (`danger-full-access`) | `NET=200` + out-of-workspace write OK | full access ✅ |
| escape-hatch `CODEX_COMPANION_SANDBOX=read-only` | `NET=000` (blocked) | reproduces original bug + hatch works ✅ |

Network is the discriminator: read-only *and* workspace-write both have network off, so
`NET=200` proves `danger-full-access` specifically (not merely workspace-write).

**Deferred (needs maintainer sign-off — outward/host-wide):** forking
`openai/codex-plugin-cc` + re-pointing the host-wide `openai-codex` marketplace (durable
"first-class" option 2), and/or promoting the re-apply hook from project scope to user scope
(`~/.claude/settings.json`) for host-wide coverage outside this repo.

**Permanent fix for fleet + adopters (2026-07-18, no-fork):** the maintainer ruled out the
fork and asked for a permanent fix reaching fleet members and adopters. Since the shipped hook
is repo-local dev config, the fix must ride the orchestrator plugin's own distribution. The
actionable design — A (plugin-shipped re-apply hook, covers the interactive plugin surface) +
C (orchestrator-owned full-access `codex exec`, covers the `codex exec` surface) as
complete-coverage belt-and-suspenders, B (upstream toggle) as endgame, plus the mandatory
anti-silent-drift canary, the adopter-default decision, and the propose-change → revise
ratification path — is in [`permanent-fix-design.md`](./permanent-fix-design.md). Only true
blocker: the maintainer's adopter-default decision (opt-in vs force-on).

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
