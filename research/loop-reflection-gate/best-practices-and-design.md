# Loop reflection gate — best practices and design

Work-item: **livespec-impl-beads-895** (research-only; Phase 1 of the
reflection-gate effort). Researched 2026-06-13. No implementation in
this item — the deliverable is this survey + design-options report,
feeding a user brainstorm.

The user directive this serves (verbatim):

> This should also eventually be baked into the fabro factory loop, as
> an eval/audit/reflection gate before the loop exits (or at other
> appropriate points for multi-task loops). Not just for performance,
> but as a node which does holistic reviews of everything that happened
> in the loop, so it can improve. All activity, turns, tool calls,
> failures, etc. Leverage honeycomb heavily for all captured telemetry.
> It should open issues for anything it finds, and notify the human as
> part of the summary. We should brainstorm this for best practices,
> both across all agentic automation June 2026 best practices, and for
> fabro itself. Will need research and brainstorming - and also not
> impact performance or stability itself.

## Bottom line

- **The load-bearing invariant is fail-open**: a reflection gate must
  NEVER change a dispatch verdict, fail a green dispatch, or block loop
  exit. Every serious source surveyed (OTel error-handling principles,
  online-eval vendor architectures, SRE alerting doctrine) converges on
  the same shape: observe in-band cheaply, evaluate out-of-band, and
  let the evaluator's own failure be a logged non-event.
- **Recommended placement is a hybrid (b)+(c)**: a time-boxed,
  mechanical, fail-open reflection stage in the Dispatcher at loop exit
  (it already holds every `DispatchOutcome`, the journal, and
  credentials), plus a fully out-of-band LLM-driven holistic reviewer
  that reads its evidence from Honeycomb after the fact. A reflect node
  inside the per-item fabro phase graph (option (a)) is the WORST fit:
  it is in-band by construction, cannot see the merge or post-merge
  janitor (they happen after the fabro run returns), and cannot see
  across items.
- **Per-tool-call visibility does not exist yet anywhere in the
  pipeline**: fabro events bottom out at per-node granularity
  (`stage.completed` carries `{active,inference,tool,wall}_time_ms`
  aggregates), and the dispatcher journal at per-stage. "All activity,
  turns, tool calls" requires enabling the agent runtime's own OTel
  telemetry inside the sandbox — Claude Code is a confirmed emitter of
  the OTel GenAI semantic conventions — and projecting an OTLP
  endpoint + ingest-only key into the sandbox env via the existing
  run-config-overlay channel.
- **Honeycomb can be both the sink and the gate's evidence store**: the
  events are tiny in volume (~83 fabro events/run, dozens of
  dispatches/day), OTLP/HTTP JSON ingest at `/v1/traces` is verified
  and matches the capture file format already on disk, Honeycomb
  shipped a dedicated Agent Observability surface (2026-05-12,
  consuming GenAI semconv v1.40.0), and the hosted Honeycomb MCP
  server (GA, free on all accounts) gives an automated reflector a
  programmatic read surface — the raw Query Data API, by contrast, is
  verified Enterprise-only.
- **Issue filing must be dedup-first**: the canonical pattern
  (Sentry fingerprinting, GitHub code-scanning alert lifecycle) is a
  stable fingerprint per finding *category+locus* (never message
  text), an open/reappeared lifecycle instead of new-issue-per-run, a
  per-pass cap, and severity thresholds — findings below the bar ride
  the summary digest, not the tracker.

## 1. Survey (June 2026 best practices, cited)

> Citations: every claim carries (URL, accessed 2026-06-13). Three
> research passes against fetched primary sources; claims sourced only
> from search-result snippets are marked *(snippet)*; synthesis and
> inference are marked as such; where the state of the art is thin,
> that is stated explicitly.

### 1.1 Reflection / self-improvement loops in agentic automation

**What frameworks actually ship.**

- Anthropic's "Building Effective Agents" defines the canonical
  **evaluator-optimizer** workflow — "one LLM call generates a
  response while another provides evaluation and feedback in a loop" —
  but scopes it to tasks with "clear evaluation criteria, and when
  iterative refinement provides measurable value"; for autonomous
  agents the guidance shifts to **environment ground truth** ("tool
  call results or code execution") at each step, with pauses "for
  human feedback at checkpoints or when encountering blockers"
  (https://www.anthropic.com/research/building-effective-agents,
  accessed 2026-06-13).
- OpenAI Agents SDK **guardrails are pure gates, not improvement
  loops**: input guardrails run for the first agent (parallel by
  default), output guardrails post-completion for the last; a tripped
  guardrail raises a tripwire exception and halts — there is no
  built-in retry/self-correction
  (https://openai.github.io/openai-agents-python/guardrails/, accessed
  2026-06-13).
- Claude Code / Claude Agent SDK ship hooks (PreToolUse can block;
  PostToolUse for audit/secret-scanning) and subagents with isolated
  contexts; the documented review pattern is a code-reviewer subagent
  reporting findings back
  (https://code.claude.com/docs/en/agent-sdk/subagents, accessed
  2026-06-13, *snippet*).
- LangGraph documents Reflection and Reflexion as explicit graph
  patterns — generator node → critique node → bounded conditional loop
  back, with Reflexion variants persisting the self-critique as memory
  for the next attempt
  (https://www.langchain.com/blog/reflection-agents, accessed
  2026-06-13, *snippet*).
- Google ADK exposes a full callback lattice
  (`before/after_agent_callback`, `before/after_model_callback`,
  `before/after_tool_callback` — observe/modify/block at every level)
  plus a separate eval module with rubric-based LLM-as-judge criteria
  producing binary verdicts per rubric
  (https://google.github.io/adk-docs/callbacks/ and
  https://google.github.io/adk-docs/evaluate/criteria/, accessed
  2026-06-13, *snippet*). AG2/CrewAI first-party reflection docs:
  not found — gap.
- **Pattern synthesis**: three shapes coexist — generate→evaluate→retry
  (when criteria are crisp), gate-without-retry (guardrails,
  callbacks), and — the verified production trend for coding agents —
  **verify against the environment instead of LLM self-critique**,
  with post-hoc audit pushed to the observability layer.

**Reflexion-style memory in production is the thinnest area
surveyed.** The original mechanism (verbal reflection persisted in an
episodic buffer to improve subsequent trials, no weight updates;
https://arxiv.org/abs/2303.11366, accessed 2026-06-13, *snippet*) has
one strong verified production descendant: Anthropic's tool-testing
agent rewrites flawed MCP tool descriptions after attempting to use
them, yielding "a 40% decrease in task completion time for future
agents using the new description"
(https://www.anthropic.com/engineering/multi-agent-research-system,
accessed 2026-06-13). No 2025–2026 production write-up was found
describing automatically-generated per-failure reflections persisted
and injected into future runs at scale — production "memory" in public
write-ups is curated knowledge bases/playbooks plus human
retrospectives (e.g. Cognition's Devin 18-month review describes
human-authored playbooks and human review for non-verifiable outcomes,
not automated post-run reflection;
https://cognition.ai/blog/devin-annual-performance-review-2025,
accessed 2026-06-13).

**Online evals converged on a shape**: asynchronous LLM-as-judge over
sampled, already-ingested production traces, observe-by-default.

- LangSmith online evaluators run async on completed traces; sampling
  rate is first-class config (docs example 0.1 = 10% of matching
  traces); triggering is filter-based; scores land as trace
  annotations (https://docs.langchain.com/langsmith/online-evaluations-llm-as-judge,
  accessed 2026-06-13). No judge-model prescription in the docs.
- Braintrust online scoring runs async as logs arrive, with sampling
  and SQL span filters; the closed loop hard-gates only at CI/deploy
  (failing scores block the next deploy), never per-trace
  (https://www.braintrust.dev/docs/evaluate, accessed 2026-06-13,
  *snippet*).
- Arize runs evaluators "on incoming traces on a rolling schedule" and
  publishes explicit sampling guidance: 10–20% for high-volume apps,
  1–5% for very-high-volume, plus span-kind/model/metadata filters
  (https://arize.com/docs/ax/evaluate/online-evals, accessed
  2026-06-13).
- Judge configuration evidence: Anthropic's research system used a
  **single LLM call with one rubric prompt (0.0–1.0 scores +
  pass/fail)** and found a single judge "the most consistent and
  aligned with human judgements" — over judge ensembles
  (https://www.anthropic.com/engineering/multi-agent-research-system,
  accessed 2026-06-13).

**LLM-as-judge reliability is worse than commonly assumed (2026).**
Frontier judges "exceeded 50% error rates on advanced bias tests"
(JudgeBiasBench 2026) and a RAND 2026 assessment found no judge
"uniformly reliable across benchmarks"; position bias is systematic
across ~150k evaluation instances, with >10% pairwise-accuracy swings
from order swaps in code judging; self-preference and same-provider
family bias are documented
(https://www.adaline.ai/blog/llm-as-a-judge-reliability-bias, accessed
2026-06-13; https://arxiv.org/pdf/2410.21819, accessed 2026-06-13,
*snippet*). Published calibration practices: spot-check against
humans and recalibrate the rubric above ~20–25% divergence;
reference-anchored grading beats prompt-only scoring; meta-judge
beats multi-agent debate (debate "amplif[ies] bias after the first
round"); cross-provider judges neutralize family bias (Adaline, same
URL). No source gives explicit gate-vs-observe thresholds; observed
practice: hard gates at I/O and CI/deploy boundaries, per-trace
judges observe-and-annotate.

**Multi-task loop checkpointing (agent factories).** Anthropic's
"Effective harnesses for long-running agents" (2025-11-26) is the most
concrete public per-item review spec: an initializer agent builds
scaffolding, then coding agents work "on only one feature at a time.
This incremental approach turned out to be critical" — review points
are per-item at session boundaries with fresh context; state lives in
a JSON feature file agents may only flip a `passes` field on; and
**LLM self-assessed completion failed** ("Claude would fail [to]
recognize that the feature didn't work end-to-end") until
environment-verification tools (browser automation) replaced it
(https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents,
accessed 2026-06-13). The multi-agent research post adds end-state
evaluation plus "discrete checkpoints where specific state changes
should have occurred" (URL above, accessed 2026-06-13). Factory.ai
post-run-audit specifics: nothing public found beyond marketing —
gap. Batch-level review in production write-ups is still human
(periodic retrospectives over defect-rate data;
https://www.sitepoint.com/devin-ai-engineers-production-realities/,
accessed 2026-06-13, *snippet*).

### 1.2 Telemetry for agent loops — OTel GenAI semantic conventions status

- **Nothing in `gen_ai.*` is Stable as of June 2026, and the
  conventions MOVED**: the pages under
  `opentelemetry.io/docs/specs/semconv/gen-ai/` are deprecation stubs
  pointing at the dedicated
  `github.com/open-telemetry/semantic-conventions-genai` repo
  (https://opentelemetry.io/docs/specs/semconv/gen-ai/, accessed
  2026-06-13), which has **no tagged release** and covers GenAI
  clients, MCP, and provider-specific conventions (Anthropic, Bedrock,
  Azure, OpenAI)
  (https://github.com/open-telemetry/semantic-conventions-genai,
  accessed 2026-06-13). The main registry's "Deprecated" badges on
  most `gen_ai.*` attributes mean *relocated*, not abandoned
  (https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/,
  accessed 2026-06-13).
- **Span vocabulary (all Development status)**: inference spans named
  `{gen_ai.operation.name} {gen_ai.request.model}`; operations include
  `chat`, `embeddings`, `execute_tool`, `invoke_agent`, `create_agent`,
  `invoke_workflow`, `plan`, retrieval and memory ops. Required:
  `gen_ai.operation.name`, `gen_ai.provider.name` (e.g. `anthropic`);
  conditionally required: `gen_ai.request.model`, `error.type` on
  error, `gen_ai.conversation.id` when a session id is readily
  available; recommended: `gen_ai.usage.input_tokens` /
  `gen_ai.usage.output_tokens` (+ cache-creation/cache-read token
  splits)
  (https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/gen-ai-spans.md,
  accessed 2026-06-13).
- **Agent spans**: `create_agent {gen_ai.agent.name}`,
  `invoke_agent {gen_ai.agent.name}`,
  `invoke_workflow {gen_ai.workflow.name}`, `plan`, plus
  `execute_tool {gen_ai.tool.name}`; hierarchy guidance: the
  plan-generating LLM call is a child of the `plan` span; tool/task
  spans are siblings under the same `invoke_agent` span
  (https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/gen-ai-agent-spans.md,
  accessed 2026-06-13).
- **Content capture is Opt-In by convention**:
  `gen_ai.input.messages` / `gen_ai.output.messages` /
  `gen_ai.system_instructions` / `gen_ai.tool.definitions` "SHOULD NOT
  [be captured] by default", gated by e.g.
  `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` (gen-ai-spans
  doc, URL above) — directly relevant to the §2.3 credential-hygiene
  caveat.
- **Events/metrics**: two events now — the opt-in
  `gen_ai.client.inference.operation.details` and, notably for this
  design, **`gen_ai.evaluation.result`** (eval metric
  name/score/label/explanation, parented to the evaluated operation
  span) — i.e. the semconv already reserves a slot for reflector
  verdicts
  (https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/gen-ai-events.md,
  accessed 2026-06-13). Metrics include `gen_ai.client.token.usage`,
  `gen_ai.client.operation.duration`, `gen_ai.workflow.duration`
  (https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/gen-ai-metrics.md,
  accessed 2026-06-13).
- **Real emitters exist, including our own agent runtime**: the OTel
  blog's 2026 GenAI-observability post names VS Code Copilot, OpenAI
  Codex, and **Claude Code** as emitters of these conventions
  (https://opentelemetry.io/blog/2026/genai-observability/, accessed
  2026-06-13).
- **Trace-per-turn vs trace-per-workflow is genuinely contested**:
  OpenAI Agents SDK defaults to one trace per workflow with `group_id`
  linking turns (https://openai.github.io/openai-agents-python/tracing/,
  accessed 2026-06-13); LangSmith defaults to one trace per turn
  grouped by `thread_id`/`session_id` metadata that must be set on ALL
  child runs (https://docs.langchain.com/langsmith/threads, accessed
  2026-06-13). For this system, one-trace-per-dispatched-item (§4.2)
  matches the OpenAI/OTel shape.

### 1.3 Honeycomb surfaces for an automated gate

- **OTLP/HTTP JSON ingest is verified**: Honeycomb accepts OTLP over
  gRPC, HTTP/protobuf, and **HTTP/JSON** at
  `https://api.honeycomb.io/v1/traces` with `x-honeycomb-team` auth;
  dataset derives from `service.name`; environments are selected by
  API key (https://docs.honeycomb.io/send-data/opentelemetry/,
  accessed 2026-06-13). This matches the capture file's
  one-ExportTraceServiceRequest-per-line format exactly.
- **Limits**: ≤1 MB request body, ≤2,000 distinct fields per event,
  ≤64 KB per string field
  (https://docs.honeycomb.io/api/events/create-an-event, accessed
  2026-06-13) — ample for wide dispatch/agent spans at this volume.
- **Honeycomb launched Agent Observability (2026-05-12)**: Agent
  Timeline (Early Access; multi-agent multi-trace workflows in one
  view of LLM calls, tool invocations, handoffs, MCP calls), `gen_ai.*`
  as first-class citizens consuming **GenAI semconv v1.40.0**, no
  proprietary SDK
  (https://www.honeycomb.io/blog/honeycomb-launches-agent-observability-full-visibility-agentic-workflows,
  accessed 2026-06-13).
- **Programmatic read surfaces** (the gate's evidence path):
  - **Query Data API is Enterprise-only** ("available as part of the
    Honeycomb Enterprise plan"), async create-poll flow, 10 req/min,
    10 s max execution, 7-day max range, ≤10k rows
    (https://docs.honeycomb.io/api/query-data, accessed 2026-06-13).
  - **The hosted Honeycomb MCP server went GA 2025-09-09 and is
    "available to all of our accounts at no additional charge"** (not
    Enterprise-gated; requires Honeycomb Intelligence enrollment; OAuth
    2.1 or API key), with query parity, **BubbleUp**,
    heatmaps/histograms, Trigger/SLO state, and board creation
    (https://www.honeycomb.io/blog/honeycomb-mcp-ga-support-bubbleup-heatmaps-histograms
    and https://docs.honeycomb.io/integrations/mcp, accessed
    2026-06-13). The older self-hosted `honeycombio/honeycomb-mcp`
    (which exposed `run_query`, `list_slos`, `get_trigger`,
    `get_trace_link`, …) is archived as of 2026-04-22
    (https://github.com/honeycombio/honeycomb-mcp, accessed
    2026-06-13).
  - Triggers, SLOs, Boards, and Derived-Columns CRUD are plain REST
    with no Enterprise gating stated (https://docs.honeycomb.io/api/,
    accessed 2026-06-13).
- **Trace deep-links are documented and constructible**:
  `https://ui.honeycomb.io/<team>/environments/<env>/trace?trace_id=<id>&span=<spanId>&trace_start_ts=<ts>&trace_end_ts=<ts>`
  (timestamps optional but recommended — default search window is the
  last 2 hours)
  (https://docs.honeycomb.io/investigate/collaborate/share-trace,
  accessed 2026-06-13). Findings can therefore embed durable evidence
  links mechanically.
- Honeycomb's own LLM-product guidance ("All the Hard Stuff Nobody
  Talks About when Building Products with LLMs") emphasizes that
  chaining compounds latency and error — consonant with keeping the
  reflection chain OUT of the verdict path
  (https://www.honeycomb.io/blog/hard-stuff-nobody-talks-about-llm,
  accessed 2026-06-13).

### 1.4 Automated issue-filing from agent findings

- **Identity, not occurrence**: Sentry groups events into issues via a
  fingerprint — priority order custom `fingerprint` → stack trace →
  exception type/value → message, with message text explicitly the
  least reliable signal ("a lot less reliable because of changing
  error messages")
  (https://docs.sentry.io/concepts/data-management/event-grouping/,
  accessed 2026-06-13). PagerDuty's Events API applies subsequent
  events with the same `dedup_key` to the open alert rather than
  opening new ones; after resolve, the same key starts a fresh
  lifecycle (https://developer.pagerduty.com/docs/events-api-v2/trigger-events/index.html,
  accessed 2026-06-13, *snippet*). Grafana groups alert instances by
  label set — "the difference between receiving 1 phone call and 100
  phone calls" — and rate-limits emission with `group_wait` (30s) /
  `group_interval` (5m) / `repeat_interval` (4h)
  (https://grafana.com/docs/grafana/latest/alerting/fundamentals/notifications/group-alert-notifications/,
  accessed 2026-06-13).
- **Lifecycle, not new-issue-per-run**: GitHub code scanning tracks
  alerts per branch across analysis runs, groups related paths "under
  a single alert rather than creating separate alerts for each path",
  and identifies duplicates across configurations
  (https://docs.github.com/en/code-security/code-scanning/managing-code-scanning-alerts/about-code-scanning-alerts,
  accessed 2026-06-13). Dependabot keys alerts to
  (vulnerability, dependency), created event-driven rather than
  per-scan
  (https://docs.github.com/en/code-security/dependabot/dependabot-alerts/about-dependabot-alerts,
  accessed 2026-06-13).
- **Thresholds — the SRE ticket tier**: page only on urgent,
  actionable, user-visible, novel symptoms ("If a page merely merits a
  robotic response, it shouldn't be a page";
  https://sre.google/sre-book/monitoring-distributed-systems/,
  accessed 2026-06-13); sustained low-grade burn files a *ticket*, not
  a page — the workbook's baseline is ~10% error-budget consumption
  over three days for ticket alerts, with multi-window multi-burn-rate
  evaluation (https://sre.google/workbook/alerting-on-slos/, accessed
  2026-06-13). Automated finding-filers default to the ticket class.
- **Severity + evidence links**: GitHub code scanning uses
  Error/Warning/Note plus Critical/High/Medium/Low for security (75th-
  percentile CVSS of associated CVEs); each alert deep-links the
  triggering line, the producing analysis, and the fixing PR/branch
  (GitHub URL above, accessed 2026-06-13). Sentry's trace view links
  errors to full trace context
  (https://docs.sentry.io/concepts/key-terms/tracing/trace-view/,
  accessed 2026-06-13). The §5 design's "every finding carries a
  Honeycomb trace link + run id" follows this.
- The "stable hash of category + locus" dedup-key phrasing in §5.2 is
  a synthesis of the above sources, not a quoted rule.

### 1.5 Stability patterns for in-loop evaluators

- **The OTel error-handling spec is the canonical fail-open contract**
  (normative text): implementations "MUST NOT throw unhandled
  exceptions at runtime"; "MAY fail fast … on initialization … but
  MUST NOT cause the application to fail later at runtime"; APIs
  return no-op/default objects rather than null; suppressed errors go
  to self-diagnostics logging; default error handling must be
  user-overridable
  (https://opentelemetry.io/docs/specs/otel/error-handling/, accessed
  2026-06-13). §6 copies this contract for the reflection stage.
- **Async-by-default is what GenAI observability vendors ship**:
  Langfuse — "Trace events are queued locally and flushed in batches,
  so your application's response time is not affected"
  (https://langfuse.com/docs/observability/overview, accessed
  2026-06-13); LangSmith/Braintrust/Arize evaluators run server-side
  on already-ingested traces (§1.1 citations) — the strongest
  isolation form: the judge cannot block or crash the producer at all.
- **Sampling doctrine**: OTel head sampling is cheap but cannot
  condition on whole-trace properties; tail sampling enables "always
  sampling traces that contain an error" at the cost of buffering —
  mapping directly onto "evaluate all failed/blocked runs, sample the
  green ones" (https://opentelemetry.io/docs/concepts/sampling/,
  accessed 2026-06-13).
- **Time-boxing**: AWS Builders' Library treats timeouts as mandatory
  first-class config (hung calls hold resources; set the timeout at a
  chosen false-timeout-rate percentile of downstream latency)
  (https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/,
  accessed 2026-06-13).
- **Circuit-breaking the evaluator**: Fowler's breaker — trip open
  after a failure threshold so further calls fail fast; half-open
  probes or manual reset; "Any change in breaker state should be
  logged and breakers should reveal details of their state for deeper
  monitoring" (https://martinfowler.com/bliki/CircuitBreaker.html,
  accessed 2026-06-13); resilience4j frames the same for libraries
  ("When a system is seriously struggling, failing fast is better than
  making clients wait";
  https://github.com/resilience4j/resilience4j, accessed 2026-06-13).
  Feature-flag fallback values (LaunchDarkly) double as the operator
  kill-switch substrate
  (https://launchdarkly.com/docs/sdk/features/evaluating, accessed
  2026-06-13, *snippet*).
- **Explicit gap**: no authoritative published guidance was found
  specifically on separate-process/container isolation for LLM
  reflectors, nor a formal "evaluation must not block the critical
  path" statement in those words — the principle is well-attested only
  via the vendor + OTel + AWS sources above. An "error budget for the
  evaluator itself" is our synthesis of SRE burn-rate doctrine applied
  to the evaluator as a service, not a sourced practice.

## 2. What the gate plugs into (current-system inventory)

All paths are repo-relative to livespec-impl-beads at `origin/master`
(`ca6f7ed`, 2026-06-13) unless noted.

### 2.1 The fabro factory loop (the dispatcher)

`.claude-plugin/scripts/livespec_impl_beads/commands/dispatcher.py`
(+ `_dispatcher_engine.py`, `_dispatcher_plan.py`, `_dispatcher_io.py`):

- `loop --repo <path> --budget <n> [--parallel <k>] [--mode
  shadow|autonomous]` polls the beads Ledger, slices the ready queue to
  the budget, journals a `loop-pick` record, dispatches each item on a
  `ThreadPoolExecutor`, collects `DispatchOutcome`s, emits the summary
  (`_emit_outcomes`), and exits 0 iff all outcomes are `green`. **Loop
  exit = after `_emit_outcomes` in `_run_loop_command`** — the natural
  in-process reflection point is between collecting outcomes and
  emitting the summary (so findings can ride the summary).
- Per item (`_dispatch_one` → `run_dispatch` in the engine), the
  journaled stage sequence is: `sizing-warn` (warn-only heuristics) →
  `ledger-comments` (fail-closed read of operator riders) →
  `run-config-overlay` (credential projection + sibling clones; fails
  fast) → `fabro-run` (the whole sandbox phase graph as ONE subprocess,
  up to 54000s) → `fabro-inspect` (blocked-state detection) → `pr-view`
  / `pr-arm-fallback` / `pr-update-branch` → merge poll →
  `janitor-checkout-preclean`/`-add`/`-trust` → `janitor-post-merge`
  (fresh detached worktree of the merged ref, per `ca6f7ed`) →
  `janitor-checkout-remove` → `ledger-close` → `outcome`.
- Outcomes are three-valued: `green` / `failed` (at a named stage) /
  `blocked` (run parked at the in-loop human gate; never auto-resumed).
  Expected failures are DATA, never exceptions — the loop survives one
  item's failure and keeps budget accounting. A reflection stage must
  preserve exactly this discipline.

### 2.2 The journal

`_dispatcher_io.JournalFile`: append-only JSONL, thread-safe, one
record per stage/loop event, shape
`{"at": iso8601, "stage": ..., "work_item_id": ..., "exit_code": ...,
"detail": <last 2000 chars>}` (plus stage-specific keys:
`loop-pick.picked[]`, `outcome.outcome{}`, `ledger-check.findings[]`,
`sizing-warn.warnings[]`). Default path
`<repo>/tmp/fabro-dispatch-journal.jsonl`. This is the
machine-readable post-hoc audit surface the Dispatcher guidance
requires — and the input the interim OTLP capture already consumes.

### 2.3 Fabro's own observability surface (measured 2026-06-13)

- `fabro ps -a --json`: per-run metadata — `run_id`,
  `workflow_graph_name`, `status.kind`
  (`running|succeeded|failed|blocked|...`), `start_time`,
  `wall_time_ms`, `total_usd_micros`, `source_directory`,
  `repo_origin_url`, full `goal` text (which embeds the work-item id).
- `fabro events <run> --json`: the per-run event log. Sampled on
  completed run `01KTYZ8FX98N5G2GM5AR4YN004` (83 events): run
  lifecycle (`run.created` … `run.completed`), sandbox lifecycle
  (`sandbox.initializing` … `sandbox.stop.completed`),
  `setup.command.started/completed` (the prepare steps),
  `stage.started/completed` per graph node, `agent.acp.
  started/completed` (with `duration_ms` and the agent's full stdout
  narration), `prompt.completed`, `git.commit`, `edge.selected`,
  `checkpoint.completed`. **`stage.completed` carries a per-node
  `timing` block: `{active_time_ms, inference_time_ms, tool_time_ms,
  wall_time_ms}` plus `attempt`/`max_attempts`/`status`** — i.e.
  fabro already separates inference time from tool time per node.
- **Granularity floor: per node.** There are no per-turn or
  per-tool-call events; tool activity is aggregated into
  `tool_time_ms`. Turn/tool-call visibility must come from the agent
  runtime inside the sandbox (§4.3).
- Other read surfaces a reflector could use: `fabro logs` (raw worker
  tracing), `fabro ask` (read-only natural-language question about a
  run), `fabro dump` (durable state export), `fabro artifact`, and
  notably **`fabro mcp` — fabro ships an MCP server**, so an LLM
  reflector can query runs through a structured tool surface rather
  than shelling out.
- **Sensitivity caveat (observed, not hypothetical)**: the
  `agent.acp.completed` stdout in the sampled run contains the agent
  narrating "The PAT is embedded in the git remote URL. I'll extract
  it and use it with `gh`." Event payloads are credential-adjacent
  free text. Any pipeline shipping fabro event payloads to an external
  sink MUST truncate AND scrub (the interim capture script truncates
  attributes to 300 chars — truncation is not scrubbing), per the
  family's sandbox-probe credential-hygiene discipline.

### 2.4 The interim OTLP capture (the data shapes that exist today)

`livespec/tmp/capture_runtime_telemetry.py` harvests history into
`livespec/tmp/otel-runtime-spans.jsonl` — one OTLP/HTTP JSON
`ExportTraceServiceRequest` per line, deterministic sha256-derived
trace/span ids, idempotent re-runs (append-only with local span-id
dedup). Five resources (`service.namespace=livespec-family`):

| service.name | spans | trace shape |
|---|---|---|
| `livespec-rgr` | `rgr.red-to-green` per TDD-trailer commit pair | flat, one span per commit |
| `livespec-dispatcher` | `dispatcher.dispatch` root + `dispatcher.stage.<stage>` children | one trace per (journal, work-item) |
| `fabro-sandbox` | `fabro.<graph>` per terminal run (`wall_time_ms`-derived end) | flat; `work_item_id` regexed from goal |
| `claude-subagents` | `subagent.<agentType>` per harness transcript | flat; first/last line timestamps |
| `github-ci` | `ci.run` root + `ci.job.<name>` children | one trace per CI run |

The replay loop to Honeycomb is already documented in the script
header (`curl` per line to `https://api.honeycomb.io/v1/traces` with
`x-honeycomb-team`). Key correlation join available today:
`work_item_id` appears on dispatcher spans AND fabro spans (and the
goal text), so Honeycomb can join the host-side and sandbox-side
views per item without true W3C trace propagation.

## 3. Design options: where the reflection gate lives

The directive asks for a gate "before the loop exits (or at other
appropriate points for multi-task loops)". Three candidate homes, then
the multi-task placement question.

### Option (a): a `reflect` node in the per-item fabro phase graph

A new ACP node in `workflow.fabro` after `pr` (or on the `pr -> exit`
edge), reviewing the run from inside the sandbox.

- **What it can see**: the sandbox clone, the run branch, its own
  conversation context, janitor output blobs. It can NOT see: the
  merge (auto-merge is armed but merge happens after the fabro run
  returns — the Dispatcher polls it), the post-merge janitor, the
  ledger, other items in the wave, Honeycomb (the sandbox env is
  allowlist-scrubbed; reaching Honeycomb would mean projecting ANOTHER
  secret into every sandbox), or any cross-run history.
- **Latency/stability blast radius**: maximal. It adds an LLM turn to
  every dispatch inside the ACP turn/stall budgets that already killed
  two heavy items at the old 2h ceiling (bn4 evidence in
  `workflow.fabro` comments); a hung reflect node parks the run at the
  human gate or burns `stall_timeout`; a failed one routes through the
  failure edges and can flip a run that did green work into
  blocked/failed.
- **Failure semantics**: structurally in-band. Fabro's edge routing
  means node failure IS run-outcome-relevant; making a node truly
  consequence-free requires careful unconditional-edge design and
  still consumes sandbox wall-clock. This is the one option that
  cannot honor "never impacts the verdict" by construction.
- **Verdict**: rejected as the primary gate. (A narrow exception
  worth keeping in mind: per-item *self*-reflection prompts — e.g.
  asking the implement node to end its turn with a structured
  lessons/learnings block — are cheap prompt edits, not graph nodes,
  and feed the out-of-band reviewer good material.)

### Option (b): a loop-level reflection stage in the Dispatcher before exit

A new stage in `_run_loop_command` between collecting outcomes and
emitting the summary (and a sibling spot at the end of
`_run_dispatch_command` for single dispatches).

- **What it can see**: everything host-side — all `DispatchOutcome`s
  of the wave, the full journal, the ledger (store API in-process),
  `fabro ps/events/inspect` (authenticated CLI in the Dispatcher's
  env), `gh` (CI conclusions, PR state), and Honeycomb (API key in the
  Dispatcher's env via the same with-livespec-env.sh 1Password channel
  that carries the OAuth token). This is the first point where the
  WHOLE wave is visible.
- **Latency/stability blast radius**: bounded and controllable. It
  runs after every item's verdict is final and after `ledger-close`,
  so it delays only process exit + summary. Time-boxed subprocess with
  a hard timeout caps the worst case.
- **Failure semantics**: trivially fail-open — compute the exit code
  from outcomes FIRST, run reflection under a catch-everything wrapper
  + subprocess timeout, journal a `reflection` (or `reflection-error`)
  record, return the precomputed exit code unconditionally.
- **Verdict**: the right home for the *synchronous* part: mechanical
  aggregation (failure clustering, stage-latency outliers, retry
  counts, sizing-warning correlation), findings into the summary, and
  optionally a SMALL budgeted LLM pass. Keeps the directive's "notify
  the human as part of the summary" literal.

### Option (c): a fully out-of-band reflector process

A separate process (cron/systemd timer, or fire-and-forget spawned at
loop exit) consuming the journal + Honeycomb + fabro + ledger after
the fact; LLM-driven holistic review; files work-items.

- **What it can see**: everything (b) sees PLUS cross-loop history —
  multiple journals, Honeycomb's full retention window (trends: "fix
  loops per item are creeping up week-over-week"), closed items,
  previously-filed reflection findings (for dedup), and the full fabro
  event logs including agent narration. This is the only option that
  can do the directive's "holistic reviews of everything that happened
  in the loop, so it can improve" at depth — Reflexion-style persisted
  lessons need a durable cross-run memory, which is exactly what
  Honeycomb + the ledger provide.
- **Latency/stability blast radius**: zero on the loop. Its only
  couplings are read-only surfaces and ledger appends.
- **Failure semantics**: complete isolation; a crashed reflector is a
  no-op; circuit-breaking is process supervision, not loop logic.
- **Cost**: it runs after the summary is printed, so by itself it
  cannot satisfy "notify the human as part of the summary" — findings
  surface on the NEXT loop (the ready queue picks up filed items) or
  via an async channel.

### Recommendation: hybrid (b) + (c), with (a) reduced to prompt-level self-reports

- **(b) synchronous, mechanical, ≤60s**: cluster the wave's failures,
  flag latency/retry outliers against journal+fabro history, verify
  every non-green outcome has a filed-or-existing ledger item, and
  print a `reflection:` block in the summary. No LLM in-process
  (deterministic, testable, fast); at most ONE budgeted LLM call
  behind a flag once the mechanical tier is proven.
- **(c) asynchronous, LLM-driven, Honeycomb-fed**: the holistic
  reviewer. Reads Honeycomb (queries + trace evidence), fabro events,
  journals; writes findings as ledger work-items (dedup per §5) and a
  dated report under `tmp/` (or `research/` when durable); never
  touches repos' working trees.
- The directive's phrase "leverage honeycomb heavily" lands here: once
  telemetry ships to Honeycomb continuously (§4), the reflector reads
  its evidence from Honeycomb queries rather than re-parsing local
  logs, and every finding carries a Honeycomb trace/query link.

### Where multi-task loops should reflect

| point | what happens | LLM? | budget |
|---|---|---|---|
| per item (in `_dispatch_one`, after `outcome`) | telemetry emit only: outcome span + stage spans exported; NO analysis | no | ~0 (async enqueue) |
| per wave (= one `loop` invocation, before summary) | option (b): mechanical reflection over the wave's outcomes + journal | no (initially) | ≤60s hard cap |
| loop exit, async | fire-and-forget trigger of the option-(c) reflector (it self-rate-limits; a timer-based run also covers crashed loops) | yes | its own process, e.g. ≤15min |
| cross-loop (daily/weekly or every N waves) | option (c) full holistic pass over Honeycomb history; trend findings; Reflexion-style "lessons" digest the orchestrator can inject into future dispatch briefs | yes | its own process |

Per-item LLM reflection is deliberately absent: it multiplies cost and
latency by budget×, sees the least context, and every survey source
that runs judges in production runs them on sampled/async traces, not
inline per task.

## 4. Telemetry pipeline options (file → Honeycomb, and what's missing)

### 4.1 Getting what exists today into Honeycomb

| option | mechanism | pros | cons | when |
|---|---|---|---|---|
| (1) one-shot replay | the curl loop already documented in `capture_runtime_telemetry.py` header | zero new code; backfills ALL history (RGR, dispatcher, fabro, subagents, CI); ingest format verified (§1.3: OTLP/HTTP JSON at `/v1/traces`) | **Honeycomb ingest is append-only events — no span-id dedup on re-send** (inference from the event model, not a quoted doc claim; verify before automating), so replay must be once-only or tracked with a sent-marker file; no liveness | now — seed the dataset so reflector design can start against real data |
| (2) OTel Collector tail | a host collector with the `otlpjsonfile` receiver tailing the JSONL + OTLP exporter to Honeycomb | retries/batching for free; decoupled from dispatcher lifetime; one config file | ANOTHER long-lived daemon to babysit on this host; the capture script is currently run ad hoc, so "tail" still needs a producer writing continuously | only if/when continuous local files become the canonical producer path |
| (3) direct emit from dispatcher | `JournalFile.append` dual-writes: journal line (source of truth, written first) + span enqueue to a background OTLP/HTTP exporter (OTel Python SDK `BatchSpanProcessor`: bounded queue, drops on overflow, never blocks the caller) | live spans with REAL trace context (loop span → dispatch span → stage spans) instead of post-hoc reconstruction; fail-open by SDK design | new dependency (the OTel SDK — the standardized choice per house preference) in the dispatcher; needs the Honeycomb key in the Dispatcher env | the steady-state target |

Recommended sequence: (1) immediately, then (3); skip (2) unless the
daemon earns its keep some other way. Keep the journal authoritative —
spans are a projection of it, never the other way around.

### 4.2 Trace shape (mapping to the gen_ai semconv where it fits)

- One trace per dispatched work-item; the `loop` invocation is a root
  span (`livespec.loop`, attrs: `mode`, `budget`, `parallel`,
  `picked_count`) with per-item `livespec.dispatch` children, then
  `livespec.stage.<stage>` grandchildren — exactly the hierarchy the
  capture script already fakes deterministically.
- Fabro-side: a harvester (or future fabro-native export) maps
  `stage.started/completed` events to spans carrying the measured
  `timing` block as attributes (`fabro.node.inference_time_ms`,
  `fabro.node.tool_time_ms`, …), `attempt`, `status`, and
  `gen_ai`-mapped fields for the ACP nodes.
- gen_ai semconv mapping for the agent nodes (per §1.2 — everything
  Development status, so pin the semconv version we emit and expect
  churn): ACP nodes (`implement`, `fix`, `pr`) → spans named
  `invoke_agent <node>` with `gen_ai.operation.name = invoke_agent`,
  `gen_ai.agent.name = <node_id>`,
  `gen_ai.provider.name = anthropic`, `gen_ai.conversation.id =
  <fabro run_id>` (a session id "readily available" per the spec's
  condition); in-sandbox tool calls → `execute_tool <tool>` spans with
  `gen_ai.tool.name`; model calls → inference spans with
  `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens`;
  failures → span status ERROR + `error.type`. Message/prompt content
  stays OFF per the semconv's own opt-in default
  (`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`) — which also
  answers the §2.3 scrubbing concern at the source. Reflector verdicts
  themselves have a reserved slot: the `gen_ai.evaluation.result`
  event (§1.2). Dispatcher stages are NOT gen_ai operations — keep
  them in a `livespec.*` namespace rather than force-fitting.
- Cross-boundary correlation: true W3C `traceparent` propagation into
  the sandbox is not available today (fabro owns the sandbox env;
  no propagation hook surfaced in its CLI). Use attribute joins
  (`work_item_id`, `fabro.run_id`) — Honeycomb queries/BubbleUp work
  fine on attributes; revisit propagation only if trace-waterfall
  unification across host/sandbox proves load-bearing.

### 4.3 NEW instrumentation needed for "all activity, turns, tool calls, failures"

1. **Dispatcher native spans** (§4.1 option 3): loop/dispatch/stage
   spans with status codes; plus span events for `sizing-warn`,
   `ledger-check` findings. Effort: small; the journal seam is one
   chokepoint.
2. **Fabro event export**: extend the existing harvester from
   run-level spans (`fabro.ImplementWorkItem`) to per-node spans using
   `fabro events --json` (timing block measured in §2.3). Effort:
   small, pure read-side. Scrub/drop `stdout`/`response` payload
   fields (credential-adjacent, §2.3) — ship names, ids, timings,
   statuses, token/cost numbers only.
3. **In-sandbox agent telemetry — the only source of turns and tool
   calls**: enable the agent runtime's native OTel export inside the
   sandbox, OTLP/HTTP direct to Honeycomb. Claude Code is a confirmed
   emitter of the GenAI semconv (named alongside Codex and VS Code
   Copilot in the OTel blog's 2026 GenAI-observability post, §1.2),
   so the ACP nodes' underlying runtime can produce
   `invoke_agent`/`execute_tool`/inference telemetry without us
   writing instrumentation. Transport needs the OTLP endpoint +
   Honeycomb key in the sandbox env — the per-dispatch run-config
   overlay is the established channel for exactly this (it already
   projects `CLAUDE_CODE_OAUTH_TOKEN`; `{{ env }}` interpolation is
   proven non-viable). Use a SEPARATE low-privilege ingest-only
   Honeycomb key, never the management key; leave prompt/message
   content capture at its off-by-default (§4.2). The exact env-var
   set for Claude Code's exporter inside the ACP adapter is a Phase-2
   verification item (not re-verified in this pass).
4. **Cost/usage**: `fabro ps` exposes `total_usd_micros` (null in
   sampled runs so far) and agent-runtime telemetry carries token
   usage; wire whichever populates first into the dispatch trace.

## 5. Issue-filing + human-notification design

### 5.1 Findings → ledger work-items

The ledger (beads store) is the family's single tracker; the
Dispatcher already holds the store API (`append_work_item`) — filings
are machine-path dispositions exactly like close-on-merge, exempt from
per-operation consent. GitHub issues are NOT recommended as the
primary sink (split-brain with the ledger; cross-repo items belong in
the livespec layer anyway).

Proposed finding-record mapping:

| work-item field | content |
|---|---|
| `title` | `[reflection] <category>: <one-line subject>` |
| `description` | finding narrative + **evidence links**: Honeycomb trace deep-links (documented URL format incl. `trace_id` + start/end timestamps, §1.3), `fabro.run_id`s, journal path + stage, PR numbers |
| `type` | `bug` (verdict-threatening defect) / `chore` (hygiene, perf) |
| `priority` | from severity triage (§5.2) |
| `labels` | `reflection`, `fingerprint:<12-hex>` (dedup key), optional `reflection-mute` honored on re-encounter |
| `origin` | derives per the fail-soft origin rule (gap-tied iff `gap_id`; these are freeform) |

### 5.2 Dedup, thresholds, severity (anti-spam by construction)

- **Fingerprint = sha256(category | stage-or-node | repo |
  normalized-subject)[:12]** — never raw message text (timestamps,
  ids, and paths churn). This is Sentry's custom-fingerprint lesson
  and GitHub code-scanning's alert-identity lesson applied to the
  ledger.
- **Lifecycle, not new-issue-per-run**: before filing, query open
  items for the fingerprint label. Present → append occurrence
  evidence as a ledger comment (the Dispatcher already reads comments
  into goals, so recurrence count reaches the next implementer);
  absent → file. Closed-with-`reflection-mute` → never re-file, count
  in the digest only.
- **Per-pass cap**: at most 3 NEW items per reflection pass
  (recommendation; tune later). Everything else aggregates into the
  summary digest. A reflector that wants to file 10 items has found 1
  systemic problem, not 10 problems.
- **Severity triage** (maps to priority): `critical` = verdict
  integrity at risk (e.g. green outcome with red post-merge evidence)
  → P1 + summary banner; `warn` = recurring failure cluster, budget
  exhaustion patterns, latency regression beyond threshold → P2/P3
  item; `info` = single-occurrence oddities, style observations →
  digest only, NO item. Thresholds on recurrence (e.g. file `warn`
  only at ≥2 occurrences across waves) keep one-off noise out.

### 5.3 Human notification

- **Synchronous (option b)**: `_emit_outcomes` grows a `reflection:`
  trailer section — finding counts by severity, the top finding
  one-liner, ids of items filed/bumped, and Honeycomb links. Blocked
  and failed outcomes already surface here; reflection rides the same
  channel, JSON mode included (additive key, never altering the
  outcomes array or exit code).
- **Asynchronous (option c)**: filed items surface naturally in the
  ready queue / `next` ranking; plus one journal record per pass. If
  push notification proves wanted, a memo via the existing
  capture-memo path beats inventing a channel.

## 6. Stability and performance guardrails

**The invariant, stated once and enforced mechanically: REFLECTION
NEVER CHANGES A DISPATCH VERDICT.** Concretely: in
`_run_loop_command`/`_run_dispatch_command` the exit code is computed
from outcomes BEFORE the reflection stage runs; reflection output can
add summary text and ledger items, nothing else; no code path from
reflection into outcome objects, `ledger-close`, or the returned exit
code. A test asserting "reflection raised → exit code unchanged,
summary still emitted" is part of any Phase-2 implementation.

- **Fail-open everywhere**: reflection wrapped in catch-all + journal
  `reflection-error`; telemetry export uses bounded-queue
  drop-on-overflow batch semantics (the OTel SDK default), never
  blocking a dispatch thread; Honeycomb unreachable → spans drop,
  loop unaffected; the out-of-band reflector crashing is a logged
  no-op.
- **Time-boxes**: per-item emit ≈ 0 (async enqueue); wave-level
  mechanical pass ≤60s hard cap (subprocess or watchdog-thread
  timeout); any in-process LLM call (if ever enabled) ≤300s, one
  attempt, no retry; out-of-band reflector self-budgets (suggest
  ≤15min) and is supervised by its own timer, not the loop.
- **Sampling**: telemetry 100% (volume is trivially small, §1.3);
  LLM-judge evaluation sampled — all `failed`/`blocked` runs, top-k
  latency/cost outliers, ~10% of green runs as a control. Sampling
  policy lives in config, not code.
- **Isolation**: the out-of-band reflector is a separate process with
  read-only access to repos (no checkouts, no worktrees — it reads
  Honeycomb/fabro/journal/gh), write access ONLY to the ledger and
  its own report file. It does not run inside a fabro sandbox dispatch
  (no recursion: the reflector must never become a thing the
  reflector reviews on the same tier).
- **Circuit breaker — one self-documenting lever, always wired** (per
  the family's carve-out-as-severity-lever discipline):
  `LIVESPEC_REFLECTION=off|observe|file` (default `observe` until the
  mechanical tier proves quiet, then `file`). Plus an automatic trip:
  N consecutive `reflection-error` journal records (suggest N=3) →
  the stage self-skips with a WARN line until the lever is cycled.
  No other skip flags, no per-check exemptions.
- **Performance**: no LLM in the per-item path, ever; reflection never
  sits between merge-confirmation and `ledger-close` (verdict path
  stays minimal); fabro-event harvesting is read-side and rate-bound
  by the handful of runs per day.

## 7. Open questions for the user brainstorm

1. **Gate placement** — adopt the hybrid (b)+(c)? *Recommendation:
   yes.* (b) alone can't do holistic/trend review and can't afford
   deep LLM passes in-process; (c) alone can't put findings in the
   loop summary. (a) violates the stability directive by construction.
2. **Does the in-process wave stage get an LLM call at all?**
   *Recommendation: no — mechanical-only.* Deterministic, testable,
   fast, zero new failure modes in the dispatcher; ALL LLM judgment
   moves out-of-band where it is sampled, time-boxed, and isolated.
   Revisit only if the mechanical tier demonstrably misses findings
   the async tier catches too late.
3. **Telemetry transport** — one-shot replay now + direct emit from
   the dispatcher (OTel Python SDK) as steady state, skipping a host
   collector daemon? *Recommendation: yes.* The SDK is the
   standardized library, its batch processor is fail-open by design,
   and a collector is one more daemon for marginal benefit at this
   volume.
4. **In-sandbox agent telemetry** — enable the agent runtime's native
   OTel export inside the fabro sandbox, projecting an ingest-only
   Honeycomb key via the existing run-config overlay channel?
   *Recommendation: yes, with a dedicated ingest-only key.* It is the
   only path to per-turn/per-tool-call visibility ("all activity,
   turns, tool calls"); the overlay is the proven secret channel.
   Decision needed on key handling: same 1Password environment, new
   entry.
5. **Issue sink** — ledger work-items (not GitHub issues)?
   *Recommendation: ledger.* Single tracker, existing store API,
   existing ranking/dispatch integration; the dispatcher already does
   machine-path ledger writes on the same consent footing.
6. **Dedup mechanics** — fingerprint label + open-item query +
   comment-bump on recurrence + `reflection-mute` honor + ≤3 new
   items/pass? *Recommendation: yes as the starting policy.* Matches
   the Sentry/code-scanning lifecycle consensus; every knob is a
   constant we can tune from evidence later.
7. **Reflection cadence for multi-task loops** — per-item emit-only,
   per-wave mechanical, async holistic at loop exit + timer?
   *Recommendation: yes (the §3 table).* Matches where context becomes
   visible and keeps cost sublinear in budget.
8. **Honeycomb read path for the reflector** — hosted Honeycomb MCP
   server vs raw Query Data API? *Recommendation: the hosted MCP
   server.* Verified (§1.3): the Query Data REST API is
   Enterprise-only with tight limits (10 req/min, 7-day window),
   while the hosted MCP is GA, free on all accounts (Honeycomb
   Intelligence enrollment + OAuth 2.1/API key), and exposes queries,
   BubbleUp, and Trigger/SLO state — a strictly better fit for an
   LLM-driven reflector, and the only viable one off-Enterprise. The
   decision rider: enroll the account in Honeycomb Intelligence and
   choose the auth mode (OAuth 2.1 vs API key) for an unattended
   reflector.
9. **Reflector identity/runtime** — plain headless agent invocation
   (e.g. `claude -p` with the reflection prompt + MCP read tools) vs
   a fabro workflow of its own? *Recommendation: plain headless
   invocation first.* A fabro run gets sandboxing for free but adds
   the recursion hazard (reflector runs become reflection subjects)
   and sandbox-credential plumbing for a read-mostly job; promote to
   a workflow only if it needs multi-node structure.
10. **Where do "lessons" live so the loop actually improves?**
    Findings-as-work-items close the defect loop, but Reflexion-style
    improvement also wants a digest the orchestrator injects into
    future dispatch briefs (the goal file) or prompts.
    *Recommendation: a small curated `lessons` artifact (ledger
    comments on an epic item, or a committed doc updated via PR), fed
    by the reflector but human-ratified* — auto-injecting unreviewed
    LLM lessons into every future brief is a prompt-injection-shaped
    risk and dilutes briefs; ratification keeps the improvement loop
    human-supervised, matching the family's consent discipline.
