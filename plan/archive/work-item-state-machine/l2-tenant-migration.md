# L2 tenant migration — `livespec-orch-beads-fabro`

The per-tenant half of the fleet's L2 lockstep migration onto the
work-item-state-machine schema that L1a (released as **v0.3.0**, see
[handoff.md](handoff.md)) shipped. This note records the migration of THIS
repo's own beads tenant; the same two mechanical primitives migrate every
fleet tenant.

## What the migration does (mechanical, schema-level)

Two steps, both run against the LIVE tenant under the family env wrapper
(`/data/projects/1password-env-wrapper/with-livespec-env.sh`, which injects the
single bare `BEADS_DOLT_PASSWORD`) using the primitives THIS plugin ships
(v0.3.0) — no pin needed, the repo IS the producer:

1. **Register the 5 custom lifecycle statuses** via
   `store.register_custom_statuses` (S2's verb) → `bd config set status.custom
   "backlog,pending-approval,ready:active,active:wip,acceptance:wip"`.
   Idempotent; makes the tenant ACCEPT the custom statuses going forward
   (beads built-ins `open` / `closed` / `blocked` remain valid).
2. **Backfill the required `rank` field** on every live (non-`done`) head via
   the S5 `rebalance_ranks.legacy_seed` primitive: order the pre-migration
   rows by the legacy `priority → captured_at → id` key (the ordering the
   dropped logical `priority` field is replaced by) and assign evenly-spaced
   fractional keys, written in place through `store.update_work_item_rank`
   (metadata-only; status, labels, and `blocks` edges untouched). This is the
   one-time backfill so every live head carries a real `rank` instead of the
   read-path `BOTTOM_SENTINEL` fallback.

## Applied 2026-06-29 — result

Pre-migration tenant: **99 issues** (90 `closed`, 9 `open`); all 9 live heads
rank-less; legacy native `priority` ∈ {2, 3}.

- Step 1: custom statuses registered (verified via `bd config get
  status.custom`).
- Step 2: 9 live heads re-keyed in `(priority, captured_at, id)` order →
  `a0`…`a8` (the six `priority=2` heads first, then the three `priority=3`).
  All 9 live heads now carry a real, evenly-spaced `rank`; metadata was `None`
  on every live head, so nothing was clobbered.

Verification: the S6 doctor check
(`dev-tooling/checks/work_item_state_invariants.py`) run against the LIVE
tenant exits **0** — no non-sentinel-rank / rank-key-length WARNINGS, no
`active ⟹ assignee` / `blocked ⟹ blocked_reason` ERRORS.

## Scope boundary — legacy status VALUES are NOT reclassified

This migration is the SCHEMA migration the lockstep step calls for: custom
statuses registered + `rank` backfilled. It deliberately does NOT reclassify
the legacy beads status VALUES of existing rows:

- `closed` rows read back as livespec `done` via the adapter's one name
  mapping — already correct, no write needed.
- the 9 `open` rows are left at the beads built-in `open`. Mapping an `open`
  row onto a canonical lifecycle state (`backlog` / `pending-approval` /
  `ready`) is a per-item JUDGMENT (is it approved? ready? still triage?), not a
  mechanical transform, so it is out of scope for the mechanical lockstep
  migration. The post-migration read path tolerates a legacy `open` (it passes
  through unmapped), and the doctor invariants do not gate on it. If a per-row
  status reclassification is ever wanted it is a separate, judgment-bearing
  follow-up (and the `needs-regroom`-labelled live head `bd-ib-un226z` would be
  groomed through the normal grooming lifecycle, not bulk-rewritten).
