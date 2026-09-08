# 010 — Cross-host OTLP endpoint is the real root cause (CC is not the problem)

**Date:** 2026-09-06. **Supersedes the causal framing of 007 and the
CC-side reading it invited.** 008/009 (heartbeat key mismatch; heartbeat is
liveness-not-progress) remain valid but are *downstream* of this: even a
correctly-keyed, progress-bearing beat never reaches the watchdog probe for a
factory run, because the beat is dropped at the source.

This note is the authoritative filesystem record; the blow-by-blow measurements
and the retraction of the earlier "CC-in-sandbox-export-side / outward-facing"
conclusion are in the `bd-ib-25fjk2` ledger comments (2026-09-06).

## The claim that was wrong

Earlier this plan concluded the metrics/heartbeat pipeline was dark because
Claude Code stopped exporting OTLP metrics (an outward-facing regression). That
is **false**, proven by direct experiment.

## What was measured (reproducible)

1. **CC still exports metrics.** Raw TCP capture of current CC (2.1.263) with
   this repo's exact sandbox OTel env shows `POST /v1/metrics` (UA
   `OTel-OTLP-Exporter-JavaScript/0.208.0`) carrying `livespec.dispatch.id` +
   `work.item.id`; metrics `claude_code.token.usage`/`cost.usage`/
   `session.count`/`active_time.total`.
2. **Our parser + receiver + sink work end-to-end.** The real `OtelReceiver`
   fed by a live current CC wrote a correct beat (`{"e2edispatch": <ts>}`).
3. **The "fleet-wide ~08-30 cutoff" is not real.** Per-repo *local* sink freeze
   dates are staggered (08-09..08-30), each = that repo's last *local* dispatch.
   The "traces flow while metrics dark" evidence was a wrong-population error:
   those `*-spans.jsonl` are the dispatcher's OWN spans
   (`service.name=livespec-dispatcher`), not the sandbox's OTLP.
4. **The live factory sandbox is pointed at a dead port.** A live this-repo
   factory sandbox (item `bd-ib-7hta4l`, on hp) has
   `OTEL_EXPORTER_OTLP_ENDPOINT=http://172.17.0.1:45791`. On hp **nothing listens
   on `:45791`**; the only receiver is the persistent `otel-receiver.service`
   daemon on `:4318`, which the sandbox is not using. The sandbox *can* reach the
   daemon (`curl 172.17.0.1:4318` → 200) but is not aimed there. Beats are
   refused at the source. No `dispatcher.py loop` runs on hp.

## Root cause (exact line)

`commands/_dispatcher_otel_wiring.py` → `_project_owned_receiver_endpoint`:

```python
os.environ[SANDBOX_OTEL_ENDPOINT_ENV_VAR] = f"http://{server.config.host}:{server.bound_port}"
```

The dispatcher arms a receiver (`ensure_receiver_started`; falls back to an
**ephemeral** port via `_ensure_fallback_otel_receiver(port=0)` when the default
`:4318` is unavailable) and then **unconditionally** stamps the sandbox endpoint
as `http://{server.config.host}:{server.bound_port}`.

- `server.config.host` is the literal docker-bridge IP `172.17.0.1`, which inside
  the sandbox means **the sandbox's own host**.
- `server.bound_port` is the port the receiver bound **on the dispatcher host**.

This is correct only when sandbox-host == dispatcher-host (a *local* dispatch).
For a remote factory dispatch (`default_factory: hp`; dispatcher on vps) the
sandbox posts to *its own* host (hp) at a port only bound on vps → refused.
Because the assignment is unconditional, a static
`LIVESPEC_SANDBOX_OTEL_ENDPOINT` override cannot mitigate it — **the fix must be
code.**

## This is a known class

- `bd-ib-jb7rzr.10` (closed) documents the identical cross-host mechanism for the
  `run_turn`-absent guard (~59 false criticals across 3 hp-default repos). It
  fixed the guard to *tolerate* cross-host absence.
- `bd-ib-jb7rzr.5` (closed): host-global marker fix for the same receiver.
- `bd-ib-dg20` (open): "a completed dispatch delivers ZERO Claude-Code OTel rows
  silently" — the same host-local-receiver topology.
- `fix-honeycomb-telemetry-holes` (`bd-ib-rdbtzo` / `bd-ib-jb7rzr`, closed) is
  prior art that fixed the run_turn guard + built the dead-man trigger; it did
  **not** fix this heartbeat endpoint-vs-host mismatch.

The watchdog need is the *opposite* of the run_turn guard's: it must actually
**read** the beat, which for a factory run is produced on the factory host.

## Fix shape (two halves)

1. **Write half — stop aiming the sandbox at a dispatcher-host port.** For a
   remote factory dispatch, do not stamp a dispatcher-host-armed ephemeral
   endpoint. Point the sandbox at the *factory host's* co-located receiver — the
   persistent `otel-receiver.service` on `:4318` already exists for exactly this.
   (Also: do not bother arming a local receiver for a remote factory run; it is
   unreachable.)
2. **Read half — get the factory-host beats to the probe.** The watchdog probe
   runs in the dispatcher process (vps) and reads `heartbeat_path(args, repo)`.
   For factory runs the beats live on the factory host. Options: run the
   liveness collector/probe on the factory host; or replicate/ship the
   factory-host heartbeat sink to the dispatcher host; or have the probe query
   the factory host over the tailnet.

## Open sub-question

Why is hp's `otel-receiver.service` daemon sink itself stale (~02:00 on
2026-09-06) while sandboxes run? Because live sandboxes are aimed at `:45791`
(the write-half bug), not the `:4318` daemon — so even the co-located daemon is
bypassed. Confirm on the next live hp dispatch.

## Blast radius / discipline

`_dispatcher_otel_wiring.py` is **shared plugin code**; any fix must be verified
correct for every `default_factory: hp` repo (this one, `livespec-console-beads-fabro`,
`livespec-overseer`), matching the `bd-ib-jb7rzr` cross-repo discipline. The cut
(`bd-ib-25fjk2` + Child B `bd-ib-q5wxkh`) is a maintainer grooming decision.
