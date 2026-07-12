# Handoff — codex-factory-telemetry

## What this thread is

Restore end-to-end factory observability for the **Codex era**. The
Honeycomb telemetry pipeline is Claude-Code-native and has been dark for
every run since ~2026-06-13 because the factory now drives work with
Codex (`@zed-industries/codex-acp@0.16.0`), which emits none of the
telemetry the pipeline captures. The receive/egress plane is intact and
armed on every dispatch; the gap is purely the **emitter**.

## Read-first chain (open these, in order, before acting)

1. `plan/codex-factory-telemetry/research/observability-gap.md` — the
   full reasoning: the evidence (dataset dark-dates), the mechanism (why
   Codex emits nothing), what is already intact and reusable, the three
   approach options, and the open questions. **This is the load-bearing
   context; do not proceed without it.**
2. `plan/codex-factory-telemetry/research/codex-otel-support.md` — the
   2026-07-12 **outcome** of the "can Codex emit OTel?" investigation
   (verdict `no-native-otel`; **Approach 2 selected**). Read before acting
   on any build step; it lists the ready steps + the receiver-protocol call.
3. `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_plan.py`
   — `cc_otel_overlay_env()` (the CC-only overlay),
   `DEFAULT_SANDBOX_OTEL_ENDPOINT` (`http://172.17.0.1:4318`),
   `CODEX_IMPLEMENTER_ADAPTER` (the Codex adapter pin).
4. `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_otel_receive.py`
   — the host OTLP receiver (port 4318, JSON-only today).

## Next action (exactly one)

**Groom the Approach-2 build steps into dependency-layered children of the
epic `bd-ib-98c`** — reconciling the EXISTING related items rather than
filing duplicates. The "can Codex emit OTel?" investigation is DONE
(2026-07-12): verdict `no-native-otel`, Approach 1 (config-only via
`OTEL_*`) FALSIFIED, **Approach 2 (fabro-side OTLP from the ACP handler)
selected**. See `research/codex-otel-support.md` for the full evidence +
the ready steps.

Reconcile with existing `bd-ib` items before filing anything new:
- **`bd-ib-i4r`** — "Upstream fabro PR: fabro-side OTLP export" — is the
  Approach-2 ENABLER (the fabro-side exporter, uncommitted on a stale
  `~/.worktrees/fabro/instrument-v0254` base, must be re-derived vs current
  main). Step 1 of Approach 2 rides it.
- **`livespec-impl-beads-zbl`** — "Multi-provider cost observability" —
  owns the token-cost fidelity the *native* follow-on would serve.
- **`bd-ib-v2u`** — cred-lifecycle instrumentation (related, distinct).

Do the grooming through the `groom` / `capture-work-item` consent seam
(maintainer owns the cut), NOT a raw bulk `bd` write. The one genuine
decision to surface: coarse-token-now (Approach 2, no external dep beyond
`bd-ib-i4r`) vs. also pursuing the native-codex fork path (richer per-turn
cost, but an upstream/fork dependency + the Statsig-egress override).

## Ledger status

**Epic anchor FILED: `bd-ib-98c`** — "Codex-era factory telemetry —
restore end-to-end factory observability for Codex-driven runs (emitter
gap)" (`bd-ib` tenant / `livespec-orch-beads-fabro`), filed 2026-07-12 by
the properly-wrapped driving session under the env wrapper. Its description
carries the verdict, Approach-2 decision, the ready build steps, and the
related-item cross-links (`bd-ib-i4r`, `livespec-impl-beads-zbl`,
`bd-ib-v2u`). The anchor was filed via a maintainer-consented direct `bd`
write; the **child** build steps still route through the `groom` /
`capture-work-item` consent seam (never a raw bulk write) — see Next action.

Not yet filed: the dependency-layered CHILD build steps (they need the
grooming pass that reconciles `bd-ib-i4r` — see Next action + the ready
steps in `research/codex-otel-support.md`).

## Coordination

Coordinate with the **`fabro-token-refresh`** plan thread: it is adding
OTLP export to fabro (upstream-worthy) to debug the >60-min expired-
token bug. Agree on receiver protocol (json vs protobuf), dataset/
`service.name` naming, and correlation attributes so both emitters land
coherently.

## Do NOT

- Do not implement inline in a planning session — FILE ripe work to the
  ledger; the Dispatcher / `drive` builds it factory-side.
- Do not let any emitter ship unredacted prompts / tool I/O / raw API
  bodies out of the sandbox (mirror the CC content-flags-off hygiene).
