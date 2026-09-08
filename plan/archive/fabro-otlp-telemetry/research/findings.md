# Fabro OTLP telemetry findings

## Scope and provenance

This research was consolidated on 2026-08-02. Current-state claims were checked
against:

- [fabro-sh/fabro PR #576](https://github.com/fabro-sh/fabro/pull/576), including
  the PR body and complete conversation returned by the GitHub forge.
- Bryan's
  [blocking-versus-async question](https://github.com/fabro-sh/fabro/pull/576#issuecomment-5038560029)
  from 2026-07-21.
- Bryan's later
  [OTLP-logs direction](https://github.com/fabro-sh/fabro/pull/576#issuecomment-5079036739)
  from 2026-07-25.
- The local
  [timestamped Quarry Markdown snapshot](quarry-otlp-logs-export-2026-08-02.md).
- OpenTelemetry Rust's versioned
  [stable batch log processor source](https://github.com/open-telemetry/opentelemetry-rust/blob/opentelemetry_sdk-0.32.0/opentelemetry-sdk/src/logs/batch_log_processor.rs#L74-L103),
  [0.32 feature definitions](https://github.com/open-telemetry/opentelemetry-rust/blob/opentelemetry_sdk-0.32.0/opentelemetry-sdk/Cargo.toml#L45-L60),
  [0.32 OTLP HTTP feature definitions](https://github.com/open-telemetry/opentelemetry-rust/blob/opentelemetry-otlp-0.32.0/opentelemetry-otlp/Cargo.toml#L70-L103),
  and
  [experimental async processor source](https://github.com/open-telemetry/opentelemetry-rust/blob/opentelemetry_sdk-0.32.0/opentelemetry-sdk/src/logs/log_processor_with_async_runtime.rs).
- The full materialized livespec ledger across all lifecycle statuses and the
  whole repository plan store. The absence search used copied source tokens:
  GitHub comment id `5079036739`, Quarry id
  `4c799d4a7e164723bc2f416ee06ff580`, `Quarry`, and combinations of
  `RunEvent` with `OTLP`.

The exact-token search found no durable record of Bryan's newer design before
this thread. The older tracing work was present in
`plan/archive/codex-factory-telemetry/`, but that plan was archived on
2026-07-19, before either Bryan comment.

## Forge state captured on 2026-08-02

PR #576 was open, non-draft, and unmerged. Its head was
`thewoolleyman:otlp-span-export` at `da277a4e5945e98827866fb407b7aa1d28a1d4d8`.
The submitted implementation exported existing developer `tracing` spans over
OTLP/HTTP and used `reqwest-blocking-client` with the SDK's stable batch span
processor.

The relevant conversation sequence was:

1. On 2026-07-21 Bryan agreed that OTLP export made sense and asked whether the
   exporter should be async because Fabro runs on Tokio.
2. On 2026-07-25 Bryan offered a more fundamental direction: be all-in on OTLP
   and initially export Fabro events as OTel logs, linking the Quarry design.
3. The maintainer replied that travel might delay a deeper response. The
   complete forge conversation contained no later technical confirmation as of
   the 2026-08-02 read.
4. On 2026-08-02 at 03:31:41 UTC, the maintainer posted the reviewed direction
   response as
   [comment 5154982522](https://github.com/fabro-sh/fabro/pull/576#issuecomment-5154982522).
   It offers to rewrite the PR around the corrected OTLP-logs design while
   explicitly holding the current branch unchanged pending Bryan's
   confirmation. The complete conversation contained no reply after that
   comment in the immediate post-publication forge read.

The absence statements are scoped to the complete PR #576 conversation returned
by the forge at the stated reads. They must be rechecked before being repeated
later.

## Ledger and plan reconciliation

`bd-ib-i4r` is the direct work item for the upstream Fabro exporter and PR
#576. Its title and description still describe the older `otel.rs` plus CLI
wiring and tracing-span transport.

`bd-ib-98c` carries the broader Codex-era factory-observability problem. It
names `bd-ib-i4r` as related enabling work, but it is not the formal ledger
parent of `bd-ib-i4r`.

`bd-ib-zjz3ie` is the new epic anchor for
`plan/fabro-otlp-telemetry/`. Its purpose is to preserve the new upstream
direction and coordinate the eventual reconciliation of the two older records.
No lifecycle dependency edge was added among these records because the present
relationship is contextual and coordinative, not a claim that one record's
closure is blocked on another.

## What the Quarry proposal gets right

The core move is strong: `RunEvent` is already Fabro's curated, typed domain
event vocabulary, whereas developer `tracing` output is intentionally unstable
and poorly suited to becoming an external telemetry contract.

The proposed boundary is coherent:

- Logs only in the first increment; metrics and traces are deferred.
- One eligible canonical event maps to one structured OTLP log record.
- Export is disabled unless an operator configures an endpoint.
- Envelope identifiers become bounded attributes; redacted properties remain
  in the body with a configurable size cap.
- A new `fabro-otel` foundation crate calls the OpenTelemetry Logs API
  directly, without `opentelemetry-appender-tracing` or
  `tracing-opentelemetry`.
- Existing `RunEventSink` fanout and `RunEventLogger` provide natural
  composition and keep workflow execution off the network path.
- Server and worker roots both receive sinks, with resolved configuration
  propagated to workers.
- Export errors are operational warnings and never run failures.
- The proposed tests cover mapping, configuration precedence, disabled mode,
  loopback transport, redaction, explicit per-variant disposition, worker
  propagation, and shutdown ordering.

This later direction should be treated as the candidate replacement for the
current PR, not as a small amendment to the existing tracing exporter.

## Required technical corrections

### Stable batching and the reqwest client

The Quarry dependency sketch enables:

```toml
opentelemetry_sdk = { version = "0.32", default-features = false, features = ["logs", "rt-tokio"] }
opentelemetry-otlp = { version = "0.32", default-features = false, features = [
    "logs", "http-proto", "http-json", "reqwest-client", "reqwest-rustls",
] }
```

That feature set does not select the experimental async log processor.
`rt-tokio` enables the shared experimental runtime infrastructure, while the
async log processor itself requires
`experimental_logs_batch_log_processor_with_async_runtime`.

OpenTelemetry Rust 0.32's stable `BatchLogProcessor` runs export work on a
dedicated background thread. Its own documentation says that the supported HTTP
choice is `reqwest-blocking-client`; ordinary async reqwest and hyper clients
are not supported on this path. The stable first-slice recommendation is
therefore:

```toml
opentelemetry_sdk = { version = "0.32", default-features = false, features = ["logs"] }
opentelemetry-otlp = { version = "0.32", default-features = false, features = [
    "logs", "http-proto", "http-json", "reqwest-blocking-client", "reqwest-rustls",
] }
```

This remains non-blocking from Fabro's event-emission path because enqueueing
hands the export to the processor's dedicated thread. If upstream prefers the
async reqwest exporter, the design must instead name and enable the experimental
async-runtime processor deliberately.

There is a second dependency correction: in `opentelemetry-otlp` 0.32,
`http-proto` and `http-json` both force-enable the SDK's `trace` and
`metrics` features. Therefore `default-features = false` does not produce the
strict logs-only dependency graph claimed by the Quarry sketch. The first slice
can remain logs-only in behavior and public surface, but the compiled dependency
surface still includes trace and metrics support while either HTTP encoding is
enabled.

The stable processor also warns that `shutdown()` can deadlock if invoked on a
Tokio current-thread runtime's main thread. A rewrite must preserve the Quarry
design's explicit flush ordering and validate the actual runtime/shutdown call
site, using a separate thread or `spawn_blocking` where required.

### Event scope

The Quarry goal says every canonical event is exported, but Decision 7 excludes
`TextDelta` and `ToolCallOutputDelta`. Durable prose and tests should use the
precise phrase “eligible, non-streaming canonical events.” The explicit
disposition test is the right mechanism: every new event variant must select a
severity or an intentional exclusion.

### Redaction parity

The mapping defines the OTLP body as the redacted `properties` structured
`AnyValue` map. The proposed `redacted_event_json` comparison serializes the
whole event envelope. Those artifacts cannot have literal byte parity while
remaining different shapes.

The meaningful invariant is semantic equality of the redacted property values
after normalization, plus separate assertions for the mapped envelope
attributes. Secret-bearing URLs and `ExecOutputTail` remain valuable fixtures.

## Policy and documentation cautions

The Quarry review deliberately chooses to pass resolved
`OTEL_EXPORTER_OTLP_HEADERS`, including an ingest credential, into worker
environment variables. Local sandbox commands, some MCP subprocesses, and
non-sandbox hooks can inherit worker environment. The proposal accepts this
because stronger cloud credentials already cross parts of the same boundary and
records an explicit deny-list follow-up. This is a conscious exposure decision,
not an accidental omission. The direction-confirmation reply should not reopen
it without new evidence, but implementation review must verify that behavior
matches the accepted decision.

Redaction is also narrower than data minimization. Exporting redacted event
properties can still export prompts, responses, patches, commands, and other
operator content that is not recognized as a credential. Because OTLP crosses
the process and often the operator's local trust boundary, public documentation
must describe what leaves Fabro rather than implying that “redacted” means
metadata-only.

The record mapping lists `fabro-cli` as a possible `service.name`, while the
wiring section says no CLI-local run execution exists. This is minor, but the
rewrite should either identify the CLI event source or omit that resource name
from the first slice.

## Coordination ruling

The maintainer is willing to rewrite PR #576 around the corrected logs design.
The reviewed response was posted as
[comment 5154982522](https://github.com/fabro-sh/fabro/pull/576#issuecomment-5154982522),
and its exact body remains preserved in
`plan/fabro-otlp-telemetry/pr-576-comment.md`. The existing branch must remain
unchanged until Bryan confirms that direction. The current action is to wait
for that confirmation or correction, then reconcile `bd-ib-i4r` and the
implementation direction against his ruling.
