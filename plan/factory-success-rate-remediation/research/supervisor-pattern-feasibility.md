# Supervisor (watch-and-steer) pattern feasibility for the fabro factory

Question investigated: could one agent WATCH another agent's
implementing session in near-real-time (via tmux / socket / OTel / ACP
events / hooks) and offer corrective feedback DURING the work, instead
of the current wait-for-failed-review cycle? Source citations are
`file:line` under `/data/projects/fabro` unless noted.

Bottom line: **fabro already ships a mid-run injection channel that
reaches the ACP backend in the running fork server (v0.254.0) —
`fabro steer <run> [--interrupt]` and the HTTP pair API. The hard
limiter is not injection, it is WATCHING:** over the ACP backend
fabro's event/telemetry stream is turn-granular, not intra-turn, so a
watcher sees a 4-hour implement node as "started → silence →
completed" with no per-tool-call visibility. Fine-grained oversight
requires either an in-sandbox Claude Code hook chokepoint (no fabro
fork) or a fork that tees ACP tool-call notifications into the event
stream.

Anchor: `implement` runs `backend="acp"`, ONE turn up to 14400s/4h in a
docker sandbox (`workflow.fabro:73-82`, `workflow.toml:148-153`). From
fabro's view that whole 4h is one ACP `session/prompt` turn with
hundreds of internal tool calls.

## Watching — channel-by-channel feasibility

| Channel | Mechanism | Latency | Granularity over ACP | Works today? |
|---|---|---|---|---|
| fabro SSE `/attach` | `GET /api/v1/runs/{id}/attach` (durable replay + live broadcast); `fabro-server/src/server/handler/events.rs:18-31,75-95,375-509` | Sub-second | **Coarse**: `agent.acp.started` + `agent.acp.completed` (full text at end) + stage transitions; NO per-tool-call events | Yes |
| `fabro events <run> --follow` | CLI over the same stream (`fabro-cli/src/args.rs:421-441`) | Same | Same coarse | Yes |
| Fine-grained event vocabulary (`agent.tool.started/completed`, …) | `fabro-types/src/run_event/mod.rs:193-351` | — | Emitted by fabro's NATIVE agent only, not ACP | Native only |
| Why ACP is coarse | ACP loop accumulates message chunks and `.otherwise_ignore()`s tool-call `session/update`s (`fabro-acp/src/session.rs:403-428`); intra-turn the handler only bumps a liveness timestamp (`handler/llm/acp.rs:78-81,150`) | — | Root cause | — |
| OTel `run_turn` span (fork O4) | `handler/llm/acp.rs:66,165` → Honeycomb | At turn END | Turn-granular | Yes |
| tmux pane scrape | — | — | N/A — the ACP adapter is headless, no pane | No |
| **In-sandbox Claude Code hooks** | PreToolUse/PostToolUse fire synchronously per tool call; committed `.claude/settings.json` rides into the sandbox clone (factory already ships guard hooks: `.claude/settings.json:18-38` in this repo) | Per tool call | **Fine-grained** — the only in-tree way to see every ACP tool call | Yes, IF the adapter honors hooks (unknown #1) |
| eBPF/TLS boundary tracing (AgentSight, arxiv 2508.02736) | External tracer; no SDK/pane needed | Near-real-time | Fine | Would need adding |

## Injection — options

| Option | Today? | Semantics / failure modes |
|---|---|---|
| `fabro steer <run> "<text>"` (queue) | Yes | Delivered at the NEXT turn boundary (`fabro-acp/src/session.rs:351-361`) — for the 4h implement turn that is end-of-node, near-useless mid-work |
| `fabro steer … --interrupt` | Yes | ACP `session/cancel` then re-prompt (`session.rs:363-399`; `args.rs:786-790`) — the ONLY mid-work injection over ACP with Claude; discards in-flight reasoning (disk edits persist). Corroborated by ACP discussion #1220: the Claude path has queue + hard-interrupt only |
| Pair HTTP API | Yes | `POST /runs/{id}/pair` + `…/pair/{id}/messages` (`server/handler/pair.rs:30-39,167-220`) — enqueues a steer WITHOUT interrupt → turn-boundary delivery; requires run status `Running` |
| Claude Code hook verdict (in-sandbox) | Pending adapter confirmation | PreToolUse exit-2/deny or JSON `permissionDecision` + `additionalContext` — synchronous per-tool-call allow/deny/redirect + context injection, no fabro fork; needs sandbox egress |
| Between-node graph edges | Already built | The existing review → review_fix loop IS the sequential supervisor; the DOT vocabulary has no concurrent-observer-node concept |

Version check: steer/pair/attach machinery is an ancestor of BOTH
v0.254.0 and `factory-integration` (verified via
`git merge-base --is-ancestor`) — works against the running server, no
version bump, no conflict with the "never modernize past 0.256" rule.

## Prior art (channel + evidence)

- **Synchronous tool-boundary chokepoint** — the dominant production
  pattern, 4 independent implementations: Claude Code hooks (HTTP hooks
  let an external supervisor return the verdict), OpenAI Agents SDK
  tool guardrails, NVIDIA NeMo execution rails, Invariant Labs proxy
  interception. Best transfer to this factory.
- **Non-interrupting mid-turn steer** — production-real only in Codex
  (`turn/steer`); the Claude/ACP path lacks it (the single biggest
  injection gap).
- **Watch-only**: AgentSight (eBPF), MI9 (arxiv 2508.03858 — the
  blueprint for a supervisor's decision logic), Better Agent (detached
  runners + operator queue).
- **Rejected as models**: LangGraph "supervisor" (orchestration
  ROUTING, not watching), evaluator-optimizer / Reflexion-style
  between-turn critics, Tmux-Orchestrator (needs a pane; ACP is
  headless).
- **Outcome evidence: essentially none** shows concurrent oversight
  improving CODE QUALITY — guardrail systems are validated for
  safety/policy. A quality-supervisor would be novel territory; judge
  it by our own failure data (which currently shows the buckets it
  targets are small — failure-telemetry-2026-07-23.md).

## Candidate designs (ranked by cost; options, no decision)

- **A — Native watch + interrupt-steer, out-of-sandbox (lowest cost).**
  Host supervisor subscribes to `/attach`; on a concerning signal runs
  `fabro steer --interrupt`. All primitives exist today. Limited by
  coarse watch — realistically acts at node boundaries only.
- **B — In-sandbox PreToolUse HTTP hook → external supervisor service
  (medium cost, no fork).** True per-tool-call oversight with a
  synchronous verdict; matches the dominant prior-art pattern. Needs:
  the service, sandbox egress, and confirmation the ACP adapter runs
  project hooks (unknown #1 — verify with a one-shot dispatch carrying
  a logging PreToolUse hook).
- **C — Fork fabro to emit ACP tool-call events natively (highest
  cost).** Change `fabro-acp/src/session.rs:403-428` to tee tool-call
  `session/update`s into the event stream; gives `/attach` fine-grained
  ACP visibility; optionally adopt upstream non-interrupting steer if
  ACP grows it. Fork work on the pinned 0.254 base.

Coherent path if ever pursued: B now, C later.

## Unknowns

1. Does the ACP adapter execute Claude Code project hooks in the
   sandbox? (#1 thing to verify; cheap one-shot dispatch test.)
2. Sandbox egress in the factory's effective docker config
   (`network_mode`/`network_allow` knobs found, effective value not).
3. Measured SSE latency (sub-second by construction, not timed).
4. How much useful in-flight reasoning `--interrupt` actually costs.
5. Steer targeting with parallel nodes (broadcast today; moot with one
   active node).
6. fabro API auth mechanics for a bespoke supervisor client.
7. No prior in-repo supervisor/steer/pair design work exists
   (greenfield).
