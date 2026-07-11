# Handoff — fabro-token-refresh — ✅ SHIPPED: part 1 merged; parts 2+3 opened as fabro PR #568

**Thread:** `plan/fabro-token-refresh/` · **Ledger anchor:** epic **`bd-ib-2nq`**
(resolution + PR notes appended; see "Ledger" below).

> The credential fix (**Design A**) is complete to the extent this repo can drive
> it. Part 1 is **merged**; parts 2+3 are an **open upstream PR** awaiting
> fabro-side review/merge. What remains is external (upstream merge + a fabro
> release) plus documented follow-ups. Detailed technical record: `design-notes.md`.

---

## The bug (one line)

Factory runs longer than ~60 min died at the publish (`pr`) node on the GitHub
App installation-token TTL — both `git push` and `gh pr create` used tokens
minted at clone/dispatch time. Root cause: ledger item **`bd-ib-4sy`**.

## The fix — Design A (three parts, all proven live)

| Part | Repo | Mechanism | State |
|---|---|---|---|
| **1** | this repo | `workflow.toml` `[run.integrations.github.permissions] {contents, pull_requests = "write"}` → Fabro projects a fresh `GITHUB_TOKEN` per node (fresh `gh pr create`) | ✅ **MERGED — PR #429** |
| **2** | fabro upstream | turn-entry re-mint of the origin push token at each ACP node entry | ✅ **OPEN — fabro PR #568** |
| **3** | fabro upstream | host-side refresh-ahead loop (~45-min tick, tunable) for a single >60-min push-bearing turn | ✅ **OPEN — fabro PR #568** |

**Proof:** T1 = a 92-min console run (fresh token minted at +90 min, zero
TTL-expiry errors); driver-codex **B2/T2 A/B** (part-3 necessary + sufficient for
`git push` in a >60-min single turn).

## What landed this session

- **#426** — deps: sandbox image pin v0.37.2 → v0.37.3 (restored a pre-existing
  lockstep drift that was blocking every PR's `just check`).
- **#429** — part 1 (`workflow.toml` github-permissions).
- **#430** — plan-thread docs refresh (+ `design-notes.md`, `gh-free-publish-reference.patch`).
- **fabro #568** — parts 2+3, dual-review hardened (below). Fork branch
  `push-credential-refresh-ahead`, commit `7e97fba7f`, 10 files +336/−27,
  `fabro-sh/fabro:main` ← `thewoolleyman:push-credential-refresh-ahead`.
  <https://github.com/fabro-sh/fabro/pull/568>

## Dual-review hardening of #568 (before opening)

- **Codex** (gpt-5.5 high): submittable, no blocking findings.
- **Fable 5** (xhigh, 28-agent workflow-backed review): 15 findings — **9 fixed +
  verified**, **6 deferred + documented in-code and in the commit message**.
  - Fixed: clippy CI-blocker (7 errors); 30s timeout on the mint (a real hang
    vector — node entry had no timeout window); retry-sooner on a failed tick;
    the `…_AHEAD` flag now disables the whole feature (turn-entry + loop);
    case-insensitive/empty falsy parsing; accurate `RefreshOutcome` (static
    PAT/`Installation` → `Skipped` before the set-url exec); `INTERVAL=0`
    disables the loop + unparsable warns; `display_for_log`; unit tests.
  - Fable also reviewed and approved the PR description text.
- **One accepted behavior delta vs `main`:** a static-PAT sandbox no longer
  re-runs `set-url` on refresh (only App tokens can be re-minted). No factory
  impact (the factory uses App creds).

## Remaining work (in order)

1. **Production rollout of parts 2+3** — await fabro #568 review/merge + a fabro
   release, then bump this repo's sandbox-image pin (the normal
   `deps-fabro-sandbox-image-vX` `deps:` flow). Part 1 already helps on stock
   fabro today; parts 2+3 reach production only via that release.
2. **Separable upstream PRs** from the fork `~/.worktrees/fabro/instrument-v0254`
   (RETAINED for exactly this): the **OTLP export** (`fabro-cli/src/otel.rs` +
   wiring; coordinate with the `codex-factory-telemetry` thread) and the
   **cred-lifecycle instrumentation**. Both were deliberately excluded from #568.
   Categorized hunk-by-hunk in `design-notes.md`.
3. **Fork/artifact cleanup** once (2) is opened: remove the `instrument-v0254`
   worktree and the `livespec-orchestrator:dev` image. (The #568 worktree
   `push-credential-refresh-ahead` stays until the PR merges.)
4. **#568 deferred follow-ups** (documented in-code + on `bd-ib-2nq`), highest
   value first: **#2** resumed/parked runs reconnect with `github_app: None` so
   refresh no-ops until App creds are threaded through the reconnect path
   (overlaps `bd-ib-6vu`); **#9/#12** the background `set-url` can contend on
   `.git/config.lock`, amplified N-fold under parallel ACP fan-out (post-merge
   watch); **#10** RunNotice on refresh failure; **#13** stage-agnostic hoist;
   **#14** freshness-checked mint.
5. **Minor:** `dolt-backup.service` fails (`command denied to user
   'livespec-orch-beads-fabro'` — tenant lacks `DOLT_BACKUP`; file a work-item);
   `jq` missing in the sandbox image; set `LIVESPEC_BD_PATH` to the pinned `bd`;
   the App token is `{contents, pull_requests}` — cannot push `.github/workflows/`.

## Fleet-wide gh removal (separate, deferred track — task #8)

Design A keeps `gh`. The gh-free REST-publish `pr.md` approach (validated earlier
via console PR #136) is preserved as `gh-free-publish-reference.patch` in this
folder for whenever that track is opened; the `gh-free-publish` branch was dropped.

## Artifacts

- **#568 branch:** `~/.worktrees/fabro/push-credential-refresh-ahead` (commit
  `7e97fba7f`).
- **Instrumented fork:** `~/.worktrees/fabro/instrument-v0254` (full fork — source
  for the OTLP + instrumentation follow-up PRs). Fabro remotes: `origin` =
  `thewoolleyman/fabro`, `upstream` = `fabro-sh/fabro`.
- **Image:** `livespec-orchestrator:dev` (retain until the follow-up PRs are open).
- **`design-notes.md`** — detailed session-by-session technical record.

## Ledger

Anchor epic **`bd-ib-2nq`**. Its title frames the *superseded* GH_TOKEN→GITHUB_TOKEN
rename hypothesis; resolution + PR-#568 notes are appended. **Maintainer decision
(not actioned autonomously):** whether to close `bd-ib-2nq` as resolved-by-Design-A
or re-title it; slice `bd-ib-2nq.2` describes the superseded rename approach.
Related bugs `bd-ib-4sy` (root cause) and `bd-ib-6vu` (parked-run resume) are
addressed by parts 2+3 (with #2 above the exception for resumed runs).

## Standing disciplines

Worktree → PR → rebase-merge; `mise exec -- git`; NEVER `--no-verify`; ledger/git
under the env wrapper (`/data/projects/1password-env-wrapper/with-livespec-env.sh --`);
secrets probe-only; "done means exercised live"; **surface before any outward-facing
action** (upstream PRs, cross-repo).
