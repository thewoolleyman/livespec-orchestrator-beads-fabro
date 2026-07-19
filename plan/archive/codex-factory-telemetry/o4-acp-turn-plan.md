# O4 execution plan — a `run_turn` ACP span (command / config_name / visit / stop_reason) (bd-ib-98c.7)

**Execution-ready build plan for O4**, the fourth slice of the outward fabro emitter
spine. Grounded in fresh code verification on `factory-integration` (2026-07-17, tip
`b651dba`, which carries O1 + O2). Companion to `handoff.md`, `emitter-replan.md`,
`o1-worker-exporter-plan.md`, and `o2-traceparent-plan.md`.

## Why O4

O1 exports fabro's span tree; O2 joins the server and worker halves into one trace; O3
was confirmed already-covered (the node-lifecycle "which-node-ran" layer arrives on the
existing `Stage started/completed` telemetry). The one **genuine remaining gap**, confirmed
against the live `fabro` dataset (O2 proof trace `d74367bc…`), is **per-ACP-turn detail**:
there is NO `run_turn` span today, so the finest per-agent granularity is the
`handler_type=agent` `Stage started/completed` telemetry, which does not carry what the
specific agent turn ran (`command`) or how it ended (`stop_reason`). O4 adds a `run_turn`
span carrying that. (Terminology: those `Stage` records are tracing EVENTS, not spans —
`fabro-workflow` has no spans of its own pre-O4 — so they land in Honeycomb as span-event
rows. This matters for the verification step below.)

## The seam (verified on `factory-integration`, `b651dba`)

`lib/crates/fabro-workflow/src/handler/llm/acp.rs`, the `run_turn` method (`:196`):

- **No span exists here.** Repo-wide, `fabro-workflow` has ZERO `info_span!` / `.instrument`
  sites (verified), so O4 CREATES the span — it does not add fields to an existing one.
- **The call to wrap:** `fabro_acp::run_acp_turn(AcpRunRequest { … }).await` at `:333-348`,
  whose result is `match`ed at `:349-410`.
- **Fields, all already in scope at the seam (no new plumbing):**
  - `command` — `command_display` (a `String`) captured at `:212` as
    `process_spec.to_string()` BEFORE `process_spec` is moved into the request at `:334`.
    Use `command_display`; do not re-touch `process_spec`.
  - `config_name` — `process_spec.name().map(str::to_string)` at `:206` (`Option<String>`).
  - `visit` — `stage_scope.visit`, a plain `u32` (`stage_scope.rs:12`), already handed to
    `Event::AgentAcpStarted` at `:213-221`. (This corrects the earlier "visit is
    workflow-layer, defer" note — it is a field right here.)
  - `node_id` — `node.id` at `:215`.
  - `stop_reason` — knowable on two of the five match arms:
    - `Ok(result)` (`:350`): `render_stop_reason(&result.stop_reason)` (already computed
      for the event at `:356`).
    - `Err(AcpError::StopReason { stop_reason, .. })` (`:393`): the `stop_reason` string
      (already used at `:399`).
    - The other three arms — `Cancelled` (`:363`), `TimedOut` (`:375`), generic `Err`
      (`:409`) — carry no model stop reason; leave `stop_reason` empty OR record a literal
      (`"cancelled"` / `"timed_out"`) for completeness (design choice; see below).

## Dependencies already present

`fabro-workflow/Cargo.toml` has `tracing.workspace = true`. `tracing::info_span!` is
available; the `Instrument` trait needs `use tracing::Instrument as _;` (unused in the
crate today, so O4 introduces it cleanly, mirroring how O2 introduced propagation). **No
new dependency.** The span exports with no other wiring: fabro-workflow spans already reach
the worker's O1 OTLP layer (the existing `Stage`/`Edge` telemetry has
`target: fabro_workflow::event::events`), and the `run_turn` span nests under the current
`Stage` span, so O2's join carries it into the one dispatch trace automatically.

## Design

Create the span before the call, `.instrument()` the future, and `record` the outcome
field after the `.await` (the original `turn_span` handle stays alive across the match, so
the deferred `record` lands before the span closes — the same handle-outlives-future
pattern O2 uses):

```rust
use tracing::Instrument as _;

let turn_span = tracing::info_span!(
    "run_turn",
    node_id = %node.id,
    command = %command_display,
    config_name = config_name.as_deref().unwrap_or_default(),
    visit = stage_scope.visit,
    stop_reason = tracing::field::Empty,   // filled on the two arms that know it
);

let result = match fabro_acp::run_acp_turn(AcpRunRequest { /* :334-346 unchanged */ })
    .instrument(turn_span.clone())
    .await
{
    Ok(result) => {
        turn_span.record(
            "stop_reason",
            tracing::field::display(render_stop_reason(&result.stop_reason)),
        );
        /* existing emit_scoped(AgentAcpCompleted…) at :351-360 */
        result
    }
    Err(AcpError::StopReason { stop_reason, text }) => {
        turn_span.record("stop_reason", tracing::field::display(&stop_reason));
        /* existing emit_scoped(…) + early return at :394-407 */
    }
    /* Cancelled / TimedOut / generic Err arms unchanged */
};
```

`command_display` is currently consumed by the `AgentAcpStarted` emit at `:217` (it is
`command: command_display`, a move). If the span needs it too, either `.clone()` it for the
span or reorder so the span borrows first — verify the borrow/move at build time and pick
the minimal change (a single `command_display.clone()` is the low-blast-radius option).

## What O4 does NOT do (still deferred)

- `files_touched` — genuinely absent from `AcpRunResult`; needs git-diff derivation
  (`changed_files::detect_changed_files` at `:331` gives `files_before`; a matching after
  would derive the delta). Workflow-layer follow-on, out of O4-EASY scope.
- Token/cost — O5 (`bd-ib-98c.8`), deferred (`acp.rs` hardcodes `usage: None`).

## Guardrails

- **Inert when export is off** — like every emitter slice: with no OTLP layer installed the
  span is created but exports nowhere; behavior is unchanged. The span carries no secret
  (command name, config name, a visit counter, a stop-reason enum — no prompt text, no
  tool I/O; keep it that way — do NOT add `result.text`/`stderr` to the span).
- **No behavior change to the turn** — the `.instrument()` wraps the existing future and the
  `record` calls are additive; the match arms, events, and early returns are untouched.

## Verification (the gate before calling O4 done)

1. CI-equivalent on `factory-integration` under the pinned `nightly-2026-04-14`:
   `fmt --check --all`, `clippy --locked --workspace --all-targets -- -D warnings`, and
   `nextest` (prefer `-j4` locally — full-parallelism integration flakes are environmental,
   as seen on O2). Add a unit test asserting the span is created with the four fields when a
   turn runs (a fabro-workflow test that drives `run_turn` against a fake ACP backend, or at
   minimum a focused test of the field wiring).
2. Rebuild + re-pin the host binary (per `orchestrator-image/README.md`; the O2 cutover at
   `b651dba` is the worked example — and MIND THE SHA-STAMP TRAP: amend before the final
   build, because the binary embeds git HEAD at build start; a mid-build amend orphans the
   stamped SHA and violates the reachability constraint). Update the runbook + `AGENTS.md`
   pin lines in lockstep (the ratified `constraints.md` rule).
3. Proof-dispatch (promote a throwaway item to `ready`). Then in Honeycomb (`livespec` env,
   `fabro` dataset): a `run_turn` span must now appear carrying `command` / `config_name` /
   `visit` / `stop_reason`, inside the one dispatch trace. Today (pre-O4) `list_spans` shows
   no `run_turn`.
   **Expect the worker `run` span as its parent — NOT a `Stage` span.** `fabro-workflow` has
   zero spans of its own, so there is no `handler_type=agent` Stage SPAN to nest under:
   "Stage started/completed" are tracing EVENTS (`info!` at `event/events.rs`), which reach
   Honeycomb as span-event rows, not spans. The nearest enclosing span is the worker's root
   `run` span (`fabro-cli/src/commands/run/mod.rs`, whose `.instrument(run_span)` covers the
   whole engine execution; the agent handler awaits `backend.run` inline). An earlier draft of
   this step asserted a Stage-span parent — that check can never pass and would misread a
   correct result as a failure.
4. Update `bd-ib-98c.7` + `handoff.md`.

## Review criteria (Codex + Fable loops, like O1/O2)

Completeness (all five match arms handled; `stop_reason` recorded on both arms that know it;
the `command_display` move/borrow resolved); narrow fix; preserves all fabro APIs; no
regression in fabro OR livespec; inert when export is off; NO secret/prompt/tool-output on
the span. Run BOTH adversarial loops before the upstream-facing carry lands, and — per the
lesson logged this session — invoke raw `codex exec` with `< /dev/null` so it does not hang
on stdin.

## Ledger / sequencing

O4 (`bd-ib-98c.7`) depends on O3 (`bd-ib-98c.6`), which is verification-complete
(already-covered) but formally held open behind the O1→O2 upstream-transport entanglement
(`bd-ib-i4r`); the dependency guard will block a clean `bd close` on O4 the same way, so
expect the maintainer to force-close the chain when `bd-ib-i4r` resolves. O4's build does not
need O3 closed — O3 required no code, so O4 rides directly on the O1/O2 seams already pinned.
O5 (`bd-ib-98c.8`, token/cost) stays deferred.
