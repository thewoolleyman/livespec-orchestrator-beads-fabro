# Emitter re-plan — bd-ib-98c.1 (2026-07-15)

**Supersedes the plan bd-ib-98c.1 was written against.** The original item is a
single monolithic outward-facing task ("add `tracing` spans in fabro's ACP handler
mapping `UsageUpdate`/`TurnComplete` → span fields, plus emit four review-gate
attributes"). Two code investigations on 2026-07-14/07-15 falsified that plan and
re-shaped it. This document is the corrected decomposition, grounded in file:line
evidence, plus the one decision the maintainer owns before any of it is filed.

Read alongside: `handoff.md` §"CURRENT STATE" (the falsification summary) and the
ledger comments on `bd-ib-98c.1` / `bd-ib-98c.2` (the raw evidence). Nothing here
is filed yet — this is the drafted cut for approval.

**Adversarial review incorporated (2026-07-15, Fable).** All eight constraints
below and every fabro seam citation were verified against both codebases at the
stated file:line. The review found — and this revision fixes — one design-breaking
flaw: F1's original stderr-sentinel detection was invisible on the green path
(recorded as a rejected design below). F1 now reads the structured
`fabro events --json` stream instead — simpler, and it lands all four review-gate
attributes. The review also tightened O1's acceptance criteria (the host-server
OTEL overlay is constitutive, not a footnote), added an O5 data-dependency check,
and scoped the review-gate equivalence honestly (non-green tails + malformed
verdicts). No dropped constraints were found.

## The one-sentence re-plan

The monolithic emitter is actually **a stack of independent capabilities at two
tiers in a strict dependency order — and the single highest-value signal
(ship-on-cap) can be delivered factory-safe, in days, without ANY of the hard
outward-facing fabro work.** So: carve the ship-on-cap signal out as its own
factory-safe slice, and reduce the outward-facing track to a clean,
single-purpose orchestration-observability spine.

## Constraint set (code-verified ground truth)

Every emitter design must satisfy these. Citations are to
`~/.worktrees/fabro/factory-integration` (fabro) and this repo (dispatcher).

1. **The transport exists but is INERT in the emitting process.** The OTLP/HTTP
   exporter (`bd-ib-i4r`, PR #576, on `factory-integration`) is opt-in and
   no-op unless an OTLP endpoint env is set (`fabro-cli/src/otel.rs`
   `resolve_endpoint()` → `otel_layer()` early-returns `None`). The ACP handler
   runs in a **server-spawned `fabro __run-worker` subprocess** (production
   always takes the subprocess path). `apply_worker_env`
   (`fabro-server/src/spawn_env.rs:29`, allowlist `:6-25`) does `env_clear()` +
   **exact-name** copy with **no `OTEL_*`** — so the worker's env has no
   endpoint and the exporter stays inert. **The sandbox OTEL overlay never
   reaches the emitting process.**

2. **The worker already installs the layer — only the env is missing.**
   `logging.rs:419` and `:453` (both worker subscribers) end in
   `.with(otel::otel_layer())`; `main.rs:252` calls `init_tracing` for every
   subcommand. So activation is an **env-plumbing** change, not subscriber work.
   Preferred seam: explicit re-injection at `worker_runtime.rs:89-99`, beside the
   existing `FABRO_LOG` / `FABRO_CONFIG` / `FABRO_WORKER_TOKEN` re-injections —
   NOT widening the fail-closed allowlist (there is a `worker_allowlist_is_fail_closed`
   test asserting nothing leaks by default).

3. **`OTEL_EXPORTER_OTLP_HEADERS` is the secret and must NOT be blanket-copied.**
   The 5 non-secret consts (`OTEL_EXPORTER_OTLP_{ENDPOINT,TRACES_ENDPOINT,PROTOCOL,
   TRACES_PROTOCOL}`, `OTEL_SERVICE_NAME`) are declared in
   `fabro-static/src/env_vars.rs:140-146`; the Honeycomb-key-bearing
   `OTEL_EXPORTER_OTLP_HEADERS` is deliberately **absent** (the exporter reads it
   from raw env — `otel.rs:19`). Re-inject only the 5; use a no-auth-header
   receiver endpoint or server-side header injection for auth.

4. **Trace context does not cross the process boundary.** Server
   (`server.rs:4339`) and worker (`commands/run/mod.rs:96`) each create a bare
   `info_span!("run", id)`; no `traceparent` is passed. Enabling OTLP on both
   today yields **two disconnected traces per run**. A W3C `traceparent` must be
   captured in `execute_run` (before the `spawn_blocking` at `server.rs:4159`,
   whose thread does not carry the run span), injected at `worker_runtime.rs:89-99`,
   and extracted in `commands/run/mod.rs:96` before the worker run span.

5. **fabro-workflow has ZERO span instrumentation.** The tracing tree is one span
   deep; node/turn spans must be **created new**. The metadata-complete seam is
   **`fabro-workflow/src/lifecycle/event.rs`** `EventLifecycle` — `before_attempt`
   (`:197`, `StageStarted{node_id,name,index,handler_type,attempt,max_attempts}`)
   and `after_node` (`:263`, `StageCompleted{…files_touched,billing,response,status}`).
   (NOT `node_handler.rs:36`, which only has `node`/`context` in scope.)

6. **No token/cost on the ACP path today — but the seam is reachable.**
   `acp.rs:424` hardcodes `usage: None`, forced upstream (`AcpRunResult`,
   `fabro-acp/src/session.rs:173-179`, has no usage field). **However** the
   workspace `Cargo.toml:12` already enables
   `agent-client-protocol/unstable_session_usage`, which exposes an
   `Option<Usage>` on `PromptResponse` (input/output/cached/thought tokens) that
   nothing in fabro reads yet. So token/cost is an **unplumbed-but-buildable**
   upstream seam, not a dead end. ACP `ToolCall` notifications are also dropped
   (`session.rs` handles only `AgentMessageChunk` text; every other
   `SessionUpdate` variant falls through).

7. **The receiver silently drops any new field.** `_otel_scrub.py`'s
   `ATTRIBUTE_ALLOWLIST` is fail-closed; `_otel_enrich.py:213-215`
   (`if not is_allowed_attr(key=key): continue`) drops non-allowlisted keys with
   **no log, no warning, no counter**. Any new emitter field must be allowlisted
   in lockstep or it vanishes with no signal ("spans appear" ≠ "the emitter works").

8. **Protocol mismatch on the fabro path.** The exporter defaults to
   `http/protobuf`; our receiver is JSON-only. The fabro OTEL overlay must set
   `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`, or the POST is rejected and spans are
   silently dropped.

## The pivotal finding: the review-gate signal is recoverable factory-safe — from the structured event stream

The four review-gate attributes (`review.verdict`, `review.fix_rounds`,
`review.hit_cap`, `pr.shipped_on_cap`) are the reason the emitter's scope was
expanded on 2026-07-14 — they answer the standing question *"how often does the
factory ship a PR despite the in-loop review never approving (ship-on-cap)?"*
The dispatcher investigation found these are **not parsed by the dispatcher
today**, and the ledger concluded they therefore require the outward-facing fabro
emitter. **That conclusion is wrong.** The Fable review of this plan verified
against fabro's own source that all four are already present in the structured
run-event stream — the dispatcher simply doesn't read those fields.

**The mechanism:** `fabro events <run-id> --json` — whose argv builder already
exists in the dispatcher (`_dispatcher_fabro_argv.py:198-205`, used today only by
the stall watchdog, and only for timestamps) — dumps the full event stream. Each
node's `StageCompleted` event carries `preferred_label` **and** `node_visits`
(`fabro-types/src/run_event/stage.rs:24-43`, emitted at
`fabro-workflow/src/lifecycle/event.rs:301+`). Parsing the **review** node's
`StageCompleted` records yields **all four** attributes directly and
authoritatively — the verdict on each visit, the fix-round count, whether the cap
was hit, and whether a PR followed a non-approving final verdict — with **no
`workflow.fabro` change and no upstream fabro PR**. This is the same
"read structured post-run state" pattern the cost seam already uses
(`_dispatcher_cost` over `fabro ps -a --json`), and the dispatcher already invokes
the sibling `fabro inspect <run-id> --json` on every run, green included
(`_dispatcher_engine.py:257→323`).

### Rejected design — the stderr sentinel (recorded so it is not re-proposed)

An earlier draft of this plan proposed mirroring the janitor's
`LIVESPEC_NON_CONVERGED` sentinel: a `ship_on_cap` script node on a conditioned
`review -> ship_on_cap [preferred_label=fix && node_visit_count >= 3]` edge that
echoes a marker to stderr, grepped by the dispatcher. **This does not work, and
the Fable review caught why.** The janitor sentinel reaches the dispatcher *only
because that node exits 1* — fabro's command handler embeds script output into the
outcome (`append_output_tail`) exclusively on failure/timeout/cancel; on a
**success (exit 0)** the output goes only to the run-store recorder, and the
foreground, non-verbose `fabro run` renders the stage as nothing but
`✓ <label> <duration>`. A ship-on-cap node is by definition on the **green** path,
so its stderr marker never enters the dispatcher's captured
`fabro.stdout`/`fabro.stderr`, the grep never matches, and F1 would silently
record `shipped_on_cap=false` forever — the exact "false success" trap constraint
7 warns about, one layer up. (The DSL parts of that design were all sound — `>=`
is supported [`fabro-workflow/src/condition.rs:102-118`], a satisfied condition
wins edge precedence [`graph/routing.rs:35-64`], an exit-0 pass-through preserves
green [`handler/command.rs`] — but the detection *channel* was fatally chosen.)
The `fabro events --json` route is strictly simpler and structurally reliable, so
the sentinel node is dropped entirely.

The outward-facing O3 (node-lifecycle spans) would *also* surface these fields in
fabro's own trace once its spans carry `preferred_label`/`node_visits` — but F1 via
the event stream already answers the business question in full, so **O3 is no
longer on the review-gate critical path**; it is per-node *trace* observability,
not the review-gate source.

## Proposed decomposition (drafted cut — nothing filed)

### Tier F — factory-safe, ours, buildable NOW (no upstream dependency)

**F1 — Review-gate attributes from the run-event stream.** *(the high-value standalone slice; dispatcher-only, no `workflow.fabro` change)*
- `_dispatcher_*`: after a run, query `fabro events <run-id> --json` (argv builder
  already exists), parse the review node's `StageCompleted` records, and derive the
  four attributes — `review.verdict` (last visit's `preferred_label`),
  `review.fix_rounds` (review_fix `StageCompleted` count, = review visits − 1),
  `review.hit_cap` (review reached its 3rd visit with a non-approve final verdict),
  `pr.shipped_on_cap` (hit_cap AND a `pr` node ran). Thread them onto a new
  per-dispatch `livespec-dispatcher` span.
- Parse on **every** terminal path (green, blocked, failed) — not green-only — so
  `hit_cap` is not undercounted when the `pr` node fails after the cap
  (`pr -> escalate [outcome=failed]`, workflow.fabro:290).
- Handle the **malformed/absent-verdict** class explicitly: a succeeded review
  with no/garbled `preferred_next_label` falls through `review -> pr` at ANY visit
  count (`graph/routing.rs:50-64→81-91`) and ships without an approve — record it as
  `verdict=unknown` / `shipped_without_approve`, NOT as `approve`. (The review node
  runs on the Claude `review_adapter`, not the Codex adapter — workflow.fabro:137 —
  so a well-formed verdict is the norm, but the class must not be mislabeled.)
- `_otel_scrub.py`: widen `ATTRIBUTE_ALLOWLIST` by exactly the emitted keys, with a
  unit test asserting they survive enrich AND a content-shaped key still drops.
- Product `.py` → Red-Green-Replay; plugin-observable (new dispatcher span) ⇒
  needs a Gherkin scenario.
- **Build-time verify FIRST:** capture a real `fabro events --json` from a dispatch
  that actually took a review round, and confirm `StageCompleted` carries
  `preferred_label` + `node_visits` for the review node. This is the one
  source-level claim F1 rests on (Fable verified it against the Rust types; confirm
  it empirically before writing the parser). Fallback if the field is absent
  post-run: `fabro inspect --json` `checkpoint.node_visits`
  (`fabro-types/src/checkpoint.rs:29`) — weaker (final-checkpoint coverage of the
  last nodes unverified).

### Tier O — outward-facing fabro (rides `bd-ib-i4r`; carried on `factory-integration`, surfaced before any upstream PR)

Strict dependency order; each is independently valuable and verifiable.

- **O1 — Activate the exporter in the worker.** Re-inject the 5 `OTEL_*` consts
  (incl. `PROTOCOL=http/json`, `SERVICE_NAME`) at `worker_runtime.rs:89-99`,
  excluding `OTEL_EXPORTER_OTLP_HEADERS`. **`apply_worker_env` copies from the
  server's OWN process env (`spawn_env.rs:41-43`), so the re-injection can only
  forward what `fabro server start` was launched with — carrying the OTEL overlay
  on the host server (and the server restart that implies) is CONSTITUTIVE of O1's
  milestone and belongs in its acceptance criteria, NOT as a separate ops
  footnote.** (Alternative: carry the values through `WorkerLaunchSpec` from server
  settings — more fabro code, but decouples from server-launch env.)
  **Milestone/acceptance: with the host server started under the OTEL overlay, one
  dispatch takes fabro-sandbox dark → ≥1 span** (the existing flat `run` span).
  Smallest true end-to-end proof.
- **O2 — Cross-process traceparent.** Add `traceparent` to `WorkerLaunchSpec`;
  capture in `execute_run` pre-`spawn_blocking`; inject at `worker_runtime.rs`;
  extract at `commands/run/mod.rs:96`. Joins server+worker into one trace. Rides O1.
- **O3 — Node-lifecycle spans.** Instrument `EventLifecycle`
  (`before_attempt`/`after_node`) to open/close a span per node with
  `node_id/name/index/handler_type/attempt/max_attempts/status` (and, cheaply, the
  routing `preferred_label`/`node_visits` already in the payload). This is the
  "which node ran" *trace-level* layer. Note: F1 already answers the review-gate
  question from the same underlying fields via the event stream, so O3 is **not** on
  the review-gate critical path — it adds in-trace per-node visibility, not the
  review-gate source. Rides O2.
- **O4 — ACP turn spans.** Span at `acp.rs:196` `run_turn`
  (command/config_name/stop_reason/visit/session_id/files_touched). Rides O3.
- **O5 (deferred/optional) — ACP token/cost plumbing.** Plumb the already-enabled
  `unstable_session_usage` `PromptResponse.usage` → `AcpRunResult` →
  `CodergenResult.usage` → `StageCompleted.billing` onto turn spans. Closes the
  `total_usd_micros` gap (`livespec-impl-beads-zbl`). **First verify the data
  dependency:** confirm the `codex-acp` adapter actually POPULATES session usage
  over ACP — the feature only exposes an `Option<Usage>` field, so if the adapter
  never sends it, O5 plumbs an always-`None` value. Larger upstream change; own
  follow-on.

### Re-scoped existing child

- **`bd-ib-98c.2` (receiver)** → the allowlist widening that rides BOTH F1
  (dispatcher review-gate keys) and O3/O4 (fabro node/turn keys), plus the
  `http/json` overlay for the fabro path (constraint 8). Its exact key set is
  pinned when the emitters land. Sequencing unchanged: **must land before or with
  the emitter it serves**, or the first dispatch is a false success.

## Proposed ledger re-slice (for approval — not yet filed)

Under epic `bd-ib-98c`, supersede the monolithic `bd-ib-98c.1` with:

| id | slice | tier | depends on |
| --- | --- | --- | --- |
| `bd-ib-i4r` | OTLP transport | outward | — (**DONE**) |
| **NEW** | F1 review-gate attrs from `fabro events --json` (dispatcher-only) | factory-safe | — (now) |
| **NEW** | O1 activate exporter in worker | outward | `bd-ib-i4r` |
| **NEW** | O2 cross-process traceparent | outward | O1 |
| **NEW** | O3 node-lifecycle spans + routing attrs | outward | O2 |
| **NEW** | O4 ACP turn spans | outward | O3 |
| **NEW** | O5 ACP token/cost plumbing (deferred) | outward | O4 |
| `bd-ib-98c.2` | receiver allowlist + http/json overlay (re-scoped) | factory-safe | F1, O1, O3 |

`bd-ib-98c.1` is closed as `superseded` (or regroomed) into the above.

## The decision the maintainer owns

**Do we ship F1 (factory-safe ship-on-cap) NOW, decoupled from the outward-facing
O-track?**

- **Recommended — yes (F1 now + O-track as the richer follow-on).** F1 answers the
  standing ship-on-cap question in Honeycomb within days: a **dispatcher-only**
  change parsing the existing `fabro events --json` stream — no `workflow.fabro`
  edit, no upstream fabro PR — and it lands **all four** review-gate attributes
  (not the three-of-four the earlier sentinel draft managed). The O-track then has a
  clean single purpose — orchestration/node/turn *trace* observability — entirely
  off the review-gate critical path.
- **Alternative — everything on the O-track.** One coherent in-trace telemetry
  model, but all-or-nothing: the business question stays unanswerable until the full
  outward-facing spine (O1→O3 minimum, including O1's host-server OTEL overlay +
  restart) lands. Strictly slower, for no added coverage of the review-gate question
  F1 already covers.

Secondary decisions, none blocking F1:
- **Auth-header handling (O1):** confirm the no-auth-header receiver endpoint vs.
  server-side header injection choice for `OTEL_EXPORTER_OTLP_HEADERS`
  (constraint 3). (The host-server OTEL overlay itself is now folded into O1's
  acceptance criteria above, not a loose footnote.)
- **Dataset naming:** fabro spans (`service.name=fabro`) auto-route to a `fabro`
  dataset (`_otel_enrich_export.py` is already generic). Co-locate in
  `fabro-sandbox` instead? (emitter sets `service.name=fabro-sandbox`).
- **O5 token/cost:** pursue the `unstable_session_usage` plumbing, or leave
  ACP-path token/cost out of scope for now.
