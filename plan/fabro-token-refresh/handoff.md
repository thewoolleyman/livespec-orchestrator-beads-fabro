# Handoff — fabro-token-refresh (livespec-orchestrator-beads-fabro) — 🟡 NOT STARTED

**Thread:** `plan/fabro-token-refresh/` · **Ledger anchor:** epic **TO BE FILED**
in the `livespec-orchestrator-beads-fabro` beads tenant (`bd-ib-*` prefix) — see
FIRST ACTION.

> Status is **derived from the ledger**, never stored here. Once the epic is
> filed, read it live:
> ```bash
> source /data/projects/1password-env-wrapper/with-livespec-env.sh \
>   bd -C /data/projects/livespec-orchestrator-beads-fabro show <epic-id>
> ```
> Ranked next impl action: `/livespec-orchestrator-beads-fabro:next`.

## Purpose

Fix the **Fabro GitHub-App installation-token 60-minute TTL** so long factory
runs stop dying at push. Today the token is minted ONCE at dispatch with **no
per-node refresh**, so any factory run whose build exceeds ~60 min (a cold Rust
`cargo` build — e.g. `livespec-console-beads-fabro` at ~67 min) fails at the
**push/PR node** with `Invalid username or token` — an infra expiry, NOT a code
failure. This makes cold-Rust-build (and any long) factory runs un-completable.

This doc is the single resumable entry point — a fresh session should be able to
execute the NEXT ACTION from this file alone (via the read-first chain), no chat
history required.

Repo: `thewoolleyman/livespec-orchestrator-beads-fabro` (host checkout
`/data/projects/livespec-orchestrator-beads-fabro`). The Fabro fork:
`thewoolleyman/fabro` (host checkout `/data/projects/fabro`; upstream
`fabro-sh/fabro`).

## The bug (what is known)

- The fleet Fabro GitHub-App **installation token has a 60-min hard TTL**, minted
  once at dispatch. There is NO per-node refresh.
- Surfaced 2026-07-07 (CN1 console/Rust dispatch): a cold Rust `cargo` build
  (~67 min for `livespec-console-beads-fabro`) exceeds the TTL, so the in-sandbox
  **push/PR node** presents an EXPIRED token → `Invalid username or token`.
- Framing from `bd-ib-4sy` (beads-fabro tenant): "the in-sandbox PR node **rides
  the launch-time `GH_TOKEN` sandbox-env**" — the token is injected as a sandbox
  env var at launch and the PR node reuses that stale one.
- DURABLE FIX DIRECTION (per the `livespec-nrdk` candidate slice): **JIT-refresh
  the token at the push/PR node**.

## THE ROUTE QUESTION (settle this FIRST, before implementing)

The fix location is UNDECIDED. Settle it with evidence, then record the decision
on the epic:

- **Route A — upstream Fabro (re-mint at the PR node).** If the PR/push node
  reuses a launch-time env token, the fabro workflow itself must re-mint/refresh
  at that node. This is a cross-fork upstream PR into `fabro-sh/fabro` from the
  `thewoolleyman/fabro` fork — the SAME pattern as the checkpoint-timeout fix
  (PR #552). Investigate: where does fabro set/consume the push-node `GH_TOKEN`?
  (mirror how #552 located `sandbox_git.rs`; look for the PR/push node + token
  handling in the fork's workflow crates).
- **Route B — dispatcher-side (livespec).** If livespec's Dispatcher
  (`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/dispatcher.py`)
  mints + injects the token at dispatch, a livespec-side fix could inject a
  refreshable credential or re-project a fresh token before the push node.
  Investigate: how does the Dispatcher provide `GH_TOKEN` to the fabro run? Is the
  60-min TTL an inherent GitHub-App-installation-token property or a mint-scope
  choice?
- Likely BOTH interact (the TTL is a GitHub property; the refresh must happen
  where the push runs). Determine the minimal correct fix + which repo owns it.

## FIRST ACTION (execute from this file alone)

1. **Investigate the route** (A vs B): read the Dispatcher token-injection path
   (beads-fabro `dispatcher.py`) AND the fabro fork's push-node token handling
   (`/data/projects/fabro`, mirror #552's method). Pin the exact code sites.
   Confirm whether a GitHub-App installation token can be re-minted JIT at the
   push node.
2. **Settle the route + record it on the epic.** Route A → deliverable is a
   cross-fork fabro PR (like #552) + a livespec-side wiring/config change; Route B
   → a beads-fabro dispatcher change. HALT + surface to the maintainer if the
   route is a genuine judgment call or needs a new external dependency.
3. **Anchor a ledger epic** in the `bd-ib` tenant: *"Fabro push-node token
   JIT-refresh — long factory runs (>60-min TTL) no longer die at push."*
   Prose-link the related items (`bd-ib-4sy` remint coverage, `bd-ib-6vu`
   parked-run credential re-projection, `bd-ib-un226z` dual-credential
   projection; the `livespec-nrdk` candidate slice). File dependency-layered
   slices.
4. **Implement** — through the factory (product `.py` → Red-Green-Replay) for a
   dispatcher-side fix, OR drive the upstream fabro PR (Route A; surface before
   opening it).
5. **Live-exercise the fix** ("done means exercised live"): the ONLY real proof
   is a genuinely **>60-minute factory run that pushes successfully** (a cold Rust
   build like the console). A short run proves NOTHING.

## Read-first chain (open these, in order, before acting)

1. **THIS handoff.**
2. `live-adversarial-review-prompt.md` (sibling) — the attack points a live
   reviewer uses to keep the driver honest.
3. The related ledger items (live): `bd-ib-4sy`, `bd-ib-6vu`, `bd-ib-un226z`
   (beads-fabro tenant); the `livespec-nrdk` candidate slice (core tenant — read
   its token-TTL note).
4. The checkpoint-timeout precedent: `fabro-sh/fabro` PR #552 + the fork branch
   `feat/configurable-checkpoint-commit-timeout` (`/data/projects/fabro`) — the
   model for a cross-fork upstream fabro fix + its livespec-side config wiring.
5. The Dispatcher:
   `livespec-orchestrator-beads-fabro/.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/dispatcher.py`.

## Standing disciplines (apply throughout)

- Repo mutations: worktree → PR → rebase-merge; `mise exec -- git`; NEVER
  `--no-verify`; product `.py` uses the Red-Green-Replay ritual. Doc-only plan
  edits use `docs(plan): ...`.
- **Secrets probe-only** (`printenv NAME | wc -c`); NEVER echo a token. The
  subject IS a live GitHub credential — extreme care; on any accidental exposure,
  ROTATE.
- **"Done means exercised live":** a >60-min factory run that pushes green is the
  acceptance bar; no short-run substitute, no unit-test-only proof.
- Independent Fable review before any spec ratification; verify sub-agent claims
  (static facts + your own live re-run), never trust a self-summary.
- Route A (cross-fork fabro PR): drive from `/data/projects/fabro` (origin
  `thewoolleyman/fabro`, upstream `fabro-sh/fabro`); PR cross-fork into upstream —
  and SURFACE before opening it (outward-facing).

## Autonomy posture

Fresh plan; **no standing auto-accept authorization.** Proceed through the route
investigation + anchor + groom autonomously, but HALT + report on: the route
decision if it is a genuine judgment call, any new external dependency, any spec
ratification, opening the upstream fabro PR (outward-facing), or any
irreversible act.

## Relationship to other work

- Sibling of the **checkpoint-timeout fix** (`fabro-sh/fabro` PR #552, item
  `bd-ib-6ka`) — same "make the factory robust for gate-heavy / long-running
  core+Rust repos" family; DISTINCT bug (that one = 30s git-commit timeout; THIS
  one = 60-min token TTL). #552 is the working model for a cross-fork fabro fix.
- Extracted from `livespec-nrdk` (factory-safe-by-default), where this lived as a
  deferred candidate slice; sibling of `bd-gj-9sj` (janitor worktree-pack
  hydration). This thread gives the token-TTL fix its own driven track.
