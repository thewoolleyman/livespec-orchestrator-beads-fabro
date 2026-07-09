# Handoff — fabro-token-refresh (livespec-orchestrator-beads-fabro) — 🔵 DIAGNOSED (root cause empirically pinned; fix design is the next step)

**Thread:** `plan/fabro-token-refresh/` · **Ledger anchor:** epic **TO BE FILED**
in the `livespec-orchestrator-beads-fabro` beads tenant (`bd-ib-*`) — the epic
anchor is deferred to a wrapper-enabled session (this diagnosis was captured from
an unwrapped session; anchor via the `capture-work-item` seam, not a raw `bd`
write).

> Status is derived from the ledger, never stored here. Run all ledger/git ops
> under `/data/projects/1password-env-wrapper/with-livespec-env.sh -- …`.

## Purpose

Make long factory runs (>60 min) stop dying at the publish node with
`Invalid username or token`. This is the GitHub-App installation-token 60-min
TTL biting the in-sandbox push/PR node on any run whose work exceeds the TTL
(a cold Rust `cargo` build, e.g. `livespec-console-beads-fabro` at ~67 min).

## ROOT CAUSE — empirically confirmed (supersedes the old "Route A vs B" question)

Confirmed two ways: (1) two independent fabro-source reads (quote-backed), and
(2) a **live instrumented fabro run** whose `cred-lifecycle:` spans captured the
exact credential flow. It is a **two-token problem**, and fabro **bypasses its
own refresh-capable machinery** for the external-agent path:

1. **cred_variant=App** — the creds ARE a GitHub App installation token
   (mintable/refreshable). This is **NOT a static-cred / provisioning problem**;
   fabro *can* mint fresh tokens.
2. **Token #1 — the clone-URL token.** fabro mints an App token and bakes it into
   the sandbox git `origin` URL (`x-access-token:<tok>@github.com`) **once at
   clone** (`fabro-github` `resolve_authenticated_url`, called from
   `fabro-sandbox/src/docker.rs:~620`). Span: `token_expires_at` = mint + **60
   min**. It is only ever refreshed by fabro's OWN native push
   (`git_push_via_exec` → `refresh_push_credentials`, reached solely via
   `git_push_ref` at `fabro-workflow/src/lifecycle/git.rs:~310`) — which the
   **external Codex ACP agent bypasses** (it runs `git push`/`gh` in its own
   shell). So for the agent, the clone-URL token is never refreshed.
3. **Token #2 — the ACP env token.** The Codex ACP process env is **frozen at
   process spawn** (`acp.rs` `resolve_launch_env`; span:
   `acp_launch_env{refresh_managed=false, "frozen at process spawn"}`). fabro's
   own code documents this via the `GithubTokenRefreshLimited` notice.
4. **fabro's refresh machinery is not even wired in this run.** The
   `built sandbox token source` / `current_token` / `projected GITHUB_TOKEN`
   spans **never fire** — because `build_sandbox_env`
   (`fabro-workflow/src/pipeline/initialize.rs:90`) **returns early**
   (`github_permissions` empty) *before* the `App → Mintable` construction at
   line 104. So no managed `GitHubTokenSource` is built, `refresh_managed=false`,
   and the agent falls back to the **dispatcher's static overlay `GITHUB_TOKEN`**
   (projected by `_dispatcher_plan.py:~979`) for `gh`, plus the static clone-URL
   token for `git`. **Both static, both stale at >60 min.**

**Net:** fabro owns an App minter capable of fresh tokens on demand, but delivers
only *frozen static* tokens to a long-running external ACP agent. On a >60-min
run both tokens are expired at push → publish fails. (Independently observed as a
real 93-min run that died at the pr node with `Invalid username or token`.)

## FIX DIRECTION — a fabro architectural improvement (upstream-worthy)

The robust, general fix is **fabro-side**: for external-ACP stages with mintable
creds, fabro should install a **git credential helper + a `gh` credential in the
sandbox that call back to fabro's App minter on demand**, so the agent's
`git push`/`gh` obtain a *fresh* token at push time regardless of run length.
This solves it for any external agent, not just ours.

- Merely requesting `github_permissions` (so `build_sandbox_env` builds a
  Mintable source) is **necessary but not sufficient** — the ACP env is still
  frozen at process spawn; a long-lived process needs on-demand refresh (the
  helper), not a one-shot fresher launch env.
- Alternative: route the publish through fabro's own refreshing native push. Less
  general (our pr node also arms auto-merge + writes a custom body).
- **Our-side lever:** the dispatcher's overlay `GITHUB_TOKEN` is also static;
  whatever lands, our projection should stop being what the agent's `gh` leans on.

This is the "unanticipated but in-scope fabro improvement" the maintainer
flagged: fabro's `GithubTokenRefreshLimited` notice *documents* the limitation
but leaves it unsolved, while fabro already has the minter to solve it.

## REPRODUCTION TOOLING (built + ready)

- **Instrumented fabro fork** at `/home/ubuntu/.worktrees/fabro/instrument-v0254`
  (v0.254.0 + `cred-lifecycle:` tracing spans + an OTLP-export capability in a new
  `fabro-cli/src/otel.rs`, honoring standard `OTEL_*`, defaulting `http/json`).
  The OTLP-export piece is a clean, separable, **upstream-worthy** change on its
  own. `cargo check -p fabro-cli` is clean.
- **Build** (glibc floor matters — host glibc 2.42 would break on the image's
  2.39): built in a `rust:1-bookworm` (glibc 2.36) container →
  `target-glibc239/release/fabro` (max GLIBC 2.35).
- **Injected image** `livespec-orchestrator:dev` (instrumented binary + a
  `FABRO_LOG=warn,fabro_workflow=info,fabro_sandbox=info,fabro_github=info`
  FROM-override layer). Rebuild the CLEAN `:dev` from the pinned binary when done.
- **Run it:** reset a console item to `ready` (`bd update <id> --status ready`)
  and dispatch UNDER THE WRAPPER, **without `--build-image`** (that would restage
  the stock binary):
  `real-work-dispatch.sh --target-repo livespec-console-beads-fabro --item <id> --run --keep-container`.
- **Read spans:** fabro logs to `/root/.fabro/storage/logs/server.log` +
  per-run `/root/.fabro/storage/scratch/<ULID>/runtime/server.log` (NOT
  `~/.fabro/logs/`):
  `docker exec livespec-orch-realwork sh -lc 'grep -rh "cred-lifecycle:" /root/.fabro/storage 2>/dev/null'`.

## NEXT ACTION (execute from this file alone)

1. **Design the fabro credential-helper improvement** (the fix above). Decide
   helper-callback transport (sandbox → fabro server mint endpoint) and how `gh`
   consumes it. SURFACE the design to the maintainer before implementing — it is
   an outward-facing upstream fabro change.
2. (Optional, confirmatory) Capture the **publish-path spans** from the still-Up
   `livespec-orch-realwork` run at ~67 min: confirm the push reuses the stale
   `token_fp=4668325a…` after its 22:59 expiry.
3. Anchor the ledger epic (wrapper-enabled), file dependency-layered slices,
   prose-link `bd-ib-4sy` / `bd-ib-6vu` / `bd-ib-un226z` + the `livespec-nrdk`
   candidate slice.
4. Land the **OTLP-export** change as its own upstream fabro PR (separable from
   the credential fix). Coordinate with the `codex-factory-telemetry` plan thread.
5. **Live-exercise:** the acceptance bar is a genuine **>60-min factory run that
   pushes green** (cold Rust build). No short-run substitute.

## Read-first chain

1. THIS handoff.
2. `live-adversarial-review-prompt.md` (sibling) — the live-reviewer attack points.
3. The instrumented fork diff at `/home/ubuntu/.worktrees/fabro/instrument-v0254`
   (`git diff` — the `cred-lifecycle:` sites + `otel.rs`).
4. fabro source sites cited above: `fabro-workflow/src/pipeline/initialize.rs:90`,
   `.../handler/llm/acp.rs`, `.../lifecycle/git.rs`, `fabro-github/src/lib.rs`
   (`resolve_authenticated_url`), `fabro-sandbox/src/docker.rs`.
5. The checkpoint-timeout precedent PR #552 (fork branch
   `feat/configurable-checkpoint-commit-timeout`) — the model for a cross-fork
   upstream fabro fix + its livespec-side wiring.

## Standing disciplines

- Repo mutations: worktree → PR → rebase-merge; `mise exec -- git`; NEVER
  `--no-verify`; product `.py` uses Red-Green-Replay; doc-only plan edits use
  `docs(plan): …`; run ledger/git ops under the env wrapper.
- **Secrets probe-only** (`printenv NAME | wc -c`); NEVER echo a token; the
  subject IS a live GitHub credential — on any accidental exposure, ROTATE. The
  instrumentation logs only a non-reversible `token_fp` + expiry, never the token.
- **"Done means exercised live":** a >60-min factory run that pushes green.
- Verify sub-agent claims against ground truth; never trust a self-summary.
- Route through upstream fabro (cross-fork): drive from `/data/projects/fabro`;
  SURFACE before opening the PR (outward-facing).

## Autonomy posture

No standing auto-accept. Proceed through design + anchoring autonomously, but HALT
+ report on the credential-helper design decision, opening any upstream fabro PR
(outward-facing), any new external dependency, or any irreversible act.

## Relationship to other work

- Sibling of the checkpoint-timeout fix (PR #552, `bd-ib-6ka`) — same "make the
  factory robust for long-running Rust repos" family; DISTINCT bug.
- The `codex-factory-telemetry` plan thread (PR #389) shares the OTLP-export
  enabler: it makes fabro's spans observable in Honeycomb. Coordinate naming +
  receiver protocol.
- The 0.13.8 `GH_TOKEN`→`GITHUB_TOKEN` rename is INEFFECTIVE for this bug (the
  failing push doesn't read that env var); harmless, kept. 4 stale sandbox-token
  comments remain to clean (acceptance-live-golden-master.sh:41,329;
  e2e-skeleton/justfile:32; test_dispatcher.py:1423).
