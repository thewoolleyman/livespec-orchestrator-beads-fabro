# Handoff — fabro-token-refresh — ✅ FIX VALIDATED LIVE; landing sequence + decisions pending

**Thread:** `plan/fabro-token-refresh/` · **Ledger anchor:** epic **TO BE FILED**
(beads is healthy — see the `/dev/tcp` note below; anchor via `capture-work-item`
under `/data/projects/1password-env-wrapper/with-livespec-env.sh --`).

> The long-run publish bug is SOLVED and proven in a real >60-min-equivalent run
> (PR #136 created gh-free). What remains is a coupled *landing sequence*, gated
> on the decisions below. Run all ledger/git ops under the env wrapper.

---

## ⛔ DECISIONS FOR THE MAINTAINER (resolve these first)

1. **Open the upstream fabro PR?** The fix is two small changes to `fabro-sh/fabro`
   (see "The fix"). They're validated and ready to extract onto a clean branch off
   fabro `main`. Opening a PR into the upstream is **outward-facing** — needs your
   go. (The OTLP-export capability is a SEPARATE upstream PR — see follow-ups.)
2. **Production-fabro sequencing (the coupling).** The gh-free `pr.md` **cannot
   merge until production fabro carries the two fixes** — otherwise every PR-create
   fails `Resource not accessible`. Pick: **(a)** wait for the upstream PR to
   merge + a fabro release, then bump our pin; or **(b)** pin production to a
   custom fork build now (build the fork binary + set `FABRO_VERSION`/image).
3. **PR #136 cleanup.** The validation created a real (trivial doc) PR on
   `livespec-console-beads-fabro` (`feat/livespec-console-beads-fabro-6tn`,
   rebase auto-merge armed). Let it merge, or close it?
4. **Fleet-wide gh removal (task #8) scope now or later?** The sandbox publish is
   now gh-free; the HOST dispatcher still uses `gh` (merge-poll `gh pr view`,
   arming fallback) + adopters. Open the plan thread now or defer?

---

## ✅ STATUS — the fix is FULLY VALIDATED

Live proof (`livespec-console-beads-fabro`, image `livespec-orchestrator:dev`
carrying the fixed fabro): **PR #136** —
`https://github.com/thewoolleyman/livespec-console-beads-fabro/pull/136` —
created **gh-free** via GitHub REST (`POST /pulls`) + GraphQL
(`enablePullRequestAutoMerge`, `mergeMethod: REBASE`, armed), on the
`feat/<work-item-id>` branch, with **zero `gh`**, **no** `Resource not accessible`,
pr node `status="succeeded"`. All family conventions preserved; complete
workflow control retained (agent-owned publish). Codex followed the REST prompt
flawlessly (used python3 when `jq` was absent).

Earlier proof of Token #1: a genuine >60-min run pushed green past the 60-min TTL.

---

## THE FIX — three coupled pieces

1. **fabro: node-entry credential refresh** (`fabro-workflow/src/handler/llm/acp.rs`,
   in `run_turn`, before the ACP process spawns): call
   `sandbox.refresh_push_credentials().await`, **warn-and-continue** (mirror the
   existing pattern at `fabro-sandbox/src/sandbox.rs:~1172`, never `?`-propagate).
   Keeps the `origin` token fresh past the 60-min TTL. VALIDATED (git push).
2. **fabro: broaden the clone/origin token scope** — `fabro-github/src/lib.rs`
   `resolve_clone_credentials_with_expiry` (v0.254.0 line ~1107; on `main` it is
   `resolve_clone_credentials` ~line 1054): change the mint permissions from
   `{ "contents": "write" }` to `{ "contents": "write", "pull_requests": "write" }`
   (the exact pair fabro already uses for its own PR ops). Lets the fresh origin
   token create PRs. The node-entry refresh inherits it (same
   `resolve_authenticated_url` path). VALIDATED (PR #136 via REST).
3. **orchestrator: gh-free `pr.md`** (`.claude-plugin/.fabro/workflows/
   implement-work-item/prompts/pr.md`): agent extracts the token from `origin`
   and publishes via token + REST/GraphQL (no `gh`); preserves `feat/<id>` branch,
   work-item body, Claude-Code footer, rebase auto-merge; python3 fallback if `jq`
   absent. On branch **`feat/gh-free-token-rest-publish`** (+ 4 stale-`GH_TOKEN`
   comment fixes). VALIDATED.

---

## ARTIFACTS — exactly where everything is

- **Instrumented fabro fork build:** `~/.worktrees/fabro/instrument-v0254`
  (detached at v0.254.0). Contains: piece #1 (acp.rs), piece #2 (lib.rs token
  scope), PLUS debug instrumentation (`cred-lifecycle:` spans) and an OTLP-export
  capability (`fabro-cli/src/otel.rs`). Built binary:
  `target-glibc239/release/fabro` (glibc 2.35; built in a `rust:1-bookworm`
  container because the host glibc 2.42 is too new for the image's 2.39).
- **Image `livespec-orchestrator:dev`** = that binary + `FABRO_LOG` layer. Rebuild
  recipe: stage `$BIN`→`orchestrator-image/fabro`, copy plugin-scripts, `docker
  build`, then a `FROM ... ENV FABRO_LOG=...` layer (see git history of this
  session / the acceptance script). Rebuild the CLEAN `:dev` from the pinned
  binary when done.
- **gh-free `pr.md` change:** branch `feat/gh-free-token-rest-publish`, worktree
  `~/.worktrees/livespec-orchestrator-beads-fabro/gh-free-publish`. Committed
  locally? NO — the commit was blocked because that worktree is off OLD master
  (`51fd8bf`, stale `livespec-fabro-sandbox:v0.34.2`). **Current master
  (`85de452`) already has `v0.35.3`** — so **rebase that branch onto current
  master**, then the commit/push passes.
- **For the upstream fabro PR:** extract ONLY pieces #1 + #2 onto a clean branch
  off fabro `main`. STRIP the debug `cred-lifecycle:` spans and the OTLP export
  (OTLP is its own separate upstream PR). Piece #1 = the refresh block in
  `run_turn`; piece #2 = the one-line permission literal.

---

## REMAINING WORK (in dependency order)

1. **Rebase `feat/gh-free-token-rest-publish` onto current master** + commit/push +
   open PR — HELD (do not merge) until production fabro has the fixes (decision #2).
2. **Upstream fabro PR** (pieces #1+#2), pending decision #1. Model: the #552
   checkpoint-timeout cross-fork PR.
3. **Production fabro pin** → a build with the fixes (decision #2).
4. **Durable stale-sandbox delivery fix (task #9).** ROOT CAUSE: fabro reads every
   `@prompts/*.md` ONCE at `fabro run` submit and bundles the *content* into the
   run manifest (`fabro-manifest/src/lib.rs:399`); the sandbox renders from the
   manifest, never re-reading disk — so patching a running container is too late,
   and a stale plugin clone runs silently. FIX (dispatcher): fail-closed on
   workflow-clone drift (verify the plugin-root clone is at its pinned ref / not
   dirty — same discipline as the plugin currency gate) + record prompt provenance
   (path + checksum) in the journal. `--workflow`/`CLAUDE_PLUGIN_ROOT` already
   exist as the supported dev/validation override.
5. **Fleet-wide gh removal (task #8)** — host dispatcher + adopters (decision #4).
6. **Minor follow-ups:** `jq` missing in the sandbox image (agent fell back to
   python3 — add `jq` or standardize on python3); `dolt-backup.service` failing
   (tenant users lack `DOLT_BACKUP` grant — file a work-item); set `LIVESPEC_BD_PATH`
   to the pinned `bd` (falls back to the mise shim); add the `/dev/tcp` gotcha to
   `AGENTS.md` (below).

---

## HOW TO RE-VALIDATE (reproduction recipe — proven)

Deliver an uncommitted local `pr.md` WITHOUT a release (fabro freezes prompts at
submit, so it must be in place *before* `fabro run` submits):
- Mount the local worktree + set `CLAUDE_PLUGIN_ROOT` on the `docker run` in a
  **scratch copy** of `real-work-dispatch.sh` (NEVER edit-and-revert the live
  script — reverting mid-run corrupts bash's byte-offset re-read and the dispatch
  dies silently): `-v <worktree>:/mnt/ghfree:ro -e
  CLAUDE_PLUGIN_ROOT=/mnt/ghfree/.claude-plugin`.
- Use a SHORT work item (the REST-publish correctness is run-length-independent;
  the >60-min part only ever tested Token #1). Reset it to `ready`; ensure it
  yields a non-empty diff.
- Dispatch WITHOUT `--build-image` (that restages the stock binary and destroys
  the fix). `--keep-container`.
- Read spans/logs in the container at `/root/.fabro/storage` (per-run
  `scratch/<ULID>/runtime/server.log`), NOT `~/.fabro/logs/`.

---

## KEY LEARNINGS (hard-won this session — don't relearn)

- **fabro freezes `@prompts` at `fabro run` submit** into the manifest bundle
  (`fabro-manifest/src/lib.rs:399`). Patching a running container's prompt file
  does nothing. This caused a whole misdiagnosis ("Codex won't follow instructions")
  — Codex was simply given the OLD prompt. **Codex follows the prompt correctly.**
- **`/dev/tcp` loopback probes read FALSE `CLOSED`** in the agent Bash sandbox
  (verified: 3307, 22, 5432 all read CLOSED though all listening). NEVER use for
  liveness. The ledger (`doltdb.service`, pid ~1134, `127.0.0.1:3307`) is healthy
  and enabled-at-boot; ledger/commit failures are almost always the **missing env
  wrapper**, not a down server. Use `sudo ss -ltnp | grep 3307` + a wrapped
  `bd list`. (Route this into `AGENTS.md`.)
- **The token had two scopes/lifetimes:** origin token (git, refreshable via the
  node-entry fix) vs env `GITHUB_TOKEN` (broader but frozen at ACP launch). Neither
  was both fresh AND `pull_requests`-capable on a long run — hence the two-part fix.
- **Don't edit-and-revert a live `real-work-dispatch.sh`** — drive from a scratch copy.
- **glibc:** build the fork binary in a `bookworm` (glibc 2.36) container; the host
  (2.42) is too new for the image (2.39).

---

## RELATED WORK / SUPERSEDED

- The 0.13.8 `GH_TOKEN`→`GITHUB_TOKEN` rename is INEFFECTIVE for this bug (the
  failing push/PR-create don't read that env var); harmless, kept. 4 stale
  sandbox-projection comments fixed on the gh-free branch.
- Codex-telemetry gap plan: PR #389 (separate thread `codex-factory-telemetry`).
- Sibling of the checkpoint-timeout fix (fabro PR #552) — same "make the factory
  robust for long-running Rust repos" family.

## Standing disciplines
Worktree → PR → rebase-merge; `mise exec -- git`; NEVER `--no-verify`; ledger/git
under the env wrapper; secrets probe-only (instrumentation logs only a non-secret
`token_fp` + expiry, never the token); "done means exercised live"; SURFACE before
opening the upstream fabro PR (outward-facing).
