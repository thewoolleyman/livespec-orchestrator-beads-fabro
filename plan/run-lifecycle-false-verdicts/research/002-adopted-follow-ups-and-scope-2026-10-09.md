# Adopted follow-ups and scope reconciliation

This note reconciles the initial research with the seven children of epic
`bd-ib-qen6rr`, read on 2026-10-09. It supersedes the ownership account in
`001-false-verdicts-collected-2026-10-09.md`, including its statement that
`bd-ib-656k7i` has no orchestrator plan. The initial fault evidence and the
maintainer's verbatim statement remain historical input.

The adoption authority is epic comment
`01a11fb8-a0b6-7df6-9cc3-f4803cd7750a`, posted at 08:12:36Z. Each adopted
child also carries a comment stating that adoption changes tracking and
preserves whoever is already driving the work. The child set was read through
`BeadsClient.children(parent_id="bd-ib-qen6rr")`, which includes both explicit
parent-child edges and implicit dotted identifiers.

## Where the collected work belongs

| Work item | Repair boundary | Owning plan |
| --- | --- | --- |
| `bd-ib-gh5xwq` | Prevent a stale orphan-sweep snapshot from cancelling a newer run as superseded. | `run-lifecycle-false-verdicts` (`bd-ib-qen6rr`) |
| `bd-ib-l55d7e` | Reconcile a worker-exit failure with evidence that the workflow completed and published its pull request. | `run-lifecycle-false-verdicts` (`bd-ib-qen6rr`) |
| `bd-ib-ma3fvj` | Name the aggregate runner's failed targets and retain the complete janitor log. | `run-lifecycle-false-verdicts` (`bd-ib-qen6rr`) |
| `bd-ib-emzxlx` | Diagnose an invalid repository path before reporting a missing connection prefix. | `run-lifecycle-false-verdicts` (`bd-ib-qen6rr`) |
| `bd-ib-656k7i` | Isolate credential tests from the host account selector and injected token pool. | `run-lifecycle-false-verdicts` (`bd-ib-qen6rr`) |
| `bd-ib-n44n4e` | Restore the watchdog's quiet window after observed progress and finish the existing acceptance recovery. | `run-lifecycle-false-verdicts` (`bd-ib-qen6rr`) |
| `bd-ib-4ouajy` | Recognize a pull request that already merged while the publish prompt was verifying auto-merge. | `run-lifecycle-false-verdicts` (`bd-ib-qen6rr`) |
| `bd-ib-k627ja` | Project the harness no-auto-background switch and raised shell timeouts into sandbox agents. | `pr-stage-backgrounded-push-fault` (`bd-ib-ctagnf`) |

The last row is a related follow-up retained under its existing live plan,
not an eighth child here. Its ledger parent and the sibling plan's
`associated_work_item_id` agree. The table records scope and ownership, not
lifecycle status; obtain current status and computed readiness through
`list-work-items` and `next`.

## Boundaries of the adopted repairs

The credential-test repair and watchdog acceptance recovery retain their
existing `llm-provider-manager` recovery ownership. The credential repair is
limited to test isolation; it must not change production account selection,
host credentials, host profile state, or the wrapper. Its owner's 08:22:10Z
comment reports that the corrected candidate passed the full normal aggregate,
including the real Codex picker test, while explicitly retaining the pending
host-publication exception. Passing validation is not approval to publish.
This reconciliation neither grants that exception nor takes over publication.

The watchdog's ledger records already identify merged PR 2684 and a released
installation receipt. Its remaining recovery must use the existing merged
work and normal acceptance reconciliation after the credential-test defect is
resolved. Re-dispatching its implementation would duplicate delivered work.
These are attributed ledger facts, not a fresh release or acceptance proof
taken by this planning session.

The publish-prompt repair retains the `factory-reliability` session's
implementation ownership. Its current boundary is the `pr` prompt's exact
pull-request lookup and handling of an already merged pull request. The
original `verify_pr` boundary was repaired separately by `bd-ib-54ijva`
(PR 2570), as recorded in this child's regrooming comment. Neither that
completed repair nor the related host lookup item `bd-ib-bvg2w2` is duplicated
by adopting this child.

## Requirement coverage and proof boundary

The five existing plan Definition of Done assertions remain unchanged.
The authoritative assertion-to-carrier relation belongs only in the epic's
formal carrier-map scope event. The inventory assertion requires a plan-level
proof that checks the complete child set and the named sibling ownership.
Adopting three existing repairs does not invent three new plan assertions or
claim that those repairs directly prove the four original fault assertions.
All seven children remain subject to the plan's child-disposition gate.

No closure, admission, readiness or implementation proof follows from this
reconciliation. The original four defect filings still require the normal
intake and Definition-of-Ready assessment before a factory dispatch is
selected through `next`. In particular, intake must check that the engine
run-store-loss item's requested evidence can actually be obtained by the
Dispatcher; the incident's two server-log timestamps must not become a
promise that every future failure exposes exactly two such timestamps.

## Explicit scope exclusions

Engine-side repair or deployment for canonical run-store loss remains a
`fabro-currency` cutover question, to be reconsidered there against the actual
candidate engine. This plan owns the Dispatcher verdict defect under
`bd-ib-l55d7e`; it does not assume that changing that verdict repairs the
engine's storage failure.

The no-auto-background environment repair remains under
`pr-stage-backgrounded-push-fault` and `bd-ib-k627ja`, where its implementation
and proof belong. Moving it here would duplicate existing ownership.

The pending publication exception for `bd-ib-656k7i` remains on that child's
ledger with its current recovery owner. Until it is explicitly resolved,
this plan must not publish that candidate or infer watchdog acceptance from
its successful test run. This hold does not prohibit independent intake of
the four original defects.

Plan-level released-artifact proof and independent completeness review belong
to eventual closure, after the relevant repairs and dispositions. A complete
ownership table and carrier map establish the scope; they do not establish
that the repaired behavior has been observed.
