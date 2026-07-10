# Handoff — fabro-token-refresh — ✅ PART 1 LANDED; PARTS 2+3 PREPPED (upstream PR awaiting review)

**Thread:** `plan/fabro-token-refresh/` · **Ledger anchor:** epic **`bd-ib-2nq`**
(already existed; a resolution note was appended 2026-07-10 — see "Ledger" below).

> The credential fix is **Design A**, fully proven live. Part 1 is **merged**.
> Parts 2+3 are a **prepped, compiling, clean** fabro branch that is **HELD for
> maintainer review before opening the outward-facing PR** into `fabro-sh/fabro`.
> This document supersedes the earlier "gh-free publish" framing; the detailed
> session-by-session technical record lives in `design-notes.md` (same folder).

---

## The bug (one line)

Factory runs longer than ~60 min die at the publish (`pr`) node on the GitHub App
installation-token TTL — both `git push` and `gh pr create` used tokens minted at
clone/dispatch time. Root cause: ledger item **`bd-ib-4sy`**.

## The fix — Design A (three parts, all proven live)

| Part | Repo | Mechanism | State |
|---|---|---|---|
| **1** | this repo | `workflow.toml` `[run.integrations.github.permissions] {contents, pull_requests = "write"}` → Fabro builds a *mintable* token source and re-projects a **fresh `GITHUB_TOKEN`** into each node's ACP launch env at spawn (fresh `gh pr create` in the short pr node) | ✅ **MERGED — PR #429** |
| **2** | fabro upstream | turn-entry re-mint of the origin-URL push token at each ACP node entry (`acp.rs`) — covers `git push` per node | ✅ prepped (see branch below) |
| **3** | fabro upstream | host-side refresh-ahead loop (~45-min tick; tunable `FABRO_PUSH_CRED_REFRESH_AHEAD` / `FABRO_PUSH_CRED_REFRESH_INTERVAL_SECONDS`) — covers a single push-bearing turn that itself exceeds the TTL | ✅ prepped (see branch below) |

**Proof on record:** T1 = a genuine **92-min** console run (fresh token minted at
+90 min, zero TTL-expiry errors, part-3 fired mid-turn). driver-codex **B2/T2 A/B**:
part-3 is **necessary and sufficient** for `git push` in a >60-min single turn.
`gh`-in-a->60-min-turn is intentionally uncovered (no real factory scenario — the
long turn is `implement`, whose pushes are fabro-native checkpoints; the pr node is
short). Full detail in `design-notes.md`.

## THE ONE REMAINING MAINTAINER GATE — open the upstream fabro PR

Parts 2+3 are on fabro fork branch **`push-credential-refresh-ahead`** (local commit,
**not pushed**), cut clean off `fabro origin/main`:

- Worktree: `~/.worktrees/fabro/push-credential-refresh-ahead`.
- Diff: **3 files, +72 lines** — `fabro-workflow/.../acp.rs` (parts 2+3),
  `fabro-server/src/spawn_env.rs` (2 allowlist entries), `fabro-static/src/env_vars.rs`
  (2 typed `EnvVars` consts + enumeration test). **Excluded on purpose:** the
  `FABRO_DEBUG_*` forcing hook, the OTLP export, and the `cred-lifecycle:`
  instrumentation (all separable follow-up PRs — see below). Origin-token
  `pull_requests` scope broadening is **not** needed for Design A and was excluded.
- Validated: `cargo check` green against `origin/main`; `cargo fmt --check` clean.
- Log messages were de-jargoned (dropped the fork-internal `cred-lifecycle:` grep prefix).

**To open (after review):** `git push -u origin push-credential-refresh-ahead` in the
worktree, then `gh pr create --repo fabro-sh/fabro --base main`. Model the body on the
#552 checkpoint-timeout cross-fork PR. Open review points: info-vs-debug on the
turn-entry success log; whether to strip the `Co-Authored-By` trailer for upstream;
the 45-min default.

## Remaining follow-ups (after the upstream PR is opened)

1. **Production fabro pin** → a fabro release carrying parts 2+3, then bump this repo's
   sandbox-image pin (the normal `deps-fabro-sandbox-image-vX` flow). Part 1 already
   helps on stock fabro; parts 2+3 reach production only via that release.
2. **Separable upstream PRs** from the fork `~/.worktrees/fabro/instrument-v0254`
   (retained until these are opened): OTLP export (`fabro-cli/src/otel.rs` + wiring;
   coordinate with the `codex-factory-telemetry` thread) and the `cred-lifecycle:`
   instrumentation. Categorized hunk-by-hunk in `design-notes.md`.
3. **Fork/artifact cleanup** once all upstream PRs are opened: remove the
   `instrument-v0254` worktree and the `livespec-orchestrator:dev` image.
4. **Fleet-wide gh removal (deferred track, task #8).** Design A keeps `gh`; the
   gh-free REST-publish `pr.md` is a *separate* future track. The validated approach is
   preserved as `gh-free-publish-reference.patch` (this folder) — the branch was dropped.
5. **Minor:** `dolt-backup.service` fails (`command denied to user
   'livespec-orch-beads-fabro'` — tenant lacks the `DOLT_BACKUP` grant; file a
   work-item); `jq` missing in the sandbox image (agent fell back to python3); set
   `LIVESPEC_BD_PATH` to the pinned `bd`; the App token is `{contents, pull_requests}`
   — it cannot push `.github/workflows/` (a scope decision only if the factory ever needs it).

## Ledger

Anchor epic **`bd-ib-2nq`** already existed (its title frames the *superseded*
GH_TOKEN→GITHUB_TOKEN rename hypothesis). A resolution note recording Design A + the
landed/prepped state was appended 2026-07-10. **Maintainer decision (not actioned
autonomously):** whether to close `bd-ib-2nq` as resolved-by-Design-A or re-title it;
slice `bd-ib-2nq.2` describes the superseded rename approach (not the parts-2+3 PR).
Related bugs `bd-ib-4sy` (root cause) and `bd-ib-6vu` (parked-run resume) are addressed
by parts 2+3.

## What was cleaned up this session

- deps PR **#426** (sandbox image pin v0.37.2 → v0.37.3) landed — it restored a
  pre-existing lockstep drift that was blocking every PR's `just check`.
- Transient `real-work-dispatch.sh` proof-scaffolding reverted on the primary checkout.
- Superseded worktrees/branches dropped: `gh-free-publish` (diff preserved as the
  reference patch), the old `fabro-token-refresh-github-permissions`, the merged
  `deps-fabro-sandbox-image-v0.37.3`.

## Standing disciplines

Worktree → PR → rebase-merge; `mise exec -- git`; NEVER `--no-verify`; ledger/git
under the env wrapper (`/data/projects/1password-env-wrapper/with-livespec-env.sh --`);
secrets probe-only; "done means exercised live"; **surface before opening the upstream
fabro PR (outward-facing).**
