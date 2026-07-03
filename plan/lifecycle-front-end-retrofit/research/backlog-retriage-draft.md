# Backlog re-triage — DRAFT disposition table (Workstream C)

**DRAFT ONLY — no status writes until the maintainer approves this
table.** Drawn from the LIVE ledger 2026-07-03 (`bd list --status
backlog` via the wrapper): 24 items at `backlog`, of which 4 are this
track's own (epic `bd-ib-ew7bdv` + slices, listed last). The console
session agent is consolidating items on this tenant — re-read live state
before executing any approved disposition; this table records the
reasoning, the ledger records the truth.

Disposition vocabulary (the 7-state lifecycle):

- **→ pending-approval** — DoR-passing: one coherent done, autonomously
  verifiable, repo-targeted, above floor, blockers linked-or-none.
- **stays backlog** — genuinely groom-shaped (epic / multiple dones /
  oversized) or explicitly deferred by the maintainer.
- **→ blocked** — not autonomously actionable; carries
  `blocked_reason: needs-human` or `infra-external`.

## Pre-existing items (20)

| Item | Type | Disposition | Why |
|---|---|---|---|
| `bd-ib-3m44nx` | bug | → pending-approval | Single done (refusal + docs enumerate the full per-wrapper credential set, incl. the target's own wrapper); testable; repo-targeted. |
| `bd-ib-82a` | feature | stays backlog | "Full autonomous mode engine" spans v025 contracts + constraints + scenarios 33–37 (config, orchestrate mode, LLM blocked-reason resolution, …) — epic-shaped; groom before dispatch. |
| `bd-ib-9ch` | bug | → pending-approval | Concrete single fix (branch-2 cwd dogfood shortcut must verify plugin identity, not just dir existence); testable. |
| `bd-ib-cur` | bug | → pending-approval | Single done; testable. NOTE for approver: carries an embedded design choice (auto-normalize `open→backlog` vs file-as-backlog) — the dispatch brief should fix the choice (draft recommends auto-normalize at the conformance gate, matching the item's own lead option). |
| `bd-ib-h55` | bug | → pending-approval | Single done (unique container name or fail-fast; never force-remove an in-flight dispatch); shell-testable like the existing `test_real_work_dispatch_script.py` pins. |
| `bd-ib-hkzcfb` | bug | → pending-approval | Single done (resolve target repo's default branch instead of hardcoded `master`); testable. |
| `bd-ib-k5p` | task | stays backlog | Two distinct dones in one item (reap-e2e-repos deletion core + regen_beads_metadata YAML parser) — groom into two slices (or maintainer accepts as one deliberately). |
| `bd-ib-ls32yb` | task | → pending-approval | Single done (tree-wide fleet-PAT absence guard); mechanically verifiable. |
| `bd-ib-mwz` | task | → pending-approval | Single done (bring sandbox image pin under bump-pin/pin-freshness); mechanically verifiable; p1. |
| `bd-ib-ss7rkr` | task | → blocked (`needs-human`) | "Re-verify upstream codex-core auth behavior + realign docs/contracts" — acceptance is a judgement call against a moving upstream; explicitly deferred P3 by epic `bd-ib-un226z`. |
| `bd-ib-umno37` | task | → pending-approval | Single done (route post-verdict fail-open stages through the provider accessor); testable per stage. |
| `bd-ib-un226z` | epic | stays backlog | Epic anchor; its groomed slices (egms32, g7e34u, di442r, 3ti4jf, 6pl3in) are CLOSED — remaining open child is `bd-ib-webwai`. Close-review the epic once webwai lands. |
| `bd-ib-v5n` | bug | → pending-approval | Single done (portable spec-side `next` CLI resolution via `.livespec.jsonc` instead of hardcoded host path); testable. |
| `bd-ib-w4iaaf` | task | → blocked (`needs-human`) | Requires PROVISIONING a GitHub App installation over the e2e throwaway repos — a human act in GitHub org settings, not factory-executable. |
| `bd-ib-webwai` | task | → pending-approval | All five `blocks` edges verified CLOSED live (3ti4jf, di442r, 6pl3in, g7e34u, egms32) — unblocked, single coherent test-suite done, factory-safe per its own text. |
| `bd-ib-z2ctra` | task | stays backlog | Two dones (adopter Fabro-server recipe docs + dispatcher preflight reachability check) — groom-shaped; also touches adopter-facing policy. |
| `livespec-impl-beads-29f` | epic | stays backlog | Reflection-gate epic — groom-shaped by construction (8 ratified design decisions, several slices). |
| `livespec-impl-beads-bqq` | task (labeled epic) | stays backlog | Maintainer wrote "Do NOT implement now — future epic." Honor the deferral. |
| `livespec-impl-beads-zbl` | task | stays backlog | Multi-provider cost observability generalization — design-heavy, multiple providers = multiple dones; groom before dispatch. |
| `livespec-impl-beads-zsl` | bug | → blocked (`infra-external`) | Root cause is upstream fabro-sh/fabro#508; cosmetic-only. Nothing local to do until the upstream fix ships. |

Tally: 11 → pending-approval · 6 stay backlog · 3 → blocked
(2 `needs-human`, 1 `infra-external`).

## This track's items (4) — managed by the track, listed for completeness

| Item | Type | Disposition | Why |
|---|---|---|---|
| `bd-ib-ew7bdv` | epic | stays backlog | This thread's epic anchor; closes when A1–A3 land. |
| `bd-ib-r3vsnd` (A1) | task | → ready at dispatch | DoR-passing, admission `auto`; status flipped via the sanctioned interim mechanism when dispatched (first in sequence). |
| `bd-ib-h2tnil` (A2) | task | → ready after A1 closes | `blocks`-edge on A1; flipped only once A1 is done. |
| `bd-ib-q3x6va` (A3) | task | → ready at dispatch | Independent of A1/A2; flipped when its dispatch slot opens. |

## Execution note (post-approval)

Approved dispositions should be executed via the store seam
(`update_work_item_status`) or `bd update --status`, one item at a time,
re-reading each item's live state first (the consolidation session may
have moved it). `blocked` items additionally need their
`blocked_reason` set (`needs-human` / `infra-external`). No writes have
been performed for anything in this table.
