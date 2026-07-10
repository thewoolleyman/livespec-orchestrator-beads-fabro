# Design notes — fabro-token-refresh credential fix (grounded in live + source ground truth)

Working notes for the holistic credential fix. Captured 2026-07-10 from (1) live
inspection of a running `fabro-run-*` sandbox container and the instrumented
`livespec-orch-realwork` run, and (2) source trace of the fork at
`/home/ubuntu/.worktrees/fabro/instrument-v0254`. Do NOT trust a self-summary —
every load-bearing claim below was verified against a live container or quoted
source.

## Confirmed sandbox architecture (LIVE `docker inspect` + `docker exec`)

- Sandbox container: `NetworkMode=bridge`, `ExtraHosts=[]`, no published ports,
  **zero bind mounts**. `host.docker.internal` does NOT resolve inside.
- Host bridge gateway from container = `172.17.0.1` (route hex `010011AC`).
  github.com egress works (`curl https://github.com` → HTTP 200).
- `gh` = v2.46.0 at `/root/.local/share/mise/shims/gh` (mise shim is PATH entry
  #1; `/usr/local/bin` is later). `gh auth status` → logged in as
  `livespec-pr-bot[bot]` via **`GITHUB_TOKEN`** (an installation token `ghs_…`).
- git origin = `https://x-access-token:<tok>@github.com/<owner>/<repo>`; **no**
  git `credential.helper` configured. `GITHUB_TOKEN` present in container env.

## Confirmed minting machinery (source trace, file:line)

- Host-side minter is whole-run + on-demand, NOT one-shot. Two paths, both hold
  the App private-key PEM for the whole run:
  1. `EngineServices.github_token: Arc<GitHubTokenSource>` (`Mintable`) →
     `current_token_with_expiry()` re-mints with a **15-min freshness cache**
     (`github_token_source.rs`, `REFRESH_THRESHOLD` = 15 min).
  2. Each Sandbox's own `github_app: GitHubCredentials` clone →
     `refresh_push_credentials()` mints directly (independent of the Mintable
     source) and `git remote set-url origin` via exec (`docker.rs:1953-1997`).
- **No IPC callback** from inside the container to the host minter. Minting is a
  host in-process function call; only the resulting URL is pushed in via exec.
- `Mintable` source is built ONLY when ALL hold (`initialize.rs:84-142`):
  (1) `GitHubCredentials::App`, (2) non-empty `spec.github_permissions`,
  (3) `spec.origin_url` set. Empty `github_permissions` → early return at
  `initialize.rs:90` → **no source** → `refresh_managed=false` (matches spans).
- Mint is per-installation (looked up by owner/repo) + scoped to the single repo
  with caller permissions. Sandbox origin token already requests
  `{contents:write, pull_requests:write}` (fork change, `lib.rs:~1107`).

## The precise two-surface split (why the bug bites gh but not git per-node)

- **git push** → origin-URL token → refreshed host-side per node by the sandbox's
  own creds (turn-entry re-mint, `acp.rs:140-148`). Covered per node; the only
  gap is a SINGLE agent turn that pushes AFTER running >60 min.
- **gh (`gh pr create`, auto-merge)** → `GITHUB_TOKEN` env, **frozen at ACP
  process spawn**. Because `github_permissions` is empty, fabro projects no fresh
  token; the env var is the **dispatcher's static overlay** (minted once at
  dispatch, never refreshed) → stale at >60 min. gh is used in the SHORT pr node,
  whose env is (re)projected at node entry — so a fresh-at-entry token suffices
  for gh IFF the pr node stays <60 min (it does, ~2 min).

## Transport reality (rules out the handoff's imagined callback helper)

Container has no inbound channel and no shared FS. True "mint-at-use over an
inbound endpoint" (container → host minter at op time) would require ADDING:
a host listener bound to 172.17.0.1, `--add-host`/gateway wiring, and a per-run
auth secret in the container env. That fights fabro's isolation model and is a
big upstream ask. The architecture-fitting holistic mechanism is **host-driven
refresh-ahead over the existing exec channel** (what fabro already does for its
native push), extended to (a) long single turns and (b) the gh/env surface.

## FINALIZED DESIGN (post 3-agent trace + live probes)

**Design B (in-container credential helper calling back to a host mint endpoint)
is REJECTED.** The sandbox has no inbound channel and its isolation is a *tested
invariant* (`docker.rs` test `container_config_has_no_bind_mounts_or_socket`
asserts `binds: None` + no socket; fabro server binds loopback `127.0.0.1:32276`,
unreachable from the bridge container). B would require adding a published port /
`--add-host host-gateway` / a per-run bearer secret — new inbound attack surface
that fights fabro's deliberate isolation. Not upstream-friendly.

**Design A — host-driven, fits fabro's existing exec model. Three parts:**

1. **livespec-side (make fabro OWN the fresh token; stop the static overlay being
   what the agent leans on).** Set `github_permissions`
   (`{contents:write, pull_requests:write}`) + ensure `origin_url` in the rendered
   fabro run config so `build_sandbox_env` builds the `Mintable` source
   (`initialize.rs:97-127`). Then fabro's `resolve_workflow_env`
   (`services.rs:369-395`) projects a FRESH `GITHUB_TOKEN` into EACH node's launch
   env AT SPAWN — overriding the dispatcher's static overlay. Because `gh` runs in
   the SHORT pr node, fresh-at-spawn is sufficient for `gh pr create` + auto-merge.
   The dispatcher overlay (`_dispatcher_plan.py:979`) stays as a harmless fallback
   (projecting under `GITHUB_TOKEN`, never `GH_TOKEN`, is deliberate so fabro's
   fresh value wins — keep that).
2. **fabro-side, git (already built).** Turn-entry re-mint (`acp.rs:140-148`)
   re-rotates the origin-URL token at every ACP node entry, incl. the pr node.
   Covers `git push` per node regardless of total run length.
3. **fabro-side, the single >60-min-turn safety net (general fix, gated on proof).**
   A host-side refresh-ahead loop scoped to each ACP turn: every ~45 min re-run
   `refresh_push_credentials` (re-mint + `git remote set-url origin`) so a single
   push-bearing turn that itself exceeds 60 min stays fresh. For `gh` inside such a
   turn (env frozen at spawn), the only cover is a host-written `gh` shim on a
   prepended PATH reading a host-refreshed token file — but `gh` runs only in the
   short pr node, so this is belt-and-suspenders. BUILD (3) ONLY IF the cold run
   shows a real >60-min push-bearing turn; otherwise (1)+(2) is the whole fix.

**Why this is the holistic/proper fix:** it puts token ownership where the minter
is (fabro, host-side), removes livespec's competing static token from the agent's
effective path, and covers both credential surfaces (git via origin-URL rotation,
gh via fresh-at-spawn env projection) using the mechanism fabro already uses for
its native push — no new network/isolation surface.

## Open empirical question (the user's "prove it") — decides scope of part 3

Does a genuine COLD >60-min console run exercise a single push-bearing turn past
60 min, or do (1)+(2) already clear it (pr node re-mints git at entry + gets a
fresh gh token at spawn)? Last run was warm (~22 min, janitor 30s) and did NOT
cross the TTL. The cold run decides whether part (3) is required or theoretical.

## Note on the current fork's residual bug

The fork today has (2) [turn-entry re-mint] but NOT (1). So on a >60-min run:
`git push` at the pr node now SUCCEEDS (re-minted), but `gh pr create`/auto-merge
still uses the dispatcher's STATIC overlay `GITHUB_TOKEN` (github_permissions is
empty → fabro projects no fresh token) → would 401 past 60 min. (1) closes that.

## IMPLEMENTATION + PROOF STATE (live, resumable — 2026-07-10)

**Implemented (full general fix, Option 2):**
- fork `/home/ubuntu/.worktrees/fabro/instrument-v0254` `acp.rs`: part 3 refresh-ahead
  loop (default-on; `FABRO_PUSH_CRED_REFRESH_AHEAD=0` disables;
  `FABRO_PUSH_CRED_REFRESH_INTERVAL_SECONDS` default 2700) + debug forcing hook
  (`FABRO_DEBUG_ACP_PRE_TURN_SLEEP_SECONDS` / `_NODE`). cargo check green.
- binary rebuilt (glibc 2.35) → `target-glibc239/release/fabro`; baked into
  `livespec-orchestrator:dev` (sha verified identical).
- part 1: worktree `~/.worktrees/livespec-orchestrator-beads-fabro/fabro-token-refresh-github-permissions`,
  branch `fabro-token-refresh-github-permissions`, `workflow.toml` +
  `[run.integrations.github.permissions] {contents,pull_requests="write"}`.
- harness (transient, on primary working tree): `real-work-dispatch.sh` gains
  `-e FABRO_*` passthrough + `inject_workflow_override` (WORKFLOW_TOML_OVERRIDE →
  docker cp into the dispatcher clone). `FABRO_*` names chosen so they survive
  fabro's fail-closed worker allowlist.

**Refined finding (important):** parts 1+2 are the ACTUAL fix for the observed
bug — pr node does git push (fresh via part-2 turn-entry re-mint) + gh pr create
(fresh via part-1 per-node projection); both fine because the pr node is <60 min.
Part 3 (refresh-ahead) + the scoped-out gh-shim guard a single >60-min
PUSH-BEARING agent turn, which does NOT occur in this factory (the long turn is
implement, whose pushes are checkpoints via fabro's native refresh; the push is
in the short pr node). Part 3 is the general safety net, proven via the forced
sleep.

**Proof runs (console, item `livespec-console-beads-fabro-6sf` = the maintainer's
pre-built >60-min TTL-exercise; PRs CLOSED after proving — no master merges):**
- T1 (RUNNING): real item (agent sleeps ~67min) + part1 injected + refresh-ahead
  on, `--mode shadow`. Expect fully GREEN → proves parts 1+2 (integrated) on a
  genuine >60-min run. Verify: `built sandbox GitHub token source is_refreshable=true`,
  `acp_launch_env{refresh_managed=true}`, pr node succeeded, real PR opened.
- B2 (todo): debug sleep in `pr` node (`FABRO_DEBUG_ACP_PRE_TURN_SLEEP_SECONDS=3720
  FABRO_DEBUG_ACP_PRE_TURN_SLEEP_NODE=pr`), `FABRO_PUSH_CRED_REFRESH_AHEAD=0` →
  expect git push FAILS (Invalid username or token).
- T2 (todo): same debug sleep, refresh-ahead ON → expect git push SUCCEEDS.
  (gh in this artificial long pr-turn may 401 — scoped out; read the failing step.)

**Merge discipline:** on each run's completion, `docker exec <container> gh pr merge
<n> --disable-auto` + `gh pr close <n>` before CI can auto-merge.

## T1 PROOF RESULT — credential fix PROVEN (2026-07-10, run 01KX5DXCKG…)

A genuine **92-min run** (wall_clock 5516s) on item `livespec-console-beads-fabro-6sf`
(agent slept ~67min in implement) with parts 1+2+3 active:
- **NO TTL-expiry / auth-failure** anywhere (grep for `Invalid username or token` /
  `Bad credentials` / `token expired` = empty).
- **pr-node push token minted FRESH at 08:49–08:50** (`token_expires_at=09:49/09:50`)
  — 90 min into a run that started 07:20. Old code would have used the 07:20
  clone-time token (expired 08:20) → 401. Fresh instead. ✅
- **Part-3 refresh-ahead FIRED mid-turn at 08:05** (`refresh-ahead re-minted push
  credentials mid-turn interval_secs=2700`) — the 45-min tick during the long
  implement turn. ✅
- **Part-1 fresh projection**: `built sandbox GitHub token source cred_variant=App
  is_refreshable=true` + `projected GITHUB_TOKEN … refreshable=true` +
  `refresh_managed=true`. ✅

The run did NOT reach a green PR, but ORTHOGONALLY: the force-overwrite of a stale
orphan `feat/6sf` branch (no PR, doc-only) whose delta touched
`.github/workflows/bump-pin-from-dispatch.yml` was rejected for missing `workflows`
permission — a server-side POLICY rejection AFTER successful auth, not a credential
failure. Orphan branch since deleted (host gh, thewoolleyman).

**Conclusion: the credential fix (parts 1+2+3) is proven** — long runs authenticate
with freshly-minted tokens; no TTL expiry.

Secondary finding (not in TTL-fix scope): the App token is `{contents,pull_requests}`
— it cannot push `.github/workflows/` changes. If the factory ever needs to modify a
workflow file, part-1's scope would need `workflows: write`.

## PART-3 ISOLATION A/B (in progress) — item `livespec-console-beads-fabro-1b1`

Trivial README-touch item (fast implement) + fabro-side debug sleep 3900s in the PR
node (forces a >60-min single push-bearing turn deterministically). Env in wrapper
child; `LIVESPEC_DISPATCH_STALL_SECONDS=5400` (survives the silent sleep).
- **B2** (`FABRO_PUSH_CRED_REFRESH_AHEAD=0`): expect git push FAILS at pr
  (Invalid username or token) — part-2 turn-entry refresh alone insufficient for a
  >60-min single turn.
- **T2** (`FABRO_PUSH_CRED_REFRESH_AHEAD=1 FABRO_PUSH_CRED_REFRESH_INTERVAL_SECONDS=1800`):
  expect git push SUCCEEDS (part-3 re-minted mid-turn), then gh pr create fails
  (frozen env, gh-shim scoped out) — read the failing STEP to confirm git push passed.

## ============ SESSION HANDOFF (context-full stop, 2026-07-10 ~13:30) ============

### BOTTOM LINE
The credential fix (parts 1+2+3) is **PROVEN**. Everything below is rigor +
finalization. The deliverable — long factory runs authenticate with freshly-minted
tokens instead of dying on the 60-min TTL — is demonstrated.

### PROOF ON RECORD
- **T1** (console item `6sf`, 92-min run): pr-node push token minted FRESH at +90min;
  ZERO TTL-expiry errors; part-3 refresh-ahead fired mid-turn; part-1 projected a
  fresh refreshable GITHUB_TOKEN. (Failed only on an orthogonal orphan-branch /
  `workflows`-perm issue, since cleaned up.)
- **Baseline** = the ORIGINAL 93-min failure (`Invalid username or token` at pr) —
  documented pre-fix.
- **B2-short** (console): clean green factory PR (#145, closed) with the fix active.
- **Causation cleared**: driver-codex implement committed fine on the SAME new
  `:dev` image → the console `no cargo` failure is console-Rust/mise-specific, NOT
  my rebuild.

### WHAT WAS RUNNING AT STOP (cross-fleet part-3 A/B on driver-codex)
- **B2-codex** (item `livespec-driver-codex-pdn`, part-3 OFF, debug sleep 3900s in
  pr node): reached the pr node, DEBUG sleep FIRED (~13:15-ish), 65-min countdown
  live. Background task was writing to scratch `B2-codex.log`. EXPECTED result: git
  push FAILS with `Invalid username or token` (~65min after the sleep started).
  IF the session ended before it completed, RE-RUN it (command below).
- **T2 (NOT yet run)**: same as B2-codex but `FABRO_PUSH_CRED_REFRESH_AHEAD=1`
  → EXPECT git push SUCCEEDS (part-3 re-mints during the sleep). This is the
  positive part-3 proof still owed.

### RESUME — exact A/B commands (driver-codex; env MUST be set inside the wrapper child)
Reset item first each run: `with-livespec-env.sh -- bd update livespec-driver-codex-pdn --status ready`;
`docker rm -f livespec-orch-realwork`. Then:
```
/data/projects/1password-env-wrapper/with-livespec-env.sh -- bash -c '\
  export FABRO_LOG="warn,fabro_workflow=info,fabro_sandbox=info,fabro_github=info" \
    LIVESPEC_DISPATCH_STALL_SECONDS=5400 FABRO_DEBUG_ACP_PRE_TURN_SLEEP_SECONDS=3900 \
    FABRO_DEBUG_ACP_PRE_TURN_SLEEP_NODE=pr FABRO_PUSH_CRED_REFRESH_AHEAD=<0=B2|1=T2> \
    WORKFLOW_TOML_OVERRIDE="<worktree>/.claude-plugin/.fabro/workflows/implement-work-item/workflow.toml" && \
  exec bash orchestrator-image/real-work-dispatch.sh --target-repo livespec-driver-codex \
    --item livespec-driver-codex-pdn --run --keep-container --mode shadow'
```
Verify result: `docker exec livespec-orch-realwork sh -lc 'grep -rhiE "Invalid username|embedding token into git remote URL" /root/.fabro/storage | tail'`
(B2: expect the Invalid-username error at pr; T2: expect a fresh embed at push + git push succeeds → then gh may 401, scoped out — read the FAILING STEP).

### KEY ENV/PLUMBING GOTCHAS (cost hours; do not relearn)
1. The 1Password wrapper SCRUBS custom env — set FABRO_*/WORKFLOW_TOML_OVERRIDE
   INSIDE the wrapper's `bash -c` child, not before it.
2. fabro's `WORKER_ENV_ALLOWLIST` (spawn_env.rs) is an EXPLICIT list, NOT a
   `FABRO_*` wildcard — the fork adds the 4 knobs there (marked "reconcile before
   upstream"). Without that, `run_turn` (in the worker) never sees them.
3. `NodeTimeoutPolicy::HandlerManaged` → the pr node `timeout=1800s` bounds only
   `run_acp_turn`, NOT the pre-turn debug sleep. Graph `stall_timeout=7200s` +
   `LIVESPEC_DISPATCH_STALL_SECONDS=5400` cover the silent 65-min sleep.
4. real-work-dispatch fails fast if `livespec-orch-realwork` already exists; a
   killed run leaves the item `active` (reset to ready) and may leave a stale
   `feat/<item>` remote branch (delete via host `gh` — thewoolleyman has repo+workflow).

### LANDING SEQUENCE (the maintainer HALT points — surface before acting)
1. **Upstream fabro PR** (outward-facing — SURFACE FIRST): from
   `/home/ubuntu/.worktrees/fabro/instrument-v0254`. Contains: turn-entry re-mint
   (part 2, already), refresh-ahead loop (part 3), cred-lifecycle instrumentation,
   OTLP export (separable — its own PR, coord w/ codex-factory-telemetry), the
   spawn_env allowlist entries, the DEBUG hook. BEFORE PR: REMOVE the FABRO_DEBUG_*
   hook + its allowlist entries; DECIDE refresh-ahead tunable-vs-hardcoded (45min
   default); the instrumentation may be its own separable PR.
2. **livespec part-1 PR**: worktree `fabro-token-refresh-github-permissions` — just
   the `workflow.toml` `[run.integrations.github.permissions]` block. Clean commit
   (`chore(dispatch):` — it's a .toml, no Red-Green-Replay). Verify `just check`.
3. **Cleanup owed**: revert the TRANSIENT `real-work-dispatch.sh` edits on the
   PRIMARY checkout (the `-e FABRO_*` passthrough + `inject_workflow_override` +
   the pre-existing `LIVESPEC_DISPATCH_STALL_SECONDS` line) — decide keep-vs-revert;
   remove probe items (`livespec-console-beads-fabro-1b1`, `livespec-driver-codex-pdn`)
   + their branches; the `instrument-v0254` fork worktree; the `:dev` image.
4. **Ledger epic** still TO BE FILED (wrapper-enabled) per the handoff; prose-link
   bd-ib-4sy / bd-ib-6vu / bd-ib-un226z + livespec-nrdk.
5. **Secondary finding**: the App token is `{contents,pull_requests}` — cannot push
   `.github/workflows/`. A security-scope decision if the factory ever needs it.

## PART-3 A/B COMPLETE (2026-07-10, on livespec-driver-codex — a NON-flaky Python fleet member)
Chosen because the console has an unrelated Rust/`cargo`/mise implement-node flake;
driver-codex committed cleanly on the same `:dev` image (which ALSO cleared my
rebuild of the console failure). Forced >60-min single pr-turn via the debug sleep:
- **B2 (part-3 OFF)**, ~69-min run: git push FAILED `Invalid username or token` (4×);
  refresh-ahead ticks = 0. → turn-entry re-mint (part 2) alone is INSUFFICIENT.
- **T2 (part-3 ON)**, ~70-min run: git push SUCCEEDED (`feat/livespec-driver-codex-pdn`
  landed on remote; `Invalid username or token` = 0); refresh-ahead ticks = 2 (30/60min);
  failure MOVED to `gh pr create` (401) — the scoped-out gh-shim case (gh's frozen env
  token; gh only runs in short pr nodes in the real factory). → part-3 is LOAD-BEARING
  for git push in a >60-min single turn.
Cleanup done: branch deleted, probe items (driver-codex-pdn, console-1b1) closed,
container removed.

**A/B verdict:** part-3 (refresh-ahead) proven necessary + sufficient for `git push`
in a >60-min single turn. Combined with T1 (whole-fix >60-min proof) the credential
fix is fully validated. gh-in-a->60-min-turn remains intentionally uncovered (no real
factory scenario); documented, not fixed.
