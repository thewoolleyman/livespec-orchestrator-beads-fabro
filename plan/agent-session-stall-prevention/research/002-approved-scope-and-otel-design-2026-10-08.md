# Approved scope and OpenTelemetry design

The maintainer approved the five outcomes and mechanism order on 2026-10-08
(Europe/Berlin), adding, verbatim: "I approve, but the inventory any any metrics
should be published via opentelemetry to honeycomb where possible, consistent
with other otel in the livespec ecosystem.  Proceed with my approval autobomously".
The opening note remains the original evidence and session-derived proposal;
this note records the subsequent authorization and engineering decisions.
Status, carrier assignments and the next action remain on epic `bd-ib-jnpvh4`.

The additional plan outcome is: With telemetry configured, an operator can query
wait lifecycle events, inventory observations and their numeric measurements in
Honeycomb by repository, session and wait identity through the existing livespec
OpenTelemetry path, while unavailable telemetry leaves local waits bounded and
reports export degradation locally.

## Delivery boundary

The orchestrator plugin owns the host-session wait command, durable wait records,
read-only inventory, explicit acknowledgement, telemetry and turn-end check.
It observes gates through the installed worktree pack's existing `gate-status`
surface. It does not move or duplicate the gate runner, change factory watchdogs,
or prescribe blocking waits inside a factory agent turn.

The public command has `wait`, `inventory`, `ack` and `check` subcommands. Its
runtime-independent CLI ships in the plugin; existing planning and drive guidance
explains its use. This adds no new named planning operation or separate daemon.
The initial target kinds are detached gates and herdr agent panes. A missing
gate pack or herdr capability is a bounded, actionable unavailable result.

The overseer repository owns the operator alert. File that work directly in its
tenant, with dependencies on the inventory and its herdr lifecycle prerequisite.
There is no local implementation item pretending the factory can edit a sibling
repository. The plan retains responsibility for observing the operator outcome;
a referral alone cannot discharge it.

## Wait and inventory semantics

`wait` requires an explicit positive finite deadline budget. Arming freezes the
primary repository identity, session identity and concrete targets. A gate target
binds the gate-store root and run id. A pane binds the backend, server/socket
instance and generation, and pane identity. Rewritten pointer files, reused PIDs
or a restarted herdr server cannot silently select another target.

One monotonic deadline governs observation, subprocess/network timeouts and final
return. Probes are concurrent or independently bounded so a slow first target
cannot hide a finished sibling. The observation interval is at most one second;
every operation consumes the remaining deadline budget. Expiry interrupts an
in-progress probe, rather than waiting for a per-probe timeout beyond the deadline.
Clock adjustment cannot extend the budget. Cancelling a waiter leaves targets alive.

Only the gate's `RUNNING` and the pane's `working` mean continue waiting. Known
terminal states preserve their verdict; gone, unreadable, malformed and unknown
states end the wait with distinct diagnostic outcomes, never fabricated success.
The result identifies the triggering target and gives each target's latest state,
observation time and freshness. A deadline result identifies unfinished targets
and distinguishes a last-known running observation from an unavailable fresh probe.
The command's exit category is separate from each gate's preserved exit code.

Arming atomically registers the wait beneath the primary checkout's ignored
`tmp/session-waits/` store before starting the blocking phase. The versioned record
includes stable wait/session/target identities, wall-clock audit times, deadline,
waiter PID plus process generation, observation sequence, latest observations,
return reason and acknowledgement. Concurrent updates cannot lose another wait.
Inventory freshly probes registered targets and verifies waiter identity; corrupt
or unsupported records and failed reads are visible, never an empty healthy list.

The waiter records `return-ready` before returning. This proves result production,
not harness delivery. Only `ack` by the owning session records consumption.
Inventory reports ended-but-unacknowledged, running-without-waiter and overdue
waits. A session's acknowledgement is a protocol fact, not proof of cognition.
Inventory publication includes an observation id and time, so Honeycomb snapshots
cannot masquerade as a current authoritative census. Retain unacknowledged records
until explicit disposition; bound acknowledged history and export queues.

## Ecosystem telemetry evidence and design

Read on this checkout and its sibling on 2026-10-08:

- `loop-reflection-gate/telemetry-pipeline-architecture.md` records the host-local
  enrichment/scrub stage followed by Honeycomb, replacing an earlier direct route.
- `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_otel_enrich_export.py`
  implements OTLP/HTTP-JSON trace export and `service.namespace=livespec-family`.
- The sibling's `overseer/_supervisor_otel.py` and `_supervisor_otel_async.py`
  supply environment-configured, bounded asynchronous event export.
- `livespec-overseer/plan/archive/overseerd-observability/research/` records
  the traces-over-logs decision and local visibility of export failures.
- `livespec-overseer/plan/archive/caam-loop-otel-instrumentation/research/telemetry-convention-and-hook-points.md`
  records the shared convention and separate repository emission modules.
- Closed items `bd-ib-nslh` and `bd-ib-dorc` document attributes silently lost at
  the receiver allowlist. Emitter-only proof is insufficient.

Use the existing orchestrator host-local OTLP ingestion/enrichment/scrub route,
including its configuration and credential boundary. Inspect its installed
endpoint during host proof rather than copying an old default. No new ingest key,
direct-to-Honeycomb bypass or exporter framework is needed. Reuse the existing
repository exporter seams, and the overseer's own seam for its alert event.

Use `service.name=livespec-dispatcher`, `service.namespace=livespec-family`,
scope `livespec.orchestrator.session_wait` with a schema version, and a closed
event catalog: `session.wait.armed`, `session.wait.observed`,
`session.wait.returned`, `session.wait.acknowledged`, `session.wait.inventory`,
and `session.wait.attention`. Emit arming immediately: a span exported only when
the wait ends would hide the very stall being measured.

Each event carries allowlisted scalar fields for repository, `session.id`,
`wait.id`, target kind/opaque identity, observation id and sequence, observed
state, return reason, acknowledgement and waiter liveness. Carry `work.item.id`,
`dispatch.id` and `fabro.run_id` only when known; never invent a parent trace.
Reuse an available trace context, otherwise start a stable wait trace with linked
snapshot observations. Resolve existing key spellings against `_otel_scrub.py`
before implementation and keep producer, scrubber and consumer consistent.

Measurements include elapsed seconds, remaining budget, observation age, overdue
seconds, target count, active and unacknowledged wait counts, and export queue
drop/rejection counts. Initially publish these as typed numeric OTLP span fields,
matching the fleet's event-derived count/distribution queries. The inventory
command publishes a timestamped summary and one observation per wait, including
an explicit zero-count summary for an empty inventory. Changes emit immediately;
unchanged state is sampled at most once per minute, with per-event sequence and
snapshot identity allowing consumers to avoid double counting.

Native OTLP metric instruments are deferred until the existing receiver and
Honeycomb metric-dataset route are demonstrated; this defers a second wire signal,
not publication of any collected measurement. If introduced, aggregate dimensions
are bounded (repository, target kind, outcome); session and wait identifiers stay
on trace events. Record any unsupported field/signal and why, with its trace
representation, rather than silently dropping it under "where possible".

Only curated fields cross the boundary: no command text, prompts, transcripts,
environment dumps, credentials or credential-bearing paths/URLs. Queue limits,
transport timeouts, retries and shutdown cannot extend the wait's deadline.
Unconfigured telemetry leaves an explicit local-only state. A configured export
failure, partial rejection or overflow is visible locally with bounded reporting;
an exporter failure must not recursively export its own failure forever.

## Turn-end and operator detection

The common `check` command reports inventory mismatches before a session parks.
Claude's existing stop-hook surface may invoke it; Codex and pi planning/drive
guidance invoke the same command explicitly. Do not claim automatic stop-hook
coverage for a runtime without exercising its actual hook surface. A bounded wait
and the external overseer remain required when automatic hooks are unavailable.

The existing overseer loop consumes the local inventory and surfaces an ended,
unacknowledged target on its watched attention/status surface within 60 seconds
of target completion while it is monitoring that registered session. Waiter process
liveness alone cannot suppress the condition. Dead waiter, overdue deadline,
unavailable inventory and stale observations remain distinct conditions. Recovery
and acknowledgement clear the condition; stable identity and age bands prevent
per-tick flooding. Publish the alert through the overseer's existing OTel seam.
Honeycomb availability is not part of the alert's control path.

Untracked sessions are explicitly outside this daemon guarantee; installed usage
must make that coverage visible. A live herdr acceptance exercise must establish
actual adoption and observation, not infer support from the mere presence of its
new transport. `overseer-vgf6d3` is now closed, while `overseer-lifebq` still owns
released interactive lifecycle proof. Keep the latter prerequisite explicit.

## Ordered implementation seams and proof

First deliver bounded gate waits, durable inventory and usage guidance. Add pane
observations on that substrate. Publish all inventory and measurements through
OTel on the same substrate. Then add the turn-end integration and the sibling
overseer consumer. These are implementation seams, not a duplicate status queue;
ids, dependencies, admission and carriers live only in the ledger.

Ratify the local contract and scenarios through the spec lifecycle before any
implementation admission. File scoped children with explicit manual admission
until that prerequisite lands; migrate each reference to its governing scenario
at that point. The overseer referral must route its daemon-behavior contract in
that repository before implementation; this proposal does not govern its internals.

Capture and independently replay released-build proofs: one of several real
detached gates ends first; herdr reaches `done`, disappears and changes server
generation; a probe hangs across the deadline; the waiter dies before delivering
a result; the session omits acknowledgement; and a tracked parked session alerts
within 60 seconds. Positive and negative controls must distinguish each outcome.
Use isolated owned targets and leave unrelated panes and gates untouched.

For telemetry, query Honeycomb for a unique proof session/wait and show the armed,
returned, inventory and acknowledgement rows, numeric field types, observation
identity, and an operator alert. An accepted HTTP request or local export file is
not delivery proof. Inject endpoint outage, partial rejection, queue saturation
and a blocked exporter; verify bounded local return and visible degradation.
Proof must name the released build, configured route, dataset, query/time window
and fetched rows without credential values.

## Explicit deferrals

Fabro-run and PR-check adapters wait until the first two target kinds are proven;
reconsider them in this plan's follow-on scoping. Shell-loop refusal hooks wait
for measured bypass of the shipped primitive and demonstrated false-positive
controls. A recurring model heartbeat waits for evidence that bounded waits plus
the overseer still leave a coverage hole. Reconsider both after released host
proof, retaining them as named deferrals in the epic scope event.

Gate zombie/store-location defects remain with `livespec-dev-tooling-zh4c` and
`livespec-dev-tooling-3bqy`. A deadline bounds their harm without claiming to fix
them. The unexplained harness timeout remains research evidence only: this design
owns its deadline and depends on no assumed harness timeout guarantee.
