---
topic: autonomous-mode-arming-and-audit-contract
author: claude-opus-4-8
created_at: 2026-07-10T00:00:01Z
---

## Proposal: Publish the autonomous-mode arming and per-decision audit contract

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

This proposal freezes the PUBLISHED surface the Control-Plane console
(`livespec-console-beads-fabro`) builds against to arm/disarm autonomous mode and
to read per-decision audit — the contract-first deliverable (overall plan I1)
that unblocks console step C3. It resolves the persistence-model seam (overall
plan §6.1) into three pins: (a) `dispatcher.autonomous_mode` is the SINGLE
persistent permission and this plugin's published arming surface, which the
console sets — the console's own duplicate persistence block is redundant and is
dropped/derived on the console side; (b) the loop launcher is the console's
existing factory-drain path, which reads the permission and passes the per-run
flag; (c) the per-run `--mode autonomous` opt-in rides the Dispatcher `loop`
subcommand, NOT `drive` — correcting the v032 wording, which is contradicted by
both the shipped `drive` surface and the shipped code. It also frames the
existing Dispatcher journal as the published per-decision audit surface the
console reads. It changes no `## ` (H2) heading, so no
`tests/heading-coverage.json` co-edit is required.

### Motivation

This is deliverable (2) of orchestrator plan step O1
(`livespec-orchestrator-beads-fabro/plan/autonomous-mode/design.md` §3; the
overall plan `livespec/plan/autonomous-mode/design.md` §6.1). The console spec
(`livespec-console-beads-fabro/SPECIFICATION/contracts.md` §"Autonomous Mode",
v016) already says the console issues `factory.autonomous_mode_enable/disable_requested`
"to the orchestrator plane, through that plane's published command surface, to
turn the orchestrator's own autonomous mode on or off" — but the orchestrator
spec never named that surface. It ALSO persists its own
`livespec-console-beads-fabro.autonomous_mode.enabled` block in the same
`.livespec.jsonc`, so two persistent autonomous-mode booleans would coexist. This
proposal designates the orchestrator's `dispatcher.autonomous_mode` key the
single persistent permission and the published arming surface, resolving the
seam; the console-side change (dropping/deriving its own block) is console step
C1's concern and is flagged, not made, here.

First-hand evidence for pin (c), verified against `origin/master` (release
0.13.12):

- `contracts.md` §"`drive`" CLI surface is `drive [--repo <path>] --action
  <action-id> [--json]` — there is NO `--mode` flag on `drive`; and §"`drive`"
  states `drive` "invokes the existing Dispatcher/Fabro loop with `--mode shadow
  --budget 1 --parallel 1 --item <work-item-id> --json`" (mode hardcoded to
  `shadow`).
- Shipped code agrees: `commands/drive.py` `_build_parser()` exposes only
  `--repo` / `--action` / `--json` (no `--mode`), and its `build_dispatcher_argv`
  hardcodes `--mode shadow`; the `--mode {shadow,autonomous}` argument is added
  ONLY to the dispatcher `loop` subparser (`commands/dispatcher.py:2594`), and
  `dispatcher.py:1369` reads it purely as a queue-scope switch today.

So the mode-bearing entry point is the Dispatcher `loop` subcommand — the path
that drains the ready queue, which is what an unattended autonomous run does. A
full autonomous run is inherently a `loop`, not a single `drive --action`. The
per-invocation-opt-in and never-persist rules governing the ARMED MODE are
unchanged; only the surface name is corrected and the persistent-permission
role of the config key is made explicit.

The recommended realization treats the `.livespec.jsonc` config key itself as
the published arming surface (declarative, shared config the console's
Configuration context already manages), which adds no new orchestrator command —
consistent with "prefer primitives over new artifacts." A strictly
command-mediated write (a new `drive`-grammar arming action) is a possible
alternative if the console contract's "published command surface" wording is read
to require a runtime command; that is a cross-repo choice flagged for the driver
/ maintainer, not made here. The impl follow-up is the existing O2 engine item
`bd-ib-82a`; this proposal files no new work-item.

### Proposed Changes

All target text below is quoted verbatim from the live spec at `origin/master`
(v032, release 0.13.12). Six edits across three files; no `## ` (H2) heading is
added, changed, or removed. This proposal is DISJOINT from its sibling
`autonomous-mode-irreducible-human-touchpoints`: where both touch `spec.md`
§"Full autonomous mode", `contracts.md` §"Full autonomous mode", and
`scenarios.md` they target different, non-overlapping verbatim strings (this
proposal's Scenarios 33/37 vs the sibling's Scenario 36), so the two may be
revised in either order.

**A. `SPECIFICATION/spec.md` §"Full autonomous mode" — correct the wire-surface
pointer sentence.** Replace the verbatim paragraph:

> The wire surface (the `dispatcher.autonomous_mode` config key, the
> `drive --mode autonomous` opt-in, and the per-decision audit
> record) is specified in `contracts.md` §"Full autonomous mode"; the
> safety rails are in `constraints.md` §"Full autonomous mode constraints".

with:

> The wire surface (the persistent `dispatcher.autonomous_mode` permission key,
> the per-run `--mode autonomous` opt-in on the Dispatcher `loop` subcommand,
> and the per-decision audit record) is specified in `contracts.md` §"Full
> autonomous mode"; the safety rails are in `constraints.md` §"Full autonomous
> mode constraints".

**B. `SPECIFICATION/contracts.md` §"Arming full autonomous mode" — replace the
whole subsection body with the two-factor arming contract (pins a, b, c).**
Replace the verbatim block:

> ### Arming full autonomous mode
>
> - **Config key.** `livespec-orchestrator-beads-fabro.dispatcher.autonomous_mode`
>   in the consumer project's `.livespec.jsonc`, sibling to
>   `dispatcher.wip_cap` (§"`compat` block"), a boolean that MUST default to
>   `false`.
> - **Opt-in flag.** The run path MUST require an explicit opt-in:
>   `drive --mode autonomous` (alongside the existing
>   `--mode shadow`). Enabling the mode — whether via the config key or the
>   flag — is a dangerous action and MUST be surfaced as such; it MUST NOT
>   be inferred from context and MUST NOT persist beyond the current
>   invocation.

with:

> ### Arming full autonomous mode
>
> Arming is TWO-FACTOR: a persistent permission plus a per-run flag. The
> permission is durable operator intent; the armed MODE is per-invocation and
> never persists.
>
> - **Persistent permission (config key).**
>   `livespec-orchestrator-beads-fabro.dispatcher.autonomous_mode` in the
>   consumer project's `.livespec.jsonc`, sibling to `dispatcher.wip_cap`
>   (§"`compat` block"), a boolean that MUST default to `false`. This key is the
>   SINGLE persistent record of the operator's intent to allow unattended
>   autonomous runs for this repo, and it is this plugin's PUBLISHED arming
>   surface: the Control-Plane console arms and disarms autonomous mode by
>   setting this key (the console's `factory.autonomous_mode_enable_requested` /
>   `factory.autonomous_mode_disable_requested` commands map to writing it). It
>   is declarative, shared config the console MAY set directly; the plugin never
>   reaches into the console and the console never owns this plane's decision
>   semantics — it only flips the permission this plane's own engine honors. The
>   key persisting is correct BY DESIGN: "MUST NOT persist beyond the current
>   invocation" below governs the armed MODE, not this permission. Any duplicate
>   persistent autonomous-mode preference in the same `.livespec.jsonc` is
>   redundant with this key and is dropped or defined as derived from it;
>   reconciling the console's own block is the console contract's concern.
> - **Per-run opt-in flag.** Even when the permission is enabled, arming the mode
>   for a run MUST require an explicit, per-invocation opt-in: the `--mode
>   autonomous` flag on the Dispatcher `loop` subcommand (alongside the existing
>   `--mode shadow`). This flag rides the Dispatcher `loop` subcommand — the
>   mode-bearing entry point that drains the ready queue — NOT `drive`, whose
>   surface is `drive --action <action-id>` and which always invokes the loop
>   with `--mode shadow` (§"`drive`"). Enabling the mode is a dangerous action
>   and MUST be surfaced as such; the armed mode MUST NOT be inferred from
>   context and MUST NOT persist beyond the current invocation — each run
>   re-passes the flag.
> - **Loop launcher.** The launcher — the Control-Plane console's existing
>   factory-drain path — reads the persistent permission and, while it is
>   enabled, passes `--mode autonomous` to the Dispatcher `loop` per run. The
>   Dispatcher arms full autonomous mode for a run on the explicit per-run flag;
>   it MUST NOT arm the mode from the permission key alone.

**C. `SPECIFICATION/contracts.md` §"Auditing auto-resolutions" — frame the
Dispatcher journal as the published Control-Plane audit surface.** Replace the
verbatim block:

> Every decision the mode auto-resolves MUST be recorded on the existing
> Dispatcher journal (the same journal → Honeycomb leg used for calibration
> telemetry), carrying at minimum the work-item id, which gate was collapsed (`approve` / `acceptance` / `needs-human`), and what the LLM
> decided. No auto-resolution MAY be silent. The set of decisions the mode
> escalated as truly-unresolvable MUST be queryable from that same journal.
> This auditing is what makes autonomous-mode auto-resolution a BOUNDED
> extension of §"Machine-path exemption — the Dispatcher": like the
> Dispatcher's ordinary machine-path dispositions, autonomous-mode
> resolutions dispose of already-filed items only and MUST NOT create
> net-new work-items.

with:

> Every decision the mode auto-resolves MUST be recorded on the existing
> Dispatcher journal (the same journal → Honeycomb leg used for calibration
> telemetry), carrying at minimum the work-item id, which gate was collapsed (`approve` / `acceptance` / `needs-human`), and what the LLM
> decided. No auto-resolution MAY be silent. The set of decisions the mode
> escalated as truly-unresolvable MUST be queryable from that same journal.
> This Dispatcher journal is this plugin's PUBLISHED per-decision audit surface:
> the Control-Plane console reads each auto-resolution and each
> truly-unresolvable escalation from it (through this plane's published read
> surface) to observe, record, and reflect the run and to surface the
> escalations as in-console needs-attention — it does not re-derive them. This
> auditing is what makes autonomous-mode auto-resolution a BOUNDED
> extension of §"Machine-path exemption — the Dispatcher": like the
> Dispatcher's ordinary machine-path dispositions, autonomous-mode
> resolutions dispose of already-filed items only and MUST NOT create
> net-new work-items.

**D. `SPECIFICATION/contracts.md` §"Autonomous-mode gap-detectable clauses" —
name the `loop` surface and forbid key-only arming.** Replace the verbatim
clause:

> - The Dispatcher MUST default `dispatcher.autonomous_mode` to `false` and
>   MUST require an explicit `--mode autonomous` opt-in per invocation.

with:

> - The Dispatcher MUST default `dispatcher.autonomous_mode` to `false` and
>   MUST require an explicit per-invocation `--mode autonomous` opt-in on the
>   `loop` subcommand; it MUST NOT arm the mode from the permission key alone.

**E. `SPECIFICATION/scenarios.md` Scenario 33 — correct the arming surface and
qualify the auto-admitted item as routine (not design-human-gated).** Replace the
verbatim block (two leading spaces preserved on each Gherkin line):

>   Given full autonomous mode is enabled for the invocation via `drive --mode autonomous`
>   And a `pending-approval` item whose stored admission_policy is manual, with dependencies clear and an assignee resolvable

with:

>   Given full autonomous mode is enabled for the invocation via `loop --mode autonomous`
>   And a routine `pending-approval` item (risky/irreversible tier, not a design-human-gated decision) whose stored admission_policy is manual, with dependencies clear and an assignee resolvable

**F. `SPECIFICATION/scenarios.md` Scenario 37 — correct the arming surface.**
Replace the verbatim line (two leading spaces preserved; the only change is
`drive` → `loop`):

>   Given an operator requests `drive --mode autonomous`

with:

>   Given an operator requests `loop --mode autonomous`
