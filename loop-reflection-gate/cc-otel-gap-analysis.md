# Claude Code OTel gap analysis + augmentation plan

**Status: DRAFT — pending user review** (this item is a USER RIDER).

Work-item: **livespec-impl-beads-29f.1** (research-only; child of epic
29f, the loop-reflection-gate effort). Researched 2026-06-13. Prereq
for **29f.3** (in-sandbox enablement, user-blocked on Honeycomb keys).

This report serves the reflector design pinned in
[`best-practices-and-design.md`](./best-practices-and-design.md)
(work-item 895): hybrid placement (mechanical fail-open ≤60s stage at
Dispatcher loop exit + fully out-of-band LLM reflector), direct OTel
SDK emit from the dispatcher + one-shot replay of the interim capture,
no collector daemon. The question here: **what does Claude Code (CC)
export natively, what does the reflector need that native export does
not carry, and exactly how do we augment until Honeycomb carries ALL
activity / turns / tool calls / failures.**

Claude Code facts below were gathered 2026-06-13 against the official
docs (`code.claude.com/docs/en/monitoring-usage.md`, doc revision
2026-06-12, and `code.claude.com/docs/en/hooks.md`) via the
claude-code-guide research agent; facts that must be re-verified
empirically at enablement time are collected in §6.

## Bottom line

- **The headline gap from the 895 survey is smaller than assumed**:
  CC native telemetry is NOT just metrics + events. A **beta trace
  exporter exists** (`OTEL_TRACES_EXPORTER` +
  `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`) producing genuine spans
  with parent/child structure (`claude_code.interaction` →
  `llm_request` / `hook` / `tool` → `tool.execution`), W3C
  `TRACEPARENT` propagation into subprocesses, and **inbound
  `TRACEPARENT` honored in `-p`/SDK sessions** — which is exactly how
  fabro's ACP nodes run CC. True host↔sandbox trace unification is
  therefore plausibly available, contradicting the 895 doc's "no
  propagation hook" assumption (verification item V3).
- **Per-turn and per-tool-call data exists natively even without the
  beta**: `claude_code.api_request` events carry per-API-call model,
  duration, input/output/cache tokens, and `cost_usd`;
  `claude_code.tool_result` events carry per-tool-call name, success,
  `duration_ms`, and error type; `prompt.id` chains every event to its
  triggering turn. The events/logs signal alone covers the directive's
  "all activity, turns, tool calls, failures" at the data level — the
  beta spans add the waterfall, not the facts.
- **The augmentation burden therefore concentrates on three things
  CC cannot do**: (1) host-side dispatch/loop/merge/janitor telemetry
  (dispatcher direct-emit, already designed in 895 §4.1 option 3);
  (2) correlation keys (CC knows nothing about `work_item_id` or
  `fabro.run_id` — injected via `OTEL_RESOURCE_ATTRIBUTES` in the
  sandbox env overlay); (3) sandbox-host gate visibility (RGR hook,
  `just check`, git push appear only as opaque Bash `tool_result`
  aggregates — family hooks close this if wanted).
- **Credential hygiene is satisfiable by defaults**: every
  content-bearing export (`OTEL_LOG_USER_PROMPTS`,
  `OTEL_LOG_TOOL_DETAILS`, `OTEL_LOG_TOOL_CONTENT`,
  `OTEL_LOG_RAW_API_BODIES`) is **off by default** and stays off; what
  remains (names, ids, durations, token counts, cost) is exactly the
  scrub-safe attribute set. The risky payload path is fabro's
  `agent.acp.*` stdout (PROVEN credential-adjacent, 895 §2.3), which
  the fabro harvester must never ship.

## 1. Native-export inventory

### 1.1 Enablement + transport config

All facts: https://code.claude.com/docs/en/monitoring-usage.md
(sections `#quick-start`, `#common-configuration-variables`,
`#administrator-configuration`, `#dynamic-headers`,
`#metrics-cardinality-control`).

| Env var | Purpose | Notes |
|---|---|---|
| `CLAUDE_CODE_ENABLE_TELEMETRY=1` | master switch | required for everything |
| `OTEL_METRICS_EXPORTER` | `otlp` / `prometheus` / `console` / `none` | |
| `OTEL_LOGS_EXPORTER` | `otlp` / `console` / `none` | events ride the logs signal |
| `OTEL_TRACES_EXPORTER` | `otlp` / `console` / `none` | **beta**; also needs `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` / `http/json` / `http/protobuf` | Honeycomb accepts all three (`docs.honeycomb.io/send-data/opentelemetry/`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | global endpoint | `https://api.honeycomb.io` |
| `OTEL_EXPORTER_OTLP_HEADERS` | auth | `x-honeycomb-team=<key>` |
| `OTEL_EXPORTER_OTLP_{METRICS,LOGS}_{PROTOCOL,ENDPOINT}` | per-signal overrides | |
| `OTEL_METRIC_EXPORT_INTERVAL` | default 60000 ms | shorten for short-lived sandboxes (V4) |
| `OTEL_LOGS_EXPORT_INTERVAL` | default 5000 ms | |
| `OTEL_RESOURCE_ATTRIBUTES` | custom resource attrs on ALL signals | **the correlation-key injection point** (§3.1) |
| `OTEL_METRICS_INCLUDE_SESSION_ID` (default true), `..._INCLUDE_VERSION` (false), `..._INCLUDE_ACCOUNT_UUID` (true), `..._INCLUDE_ENTRYPOINT` (false), `..._INCLUDE_RESOURCE_ATTRIBUTES` (true) | cardinality knobs | |
| `otelHeadersHelper` (settings.json) | dynamic auth-header script | http protocols only; refresh ~29 min |

Config can be centrally forced via the `env` block in
`.claude/settings.json` / managed settings — relevant because the
fabro **run-config overlay is the established channel** for projecting
env into the sandbox (it already projects `CLAUDE_CODE_OAUTH_TOKEN`;
895 §4.3).

### 1.2 Signals — what kinds of telemetry exist

| Signal | Exists natively? | Granularity floor | Citation |
|---|---|---|---|
| Metrics | yes (8 instruments, `claude_code.*`) | per session/model/type counters | monitoring-usage.md `#metrics` |
| Log records / events | yes (~23 event types) | **per tool call, per API call, per prompt** | monitoring-usage.md `#events` |
| Trace spans | **yes, BETA** — genuine traceId/spanId/parent | per interaction → per LLM request / tool execution / hook | monitoring-usage.md `#traces-beta` |

Trace beta specifics: root `claude_code.interaction` span per turn
with children `claude_code.llm_request`, `claude_code.hook`,
`claude_code.tool` (sub-spans `tool.blocked_on_user`,
`tool.execution`, and subagent spans under the Agent tool); spans
carry W3C context; Bash/PowerShell subprocesses inherit a
`TRACEPARENT` env var while tracing is active; **Agent SDK and
non-interactive `-p` sessions read inbound `TRACEPARENT`/`TRACESTATE`**
(interactive CLI deliberately ignores them); span content (prompts,
tool inputs/outputs) is redacted by default even with tracing on.
(monitoring-usage.md `#traces-beta`, `#span-hierarchy`.)

### 1.3 Metrics (complete list)

Citation: monitoring-usage.md `#metrics`, `#metric-details`.

| Metric | Unit | Key attributes |
|---|---|---|
| `claude_code.session.count` | count | `start_type` |
| `claude_code.lines_of_code.count` | count | `type` (added/removed), `model` |
| `claude_code.pull_request.count` | count | |
| `claude_code.commit.count` | count | |
| `claude_code.cost.usage` | USD | `model`, `query_source` (main/subagent/auxiliary), `effort`, `agent.name`, `skill.name`, `plugin.name`, `mcp_server.name`, `mcp_tool.name` |
| `claude_code.token.usage` | tokens | `type` (input/output/cacheRead/cacheCreation) + same attribution set as cost |
| `claude_code.code_edit_tool.decision` | count | `tool_name`, `decision`, `source`, `language` |
| `claude_code.active_time.total` | s | `type` (user/cli) |

### 1.4 Events (the reflector-relevant subset, complete attribute lists)

Citation: monitoring-usage.md `#events`. Every event carries
`event.name`, `event.timestamp`, `event.sequence` (in-session
ordering), the standard dimensions (§1.5), and **`prompt.id`** — a
UUID correlating a user prompt with all subsequent events, i.e. the
native per-turn chain key.

| Event | Fires | Reflector-relevant attributes |
|---|---|---|
| `claude_code.user_prompt` | each prompt | `prompt_length`; `prompt` text REDACTED by default; `command_name`, `command_source` |
| `claude_code.tool_result` | **each tool call completion** | `tool_name`, `tool_use_id`, `success`, `duration_ms`, `error_type`, `error`, `decision_type`, `decision_source`, `tool_input_size_bytes`, `tool_result_size_bytes`; `tool_parameters`/`tool_input` only if `OTEL_LOG_TOOL_DETAILS=1` |
| `claude_code.api_request` | **each API call** | `model`, `cost_usd`, `duration_ms`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `request_id`, `query_source`, `effort`, `agent.name`, `skill.name`, `plugin.name`, `mcp_server.name`, `mcp_tool.name` |
| `claude_code.api_error` | API failure | `model`, `error`, `status_code`, `duration_ms`, `attempt`, `request_id` + attribution set |
| `claude_code.api_retries_exhausted` | retries exhausted | `model`, `error`, `status_code`, `total_attempts`, `total_retry_duration_ms` |
| `claude_code.tool_decision` | permission decision | `tool_name`, `tool_use_id`, `decision`, `source` |
| `claude_code.hook_execution_start` / `_complete` | hook batches (lefthook shims, RGR guards, settings hooks) | `hook_event`, `hook_name`, `num_hooks`, `num_success`, `num_blocking`, `num_non_blocking_error`, `total_duration_ms`, `hook_source` |
| `claude_code.compaction` | context compaction | `trigger`, `success`, `duration_ms`, `pre_tokens`, `post_tokens` |
| `claude_code.internal_error` | unexpected CC error | `error_name`, `error_code` |
| `claude_code.mcp_server_connection` | MCP connect/fail | `status`, `transport_type`, `duration_ms`, `error_code`, `server_name` |
| `claude_code.api_refusal` | refusal stop_reason | `model`, `request_id` |

Other documented events (not load-bearing for the reflector):
`permission_mode_changed`, `auth`, `plugin_installed`,
`plugin_loaded`, `skill_activated`, `at_mention`, `hook_registered`,
`hook_plugin_metrics`, `feedback_survey`,
`api_request_body`/`api_response_body` (gated by
`OTEL_LOG_RAW_API_BODIES`, stays off).

### 1.5 Dimensions and privacy defaults

Standard attributes on all signals: `session.id` (default on),
`user.account_uuid` / `user.account_id` (default on), `user.id`,
`user.email` (OAuth), `organization.id`, `terminal.type`,
`app.version` (default off), `app.entrypoint` (default off; values
incl. `sdk-cli`, `sdk-py` — distinguishes sandbox ACP sessions from
interactive ones), plus custom `OTEL_RESOURCE_ATTRIBUTES`. Resource
metadata: `service.name=claude-code`, `service.version`, os/arch.
(monitoring-usage.md `#standard-attributes`,
`#service-information`.)

Privacy defaults (all OFF): `OTEL_LOG_USER_PROMPTS` (prompt text),
`OTEL_LOG_TOOL_DETAILS` (tool params/inputs, ~4 KB truncated),
`OTEL_LOG_TOOL_CONTENT` (full tool I/O on spans, 60 KB cap),
`OTEL_LOG_RAW_API_BODIES` (full Messages API bodies). Subprocesses
(Bash, hooks, MCP servers) do NOT get `OTEL_*` injected by CC itself
— but they inherit whatever the parent environment carries, which is
how the sandbox overlay config reaches family hooks (§3.2).

### 1.6 GenAI semconv cross-check

The OTel GenAI conventions (all Development status; relocated to
`github.com/open-telemetry/semantic-conventions-genai`; see 895 §1.2
for the full review) define `invoke_agent`/`execute_tool`/inference
span names, `gen_ai.provider.name`, `gen_ai.conversation.id`,
`gen_ai.usage.input_tokens`/`output_tokens` (+cache splits), opt-in
content capture, and the `gen_ai.evaluation.result` event
(https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/gen-ai-spans.md,
.../gen-ai-events.md, accessed 2026-06-13).

What CC actually emits: **primary namespace is `claude_code.*`, with
supplementary `gen_ai.*` attributes on the beta spans** —
`gen_ai.system="anthropic"`, `gen_ai.request.model`,
`gen_ai.response.id`, `gen_ai.response.finish_reasons` on
`llm_request` spans; `gen_ai.tool.call.id` on tool spans
(monitoring-usage.md `#span-attributes`). This reconciles the OTel
blog's naming of Claude Code as a GenAI-semconv emitter
(https://opentelemetry.io/blog/2026/genai-observability/): it emits
*some* semconv attributes, not the full `invoke_agent`/`execute_tool`
span vocabulary. Consequences:

- Honeycomb's Agent Observability surface (consumes GenAI semconv
  v1.40.0) may only partially light up on CC's `claude_code.*` names
  (V5). Plain Honeycomb queries/BubbleUp on `claude_code.*` fields
  are unaffected.
- Token usage on CC events is `input_tokens`/`output_tokens`
  (claude_code namespace), not `gen_ai.usage.*` — reflector queries
  must use CC's names for sandbox data and `gen_ai.*`/`livespec.*`
  for anything we emit ourselves.
- Our own emitted spans (dispatcher, hooks, fabro harvester) follow
  895 §4.2: `livespec.*` for non-GenAI operations, `gen_ai.*`-mapped
  attributes for agent/inference facts, and
  `gen_ai.evaluation.result` reserved for reflector verdicts.

## 2. Reflector needs vs native coverage

Needs are the 29f epic decisions (895 §3 hybrid placement, §4.3
instrumentation list, §5 evidence links) plus the user directive's
"all activity, turns, tool calls, failures". Verdict column:
**native** = covered by CC export once enabled in-sandbox; **augment**
= coverable by dispatcher/harvester/overlay work, no CC hooks needed;
**hooks** = impossible without hook-emitted telemetry.

| # | Reflector need | Native CC coverage | Verdict |
|---|---|---|---|
| R1 | Per-run (dispatch) outcome: green/failed/blocked + failing stage | none — CC has no dispatch concept | **augment** (dispatcher direct-emit; journal already authoritative) |
| R2 | Per-turn activity inside the sandbox agent | `prompt.id`-chained events per turn; `claude_code.interaction` span per turn (beta) | **native** |
| R3 | Tool-call-level visibility incl. failures | `tool_result` (`tool_name`, `success`, `duration_ms`, `error_type`) per call; `claude_code.tool`/`tool.execution` spans (beta) | **native** |
| R4 | Token/cost per model/agent/item | `api_request` events (`cost_usd`, 4 token counts) + `token.usage`/`cost.usage` metrics with attribution attrs | **native** (join to item via R5 keys) |
| R5 | Correlation ids: CC session ↔ dispatcher journal ↔ fabro run | `session.id` native; `work_item_id`/`fabro.run_id` unknown to CC | **augment** (`OTEL_RESOURCE_ATTRIBUTES` injection via overlay; §3.5) |
| R6 | API/runtime failure clustering | `api_error`, `api_retries_exhausted`, `internal_error`, `mcp_server_connection` events | **native** |
| R7 | Gate visibility: RGR commit hook, `just check`, push gates inside sandbox | only as opaque Bash `tool_result` (name + duration + exit success); `hook_execution_*` covers CC-level hooks only | partially native; per-gate semantics need **hooks** (§3.2) — optional tier |
| R8 | Wave/loop rollup (budget, picks, outcome mix) | none | **augment** (dispatcher loop span) |
| R9 | Merge / CI / post-merge janitor outcomes | none — happens host-side after the fabro run returns | **augment** (dispatcher stages + existing `github-ci` harvester) |
| R10 | Sandbox node timings (inference vs tool time per phase node) | not from CC (CC doesn't know fabro nodes) | **augment** (fabro `events --json` harvester; timing block measured in 895 §2.3) |
| R11 | Evidence deep-links for findings (trace links per 895 §5.1) | trace ids exist once beta spans flow | **native+augment** (link format per docs.honeycomb.io/investigate/collaborate/share-trace) |
| R12 | Reflector verdict storage | n/a | **augment** (reflector emits `gen_ai.evaluation.result` parented to the dispatch span) |
| R13 | Cross-session subagent activity (harness subagents on the host) | host sessions could enable CC telemetry too | **augment** (enable on host sessions later; interim `claude-subagents` harvester already covers historically) |

Nothing in the needs matrix is *impossible*: R7's per-gate semantics
is the only row where hook-emitted telemetry is the sole path to full
fidelity, and it is an optional-fidelity tier, not a blocker —
gate failures already surface as `tool_result.success=false` plus the
dispatcher's stage outcome.

## 3. Augmentation plan

Build order matches the 895 decisions: one-shot replay first (already
designed), dispatcher direct-emit second, in-sandbox CC enablement
(29f.3) third, optional hook tier last.

### 3.1 In-sandbox CC native enablement (the backbone; executed as 29f.3)

Project the telemetry env into the sandbox via the **run-config
overlay** (the proven secret channel; `{{ env }}` interpolation is
proven non-viable, 895 §4.3). Full env set in §4. Key points:

- **Correlation injection**: `OTEL_RESOURCE_ATTRIBUTES` carries
  `work.item.id=<id>` and `livespec.dispatch.id=<journal-derived id>`
  so every CC metric, event, and span lands in Honeycomb pre-joined
  to the dispatcher trace. `fabro.run_id` is NOT knowable at overlay
  time (fabro assigns it at run creation) — it joins via `fabro ps`
  attributes on the harvester side instead.
- **Separate ingest-only Honeycomb key**, never the management key,
  same 1Password environment as the OAuth token (epic decision; new
  entry pending user key provisioning).
- **All content flags stay unset** (§1.5) — names/ids/durations/
  tokens/cost only. This satisfies credential hygiene at the source.
- **Trace beta**: set `OTEL_TRACES_EXPORTER=otlp` +
  `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`; if the beta is
  org-allowlisted and unavailable (V2), metrics+events still deliver
  R2/R3/R4/R6 — only the waterfall view degrades.

### 3.2 Hook-emitted spans (optional fidelity tier for R7)

CC hooks (full event list: https://code.claude.com/docs/en/hooks.md —
`SessionStart/End`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
`PermissionRequest`, `Stop`, `SubagentStop`, plus newer
`FileChanged`/`CwdChanged`/`WorktreeCreate`) receive on stdin:
`session_id`, `transcript_path`, `cwd`, and per-tool `tool_name`,
`tool_use_id`, `tool_input`, `tool_output` (PostToolUse). They do
NOT receive token/cost data (docs silent; assume no).

Design (only if/when R7 fidelity is wanted — native `tool_result`
events may prove sufficient):

- A single tiny emitter script (stdlib-only, OTLP/HTTP JSON one-span
  `ExportTraceServiceRequest` per invocation — the exact format
  `capture_runtime_telemetry.py` already writes) reading endpoint +
  key from the inherited env (the overlay sets them process-wide, so
  hooks DO see them even though CC itself doesn't inject `OTEL_*`
  into subprocesses).
- `PostToolUse` matcher on `Bash` for the family gate commands only
  (`just check*`, `mise exec -- git commit/push`, `gh pr ...`): emit a
  `livespec.gate.<gate>` span with `tool_use_id` (joins to CC's own
  `tool_result` event and beta tool span), exit status, duration.
  The RGR hook itself could alternatively emit from inside the
  `red_green_replay` wrapper — same emitter, richer attrs
  (`rgr.phase=red|green`, test path) — replacing the post-hoc
  `livespec-rgr` trailer harvester with live spans.
- Span parent: the `TRACEPARENT` env CC exports to subprocesses while
  beta tracing is active (§1.2) — hook spans then nest under the real
  tool span. Without the beta, fall back to deterministic
  sha256-derived ids keyed on `session_id`+`tool_use_id` (capture
  script's technique) and attribute-joins.
- Fail-open: emitter is fire-and-forget with a ≤2s socket timeout,
  exit 0 unconditionally; a hook that cannot emit must never block a
  tool call (same invariant as 895 §6).

### 3.3 Dispatcher-side enrichment (host truth: R1, R8, R9)

Per 895 §4.1 option 3 (the accepted steady-state): `JournalFile`
dual-writes journal line first (authoritative), then enqueues a span
via the OTel Python SDK `BatchSpanProcessor` (bounded queue,
drop-on-overflow, never blocks). Trace shape per 895 §4.2:
`livespec.loop` root → `livespec.dispatch` per item →
`livespec.stage.<stage>` children. Enrichment attributes the journal
side adds (the reflector's join + verdict surface):

- `work.item.id`, `livespec.dispatch.id` (same values injected into
  the sandbox env — the R5 join), journal path, `mode`, `budget`,
  `parallel`, `picked_count` (loop span).
- `fabro.run_id` parsed from the `fabro-run` stage detail once known;
  PR number from `pr-view`/`pr-arm-fallback`; merge result; janitor
  stage exit codes; final `outcome` (green/failed/blocked) as span
  status + attribute.
- Optionally generate the dispatch span's W3C context BEFORE the
  `fabro-run` stage and project it as `TRACEPARENT` in the overlay —
  if V3 verifies that the ACP adapter's CC invocation is an SDK/`-p`
  session that honors inbound `TRACEPARENT`, the sandbox's entire CC
  trace nests under the dispatch span and host↔sandbox correlation
  becomes structural rather than attribute-joined.

### 3.4 fabro `events --json` correlation (R10)

Extend the existing harvester from run-level spans to per-node spans
(read-side only, no fabro changes):

- Source: `fabro events <run> --json` per terminal run from
  `fabro ps -a --json`.
- Spans: `fabro.node.<node_id>` from `stage.started/completed` pairs,
  attributes from the measured timing block
  (`active_time_ms`, `inference_time_ms`, `tool_time_ms`,
  `wall_time_ms`), `attempt`, `max_attempts`, `status`; run-level
  span keeps `fabro.run_id`, `work_item_id` (regex from goal),
  `total_usd_micros`/`cost.usd` when populated.
- Correlation keys shipped: `fabro.run_id` + `work_item_id` — joins
  to dispatcher spans (which carry both) and, transitively, to CC
  sandbox telemetry (which carries `work.item.id` via §3.1).
- **Scrub rule is absolute**: `setup.command.*`,
  `agent.acp.completed` stdout, `prompt.completed` response payloads
  are NEVER exported — names, ids, timings, statuses, token/cost
  numbers only (the sampled run's stdout literally narrates PAT
  extraction; 895 §2.3 — truncation is not scrubbing).

### 3.5 Correlation key scheme (the one table the reflector joins on)

| Key | Dispatcher spans | CC sandbox telemetry | fabro harvester spans | CI harvester |
|---|---|---|---|---|
| `work.item.id` | yes (journal) | yes (resource attr, injected) | yes (goal regex) | via PR/branch naming (weak; acceptable) |
| `livespec.dispatch.id` | yes (generated at dispatch) | yes (resource attr, injected) | no (joins via work item + time window) | no |
| `fabro.run_id` | yes (parsed post-start) | no (unknowable at overlay time) | yes | no |
| `session.id` (CC) | no | yes (native) | no | no |
| `trace_id` (W3C) | root | nested IFF V3 verifies TRACEPARENT honor | no (deterministic ids) | no |

Reflector queries group on `work.item.id` first (present on all three
primary sources), fall back to `fabro.run_id` and time-window joins.

### 3.6 Scrubbed payload export rules (credential hygiene, family-wide)

Per the sandbox-probe credential-hygiene discipline:

1. **No env values, ever** — no attribute may carry the value of any
   environment variable; allowlisted attribute NAMES only. The
   emitters use allowlists (named numeric/id/status fields), never
   "everything minus a denylist".
2. **No remote URLs** — git remote URLs embed PATs in this fleet
   (`https://x-access-token:<PAT>@github.com/...`). Any attribute
   that could contain a URL (command lines, tool inputs, narration)
   is excluded by the allowlist; defense-in-depth regex
   (`[a-zA-Z0-9_-]+:[^@\s]+@`) rejects the span rather than
   redacting, on the principle that a scrub miss must fail closed.
3. **CC content flags stay off** (`OTEL_LOG_USER_PROMPTS`,
   `OTEL_LOG_TOOL_DETAILS`, `OTEL_LOG_TOOL_CONTENT`,
   `OTEL_LOG_RAW_API_BODIES` all unset) — CC then redacts at source.
4. **fabro stdout/response payloads never leave the host** (§3.4).
5. **Ingest-only key** in the sandbox; the Honeycomb management key
   exists only in the Dispatcher/reflector env (1Password channel);
   keys never in committed files; `user.email`/account dims are fine
   (single-operator fleet) but revisit if that changes.

## 4. What 29f.3 must set in the sandbox env (ready-to-execute)

Via the run-config overlay (values resolved at dispatch time; key
from 1Password once the user provisions it):

```
CLAUDE_CODE_ENABLE_TELEMETRY=1
OTEL_METRICS_EXPORTER=otlp
OTEL_LOGS_EXPORTER=otlp
OTEL_TRACES_EXPORTER=otlp                  # beta waterfall; harmless if gated
CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1      # verify availability (V2)
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf  # http/json equally verified at Honeycomb
OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io
OTEL_EXPORTER_OTLP_HEADERS=x-honeycomb-team=<INGEST_ONLY_KEY>   # from 1Password; never committed
OTEL_RESOURCE_ATTRIBUTES=service.namespace=livespec-family,work.item.id=<id>,livespec.dispatch.id=<id>
OTEL_METRIC_EXPORT_INTERVAL=10000          # short-lived sandbox: don't lose the tail (V4)
OTEL_LOGS_EXPORT_INTERVAL=5000
# TRACEPARENT=<dispatch span W3C context>  # enable after V3 verifies -p/SDK honor
# All OTEL_LOG_* content flags deliberately UNSET (§3.6).
```

Leave `service.name` at CC's own `claude-code` (Honeycomb dataset
derives from it; one dataset for all sandbox agent telemetry is the
desired shape — slice by `work.item.id`). Acceptance check for
29f.3: a dispatched item yields, in Honeycomb, ≥1
`claude_code.api_request` event and ≥1 `tool_result` event carrying
the injected `work.item.id`, plus (if beta active) an
`claude_code.interaction` trace; and zero attributes matching the
URL-credential regex.

## 5. Gaps that remain even after augmentation

1. **Beta availability risk**: enhanced-telemetry tracing is beta and
   possibly org-gated; without it there are no native sandbox spans —
   facts survive in events, the waterfall does not (mitigation: §3.2
   deterministic-id hook spans can fake the structure if it matters).
2. **Final-flush loss at sandbox teardown**: exporters flush on
   intervals; `sandbox.stop` may kill CC before the last batch ships.
   Shorter intervals reduce but do not eliminate tail loss (V4).
3. **Semconv mismatch at the analysis layer**: CC's `claude_code.*`
   naming means Honeycomb's GenAI/Agent-Timeline surfaces may not
   fully recognize sandbox traces (V5); raw queries are unaffected.
   The conventions themselves are Development-status and churning —
   pin what we emit, expect renames.
4. **Prompt/content opacity is permanent by design**: the reflector
   cannot read prompts, diffs, or tool payloads from Honeycomb (off
   by default, and §3.6 keeps it that way). Deep content review reads
   local transcripts / `fabro events` on the host, out-of-band.
5. **Non-CC subprocess interiors**: `just check`, pytest, git inside
   the sandbox appear as single Bash `tool_result` durations; per-gate
   breakdown requires the optional §3.2 hook tier (and per-check
   timing inside `just check` is a separate effort — 7us.3).
6. **`fabro.run_id` absent from CC telemetry**: structural (run id
   does not exist when the overlay is written); joins go through
   `work.item.id`/dispatch id.
7. **CI correlation is name-based**: `github-ci` spans join via
   branch/PR naming conventions, not propagated context — adequate,
   not airtight.
8. **Honeycomb ingest is append-only**: replay/backfill must stay
   once-only (sent-marker discipline in the replay loop); re-sent
   spans duplicate.
9. **Cost ground truth is split**: `fabro ps` `total_usd_micros` has
   been null in sampled runs; CC `cost_usd` covers in-sandbox API
   spend only (not any other model surfaces fabro itself uses). Treat
   CC token/cost as the primary signal, fabro's as corroboration when
   populated.

## 6. Verification items (re-verify empirically at enablement)

- **V1**: exact event/metric names against the live export (docs
  revision 2026-06-12; CC moves fast — console-exporter smoke test
  first).
- **V2**: whether `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA` works for
  this org/account (docs note allowlist gating for detailed hook
  tracing).
- **V3**: whether fabro's ACP adapter invokes CC in a mode that
  honors inbound `TRACEPARENT` (SDK/`-p` yes, interactive no, per
  docs) — gates §3.3's structural correlation.
- **V4**: flush-on-exit behavior at sandbox teardown (emit a sentinel
  event at session end; check it arrives).
- **V5**: how Honeycomb's Agent Observability surface renders
  `claude_code.*` traces vs full GenAI-semconv emitters.
- **V6**: that `OTEL_RESOURCE_ATTRIBUTES` values survive onto log
  events as well as metrics/spans in CC's implementation (docs state
  resource attrs apply across signals; confirm on logs).

## Sources

- https://code.claude.com/docs/en/monitoring-usage.md (doc revision
  2026-06-12; sections cited inline) — CC telemetry reference.
- https://code.claude.com/docs/en/hooks.md — hook events + payloads.
- https://opentelemetry.io/blog/2026/genai-observability/ — names CC
  as a GenAI-semconv emitter (reconciled in §1.6).
- https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/gen-ai-spans.md,
  .../gen-ai-events.md, .../gen-ai-metrics.md (accessed 2026-06-13,
  via 895 §1.2) — GenAI semconv vocabulary.
- https://docs.honeycomb.io/send-data/opentelemetry/ — OTLP ingest
  (gRPC, http/protobuf, http/json at `/v1/traces`).
- https://docs.honeycomb.io/investigate/collaborate/share-trace —
  trace deep-link format for finding evidence links.
- [`best-practices-and-design.md`](./best-practices-and-design.md) —
  epic 895 survey + pinned 29f decisions this report serves.
- `livespec/tmp/capture_runtime_telemetry.py` +
  `livespec/tmp/otel-runtime-spans.jsonl` (1,764 span lines across 5
  services as of 2026-06-13) — the interim capture whose families
  (rgr/dispatcher/fabro/subagents/ci) §3 either supersedes with live
  emit or keeps as harvesters.
