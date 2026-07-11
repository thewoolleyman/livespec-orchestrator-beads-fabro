# Handoff — fabro-token-refresh — Design A shipped + self-hosted (#568); awaiting upstream merge

**Thread:** `plan/fabro-token-refresh/` · **Ledger anchor:** epic **`bd-ib-2nq`**
(re-titled to Design A; kept open for the production last-mile).
**Detailed technical record:** `design-notes.md`.

> **Where this stands (2026-07-11).** The credential fix (**Design A**) is complete
> to the extent this repo can drive it, AND it is now **running in production via a
> self-host**: the host factory runs **fabro 0.254 + backported #568** on
> `127.0.0.1:32276`, proven end-to-end. Everything actionable is DONE. The epic
> `bd-ib-2nq` is **3/4 slices complete** and stays open ONLY for the external
> last-mile: `fabro-sh/fabro` #568 merging upstream → a fabro release → reverting
> the self-host to the canonical release. #568 is CLEAN/MERGEABLE/CI-green and
> merely awaiting the fabro-sh maintainers' review — nothing actionable on our side.

---

## The bug (one line)

Factory runs longer than ~60 min died at the publish (`pr`) node on the GitHub App
installation-token TTL — both `git push` and `gh pr create` used tokens minted at
clone/dispatch time. Root cause: ledger item **`bd-ib-4sy`**.

## The fix — Design A (three parts, all proven live)

| Part | Repo | Mechanism | State |
|---|---|---|---|
| **1** | this repo | `workflow.toml` `[run.integrations.github.permissions] {contents, pull_requests = "write"}` → Fabro projects a fresh `GITHUB_TOKEN` per node (fresh `gh pr create`) | ✅ **MERGED — PR #429** |
| **2** | fabro upstream | turn-entry re-mint of the origin push token at each ACP node entry | ⏳ **OPEN — fabro PR #568** |
| **3** | fabro upstream | host-side refresh-ahead loop (~45-min tick, tunable) for a single >60-min push-bearing turn | ⏳ **OPEN — fabro PR #568** |

**Proof:** T1 = a 92-min console run (`livespec-console-beads-fabro`; fresh token
minted at +90 min, zero TTL-expiry errors, part-3 fired mid-turn); driver-codex
**B2/T2 A/B** established part-3 necessary + sufficient for `git push` in a >60-min
single turn. This satisfies the epic's live-exercise acceptance (slice `.3`).

## Self-host of #568 in the host factory — CUTOVER COMPLETE + PROVEN (2026-07-11)

Rather than wait for the upstream merge, we self-host #568 now. **Decision
(maintainer): Recommendation A** — run **fabro 0.254 + backported #568**, NOT modern
fabro. (It's one fabro PR, **#568**; "part 1" is the already-merged this-repo config
PR #429.)

**Current live state:**
- **Host fabro server is UP** on `127.0.0.1:32276` running the **0.254+#568** binary
  (`~/.fabro/bin/fabro`, version 0.254.0, Git SHA `f7ff19e` = `v0.254.0` + #568
  cherry-pick `f630c935` + an env-configurable daemon-readiness timeout). OAuth-only;
  `fabro doctor` green (GitHub App configured; `[✗] LLM Providers` = correct — the
  model key is never on the server).
- **Live `~/.fabro` is the restored OLD-format store** (golden `~/.fabro-restore`
  copied in). Start/restart, auth posture, and the Tailscale proxy are documented in
  `AGENTS.md` → "Host Fabro server" and `orchestrator-image/README.md`.
- **#568 proven end-to-end:** a throwaway dispatch (`bd-ib-dqt`) reached the publish
  node, pushed, and merged **PR #481** GREEN on the self-hosted server (⇒ `git push`
  works ⇒ credential refresh confirmed). The throwaway was reverted as **PR #482**;
  `bd-ib-dqt` reset to backlog.
- **LEARNING — `--mode shadow` still AUTO-MERGES.** Shadow vs autonomous only gates
  the admission approve-gate arming, NOT the merge. The Dispatcher always auto-merges
  a green run, so any throwaway proof lands on master and must be reverted (or use an
  item you are fine landing).

**Why 0.254 (load-bearing — do not re-litigate):**
- The deployed binary was stock-equivalent **0.254.0** (SHA `497aaba`, tree ==
  canonical v0.254.0; no fork changes, no #552).
- **fabro #474** ("Limit DOT templates to prompt+goal", shipped v0.256-nightly)
  removes templating on `acp.command`. The factory's `workflow.fabro` uses
  `acp.command="{{ inputs.acp_adapter }}"` (5 nodes) → on any fabro ≥ 0.256 that goes
  literal → dispatch dies `exit 127` (verified live on 0.290). So ANY modern fabro
  forces a workflow migration; staying compatible ⇒ 0.254.
- **#568 compiles cleanly on 0.254** (conflict-free cherry-pick; does not depend on
  post-0.254 code).

## Track state (finish-up pass 2026-07-11)

Epic **`bd-ib-2nq`** — **3/4 slices complete**, open only for the external last-mile.
- `bd-ib-2nq.1` (GH_TOKEN→GITHUB_TOKEN rename) — ✅ CLOSED.
- `bd-ib-2nq.2` (superseded GH_TOKEN-beside emit) — ✅ CLOSED (superseded-by-Design-A).
- `bd-ib-2nq.3` (>60-min live TTL proof) — ✅ **CLOSED** `resolution:completed`,
  satisfied by the T1 92-min run + this self-host's short-run dispatch (PR #481).
  Parked-run resume (`bd-ib-6vu`) is scoped OUT (distinct deferred follow-up — #568
  review finding #2).
- `bd-ib-2nq.4` (revert-to-canonical) — ⛔ **`blocked`**, purely on the EXTERNAL
  upstream merge. Verified 2026-07-11: `fabro-sh/fabro` #568 is OPEN, CLEAN,
  MERGEABLE, all CI green, no review yet. Unblocks on: #568 merge → a fabro release →
  reinstall `~/.fabro/bin/fabro` from the release + revert `FABRO_VERSION` + drop the
  fork branches.
- `bd-ib-6qu` — the deferred **0.254→0.290 modernization** (separate track; see below).

## #568 dual-review hardening (before opening the upstream PR)

- **Codex** (gpt-5.5 high): submittable, no blocking findings.
- **Fable 5** (xhigh, 28-agent workflow-backed review): 15 findings — **9 fixed +
  verified** (clippy CI-blocker; 30s mint timeout — a real hang vector; retry-sooner
  on a failed tick; whole-feature kill switch; case-insensitive/empty falsy parse;
  accurate `RefreshOutcome` for static PAT/`Installation`; `INTERVAL=0` disables +
  unparsable warns; `display_for_log`; unit tests), **6 deferred + documented in-code
  and in the commit message**. Fable also approved the PR description.
- **One accepted behavior delta vs `main`:** a static-PAT sandbox no longer re-runs
  `set-url` on refresh (only App tokens can be re-minted). No factory impact.
- **Highest-value deferred #568 follow-ups** (post-merge watch): **#2** resumed/parked
  runs reconnect with `github_app: None` so refresh no-ops until App creds are threaded
  through the reconnect path (overlaps `bd-ib-6vu`); **#9/#12** the background `set-url`
  can contend on `.git/config.lock`, amplified N-fold under parallel ACP fan-out; **#10**
  RunNotice on refresh failure; **#13** stage-agnostic hoist; **#14** freshness-checked mint.

## Remaining work

1. **Production rollout via canonical release** (`bd-ib-2nq.4`, external-blocked) —
   await #568 merge + a fabro release, then either bump this repo's sandbox-image pin
   (normal `deps-fabro-sandbox-image-vX` flow) OR, for the host factory, reinstall the
   release binary and revert the self-host. Part 1 already helps on stock fabro today.
2. **Separable upstream PRs** (deferred, NOT ripe — the fork `instrument-v0254` is a
   ~15-file uncommitted blob on the stale v0.254.0 base, must be re-derived vs current
   `main` like #568 was):
   - **`bd-ib-i4r`** — OTLP export (`fabro-cli/src/otel.rs` + wiring); owned by the
     `codex-factory-telemetry` thread — coordinate there before opening.
   - **`bd-ib-v2u`** — cred-lifecycle instrumentation; BLOCKED-BY #568 merge; rebuild
     against #568's `refresh_push_credentials`/`RefreshOutcome`.
3. **Minor filed items:** **`bd-ib-rxf`** — beads auto-backup fails (tenant lacks the
   `DOLT_BACKUP` grant — this is the recurring "command denied" warning); **`bd-ib-vg7`**
   — `jq` missing in the orchestrator image (sibling to `bd-ib-9yi`); **`bd-ib-e0t`** —
   post-merge janitor leaves a worktree under the repo root instead of `~/.worktrees`
   (this bit us during the #481 proof — the janitor's nested checkout caused a spurious
   `just check` red).

## Artifacts

- **#568 branch:** `push-credential-refresh-ahead` in `/data/projects/fabro` (the
  upstream PR source). The branch persists; its worktree was removed in the finish-up
  cleanup.
- **Self-host build branch:** `fork-0254-backport` (HEAD `f7ff19ee` = `497aaba` + #568
  `f630c935` + timeout-fix). Branch persists; worktree removed after the binary was
  installed to `~/.fabro/bin/fabro`. Re-add a worktree to rebuild.
- **`fork-selfhost`** (the abandoned 0.290 experiment) — branch persists, worktree removed.
- **`instrument-v0254`** worktree — LEFT UNTOUCHED (~15-file uncommitted WIP; source for
  the OTLP/instrumentation follow-ups). Fabro remotes: `origin` = `thewoolleyman/fabro`,
  `upstream` = `fabro-sh/fabro`.
- **Image:** `livespec-orchestrator:dev` (retain until the follow-up PRs are open).
- **`design-notes.md`** — detailed session-by-session technical record;
  **`gh-free-publish-reference.patch`** — the gh-free REST-publish `pr.md` reference.

## Data situation + backup inventory (rollback reference)

The 0.290 fork server, on first start (2026-07-11 ~11:26 UTC), migrated `~/.fabro`
in place (imported the legacy `environments/` TOML dir into `storage/db/fabro.sqlite3`
via sqlx migrations `2026063001`/`2026063002`). **0.254 does NOT contain that migration
code**, so it will NOT re-migrate the restored old store. The cutover restored the
old-format golden store; the migrated state is preserved for rollback.

| # | Path | What | Use |
|---|---|---|---|
| 1 | `~/.fabro-restore/` (170M) | **GOLDEN pre-migration `.fabro`** (old format: 5 `environments/` TOML, SlateDB `objects/`, `server.json`, no `storage/db/`), from Arq mirror `/srv/arq-vps-root-snapshot/current` | **PRIMARY RECOVERY SOURCE.** Copy FROM it → `~/.fabro`. **NEVER mutate** (golden master). |
| 2 | `~/.fabro/bin/fabro.0.254.0.bak` | original stock-equiv 0.254.0 binary (SHA `497aaba`) | pure-stock 0.254 fallback binary. |
| 3 | `~/.fabro/storage.postmigration-20260711-143942.bak` | copy of the 0.290-migrated `storage/` (has `db/` sqlite) | preserves 0.290 state; only for the deferred 0.290 path. |
| 6 | `~/.fabro.migrated-20260711T133052Z` | move-aside of the live 0.290-migrated `~/.fabro` at cutover | **one-command rollback to the 0.290 state.** |

**Rollback to 0.290:** stop the server, `mv ~/.fabro ~/.fabro.rec-a && mv
~/.fabro.migrated-20260711T133052Z ~/.fabro`, install a ≥0.290 binary, restart. (But
note ≥0.256 re-breaks the workflow via #474 — see `bd-ib-6qu`.)

## Things NOT to do (learned the hard way)

- Do NOT put `ANTHROPIC_API_KEY` in the fabro **server** env — API-cost billing + it can
  leak into the sandbox. OAuth (`CLAUDE_CODE_OAUTH_TOKEN`, sandbox-injected) is the model auth.
- Do NOT start a **modern** fabro (≥ 0.256) against the restored old store — it re-migrates
  it and re-breaks the workflow (#474).
- Do NOT mutate `~/.fabro-restore/` — it's the golden master; copy from it.
- Do NOT run broad `pkill -f 'fabro server'` — it self-matches the killing shell and can
  reap unrelated shells; match real daemons via `/proc/<pid>/exe` and kill by PID.

## Separate, deferred tracks

- **0.254 → 0.290 modernization** (`bd-ib-6qu`) — version-by-version, requires a
  `workflow.fabro` de-templating migration (#474), the `server` CLI change, the 5s→60s
  daemon-readiness timeout (upstream-worthy), web-UI assets, and the environments→sqlite
  cutover; #552 rides this track. Only relevant if we modernize before #568 merges upstream.
- **Fleet-wide `gh` removal** — Design A keeps `gh`. The gh-free REST-publish `pr.md`
  approach (validated via console PR #136) is preserved as `gh-free-publish-reference.patch`
  for whenever that track opens.

## Standing disciplines

Worktree → PR → rebase-merge; `mise exec -- git`; NEVER `--no-verify`; ledger/git under
the env wrapper (`/data/projects/1password-env-wrapper/with-livespec-env.sh --`); secrets
probe-only; "done means exercised live"; **surface before any outward-facing action**
(upstream PRs, cross-repo).
