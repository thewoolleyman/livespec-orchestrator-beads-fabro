# Handoff — fabro self-host of the credential fix (#568) — IN PROGRESS (Recommendation A)

**Goal:** get fabro **PR #568** (the credential-refresh fix — keeps `git push`
tokens fresh across long ACP turns) running in the **host factory**, without
waiting for fabro-sh to merge #568.

**Decision (maintainer, 2026-07-11): Recommendation A** — backport #568 onto the
deployed **0.254** base and run that. Do NOT migrate the factory to modern fabro
now. The full 0.254→0.290 migration is a **separate, deferred, incremental
(version-by-version) track** (see below).

> Terminology: it's **one fabro PR, #568**. Ignore any "part 2 / part 3"
> language in older docs — that was a confusing label for the two *mechanisms
> inside* #568. "Part 1" was a separate, already-merged **this-repo** config PR
> (#429, `workflow.toml` github-permissions).

---

## Why 0.254 (the load-bearing finding)

- The deployed host binary (`~/.fabro/bin/fabro`, backed up to
  `~/.fabro/bin/fabro.0.254.0.bak`) was **stock-equivalent 0.254.0** (SHA
  `497aaba`, tree identical to canonical v0.254.0; **no fork changes, no
  instrumentation, no #552**). It was NOT a fork with #552 — #552 landed a month
  later (v0.289-nightly).
- **fabro #474 ("Limit DOT templates to prompt + goal") shipped in v0.256-nightly**
  and REMOVES templating on `acp.command`. The factory's
  `.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro` uses
  `acp.command="{{ inputs.acp_adapter }}"` (5 nodes). On any fabro ≥0.256 that
  becomes a literal → `exit 127` → dispatch fails. Verified live on 0.290.
- Therefore **no fabro version has #552 (or a native #568 base) without also
  breaking the current workflow.** Staying workflow-compatible ⇒ stay ≤0.255 ⇒
  0.254 + backported #568. That's Rec A.
- #552 (checkpoint-commit-timeout config) is a real fix we contributed but the
  factory does **not** set its config, so 0.254-without-#552 ran fine. #552 rides
  in the deferred migration track, not here.

## Current state (mid-flight — factory is DOWN, must finish or revert)

- **Host fabro server is currently the WRONG build**: it's running the 0.290 fork
  (`server start --bind`, pid ~616200) from an earlier attempt. The factory can't
  dispatch on it (the #474 workflow break). **Rec A must replace it.**
- **0.254+#568 build IN PROGRESS**: worktree `~/.worktrees/fabro/fork-0254-backport`
  (branch `fork-0254-backport` = `497aaba` + cherry-pick of #568 = commit
  `f630c9351`, 10 files +336/-27, cherry-picked CLEAN). Building via
  `cargo build --release --bin fabro` → output
  `~/.worktrees/fabro/fork-0254-backport/target/release/fabro`. Log:
  `scratchpad/build-0254-backport.log` (look for `BUILD_EXIT=0`). **This compile
  is the one open risk** — clean cherry-pick ≠ proof it builds on 0.254.

## Remaining Rec-A steps (in order)

1. **Confirm the build compiles** (`BUILD_EXIT=0`). If it FAILS to compile,
   #568 depends on post-0.254 code → Rec A is not viable as-is; fall back to
   discussing the migration (Rec B) with the maintainer.
2. **Install**: `cp ~/.worktrees/fabro/fork-0254-backport/target/release/fabro
   ~/.fabro/bin/fabro` (backup `fabro.0.254.0.bak` already exists). Verify
   `fabro version` → `0.254.0` and `strings | grep FABRO_PUSH_CRED_REFRESH` shows
   the knobs.
3. **Restart the server with the 0.254 syntax** (NOT the 0.290 `server start
   --bind`): the deployed 0.254 server ran as `fabro server tcp:127.0.0.1:32276`
   (daemon, parent=init). Stop the current 0.290 server first
   (`fabro server stop` works cross-version, or `pkill -f 'fabro server'`), then
   start the 0.254 one. **OAuth-only: do NOT put `ANTHROPIC_API_KEY` in the
   server env** — that bills at API cost and can leak to the sandbox; the agent
   authenticates via `CLAUDE_CODE_OAUTH_TOKEN` injected into the *sandbox* by the
   dispatcher. `[✗] LLM Providers` in `fabro doctor` is EXPECTED/correct.
4. **Prove**: throwaway item **`bd-ib-dqt`** (currently OPEN, unadmitted). Add
   `admission:auto` (`bd label add bd-ib-dqt admission:auto` under the wrapper),
   then dispatch under the env wrapper:
   `python3 .claude-plugin/scripts/bin/dispatcher.py loop --repo
   /data/projects/livespec-orchestrator-beads-fabro --budget 1 --parallel 1
   --mode shadow --item bd-ib-dqt --json`. Expect it to reach a real PR
   (workflow.fabro is 0.254-compatible → no #474 break). Confirm `git push`
   succeeded (that's #568 working). Then **close the throwaway PR (do not merge)**,
   `bd label remove bd-ib-dqt admission:auto`, reset it to open, remove the
   `fabro-run-*` sandbox.
5. **Docs (maintainer-requested)**: document the host fabro server start/restart
   procedure in **AGENTS.md** (repo-additive section) AND **orchestrator-image/README.md**
   — cover: the 0.254 `server tcp:HOST:PORT` daemon syntax (vs 0.290's
   `server start --bind`), OAuth-only posture (no `ANTHROPIC_API_KEY`), creds come
   from `~/.fabro/` store, and that the server is fleet-shared + Tailscale-served.
6. **Cleanup**: remove fabro worktrees `fork-selfhost` and (after install)
   keep `fork-0254-backport` until the binary is confirmed, then decide; remove
   this repo's `docs-host-fabro-server-procedure` worktree after its PR merges.

## Ledger updates owed

- **`bd-ib-2nq.4`** currently describes reverting a 0.290 self-host. Re-scope it:
  the self-host is now **0.254 + #568** (Rec A). Revert = restore stock 0.254
  (`fabro.0.254.0.bak`) or re-pin to a canonical fabro once #568 merges upstream.
- **File a NEW item** for the deferred **fabro 0.254→0.290 migration track**
  (incremental, version-by-version): includes the `workflow.fabro` `acp.command`
  de-templating (#474, v0.256), the `server start` CLI change, the daemon 5s
  readiness-timeout (already fixed on the `fork-selfhost` branch:
  `FABRO_SERVER_START_READY_TIMEOUT_SECS`, default 60s — an upstream-worthy PR),
  the web-UI-assets build step, and the environments→sqlite migration. #552 rides
  this track.

## Separable upstream-PR reminders (unchanged from before)

- `bd-ib-i4r` (OTLP export → codex-factory-telemetry thread), `bd-ib-v2u`
  (cred-lifecycle instrumentation, after #568 merges). The **daemon
  readiness-timeout fix** on `fork-selfhost` is a new candidate upstream PR
  (make it configurable; default 60s).

## Standing disciplines

Worktree → PR → rebase-merge; `mise exec -- git`; NEVER `--no-verify`; ledger/git
under the env wrapper; secrets probe-only; **OAuth for the factory agent, never
`ANTHROPIC_API_KEY` on the server**; surface before outward-facing actions.
