---
topic: agent-session-stall-prevention
author: codex
created_at: 2026-10-07T23:01:55Z
---

## Proposal: bounded-session-waits-with-honeycomb-observability

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Give host sessions a bounded first-event wait and acknowledged inventory, publish its observations and numeric measurements through livespec OpenTelemetry to Honeycomb, and expose local mismatches independently of telemetry availability.

### Motivation

The approved plan bd-ib-jnpvh4 measured multi-hour silent stalls from serial gate waiters and an idle-only pane loop. The maintainer approved all five outcomes and added inventory and metrics publication to Honeycomb via ecosystem OpenTelemetry.

### Proposed Changes

Add a host-session support contract under the new contracts.md H2 "Bounded session waits and observable inventory", extend spec.md Scope boundary to include this host tooling, and state in constraints.md Process boundaries that these blocking waits are host-session operations and MUST NOT be prescribed inside factory agent turns. This adds a public session-wait CLI with wait, inventory, ack and check subcommands, not an extra named planning skill or daemon.

The wait subcommand MUST require a positive finite explicit deadline budget, bind immutable repository/session/target identities at arm time, and return on the first observed target outside its still-running predicate or on deadline expiry. Detached gate RUNNING and herdr working are the only still-running states. Other states MUST end the wait with the actual verdict or a distinct gone/unavailable/unknown outcome; diagnostic uncertainty MUST NOT become success. Gate identity includes the primary gate-store root and run id; pane identity includes backend, server/socket instance and process generation, and pane id. Retargeting via a rewritten pointer or reused identity MUST be refused. Cancelling a waiter MUST leave the target untouched.

All observations, subprocesses, transport operations and final return MUST share one monotonic deadline, including cancellation of a hung probe at expiry. Observation cadence MUST be no slower than one second while budget remains, and a slow target MUST NOT serialize observation of other targets. The result MUST identify the triggering target, each target's last observed state and freshness, and unfinished targets at expiry. Command outcome and a target's exit code MUST remain separate, both visible. A stale running observation MUST be labeled with its timestamp rather than asserted current.

Arming MUST atomically register a schema-versioned wait beneath the primary repository's ignored tmp/session-waits store before blocking. Records MUST hold session/wait identities, frozen targets, audit/deadline times, waiter process generation, observation sequence, return-ready state and acknowledgement. Concurrent writers MUST preserve each other's records. Inventory MUST re-observe targets and waiter generations, report ended-but-unacknowledged, running-without-waiter and overdue records, and expose corrupt, unsupported or unreadable records as unavailable. Unacknowledged records MUST survive session and waiter exit until explicit disposition; acknowledged retention and export queues MUST be bounded. The waiter's return-ready record proves only result production. Only an explicit ack by its owning session MUST mark the result consumed; an exporter success or process exit MUST NOT do so.

The check subcommand MUST expose those same mismatches before turn end. Existing host planning/drive guidance MUST use the shipped command rather than hand-written serial or single-status wait loops and MUST derive monitoring claims from inventory. Automatic stop integration MUST be claimed only for a runtime whose installed hook surface is exercised; where unavailable, guidance MUST explicitly invoke check and disclose that limit. Factory execution guidance MUST preserve the no-blocking-wait constraint.

When the existing telemetry route is configured, arming, observation changes, return, acknowledgement and inventory snapshots MUST publish curated OTLP/HTTP-JSON trace events through the existing host-local enrichment/scrub and Honeycomb path. Resource service.name MUST be livespec-dispatcher and service.namespace MUST be livespec-family; scope MUST be livespec.orchestrator.session_wait with a version. The closed catalog is session.wait.armed, session.wait.observed, session.wait.returned, session.wait.acknowledged and session.wait.inventory. Arming MUST emit before termination. Events MUST preserve allowlisted repository/session/wait identity, opaque target identity and kind, snapshot/observation identity and sequence, observed state, return reason, acknowledgement and waiter liveness. Existing work.item.id, dispatch.id and fabro.run_id MUST be populated only when known. Context MUST use an existing trace parent when present and otherwise a stable new wait trace.

Elapsed seconds, remaining budget, observation age, overdue seconds, target count, active/unacknowledged counts and export drop/rejection counts MUST be exported as typed numeric fields. An inventory invocation MUST publish its summary plus per-wait observations, including an explicit zero-count summary. Unchanged observation export MUST be rate-limited to at most once per minute; lifecycle changes MUST remain distinguishable immediately. Snapshot time and identity MUST keep repeated observations distinguishable from new waits. These trace measurements satisfy the initial metrics publication contract; a native OTLP metrics signal MAY be added only through a demonstrated ecosystem metrics route with bounded aggregate dimensions. Any unsupported publication MUST have a documented reason and equivalent trace representation where possible.

Only curated allowlisted fields MUST leave the host; raw commands, prompts, transcripts, environment values, secrets and credential-bearing paths/URLs MUST NOT be emitted. Producer, receiver allowlist and consumer MUST agree on the field vocabulary. Telemetry MUST use bounded asynchronous work and MUST NOT extend the wait deadline or suppress local results/alerts. Absent configuration MUST be visible as local-only; configured transport errors, partial rejection and queue overflow MUST be visible locally with bounded, non-recursive reporting. Honeycomb data MUST be labeled as timestamped observations, never as authoritative live control state.

The inventory contract MUST be consumable read-only by the existing overseer. The sibling owns the daemon alert and its own specification; this repository MUST NOT add a second daemon or copy its supervision internals. The plan requires its coordinated alert to surface a completed unacknowledged wait for a monitored parked session within 60 seconds, including a live but ineffective waiter, and to remain locally effective during telemetry outage. Untracked-session coverage MUST be disclosed. This outcome remains a plan-level proof obligation until the sibling implementation is released and observed.

Add scenarios.md headings (assign the next free scenario numbers during revise) with these exact behavioral titles and Given/When/Then examples:

- "The first completed gate wakes a bounded multi-target wait": Given one long-running gate, a later-listed gate that fails first, and a frozen pointer to a third gate, When the pointer is overwritten and the second gate ends, Then the result names that second gate and its exit code before the first ends and retains the third gate's original identity.
- "A pane wait ends on non-working, missing and uncertain states": Given a qualified herdr pane, When it becomes done, blocked, idle or unknown, disappears, becomes unreadable or its server generation changes, Then wait returns a distinct observed/diagnostic result and never continues waiting solely for idle.
- "The shared deadline bounds stalled probes and telemetry": Given a missing/invalid deadline, Then arming is refused; Given a valid deadline, a hung first probe, a finished sibling and a blocked exporter, When observations run, Then the sibling remains observable and the wait returns by its deadline with freshness-aware states while targets stay alive after waiter cancellation.
- "Inventory distinguishes produced and acknowledged wake-ups": Given concurrent armed waits and one killed or reused waiter process, When inventory observes a completed target, Then it reports the completion and missing acknowledgement; When the owner acknowledges it, Then the mismatch clears; corrupt or unsupported records are unavailable, and empty inventory emits an explicit zero summary.
- "The host turn-end check exposes outstanding wait mismatches": Given an ended unacknowledged target, When the installed host check runs before parking, Then the mismatch is surfaced; automatic runtime-hook support is demonstrated only on its real installed surface, and factory agent guidance continues to avoid blocking host waits.
- "Wait inventory and measurements arrive in Honeycomb without controlling liveness": Given configured existing host-local export and a unique proof wait/session, When arming, observing, returning, inventory and acknowledgement occur, Then Honeycomb queries retrieve their identity-linked events and typed numeric fields after scrubbing; Given exporter outage, partial rejection or overflow, Then local results remain deadline-bounded and degradation is visible; unconfigured export is explicitly local-only.

Revise MUST co-edit tests/heading-coverage.json for every new H2 and scenario, linking a real exercising test or an owned non-empty TODO reason until implementation lands. The implementation children must update their generic filing references to the ratified governing scenarios before admission. This proposal defers native metric instruments, additional target adapters, shell-loop refusal hooks and recurring model heartbeats; numeric trace publication, the two initial target kinds and local boundedness remain required.
