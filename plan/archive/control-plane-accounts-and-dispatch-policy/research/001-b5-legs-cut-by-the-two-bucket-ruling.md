# 001 — b5's four legs, cut by the two-bucket ruling (2026-09-06)

This thread adopts `bd-ib-rh3iyd`, the b5 successor home re-homed at the
archive of `console-control-plane-primitives` (epic `bd-ib-w3nwz5`, archived
2026-09-06). The maintainer's rule: every surviving follow-up gets a plan slug
to run. This is b5's.

## What b5 is (from rh3iyd's re-homing record)

b3 shipped the attention kind for a fabro run parked on a question
(`bd-ib-aqith2`, PR #2168) and the v093-native answer route that carries a
human answer back as a ledger comment (`bd-ib-uuohty`, PR #2200). With that
dependency paid, b5's four legs can be cut:

1. **Valve policy on attention items.** The admission and acceptance valve
   policies attach to work-items; b5 asks what policy governs an ATTENTION
   item — in particular a run parked on a question — and who may answer it.
2. **The generalized accounts primitive.** One primitive for the accounts the
   control plane spends against, generalizing today's per-factory and
   per-credential surfaces.
3. **transient_infra re-dispatch.** A run whose failure_class is
   transient_infra is reaped or re-dispatched by hand today; b5 asks for the
   automatic valve and the discrimination that keeps a genuine defect from
   being re-dispatched forever.
4. **Starvation-driven dispatch cadence.** Dispatch order is rank plus
   readiness; b5 asks for a cadence that notices an item nothing ever selects.

## The two-bucket ruling applied (console plan epic
`livespec-console-beads-fabro-pzbdbo`, scope event 2026-09-06)

The maintainer ruled that overseerd and the caam-anthropic-loop are production
and stay, maintainer-owned, until stable with a clear path; the foreman,
grooming and supervise-plan seats are unused and are deprecated now
(overseer plan `deprecate-unused-seats-simplify-to-overseerd-and-caam`).
That splits b5:

| leg | overseer source | bucket | when |
|---|---|---|---|
| 1 valve policy on attention items | foreman panel / consensus disposition | 2 — now | first |
| 4 starvation → dispatch cadence | foreman rule prose (overseer-7ranbh, closed) | 2 — now | first |
| 2 generalized accounts primitive | caam-anthropic-loop (`accounts status \| rotate`, multi-provider, event-driven off rate-limit signals) | 1 — deferred | when the maintainer declares caam stable with a clear path |
| 3 transient_infra re-dispatch | overseerd rule | 1 — deferred | when the maintainer declares overseerd stable |

Legs 1 and 4 are also what the overseer deprecation plan's closure child
(`overseer-5ugiuj.5`) needs ids for: the bucket-2 epics close only once their
two transferred capabilities are named by orchestrator id.

## Consumers waiting on this plan

- Console: proxy `livespec-console-beads-fabro-pzbdbo.15` (BLOCKED-ON
  `bd-ib-rh3iyd`); console rendering of accounts status, transient_infra
  re-dispatch visibility, starvation cadence and attention-item valve policy
  are held behind it.
- Overseer: `overseer-5ugiuj.5` cites legs 1 and 4 by id before closing the
  twelve bucket-2 epics as superseded-by-transport.

## Ordering

1. Groom legs 1 and 4 into factory slices (spec first where the orchestrator's
   contracts.md needs a clause: the attention-item valve policy is a contract
   change; the cadence is a dispatcher rule with a scenario).
2. Leave legs 2 and 3 filed and blocked behind the bucket-1 ruling; nothing
   is invented for them here.
