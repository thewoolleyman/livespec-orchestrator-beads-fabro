---
topic: fabro-factory-integration-branch-standard
author: claude-opus-4-8
created_at: 2026-07-14T05:28:51Z
---

## Proposal: factory-integration is the standard carrier branch for unreleased Fabro fixes

### Target specification files

- SPECIFICATION/constraints.md
- tests/heading-coverage.json (co-edit; spelled `../tests/heading-coverage.json` in `resulting_files[]` at revise time, since the wrapper joins `spec_target / path`)

### Summary

Adds a new `## Fabro runtime constraints` H2 to `constraints.md` establishing `factory-integration` (in the fork `thewoolleyman/fabro`) as the single STANDARD branch the factory pins whenever it must run a Fabro build carrying fixes that are not in an official upstream release, and amends the file preamble so its stated enforcement mechanism admits constraints over external runtimes the plugin does not own. The new section fixes five rules: the carrier-branch name; its composition (base + EVERY pending fix, never a subset); the base-version ceiling (< 0.256, forced by upstream fabro #474 until the `workflow.fabro` migration `bd-ib-6qu` lands); the rebuild/re-pin/rollback obligation, which MUST re-pin BOTH the host binary and the orchestrator image that bakes a copy of it; and runbook lockstep. The volatile list of which fixes are carried today lives in the runbook, not here, so this section does not become a staleness magnet.

### Motivation

The dark factory runs a Fabro built from a fork, not an upstream release, because it depends on fixes upstream has not shipped. As of 2026-07-14 the live pin is `fabro 0.254.0 (15b89ab)` and it carries three: upstream PR #568 (`push-credential-refresh-ahead`, the >60-minute token-refresh fix), a FORK-LOCAL patch making the daemon-readiness timeout env-configurable (`FABRO_SERVER_START_READY_TIMEOUT_SECS` — the ~6s SlateDB store open exceeds stock 0.254's hard 5s cap, so stock 0.254 cannot start against this store at all), and upstream PR #576 (the opt-in OTLP/HTTP span export that restores factory observability for the Codex era). Carrying unreleased fixes is the factory's steady state, not a one-off, so the carrier needs a name fixed in the spec rather than re-invented per episode. Two failure modes this closes: (1) an operator pins a build from an ad-hoc per-fix branch and the carried set silently diverges from what the factory needs; (2) an operator modernizes the base past 0.256, where upstream fabro #474 de-templates `acp.command` — the factory's `acp.command = "{{ inputs.acp_adapter }}"` nodes then go through literally and EVERY dispatch dies with exit 127. A doctor pass over the first draft of this proposal found that the branch it names existed ONLY on the maintainer's local disk, with no remote tracking ref — the pinned commit was unreachable from any fork branch and the running binary was unreproducible if that disk were lost. It has since been pushed to `thewoolleyman/fabro` (`15b89ab0d449…`), which is precisely the durability this constraint exists to require. DELIBERATELY OUT OF SCOPE: making the base ceiling MECHANICALLY enforced via a dispatch-preflight engine-version gate (the seam `contracts.md` §"Dispatch-time baseline conformance gate" already establishes). That would convert this from a review-time rule into a tested behavior — a genuine improvement, and it would then require its own Gherkin scenario — but it is a behavior change, not a naming standard, so it is filed separately rather than folded in here.

### Proposed Changes

TWO edits to `SPECIFICATION/constraints.md`.

**Edit 1 — AMEND the file preamble.** The current preamble claims an enforcement mechanism this file already does not universally have (§"Skill orchestration constraints" already carries a "MUST be manually verified" clause), and the section added below governs an operator build step over an external repository. Replace:

> Architecture-level constraints this plugin operates under. Each constraint is a binary, mechanically-checkable rule; lint / type-check / test failures are the enforcement mechanism.

with:

> Architecture-level constraints this plugin operates under. Each constraint MUST be a binary, decidable rule. Where a constraint governs plugin code, lint / type-check / test failures are the enforcement mechanism; where it governs an external runtime the plugin does not own — the beads/Dolt server, the Fabro engine — the constraint MUST name the command that decides it, and enforcement is review-time verification against that command.

**Edit 2 — ADD a new H2 `## Fabro runtime constraints`**, placed immediately after `## Beads substrate constraints` (the two are symmetric: each governs one external runtime the plugin depends on but does not own). The section reads:

---

## Fabro runtime constraints

The Fabro engine is an EXTERNAL binary: the plugin does not vendor it, build it as part of `just check`, or own its lifecycle. **Scope — "the factory"** means the fleet's OWN Fabro servers: both the host-direct server the Dispatcher connects to at `127.0.0.1:32276` (run from `~/.fabro/bin/fabro`) and the containerized server the orchestrator image provisions, which bakes a COPY of that same host binary. An adopter's per-tenant server instance (`contracts.md` §"Per-tenant engine identity") is OUT of scope: adopters MAY run any Fabro their own workflow supports. These constraints govern which Fabro build the factory is allowed to pin.

- **Carrier branch.** When the factory must run a Fabro build carrying fixes that are NOT in an official upstream release, that build MUST be produced from a single standing branch named `factory-integration` in the project's Fabro fork (`thewoolleyman/fabro`), and that branch MUST be pushed to the fork's `origin` so the pinned commit is remotely reachable and the running binary is reproducible from something other than one machine's disk. Ad-hoc, per-fix, or per-session branch names MUST NOT be pinned into the factory.
- **Composition.** `factory-integration` MUST carry the pinned base plus EVERY pending fix the factory depends on that is not in an official upstream release — whether an unreleased UPSTREAM change or a FORK-LOCAL patch with no upstream PR. It MUST NOT carry a subset, so the branch is always the whole truth about what the factory runs. The set carried today is recorded in the runbook (below), NOT in this section, so that this constraint does not go stale each time the set changes. When a carried fix is present in the official upstream release the factory has moved onto, it MUST be dropped from the branch.
- **Base-version ceiling.** The factory MUST NOT pin any Fabro build `>= 0.256`. Within that ceiling the base MAY move forward; it is `0.254` today. The prohibition lifts ONLY when the `workflow.fabro` migration lands — upstream fabro #474 de-templates `acp.command`, so the five `acp.command = "{{ inputs.acp_adapter }}"` nodes in the dispatch graph `.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro` (the workflow graph named in `contracts.md` §"Self-contained plugin dispatch") go through literally and every dispatch dies with `exit 127`. That migration is tracked as ledger item `bd-ib-6qu`.
- **Rebuild and re-pin.** Whenever the carried-fix set changes, the binary MUST be rebuilt from `factory-integration` and re-pinned at `~/.fabro/bin/fabro`, the outgoing binary MUST be retained beside it as a rollback artifact (`~/.fabro/bin/fabro.<sha>-<label>.bak`) so the revert is a file swap plus a server restart, AND the orchestrator image MUST be rebuilt (`orchestrator-image/build-and-verify.sh`, which stages `$HOST_FABRO_BIN`) — otherwise the containerized server keeps running the OLD baked binary while the host-direct server runs the new one. The pinned build MUST be auditable from the binary itself: `fabro --version` MUST report the integration commit (e.g. `fabro 0.254.0 (15b89ab …)`), and that commit MUST be reachable from `origin/factory-integration`. This is the command that decides every rule above.
- **Runbook lockstep.** The operational procedure — build, pin, restart, health-verify, roll back — and the enumeration of which fixes `factory-integration` currently carries live in `orchestrator-image/README.md` §"Host Fabro server (self-hosted; the maintainer's factory)", which MUST be updated in the same change whenever the pinned build or the carried-fix set changes. This section fixes the rules; the runbook carries the commands and the current set.

---

No `scenarios.md` co-edit accompanies this section, and the omission is deliberate rather than an oversight of the behavior-⇒-scenario discipline: every rule above constrains which external binary an operator may pin, not an input→output, state transition, or error path of plugin code, so there is no plugin behavior for a Given/When/Then to exercise. This matches existing practice — no `constraints.md` heading is bound to an exercising scenario. (Were the base ceiling later enforced by a dispatch-preflight version gate, that gate WOULD be plugin behavior and MUST then carry its own scenario; that is filed as separate work.) The `tests/heading-coverage.json` co-edit MUST therefore add one entry for the new heading with `"test": "TODO"` and a non-empty `reason` recording that this is an operator-procedure rule over an external runtime with no plugin-side test surface — the same convention all nine existing `constraints.md` entries use.

This proposal MUST NOT disturb the retirement of `## Full autonomous mode constraints` pending in `proposed_changes/dispatcher-policy-settings.md`: the two touch `constraints.md` disjointly (that one retires and replaces an existing H2 and edits two bullets; this one amends the preamble and adds a new, unrelated H2 at a different seam), so a revise pass MAY accept them in either order. Both co-edit `tests/heading-coverage.json` with semantically disjoint entries.
