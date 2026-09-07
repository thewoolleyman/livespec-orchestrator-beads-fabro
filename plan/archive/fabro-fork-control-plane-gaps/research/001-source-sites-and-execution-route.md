# 001 — The six fabro-side gaps: source sites at the pinned fork, sibling state, and the execution route

Initial research note for plan thread `fabro-fork-control-plane-gaps` (epic
`bd-ib-bb41`), written 2026-09-06 by the session that adopted the epic into a
filesystem thread. The epic and its six children were filed 2026-09-01 by the
console plan session on the maintainer's ownership ruling; this note is the
orchestrator side picking the work up. Labels **measured** (run today, with the
instrument named) and **inferred** (reasoned, not yet run). Status is read from
the ledger, never from this file.

## 1. Provenance and ownership (from the epic, restated once)

The six children are the overseer-retirement failures that "hit any dispatch
path including the console's": they survive whatever drives the factory.
Maintainer ruling 2026-09-01: tracked in THIS tenant because the orchestrator
owns the pinned fabro fork and the consume path (the bundled
`implement-work-item` workflow re-pins); adopters (console, homelab) re-pin.
The console holds a proxy, `livespec-console-beads-fabro-pzbdbo.4`
(`blocked`, "BLOCKED-ON orchestrator bd-ib-bb41"), and the console's
re-fork stands in for these until the fork converges (console decision D3).
Do not absorb any of these into `bd-ib-wcuauj` (runaway-process-containment).

## 2. The pinned build and the carrier branch (measured 2026-09-06)

| Fact | Value | Instrument |
|---|---|---|
| Host binary | `fabro 0.254.0 (8de6611 2026-07-30)` | `~/.fabro/bin/fabro --version` |
| Carrier tip | `56a14c871` (test-only guard for O2, 2026-08-22) | `git log origin/factory-integration` in `/data/projects/fabro` after fetch |
| Pinned commit reachable from carrier | yes | `git merge-base --is-ancestor 8de661118 origin/factory-integration` |
| Upstream state | tags up to `v0.330.0-nightly.0` exist in the fork's fetch; no stable release since `v0.254.0` | `git tag --sort=-v:refname` |
| Base ceiling | `< 0.256` until `bd-ib-6qu` (workflow.fabro migration) lands | `SPECIFICATION/constraints.md` §"Fabro runtime constraints" |

"Stable-frozen" in the epic text means "no stable release", not "no upstream
commits": upstream keeps shipping nightlies. Every fix here lands on the
0.254 base and is forward-ported when `bd-ib-6qu` moves the base. That is a
standing deferral, not a blocker.

The composition rule is normative: `factory-integration` carries the base
plus EVERY pending fix, the runbook table in `orchestrator-image/README.md`
is updated in the same change, and every carried-set change means rebuild,
re-pin (outgoing binary retained as a `.bak`), server restart, AND an
orchestrator-image rebuild. The rebuild is the shared expensive step, which
is why §6 proposes waves rather than six re-pins.

## 3. Source sites, one per child (measured on `origin/factory-integration` at `56a14c871`)

All line numbers are on that tip. Each site was located with `git grep` on
the ref and read with `git show <ref>:<path>`, not from a working tree.

### .1 — needs-human preservation ref collides on `unknown-run`

- `FABRO_RUN_ID` is inserted in exactly one place: `lib/crates/fabro-hooks/src/executor.rs:165`,
  beside `FABRO_WORKFLOW` (:166) and `FABRO_NODE_ID` (:168). That is the HOOK
  executor. No `FABRO_*` insertion exists in `fabro-workflow/src` outside tests.
- The `unknown-run` placeholder is OURS, not fabro's:
  `.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro:283`
  reads `${FABRO_RUN_ID:-unknown-run}`. The comment at :266 expected a
  run-scoped ref; the fallback silently defeats it.
- Consequence: this child has TWO halves. The fork half exports the run id to
  script nodes (inferred: the same trio the hook executor inserts). The
  orchestrator half is in this repo's `workflow.fabro` and is FACTORY-SAFE:
  drop the placeholder and fail loudly when no id is present (the child's own
  criterion 3). Whether 0.254's script-template context already exposes a run
  id (which would make the fork half unnecessary) is **unverified** — §7(a).

### .2 — sandbox PID 1 is `sleep infinity`

- `lib/crates/fabro-sandbox/src/docker.rs:1137`: the container command is
  `/bin/bash -lc "mkdir -p <workdir> && sleep infinity"`.
- `host_config()` at :1120 sets only `binds`, `network_mode`, `memory`,
  `cpu_quota`; the bollard `HostConfig::init` field is not set, and
  `--init` appears nowhere under `lib/crates/fabro-sandbox` (grep, zero hits).
- Inferred fix: `init: Some(true)` in `host_config()` makes Docker's bundled
  `docker-init` (tini) PID 1 with no image change. Alternative, `exec tini`
  in the command, needs `tini` in the sandbox image (ubuntu:24.04 base;
  presence **unverified**, §7(b)). Prefer the host-config route.

### .3 — `AgentAcpTimedOut` reports `stdout: ""`

- `lib/crates/fabro-workflow/src/handler/llm/acp.rs:398`: on
  `AcpError::TimedOut { exec_output_tail }` the event is built with
  `stdout: String::new()` and `stderr` taken from the tail. The text the
  session accumulated in `read_live_session` is dropped on this arm.
- `read_live_session` (`fabro-acp/src/session.rs` ~:404) already invokes an
  `on_activity` callback on EVERY session update, so a last-activity
  timestamp and an update counter are one field away each. A per-TOOL count
  needs .4.

### .4 — no per-tool ACP events reach the run

- `lib/crates/fabro-acp/src/session.rs:411`: the notification handler matches
  ONLY `SessionUpdate::AgentMessageChunk(ContentChunk { content: Text, .. })`
  and appends text; every other `SessionUpdate` variant (tool call start and
  update, plan, thought chunks) falls to `.otherwise_ignore()`.
- Inferred shape: emit a bounded run event per tool-call start/complete (name,
  elapsed, ok/exit; no payload) through the same emitter `acp.rs` uses for
  `AgentAcp*`, so it reaches the store, the SSE attach stream and `dump`.
  Whether a new `EventBody` variant is needed or an existing generic event
  fits is **unverified**.

### .5 — checkpoint commits use `--allow-empty` unconditionally

- `lib/crates/fabro-workflow/src/sandbox_git.rs:135`: the checkpoint commit
  is `git … commit --allow-empty{no_verify} -F <msg>` with no staged-change
  check. `handler/parallel.rs:691` has the same shape and its tests at :971
  and :987 assert the flag is present, so a fix there must update those tests.
- The other `--allow-empty` hits (`lifecycle/git.rs:632`,
  `pipeline/finalize.rs:775`, `run_metadata.rs:612`) create an "initial"
  commit in test or bootstrap fixtures and are out of scope.
- Orchestrator half is already closed: `bd-ib-xmom` (an empty merged diff
  never grades as delivered). This child is the fabro half only.

### .6 — ACP permission and user-input requests are auto-answered

- `lib/crates/fabro-acp/src/session.rs:313` `select_permission_outcome`:
  `AllowAlways` → `AllowOnce` → first non-reject option → `Cancelled`.
  Wired at :205 in `on_receive_request`, with cancellation as the only other
  outcome. No route exists for a user-input request.
- The orchestrator CONSUMER half is already built and closed:
  `bd-ib-w3nwz5.3` (b3, fabro interview questions published in
  needs-attention with a typed answer route) and `bd-ib-aqith2` (b3.S1).
  This child is the PRODUCER; until it lands, b3 has nothing to publish for a
  permission question because the node never parks.
- The fabro questions API the child names (`GET /runs/{id}/questions`,
  `POST …/answer`) exists per the console research; its server-side site and
  whether a worker node can create a question programmatically are
  **unverified** — §7(c),(d). This is the largest child by far.

## 4. Sibling and cross-tenant state (measured 2026-09-06, `bd list --status all --limit 0 --json`, 942 records)

| Item | Status | Relation |
|---|---|---|
| `bd-ib-bb41.1` … `.6` | all `backlog`, no metadata, no dispatch claim, only the `parent-child` edge | the children |
| `bd-ib-w3nwz5` (console-control-plane-primitives) | `backlog` epic | references this epic as "its own epic", not moved; console re-fork stands in until convergence |
| `bd-ib-w3nwz5.3`, `bd-ib-aqith2` | `closed` | .6's consumer half |
| `bd-ib-xmom` | `closed` | .5's orchestrator half |
| `bd-ib-dgu3qg` (S6 needs-human terminal) | `closed` | introduced the preservation ref .1 collides on |
| `bd-ib-b5dg` (acp-implement-zero-output-hang) | `backlog` epic, typed next action `human` on `bd-ib-25fjk2` (metrics-pipeline regression) | .3's criterion 3 says b5dg is closed or re-cut once .3 lands; that plan's own research 009 now frames its heartbeat as liveness, not progress, which is exactly the axis .3 supplies |
| `bd-ib-wcuauj`, `.3` | `backlog` | adjacent to .2 (sandbox restarted by POST /ssh); not the same defect |
| `bd-ib-j81s` (backlog sweep) | `ready` | must not re-file these six |
| `bd-ib-6qu` (0.254 → 0.290 migration) | `backlog` | forward-port target; does not change this plan |
| `livespec-console-beads-fabro-pzbdbo.4` | `blocked` | the console proxy on this epic |

Prior-art scan: every record above was scanned (title plus description) for
zombie / defunct / PID 1 / allow-empty / AgentAcpTimedOut /
request_permission / AllowAlways / FABRO_RUN_ID / unknown-run / tool-call
event / interview question / empty checkpoint. No pre-existing item covers any
of the six beyond the cross-references in this table. `bd-ib-zg5ndm` (zombie
fabro-run reaping) is host-side run reaping, a different class from .2's
in-container process reaping.

## 5. The execution route — the load-bearing finding

The fork is not a dispatchable target and the mirror convention does not apply:

- `/data/projects/fabro` has no `.beads/` and no `.livespec.jsonc`
  (measured). The Dispatcher sandboxes the `--repo` TENANT repo; the
  cross-tenant execution mirror (`.ai/cross-tenant-execution-mirror.md`)
  needs the implementation repo to have its own tenant, which the fork lacks.
- Prior art settles the route. Every fork-local fix carried today (O1
  `bd-ib-98c.4`, O2 `.5`, O4 `.7`, P2 `.12`, the O2 guard `.11`) was
  labelled "OUTWARD-FACING fabro (Rust)", built operator-side on a branch off
  `factory-integration` in `thewoolleyman/fabro`, opened as a fork PR
  (`#1`, `#3`), reviewed by a Codex plus Claude adversarial pair, rebase-merged
  into `factory-integration`, then rebuilt, re-pinned, image-rebuilt and
  proven by a live dispatch. The maintainer's "prefer factory dispatch" rule
  names this exact class as the hand-build exception.
- Therefore every child EXCEPT .1's orchestrator half is factory-ineligible,
  and each must be RECORDED as such on the item before any handoff names an
  in-session route (plan prose Step 4, rule 3). .1's orchestrator half is a
  `workflow.fabro` change in this repo and dispatches normally.

Build constraints (measured 2026-09-06 08:54): this host reported load
average 26.7 on 18 cores, so a release build of the fork here competes with
live work; `bd-ib-qvoq3u` (closed) built the pinned fork on hp. The fork's
CI does not run on `factory-integration` PRs (its `rust.yml` triggers only
on pull requests targeting `main`, recorded on `bd-ib-98c.11`), so local
validation under the pinned toolchain (nightly-2026-04-14, per `bd-ib-98c.4`)
is the only validation. Both facts belong in each child's brief.

Not explored, recorded so nobody re-derives it silently: dispatching a fork
fix through an item in THIS tenant whose sandbox clones the fork. The bundled
implement workflow's PR stage targets the tenant repo, so it would need
workflow work first. Deferred; revisit only if the hand-build route proves
too slow across waves.

## 6. Proposed ordering (a proposal; the scope event cuts it)

One rebuild, re-pin and image rebuild per wave, runbook table updated in the
same fork change set.

- **Wave A — small, low-risk, one re-pin.** .2 (`init: Some(true)`), .5
  (staged-change check before the checkpoint commit, distinct event or skip),
  .3 (timeout event carries the accumulated text tail, last-activity
  timestamp and update count), and .1's fork half (script-node env trio).
- **Wave B — the event and question surfaces.** .4 (per-tool run events),
  which then supplies .3's per-tool count, and .6 (permission and user-input
  requests as fabro interview questions, policy-gated, default unchanged).
  .6 alone is most of the plan's engineering; it is what unblocks the
  console's b3 consumer.
- **In parallel, factory-dispatched here:** .1's orchestrator half in
  `workflow.fabro` (remove the placeholder; fail loudly without an id).

## 7. Open questions for the scope event

- (a) Does the 0.254 script-node template context expose the run id? If yes,
  .1's fork half collapses into the orchestrator half.
- (b) Does the Docker daemon on hp and on vps carry `docker-init`, so
  `init: Some(true)` works with no image change?
- (c) What is the user-input request method in the pinned
  `agent-client-protocol` crate version, and does the pinned Claude adapter
  emit it?
- (d) Where is the questions API implemented server-side, and can a worker
  node create and await a question through the existing interview handler?
- (e) Which host builds the fork for each wave (hp per `bd-ib-qvoq3u`, or
  here once load allows)?
- (f) Does .3's landing re-cut `bd-ib-b5dg` or close it, given that plan's
  own 009 conclusion?
