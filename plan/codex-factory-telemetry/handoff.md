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

## Grooming analysis — scoped 2026-07-13 (item 4a)

The item-3 prepare-step timing wrapper (`livespec-step-timer`) is DONE + accepted
live (see the sibling `livespec` plan thread `plan/fabro-ci-image-factoring/`). This
session then scoped item 4a's Approach-2 spine against the ACTUAL code:

- **Step 1 (wire format) RESOLVED — `http/json`.** The stale fabro exporter
  `~/.worktrees/fabro/instrument-v0254/lib/crates/fabro-cli/src/otel.rs` DEFAULTS to
  `http/json` (deliberately built to match this JSON-only receiver) and honors
  `OTEL_EXPORTER_OTLP_PROTOCOL`. Confirmed by reading the code — no live POST capture
  needed.
- **Step 2 (teach `_otel_receive.py` protobuf) DROPPED — not needed.** The earlier
  receiver-protocol note SPECULATED protobuf (Rust default); the actual exporter emits
  JSON, which the receiver already handles.
- **Re-derivation target: current fabro main is `0.289.0-nightly.0`** (stale fork is
  v0.254.0, ~35 versions behind; `otel.rs` is ~105 lines of clean `opentelemetry-otlp`
  0.30 Rust that should re-derive cleanly, like fabro PR #568 did).

Proposed tiered cut (children of `bd-ib-98c`, PENDING the consent seam — NOT yet filed):
- **`bd-ib-i4r` (existing, reconcile):** the fabro OTLP TRANSPORT (`otel.rs` re-derived +
  `main`/`logging` wiring, `http/json`, `service.name=fabro`). Shared enabler for BOTH the
  cred-lifecycle spans (`bd-ib-v2u`) and item 4a. OUTWARD-FACING upstream Fabro PR.
- **NEW child — fabro ACP node/turn span instrumentation (steps 3+4):** `tracing` spans
  in `fabro-workflow/src/handler/llm/acp.rs` (one span per node + child spans per ACP
  turn/tool-call), correlation triple via `OTEL_RESOURCE_ATTRIBUTES`, map
  `UsageUpdate`/`TurnComplete` → span fields. Rides `bd-ib-i4r`. OUTWARD-FACING.
- **NEW child — receiver-side dataset-mapping + scrub (step 5, OURS/factory-safe):** add
  `service.name=fabro` → dataset in `_otel_enrich.py`'s `honeycomb_dataset_for`;
  content-redaction in `_otel_scrub.py` (CC content-flags-off hygiene). Depends on the
  fabro emitter's shape.
- **`livespec-impl-beads-zbl` (existing):** native-codex token/cost fidelity (steps 6–7)
  — BLOCKED / NO-FORK (maintainer-declared 2026-07-13).

HARD GATE: item 4a's build is fully gated on OUTWARD-FACING upstream Fabro work (the
exporter + ACP instrumentation, coordinated with the `fabro-token-refresh` thread). No
part is autonomously buildable-and-live-acceptable until that lands. Surface the exporter
re-derivation + upstream-PR decision to the maintainer before opening anything.

## Review-gate telemetry attributes to emit — added 2026-07-14

Surfaced during the autonomous-mode acceptance-model redesign: we needed to
know **how often the factory ships a PR despite the in-factory `review` node
never approving** (the review↔`review_fix` loop hits its 2-round cap and the
run "ships on cap" — falls through to `pr` with the reviewer still saying
`fix`). That ship-on-cap rate is the deciding input for whether making the
review a hard/escalating gate would stall the factory.

**It is NOT answerable from Honeycomb today.** The Honeycomb factory telemetry
instruments only the outermost envelope (`fabro.ImplementWorkItem` with
`fabro.status` = succeeded/failed) plus host dispatcher stages — and that
`fabro.*`/`dispatcher.*` stream froze 2026-06-14. The Fabro workflow's internal
graph nodes (`implement`, `janitor`, `review`, `review_fix`, `pr`) emit
**nothing**, so no review verdict, fix-round count, or ship-on-cap decision is
captured. (This session mines the answer from the Fabro run logs instead —
`fabro events`/`logs`/`inspect` + the server log — since the data lives there.)

**Concrete fields to add** — these belong on the existing NEW child *"fabro ACP
node/turn span instrumentation (steps 3+4)"* above, emitted as span attributes
on the `review`/`pr` nodes (or attached to `fabro.ImplementWorkItem`):

- `review.verdict` — the review node's routing verdict on its final visit
  (`approve` | `fix`).
- `review.fix_rounds` — integer count of `review_fix` rounds taken.
- `review.hit_cap` — bool: the review↔review_fix cap was reached.
- `pr.shipped_on_cap` — bool: a PR was opened while the reviewer still said
  `fix` (the ship-on-cap fall-through).

With these four, the ship-on-cap frequency (and its trend, per work-item and
over time) is a direct Honeycomb query rather than a manual Fabro-log dig.

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
