# Telemetry pipeline architecture (epic 29f — consolidation pass)

**Status: consolidation of user-ratified decisions, grounded against
shipped code + captured telemetry.** This doc does NOT relitigate the
architecture — it grounds it, names the one structural gap (no filed
child for the host-local enrich/scrub stage), and recommends the
buildable child-item decomposition + sequencing.

Companions in this directory:
[`best-practices-and-design.md`](./best-practices-and-design.md) (the
895 survey + the original pinned decisions) and
[`cc-otel-gap-analysis.md`](./cc-otel-gap-analysis.md) (the 29f.1
Claude-Code native-export gap analysis). This doc supersedes the
"no collector / direct-to-Honeycomb" pipeline of those two docs with
the **PINNED PIPELINE UPDATE**: all telemetry now passes through a
host-LOCAL enrichment/scrub stage before Honeycomb.

Epic: **livespec-impl-beads-29f** (the dispatcher's Honeycomb-backed
reflection/audit loop — the 3rd leg of the W6 operability trio
alongside oyg's stall watchdog and h1p's failure notification).

---

## 1. Bottom line

- The 3rd leg of W6 is a **reflection/audit loop**, not just an export.
  The export pipeline is its prerequisite; this doc is about the
  pipeline.
- The user-ratified pipeline is:
  **CC-sandbox native OTel + dispatcher-emitted OTLP spans (29f.2) →
  host-LOCAL enrichment/scrub stage → Honeycomb → consumers
  (reflector / oyg watchdog / dev-tooling e60)**.
- **The one structural gap**: there is no filed child item for the
  CORE new artifact — the host-local enrich/scrub stage. Everything
  downstream (29f.3's sandbox OTLP endpoint, 29f.4's reflector,
  oyg's OTEL upgrade, e60's analysis) presumes that stage exists. It
  must be the FIRST buildable child (§6).
- **Recommended enrich-stage shape: a custom host-local OTLP processor
  (a small stdlib + OTel-SDK Python service), NOT an off-the-shelf
  otelcol collector** — rationale in §3. The decision turns on
  correlation-key injection logic and the fail-closed credential scrub
  (decision 9), both of which are bespoke livespec policy that a
  generic collector pipeline cannot express without a custom processor
  plugin anyway; once a custom processor is unavoidable, the
  single-source-of-truth + operational-simplicity case favors owning
  the whole stage rather than embedding bespoke Python inside a
  collector runtime.
- **Grounding found NO conflict** between the decided architecture and
  what the code/telemetry support. The captured telemetry confirms the
  enrich stage's value (correlation lives in per-span attributes, not
  resource attributes — §2.3) and the oyg watchdog already carries the
  exact `LivenessProbe` extension point the metrics-heartbeat consumer
  plugs into (§4.4).

---

## 2. Grounding — what exists today (verified)

### 2.1 The shipped 29f.2 reflection stage

`.claude-plugin/scripts/livespec_impl_beads/commands/_dispatcher_reflection.py`
(landed on master as 29f.2; wired into `dispatcher.py` at the loop and
single-dispatch exits). Verified facts:

- It is a purely **mechanical, fail-open, ≤60s** scan run AFTER the
  verdict is computed. `reflect(...)` NEVER raises, NEVER changes the
  verdict, auto-trips to `off` after 3 consecutive errors, honors the
  `LIVESPEC_REFLECTION=off|observe|file` lever (default `observe`).
  Decisions 1, 2, 8 are SHIPPED here.
- It **emits OTLP/HTTP-JSON spans** — `reflection.pass` (root) +
  one `reflection.finding` child per finding — but writes them to a
  LOCAL file `<journal-stem>-reflection-spans.jsonl`
  (`dispatcher._spans_path`), **not** to Honeycomb. There is no
  network egress anywhere in the dispatcher today (verified: no
  `honeycomb`, `requests.post`, `urllib.request`, `http.client`
  reference in `dispatcher.py` or `_dispatcher_reflection.py`).
- It already carries a **fail-CLOSED credential scrub** (`_scrub`):
  a value matching the credential-bearing-URL regex
  `[a-zA-Z0-9_-]+:[^@\s/]+@` is replaced wholesale with
  `[redacted-credential-shaped-value]` (reject, not redact), and the
  emitter ships an **allowlist** of scalar attributes only — never
  "everything minus a denylist". Decision 9's principle is already
  embodied at the reflection emitter; the enrich stage must apply the
  SAME discipline to every span it forwards (§3.4).
- The span format it writes is the **canonical OTLP/HTTP-JSON
  one-`ExportTraceServiceRequest`-per-line shape** the family capture
  script established (`service.name` + `service.namespace` resource
  attrs; `scopeSpans`; sha256-derived deterministic trace/span ids).
  This is the wire format the enrich stage consumes on its file-tail
  ingest path.

The dispatcher does NOT yet emit the live `livespec.loop` /
`livespec.dispatch` / `livespec.stage.<stage>` host-truth spans — those
exist today ONLY as post-hoc reconstruction in the interim capture
script. Building that live emit is part of the enrich-stage epic's
upstream (see §6 child E1 note).

### 2.2 The captured telemetry sample

`/data/projects/livespec/tmp/otel-runtime-spans.jsonl` — **2,648 spans
across 5 services** (post-hoc reconstruction by the capture script, the
cold archive the one-shot replay migrates):

| service.name | spans |
|---|---|
| `github-ci` | 1,924 |
| `claude-subagents` | 309 |
| `livespec-dispatcher` | 272 |
| `livespec-rgr` | 112 |
| `fabro-sandbox` | 31 |

Span families: `ci.run` / `ci.job.<check>` (CI), `subagent.<type>`
(host subagents), `dispatcher.dispatch` / `dispatcher.stage.<stage>`
(host truth), `rgr.red-to-green` (commit gate), `fabro.<node>` (sandbox
node timings). Correlation-bearing span attributes present:
`work_item_id` (298), `fabro.run_id` (31), `session.id` (309),
`ci.run_id` (1,924), `git.commit.sha`, `git.branch`, `repo`,
`agent.id`.

**The load-bearing grounding observation:** the only RESOURCE-level
attributes in the entire sample are `service.name` and
`service.namespace` (2,648 each). Every correlation key lives at the
SPAN-attribute level, scattered and source-specific (CC sandbox would
add `session.id`; the dispatcher adds `work_item_id` + `journal`; fabro
adds `fabro.run_id` + `fabro.goal`). Nothing today injects a UNIFORM
correlation triple across all sources at a single chokepoint. That is
precisely the enrich stage's primary job (§3.3) — and it is why the
"CC native OTel is enough" position was correctly superseded: CC emits
rich per-turn/per-tool/per-API data but knows nothing of
`work_item_id`, `livespec.dispatch.id`, or `fabro.run_id`, and emits
content the host must scrub before egress.

### 2.3 The 29f.1 CC native-export findings (folded in)

A committed 29f.1 gap-analysis report already exists
(`cc-otel-gap-analysis.md`), so its findings are referenced rather than
duplicated. The load-bearing conclusions for the pipeline:

- CC native telemetry is metrics + events + **beta trace spans**
  (`OTEL_TRACES_EXPORTER=otlp` + `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`):
  `claude_code.interaction` root → `llm_request` / `hook` / `tool` →
  `tool.execution`, W3C `TRACEPARENT` propagation into subprocesses,
  and inbound `TRACEPARENT` honored in `-p`/SDK sessions (how fabro's
  ACP nodes run CC).
- Per-turn / per-tool-call / per-API-call facts exist natively even
  without the beta: `claude_code.api_request` (model, duration,
  4 token counts, `cost_usd`), `claude_code.tool_result` (tool_name,
  success, duration_ms, error_type), `prompt.id` chaining every event
  to its turn.
- What CC CANNOT do — and therefore what the enrich stage / dispatcher
  must add: (1) host-side dispatch/loop/merge/janitor TRUTH; (2)
  correlation keys (CC knows nothing of `work_item_id` / `fabro.run_id`
  / `livespec.dispatch.id`); (3) credential scrub before egress (CC's
  content flags stay off, but fabro's `agent.acp.*` stdout is
  PROVEN credential-adjacent — narrates PAT extraction).
- All CC content flags (`OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_TOOL_DETAILS`,
  `OTEL_LOG_TOOL_CONTENT`, `OTEL_LOG_RAW_API_BODIES`) stay OFF — CC
  redacts at source; the enrich stage scrubs defense-in-depth.

---

## 3. The host-local enrich/scrub stage (the CORE new artifact)

### 3.1 Why it exists (the PINNED PIPELINE UPDATE)

The earlier docs' "direct-to-Honeycomb, no collector" stance was
correct for the dispatcher's OWN spans (which are born clean and
correlated). It is INSUFFICIENT for the full pipeline because two
sources cannot egress safely on their own:

1. **CC sandbox telemetry** carries rich turn/tool/API facts but is
   missing the livespec correlation triple and uses CC's own
   `claude_code.*` / `session.id` naming. It needs correlation-key
   augmentation so the reflector can join CC turns to a dispatch.
2. **fabro event-derived spans** carry credential-adjacent narration
   (decision 9 HAZARD) that must be SCRUBBED — not merely truncated —
   before egress.

Both require an AUGMENT + SCRUB chokepoint between emit and Honeycomb.
That chokepoint is the host-local enrich/scrub stage. Pipeline:

```
  [CC sandbox native OTel]  ──┐
  [dispatcher OTLP spans 29f.2]─┤
  [fabro events → spans]      ──┼──▶ host-LOCAL enrich/scrub stage ──▶ Honeycomb
  [RGR / CI / subagent spans] ──┘        (augment correlation,           (livespec env)
                                          fail-closed scrub,
                                          batch + retry)
                                                  │
                                                  ├──▶ (metrics heartbeat) ──▶ oyg watchdog LivenessProbe
                                                  └──▶ Honeycomb ──(MCP)──▶ 29f.4 reflector + dev-tooling e60
```

The sandbox (29f.3) points its OTLP endpoint at the enrich stage
(reachable from inside Fabro), NOT directly at Honeycomb — so the
scrub + correlation augmentation is UNAVOIDABLE for sandbox egress, not
opt-in.

### 3.2 Collector (otelcol) vs custom host processor — RECOMMENDATION

**RECOMMENDED: a custom host-local OTLP processor** — a small,
stdlib-first Python service (OTel SDK only where it earns its keep on
the export side) that (a) exposes an OTLP/HTTP receiver reachable from
inside the Fabro sandbox, (b) tails the local span files the dispatcher
+ reflection stage write, (c) applies the correlation-key augmentation
and the fail-closed credential scrub, then (d) forwards to Honeycomb
with batching + retry. NOT an off-the-shelf `otelcol` deployment.

Decision factors (weighed against the consolidation brief's list):

| Factor | otelcol collector | Custom host processor | Winner |
|---|---|---|---|
| Correlation-key injection (CC session ↔ dispatcher journal ↔ fabro run) | needs a `transform`/`attributes` processor with non-trivial config; cross-source JOIN (e.g. CC `session.id` ↔ a dispatch) is NOT expressible in stock processors — requires a custom processor plugin or an OTTL routing hack | bespoke logic in plain Python; the join table (§3.3) is a dict lookup keyed on the overlay-injected `work.item.id` | **custom** |
| Mandatory fail-CLOSED scrub (decision 9) | stock `redaction`/`attributes` processors REDACT/hash by allow/deny lists; "reject the whole span on a credential-shaped match" is not a stock behavior — needs a custom processor anyway | the EXACT `_scrub` discipline already shipped in `_dispatcher_reflection.py` (reject-not-redact, allowlist-only), lifted into a shared module | **custom** |
| Reachability from inside Fabro sandbox | yes (binds a port) | yes (binds a port) — identical | tie |
| Operational simplicity (single-operator fleet) | ANOTHER daemon to babysit, a distinct config language (YAML + OTTL), a pinned binary version in `.mise.toml`, and a separate failure surface from the rest of the (Python) machinery | one Python process under the same toolchain (`uv`, `just`, pyright-strict, the family Python rules), same test tier, same observability | **custom** |
| Single source of truth | scrub + correlation policy would be split between Python (`_dispatcher_reflection._scrub`) and collector YAML/OTTL — drift risk | ALL scrub + correlation policy in one shared Python module reused by the reflection emitter, the dispatcher emitter, and the enrich stage | **custom** |
| "Batteries" (batching, retry, backpressure) | free, mature | must be written, but the OTel Python SDK's `BatchSpanProcessor` + OTLP/HTTP exporter provide it (the house-standard library, already the chosen transport in 4.1 option 3) | otelcol (minor) |

The ONLY column the collector wins is free batching/retry — and the
OTel Python SDK supplies that too (it is the already-ratified transport
for the dispatcher's direct emit). Every load-bearing requirement
(cross-source correlation JOIN, fail-closed scrub) forces a CUSTOM
processor even inside a collector; once custom code is unavoidable, the
single-source-of-truth + one-toolchain + reuse-the-shipped-`_scrub`
case is decisive. Owning a ~one-file Python service beats babysitting a
collector daemon whose stock processors cannot express the two
policies that matter.

**Stability:** the enrich stage is fail-open toward the pipeline (a
forward error never blocks a dispatch — the dispatcher already wrote
the authoritative journal and never depends on egress) but fail-CLOSED
toward credentials (a scrub-shaped match drops/rejects the span rather
than risk leaking). Same dual posture as 29f.2.

### 3.3 The correlation-key scheme

The enrich stage stamps a uniform correlation triple onto every span
it forwards, so the reflector joins on ONE key set regardless of source
(grounding §2.2 showed these are scattered + source-specific today):

| Key | Meaning | Source of truth | Present on |
|---|---|---|---|
| `work.item.id` | the ledger work-item being dispatched | dispatcher journal; injected into sandbox via `OTEL_RESOURCE_ATTRIBUTES` (29f.3) | dispatcher spans (native), CC sandbox (injected), fabro spans (goal regex), CI (PR/branch naming, weak) |
| `livespec.dispatch.id` | one dispatch attempt (journal-derived) | dispatcher (generated at dispatch); injected into sandbox env | dispatcher spans, CC sandbox (injected) |
| `fabro.run_id` | the fabro sandbox run | parsed by dispatcher post-`fabro-run`; native on fabro spans | dispatcher spans (post-start), fabro spans |
| `session.id` | CC session | CC native | CC sandbox spans only |
| `trace_id` (W3C) | unified host↔sandbox waterfall | dispatcher root span; nested IFF `TRACEPARENT` honored in the ACP `-p`/SDK session (29f.1 V3) | dispatcher root; CC sandbox if V3 verifies |

The enrich stage's join logic: it holds a small in-memory map keyed by
`work.item.id` → `{livespec.dispatch.id, fabro.run_id}` (populated as
dispatcher spans arrive); when a CC/fabro span arrives carrying ONE key
of the triple, the stage backfills the others as span attributes before
forwarding. Reflector queries then `GROUP BY work.item.id` (present on
all three primary sources) with `fabro.run_id` + time-window joins as
fallback. The CC sandbox path also gets the triple injected at SOURCE
via `OTEL_RESOURCE_ATTRIBUTES` (29f.3), so the enrich-side backfill is
defense-in-depth for that source and the PRIMARY mechanism for fabro +
CI spans that cannot be told their dispatch id at emit time.

### 3.4 The credential-scrub requirement (every egress path)

Decision 9 HAZARD: fabro event payloads carry credential-adjacent agent
narration (the sampled run literally narrates PAT extraction). The
enrich stage MUST apply the family scrub discipline to EVERY span on
EVERY egress path, reusing the SAME `_scrub` already shipped in
`_dispatcher_reflection.py`:

1. **Allowlist, not denylist** — only named scalar attributes
   (ids/counts/statuses/durations/token+cost numbers) are forwarded;
   never "everything minus a denylist".
2. **Fail-CLOSED on credential shape** — any attribute value matching
   `[a-zA-Z0-9_-]+:[^@\s/]+@` (scheme://user:secret@host) causes the
   value to be dropped/the span rejected, never partially shipped.
   Truncation is NOT scrubbing.
3. **No env values, no remote URLs, ever** — git remote URLs in this
   fleet embed PATs (`https://x-access-token:<PAT>@github.com/...`).
4. **fabro stdout/response payloads NEVER leave the host** —
   `setup.command.*`, `agent.acp.completed` stdout, `prompt.completed`
   responses are dropped at the fabro harvester before they reach the
   enrich stage; the enrich stage's scrub is the second line of defense.
5. **Ingest-only key in the sandbox + the enrich stage's egress** —
   the dedicated `HONEYCOMB_INGEST_KEY_LIVESPEC` (write-only); the
   management/MCP key never touches the ingest path.

Lifting `_scrub` (and the credential-URL regex + the attribute
allowlist) into a SHARED module reused by the reflection emitter, the
dispatcher's direct emit, and the enrich stage is itself a small
refactor child (§6 child E1's scope, or a sibling) — single source of
truth for the scrub policy.

### 3.5 Transport + provisioning (DONE / pinned)

- Honeycomb env "livespec" (team thewoolleyweb) is provisioned.
- `HONEYCOMB_INGEST_KEY_LIVESPEC` — ingest, write-only; OTLP →
  `https://api.honeycomb.io`, header `x-honeycomb-team`, dataset
  derived from `service.name`. The enrich stage's egress uses this key;
  the sandbox (29f.3) also uses it (the enrich stage may instead be the
  ONLY holder of the egress key, with the sandbox shipping plaintext to
  the host-local enrich endpoint — preferred, since it keeps the key
  off the sandbox entirely; pin this in the enrich-stage child).
- `HONEYCOMB_MCP_API_KEY_LIVESPEC` (config key "livespec-mcp-reflector")
  — the reflector READ path via `mcp.honeycomb.io`.
- Keys live in the livespec 1Password Environment; probe-only, never
  committed.
- **WIRE-UP CAVEAT to verify once telemetry flows**: confirm the
  reflector key queries the livespec env via `mcp.honeycomb.io`
  (Intelligence ON; `queries:false` limits only the classic Query Data
  API, NOT the MCP path).

---

## 4. The consumers

### 4.1 Reflector (29f.4) — read from Honeycomb via MCP

Fully out-of-band LLM reflector (decisions 1, 2): async, sampled,
time-boxed, isolated; NO in-process LLM call, NO fabro-graph reflect
node. Read path is the **hosted Honeycomb MCP** (`mcp.honeycomb.io`),
account enrolled in Honeycomb Intelligence, API-key headless auth
(`HONEYCOMB_MCP_API_KEY_LIVESPEC`). It queries the ENRICHED telemetry
(correlation triple present), `GROUP BY work.item.id`, clusters
failures/timeouts/retries, and:

- **Issue sink** (decision 6): files ledger work-items, DEDUP-FIRST —
  fingerprint = `hash(category | stage | repo | normalized-subject)`,
  comment-bump on recurrence, honor reflection-mute, ≤3 new items/pass.
- **Lessons** (decision 7): HUMAN-RATIFIED curated artifact — the
  reflector PROPOSES lessons; only ratified lessons are injected into
  briefs (auto-injection rejected as prompt-injection-shaped).
- **Verdict storage** (29f.1 R12): emits `gen_ai.evaluation.result`
  parented to the dispatch span.

### 4.2 dev-tooling e60 — analysis consumer

Reads the same enriched Honeycomb telemetry via MCP for cross-repo
analysis (the dev-tooling-side consumer). Sequenced alongside the
reflector — both read-only, both depend on enriched telemetry flowing.

### 4.3 oyg watchdog OTEL upgrade — the FIRST control-consumer

The oyg stall watchdog (`_dispatcher_watchdog.py`, shipped as the
wall-clock backstop against the 7us.6 152-minute silent ACP/commit
deadlock) is the FIRST consumer of the pipeline's CONTROL signal. Its
module docstring already pins the extension point verbatim:

> DEFERRED PRIMARY … the eventual primary liveness signal is the 29f
> OpenTelemetry metrics-heartbeat pipeline. Spans emit on END, so a
> deadlocked commit produces NO span; a metrics heartbeat (exported on
> a short interval) keeps advancing while an agent turn is genuinely
> alive and is a finer signal than coarse event-stream timestamps. …
> When it lands it plugs in as a finer `LivenessProbe` … feeding the
> SAME `decide_stall` logic; this wall-clock layer STAYS as the
> permanent defense-in-depth backstop.

### 4.4 The metrics-heartbeat-vs-spans subtlety (load-bearing)

This is WHY the oyg consumer reads the **metrics heartbeat**, not
spans, and it constrains the pipeline:

- **Spans emit on END.** A deadlocked commit / wedged ACP turn produces
  ZERO spans for the entire hang — exactly the 7us.6 failure mode. A
  span-only pipeline is BLIND to a live-but-stuck run, so it cannot be
  the watchdog's liveness signal.
- **A metrics heartbeat exports on a short interval** (CC's
  `OTEL_METRIC_EXPORT_INTERVAL`, recommended 10s in-sandbox per 29f.1
  §4) and keeps advancing while a turn is genuinely alive — a finer,
  earlier liveness signal than coarse event-stream timestamps.
- **Pipeline consequence:** the enrich stage must forward METRICS
  (not just spans) on a low-latency path, and the oyg `LivenessProbe`
  reads the heartbeat (last metric-emit timestamp for the run/session)
  rather than spans. The wall-clock backstop STAYS regardless — if the
  observability pipeline has an outage, the watchdog degrades to coarse
  event-stream detection, never to NO detection.

---

## 5. Grounding verdict — NO conflict (no halt)

The decided architecture is consistent with the shipped code and the
captured telemetry. Specifically confirmed:

- 29f.2 ships exactly decisions 1/2/8 and the decision-9 scrub
  primitive; it writes to a local span file, leaving the
  file→Honeycomb forwarding to the (unbuilt) enrich stage — consistent
  with the pinned pipeline.
- The captured telemetry's resource-attr poverty (`service.name` +
  `service.namespace` only) confirms the enrich stage's correlation
  job is real, not redundant.
- The oyg watchdog already carries the `LivenessProbe` extension point
  and explicitly defers to the 29f metrics-heartbeat — the consumer
  contract is pre-wired.
- No enrich-stage hard blocker found. The only verification items are
  inherited from 29f.1 (V2 beta availability, V3 `TRACEPARENT` honor,
  V4 flush-on-teardown) plus the §3.5 reflector-key wire-up caveat —
  none blocks building the enrich stage.

---

## 6. Recommended child-item decomposition

Numbered, with scope, repo, product-`.py`-or-config, and dependencies.
The CORE GAP (no existing child for the enrich/scrub stage) is **E1**.
Existing children mapped: **29f.1** = the CC native-export gap analysis
(research, DONE — `cc-otel-gap-analysis.md`); **29f.2** = the mechanical
loop-exit reflection stage (DONE on master); **29f.3** = in-sandbox CC
OTel enablement; **29f.4** = the out-of-band reflector.

| # | Child | Repo | Kind | Scope | Depends on |
|---|---|---|---|---|---|
| **E1** | **NEW — host-local enrich/scrub stage** | livespec-impl-beads | product `.py` (+ a shared `_otel_scrub` module lifting `_dispatcher_reflection._scrub`; service config) | Custom host-local OTLP processor: OTLP/HTTP receiver reachable from inside Fabro; tail of the dispatcher/reflection local span files; correlation-triple augmentation (§3.3); fail-closed credential scrub on every forwarded span (§3.4); batch + retry egress to Honeycomb (ingest-only key); fail-open toward pipeline, fail-closed toward credentials. Includes the metrics-heartbeat low-latency forward path (§4.4). | 29f.2 (span format + `_scrub` to lift), 29f.1 (env/key facts) |
| **E1a** | (optional split of E1) dispatcher LIVE dispatch/stage span emit | livespec-impl-beads | product `.py` | `JournalFile.append` dual-write → OTel SDK `BatchSpanProcessor` so `livespec.loop`/`livespec.dispatch`/`livespec.stage.*` spans are born live + correlated (today only post-hoc in the capture script). Can fold into E1 or be its own child. | E1 (or parallel) |
| **29f.3** | in-sandbox CC OTel enablement | livespec-impl-beads (+ fabro run-config overlay) | config (overlay env) + small `.py` for overlay assembly if needed | Set the §4 env in the sandbox via the run-config overlay; `OTEL_RESOURCE_ATTRIBUTES` carries `work.item.id` + `livespec.dispatch.id`; **OTLP endpoint points at E1 (host-local enrich stage), NOT Honeycomb directly**; content flags stay off; verify V2/V3/V4. | **E1** (endpoint target must exist), 29f.1 |
| **29f.4** | out-of-band LLM reflector | livespec-impl-beads | product `.py` | Async/sampled/time-boxed/isolated reflector reading ENRICHED telemetry from Honeycomb via MCP; dedup-first ledger filing (decision 6); lessons PROPOSAL (decision 7, human-ratified); `gen_ai.evaluation.result` verdict emit. | **E1** (enriched telemetry), 29f.3 (sandbox data flowing), Honeycomb MCP key |
| **oyg-OTEL** | oyg watchdog OTEL upgrade | livespec-impl-beads | product `.py` | Add a `LivenessProbe` impl reading the metrics-HEARTBEAT (§4.4) from the pipeline, feeding the existing `decide_stall`; wall-clock backstop STAYS. | **E1** (metrics-heartbeat forward path), oyg shipped |
| **e60** | dev-tooling analysis consumer | livespec-dev-tooling | product `.py` | Cross-repo analysis reading enriched Honeycomb telemetry via MCP. | **E1**, 29f.3 |

### Sequencing

```
   E1 (host-local enrich/scrub stage)         ← FIRST; the missing core child
      │  (E1a dispatcher live-span emit folds in or parallels)
      ▼
   29f.3 (sandbox OTLP → enrich stage)         ← depends on E1's endpoint existing
      │
      ├──▶ 29f.4 (out-of-band reflector)        ┐
      ├──▶ oyg-OTEL (watchdog heartbeat probe)  ├─ all three read the ENRICHED pipeline;
      └──▶ e60 (dev-tooling analysis consumer)  ┘  parallelizable once E1 + 29f.3 land
```

E1 is the critical-path long pole: nothing downstream can read enriched,
scrubbed, correlated telemetry until it exists, and 29f.3 cannot point
its sandbox endpoint anywhere until E1 exposes one. File E1 first.

---

## 7. Verification items (carried, none blocking)

- **V2/V3/V4** (from 29f.1): CC enhanced-telemetry beta availability;
  `-p`/SDK `TRACEPARENT` honor (gates structural host↔sandbox
  correlation vs attribute-join); flush-on-teardown tail loss.
- **Reflector key wire-up** (§3.5): confirm `HONEYCOMB_MCP_API_KEY_LIVESPEC`
  queries the livespec env via `mcp.honeycomb.io` once telemetry flows.
- **Heartbeat granularity** (§4.4): confirm CC's metrics export interval
  in-sandbox is fine enough for the oyg `LivenessProbe` to beat the
  coarse event-stream signal.
