# Handoff — fabro self-host of the credential fix (#568) — MID-CUTOVER (Recommendation A + data recovery)

**Goal:** run fabro **PR #568** (credential-refresh fix — keeps `git push` tokens
fresh across long ACP turns) in the **host factory**, without waiting for
fabro-sh to merge #568.

**Decision (maintainer, 2026-07-11): Recommendation A** — run **fabro 0.254 +
backported #568** (NOT modern fabro). The full 0.254→0.290 migration is a
**separate, deferred, incremental (version-by-version) track**.

> Terminology: it's **one fabro PR, #568**. Ignore "part 2/3" in older docs.
> "Part 1" was a separate, already-merged **this-repo** config PR (#429).

## STATUS RIGHT NOW: factory is DOWN, state is SAFE to leave

- **No fabro server is running** (verified: 0 listeners on 127.0.0.1:32276, 0 real
  `__serve` daemons). Nothing is mutating the live store.
- **Live `~/.fabro` is the 0.290-MIGRATED state** (wrong for Rec A). It must be
  swapped for the restored old-format store (see cutover).
- The **0.254+#568+timeout binary** is built at
  `~/.worktrees/fabro/fork-0254-backport/target/release/fabro`
  (branch `fork-0254-backport`, HEAD `f7ff19ee` = `497aaba` + #568 `f630c935` +
  timeout-fix). **Before using it, verify** `BUILD_EXIT=0` in
  `scratchpad/build-0254-final.log` AND `fabro version` = 0.254.0 AND
  `strings <bin> | grep FABRO_SERVER_START_READY_TIMEOUT_SECS` is present (proves
  the timeout fix is compiled in — the store open exceeds the stock 5s daemon
  readiness cap).

## Why 0.254 (load-bearing findings — do not re-litigate)

- The deployed binary was **stock-equivalent 0.254.0** (SHA `497aaba`, tree ==
  canonical v0.254.0, **no fork changes, no #552**). #552 (checkpoint-timeout, a
  real PR we contributed) landed in v0.289-nightly, a month later; the factory
  never ran it and its workflow does not use its config.
- **fabro #474 ("Limit DOT templates to prompt+goal") shipped in v0.256-nightly**
  and removes templating on `acp.command`. The factory's `workflow.fabro` uses
  `acp.command="{{ inputs.acp_adapter }}"` (5 nodes) → on any fabro ≥0.256 that is
  literal → dispatch dies `exit 127`. **Verified live on 0.290.** So ANY modern
  fabro forces a workflow migration; staying compatible ⇒ 0.254.
- **#568 compiles cleanly on 0.254** (`BUILD_EXIT=0`) — it does NOT depend on
  post-0.254 code. Cherry-pick was conflict-free.

## THE DATA SITUATION (why there's a restore) + BACKUP INVENTORY

My 0.290 fork server, on first start **today ~11:26 UTC**, migrated `~/.fabro`
in place: imported the legacy `environments/` TOML dir into a new
`storage/db/fabro.sqlite3` (sqlx migrations `2026063001`,`2026063002`). **0.254
does NOT contain that migration code** (verified: the string
`"imported legacy environments"` is absent from 0.254 source), and 0.254 ran on
the old-format store for 1.5 days untouched — so **0.254 will NOT re-migrate** the
restored old store. The SlateDB `objects/` store is shared by both versions; the
restore includes 0.254's own pre-migration copy, so no format skew.

**BACKUPS (exact — the maintainer asked these be named explicitly):**

| # | Path | Point-in-time | What | By | Use |
|---|---|---|---|---|---|
| 1 | `~/.fabro-restore/` (170M) | **2026-07-11 10:00 UTC / 03:00 PT** | **GOLDEN pre-migration `.fabro`** (old format: `environments/` 5 TOML, SlateDB `objects/`, `server.json`, **no `storage/db/`**) | maintainer, from Arq mirror `/srv/arq-vps-root-snapshot/current` (== Arq Cloud "Contabo VPS" latest) | **PRIMARY RECOVERY SOURCE.** Cutover **copies FROM** it → live `~/.fabro`. **NEVER mutate** (golden master). |
| 2 | `~/.fabro/bin/fabro.0.254.0.bak` (111M) | binary 2026-06-04 | original stock-equiv 0.254.0 binary (SHA `497aaba`) | me, pre-swap | pure-stock 0.254 fallback binary (superseded by the built 0.254+#568 binary). |
| 3 | `~/.fabro/storage.postmigration-20260711-143942.bak` (53M) | 2026-07-11 14:39 | copy of the **0.290-migrated** `storage/` (has `db/` sqlite) | me | preserves 0.290 state; **only for the deferred 0.290 path**, not Rec A. |
| 4 | `~/.fabro/environments.imported-20260711T112647Z.bak/` | moved 11:26:47 UTC | healthy `environments/` dir the migration moved aside (byte-identical to #1's) | 0.290 migration (auto) | corroboration; #1 is authoritative. |
| 5 | `~/.fabro/settings.toml.settings-environments-migration.bak` | 2026-06-11 | `settings.toml` backup | migration (auto) | minor. |
| 6 | `~/.fabro.migrated-<ts>` | **created DURING cutover step 2** | move-aside of the current live 0.290-migrated `~/.fabro` | next session | one-command rollback to today's 0.290 state. |

## CUTOVER PLAN (all reversible; maintainer to give GO — destructive: swaps live `~/.fabro`)

1. Re-confirm **no fabro server running** (0 listeners/daemons).
2. **Back up current live** `~/.fabro`: `mv ~/.fabro ~/.fabro.migrated-<ts>` (= backup #6).
3. **Restore golden**: `cp -a ~/.fabro-restore ~/.fabro` (COPY — leave `~/.fabro-restore` pristine).
4. **Install binary**: `cp ~/.worktrees/fabro/fork-0254-backport/target/release/fabro ~/.fabro/bin/fabro && chmod +x`.
5. **Start OAuth-only** (NO wrapper, NO `ANTHROPIC_API_KEY` — that bills API cost + can leak to the sandbox; the agent auths via `CLAUDE_CODE_OAUTH_TOKEN` injected into the *sandbox* by the dispatcher):
   `~/.fabro/bin/fabro server start --bind 127.0.0.1:32276 --no-web --no-upgrade-check`
   (daemonizes; the 60s timeout fix covers the ~6s SlateDB open. `--no-web`: the
   fork binary has no bundled web-UI assets.)
6. **Verify** `fabro doctor`: expect GitHub App **configured** (from the restored
   vault), Docker Sandbox reachable, storage OK; **`[✗] LLM Providers` is CORRECT**
   (OAuth). If GitHub App is NOT configured, the restore's vault didn't carry —
   STOP and reassess (do not put ANTHROPIC_API_KEY on to "fix" it).
7. **Prove**: `bd label add bd-ib-dqt admission:auto` (under the env wrapper), then
   dispatch under the wrapper:
   `python3 .claude-plugin/scripts/bin/dispatcher.py loop --repo /data/projects/livespec-orchestrator-beads-fabro --budget 1 --parallel 1 --mode shadow --item bd-ib-dqt --json`
   Expect a real PR (0.254 workflow intact, no #474 break); confirm `git push`
   succeeded (= #568 working). Then **close the throwaway PR (do NOT merge)**,
   `bd label remove bd-ib-dqt admission:auto`, set it back to open, `docker rm -f`
   the `fabro-run-*` sandbox.

## After the cutover proves out

- **Docs (maintainer-requested)**: document the host fabro server start/restart in
  **AGENTS.md** + **orchestrator-image/README.md** — the `server start --bind`
  syntax, **OAuth-only** posture (never `ANTHROPIC_API_KEY` on the server), creds
  from `~/.fabro/`, fleet-shared + Tailscale-served, and the 60s daemon-readiness
  need.
- **Ledger**: re-scope `bd-ib-2nq.4` to "revert 0.254-selfhost → canonical once
  #568 merges." **File a NEW item** for the deferred fabro 0.254→0.290 migration
  track (workflow.fabro #474 de-templating, `server` CLI change, daemon 5s→60s
  timeout [already on `fork-selfhost`, upstream-worthy], web-UI assets,
  environments→sqlite; #552 rides this track).
- **Cleanup worktrees**: fabro `fork-selfhost` (0.290 experiment), `fork-0254-backport`
  (after the binary is confirmed installed), `push-credential-refresh-ahead` stays
  (#568). This repo's `docs-*` handoff worktrees after their PRs merge.

## Things NOT to do (learned the hard way this session)

- Do NOT put `ANTHROPIC_API_KEY` in the fabro **server** env — API-cost billing +
  sandbox leak. OAuth (`CLAUDE_CODE_OAUTH_TOKEN`, sandbox-injected) is the model auth.
- Do NOT start a **modern** fabro (≥0.256) against the restored old store — it will
  re-migrate it and re-break the workflow.
- Do NOT mutate `~/.fabro-restore/` — it's the golden master; copy from it.
- Do NOT run broad `pkill -f 'fabro server'` — it self-matches the shell (exit
  144s) and can kill unrelated codex-companion shells; match real daemons via
  `/proc/PID/exe`.

## Standing disciplines

Worktree → PR → rebase-merge; `mise exec -- git`; NEVER `--no-verify`; ledger/git
under the env wrapper; secrets probe-only; surface before outward-facing actions.
