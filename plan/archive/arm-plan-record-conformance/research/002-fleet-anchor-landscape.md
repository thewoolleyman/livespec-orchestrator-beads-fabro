# 002 — Fleet anchor landscape for leg 2b / arming (2026-09-06)

Snapshot for legs `.4` (every other tenant's unassigned archived plan anchors)
and `.5` (arming per tenant). It answers one question: **how many archived
`plan/<slug>/` directories in each fleet tenant still carry an
`associated_work_item_id` reading the literal `unassigned`** — i.e. still owe
leg-2 reconciliation before that tenant's plan-record conformance check can be
armed green.

## Method

Read-only. For every sibling repository under `/data/projects/` that carries a
`.beads/config.yaml` (a beads tenant) and a `plan/archive/` tree, count the
`plan/archive/*/associated_work_item_id` files whose sole token is
`unassigned`. No ledger writes, no cross-tenant mutation. A count is a snapshot
of the working tree at survey time, not a live figure — a tenant with an
in-flight anchor PR will read lower once it merges.

## Result

| tenant | archived | unassigned | notes |
|---|---:|---:|---|
| livespec (CORE) | 48 | **39** | largest remainder |
| livespec-overseer | 52 | **20** | plus one non-anchor slug dup (`make-supervisors-reliable` on `overseer-cvyfzo`/`overseer-ocj2yi`) |
| livespec-orchestrator-beads-fabro (THIS) | 39 | 8→**4** | 10/14 landed (PR #2242, #2250); 4 remain as maintainer orphan calls |
| livespec-dev-tooling | 11 | **7** | |
| livespec-console-beads-fabro | 16 | **3** | the 3 pending orphan calls from `pzbdbo.16` (10/13 done) |
| livespec-runtime | 3 | **2** | |
| dolt-server | 3 | **1** | `governed-repo-bootstrap` |
| openbrain | 0 | 0 | done (`ob-ck4nao`) |
| homelab / resume / livespec-driver-codex / livespec-driver-pi | 0–1 | 0 | nothing outstanding |

"archived" is the count of archived plan directories carrying an anchor file;
"unassigned" is how many of those still read `unassigned`. "8→4" for this
tenant reflects that four of the eight were the evidence-confirmed retags landed
in PR #2250; the four that remain are genuine maintainer orphan calls
(`codex-factory-telemetry`, `factory-hardening`, `loop-reflection-gate`,
`orchestrator-plugin-self-containment`).

## Reading for sequencing

- Fleet-wide arming (`.5`) is blocked everywhere on the prerequisite
  `livespec-dev-tooling-lnbf` (the `issue_type` recognition fix): until each
  tenant's dev-tooling pin carries it, an armed run recognizes zero epics and
  can never be clean. Reconciliation (legs 1–2) does not wait on it; arming
  does.
- The two large remainders — **livespec (39)** and **livespec-overseer (20)** —
  dominate the outstanding work and are each owned by their own tenant's
  reconciliation thread, not by this orchestrator plan. This plan's `.4`
  records their state; it does not reach into them.
- Per the scope event, each tenant's per-directory reconciliation lands through
  that tenant's OWN anchor PR, and a directory with no candidate epic is the
  maintainer's orphan call — recorded, never guessed.
- Total outstanding across the fleet at survey time is roughly 76 directories
  (excluding this tenant's four already in-flight), heavily concentrated in the
  two core tenants above.
