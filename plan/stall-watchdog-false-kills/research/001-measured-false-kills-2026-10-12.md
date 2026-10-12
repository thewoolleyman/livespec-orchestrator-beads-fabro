## The maintainer's statement of what done means

"The HP Fabro factory is very overloaded. But what's even worse is that most of the recent runs are failing. There have only been a couple of successes." ... "For 2 and 3, ensure that work items are created to cover all aspects, and that the work items are all assigned to an appropriate existing/new plan"

## Definition of Done assertions derived from that statement

- On the hp factory, a dispatched run whose janitor and publish_draft stages together run longer than the stall window after its last agent stage completes without a stall-watchdog cancel.
- A stall-watchdog cancel leaves its item resting with a reason naming the cancelled run and stage, and never bounces it to backlog as non-convergence.
- Re-dispatching an item whose run was stall-cancelled after publishing resumes from the published branch, and the completed implement and janitor stages do not run again.
- Over the seven days after the fixes are released, no stall-watchdog cancel in any fleet dispatch journal names a run whose Fabro event stream or open command node showed progress inside the stall window.

# Stall-watchdog false kills — measured 2026-10-12

Measured 2026-10-12 by session factory-failure-mitigation (project livespec-orchestrator-beads-fabro) from the dispatch journals of every repo dispatching to hp since 2026-10-08 (301 distinct runs: 72 green, 114 blocked at needs_human, 57 failed, 12 post-merge janitor red, 6 watchdog-cancelled), the hp fabro-server journal since 2026-10-09 (213 runs), per-run `fabro events` and `fabro inspect` reads against https://hp-xubuntu.perch-rudd.ts.net:32276, and this tenant's full ledger. hp was at load 25 to 38 on 16 cores with 14 of 15 scheduler slots busy; sandbox janitor (`just check`) duration rose from a 3.4 min median on 2026-10-05 to 6.5 min (max 21 min) on 2026-10-12.

## Finding

Six `watchdog-stall-cancel` rows since 2026-10-08. Three cancelled HEALTHY runs that were inside
command nodes (no agent process running):

| Item | Run | State at cancel |
|---|---|---|
| bd-ib-xatgja | 01M4QKN0R3N3HXX8FWV9T0QJB3 | implement done 09:30:53Z, janitor green 09:30:56-09:52:05Z, in publish_draft, cancelled 09:57:54Z |
| bd-ib-z6fmp | 01M4Q4XBZ5398FJAWQ131QER60 | janitor and publish_draft green, cancelled 12 s into proof_capture at 06:33Z |
| bd-ib-kawo6a | 01M4MMCFZNA3MXZP8S9Z28N6M8 | review_fix done, janitor green, in publish_draft, cancelled 08:14Z |

Mechanism. `liveness_sample` (`_dispatcher_io_liveness_probe.py`) layers `HeartbeatLivenessProbe`
as PRIMARY over the `fabro events` wall-clock fallback, and `LayeredLivenessProbe.sample`
(`_dispatcher_heartbeat_probe.py`) returns the primary whenever it carries ANY timestamp. The
heartbeat is Claude Code's OTel metrics beat, which only advances while an agent process runs.
The sink (`tmp/fabro-dispatch-journal-otel-heartbeat.json`) shows xatgja's dispatch
`f655b8d1f9b8423ab0e4009ee37d29dc` last beat at 09:30:53Z, the second implement ended; the
event stream meanwhile carried `command.started`/`command.completed` for janitor and
publish_draft but was never consulted. Each cancel landed at last agent activity + 1500 s +
one 30 s poll. `DEFAULT_STALL_SECONDS` (1500) was sized on the premise that a janitor leg is
minutes, not tens of minutes; under the 2026-10-12 load it is not. Note also that a command
node emits only its start and completion events, so even the event stream is flat for the
whole of a long janitor: the node's own `timeout` (1800 s in workflow.fabro) is the bound
that should govern while a command node is open.

Second-order costs, both measured: every one of the six cancels journaled a
`non-convergence-bounce` (bounce_cap LIVESPEC_DISPATCH_STALL_SECONDS), routing the item to
backlog and feeding slice-size calibration a too-big signal; and the next dispatch of z6fmp
(07:08Z) and kawo6a (09:31Z) journaled `publish-branch-reclaim` and restarted from scratch
although the cancelled run had already published (kawo6a then took five more hours to merge).

Prior art read: closed bd-ib-n44n4e (re-arm quiet window after progress), closed
bd-ib-lfkt6z (heartbeat keyed on dispatch id), closed bd-ib-n6cobe (discovery observability),
closed bd-ib-q5wxkh, closed livespec-impl-beads-oyg. None covers a stale primary masking a
fresher fallback. Related plan run-lifecycle-false-verdicts (bd-ib-qen6rr) owns other
healthy-run-cancelled verdicts; this plan was opened separately because that plan is closing
out its own carrier set in a live session.