## The maintainer's statement of what done means

ensure they get through the factory and get done correctly.

## Definition of Done assertions derived from that statement

- A factory run whose gates have passed while master moved underneath it publishes its branch with the run's work intact instead of ending at needs_human.
- On a loaded factory host, a green run's sandbox commit and push hooks complete within the agent tool-call and publish_draft stage limits and the run reaches its pull request.
- Over a 24-hour window on hp's fleet Fabro server after the fixes are released, no run that passed janitor ends at needs_human because publish_draft failed for a rebase-conflict or hook-time-limit cause.

# publish-draft-green-work-loss — origin and per-run classification

Opened 2026-10-14 by session publish-draft-green-work-loss, at the direction of the
gitops-fleet-capacity coordinator (plan gitops-fleet-capacity-monitoring in
livespec-dev-tooling, epic livespec-dev-tooling-dfixhe), under the maintainer's
standing directive of 2026-10-14 quoted on that epic.

## The problem

On hp on 2026-10-13, 11 factory runs passed their janitor stage (the full `just check`
gate) and then ended at needs_human after their `publish_draft` stage failed. The
coordinator measured that as 44 slot-hours, 37% of all slot-hours spent that day. This
session re-measured the hours from each run's own record: start time from `fabro ps -a`,
end time from the checkpoint timestamp. They total **44.0 hours**, so the coordinator's
figure reproduces. The 37% share is the coordinator's and was not re-measured here.

The needs_human handler then failed with `LIVESPEC_NEEDS_HUMAN_NO_RUN_ID`, so nothing was
pushed to a preservation ref. The run conclusion reads either "stage needs_human failed
with no outgoing fail edge" or "Worker exited before emitting a terminal run event". Both
are the label of the needs_human ending, not its cause. That handler defect is owned by
bd-ib-zddbkq (plan fabro-currency) and is not this plan's.

## Method

For each run this session read the publish_draft node outcome on hp. Command:
`ssh cwoolley@hp-xubuntu '~/.fabro/bin/fabro inspect --json --server http://127.0.0.1:32276 <run>'`.
The field read was `checkpoint.node_outcomes.publish_draft.failure.message`, specifically
the script's `## output` tail.

As a control on the coordinator's list, the same read was taken over **all 58 failed runs**
on hp's fleet server that started between 2026-10-12T22:00Z and the end of 2026-10-13, in
every repository. A run was selected when its janitor outcome was `succeeded` and its final
node was `needs_human`. That selection returned the 11 listed runs, plus three classes this
plan does not own (listed further below).

## Per-run classification

The column headings mean:

- **start** is the run's start time as `fabro ps -a` reports it.
- **end** is the checkpoint timestamp from `fabro inspect`.
- **hours** is end minus start.
- **cause** is read from the publish_draft output tail.

| run | item | start (UTC) | end (UTC) | hours | cause |
|---|---|---|---|---|---|
| 01M4T1ZM6BEQ21DBRSAKY3434G | bd-ib-jqvqlf | 10-13 07:18 | 11:06 | 3.8 | stage time limit: refresh rebased cleanly, then the push (its pre-push suite) ran past the 1800 s script limit |
| 01M4T26F0ZERZ7TF0CAFNBJSDA | bd-ib-zddbkq | 10-13 07:21 | 10:36 | 3.2 | rebase conflict: workflow.fabro, tests/integration/CLAUDE.md |
| 01M4T28A9B79A7B971N9A5J3NW | bd-ib-6jkjzm | 10-13 07:22 | 11:23 | 4.0 | rebase conflict while applying 46e8df7e |
| 01M4T2KF3K6B2PH5YGTKMCA2C0 | bd-ib-qsk4o5 | 10-13 07:29 | 10:51 | 3.4 | push HTTP 401 (expired App token) after the pre-push suite passed in 670 s |
| 01M4T2KEGPQPAR1XS1KEK91P0E | bd-ib-l55d7e | 10-13 08:42 | 12:02 | 3.3 | post-refresh gate red: clean rebase, then the pre-push suite failed `check-per-file-coverage` and `check-coverage` |
| 01M4T4A3374PGBRPGEPWAY0AMV | bd-ib-ex35cb | 10-13 09:20 | 12:18 | 3.0 | rebase conflict: tests/heading-coverage.json, tests/heading-coverage-debt.json |
| 01M4TFVABFNB8AZAZH0A2BNAQX | bd-ib-s22sg | 10-13 11:49 | 15:53 | 4.1 | rebase conflict: test_config.py, test_dispatcher.py (NOT the 401 the item's title names) |
| 01M4TN35JART0Z0B3DYP78Z24X | bd-ib-nfbyot | 10-13 12:52 | 19:22 | 6.5 | rebase conflict: implement-work-item/workflow.fabro |
| 01M4TN6V5M5WSRA57JENX0MVXW | bd-ib-vlctc3 | 10-13 12:54 | 15:27 | 2.6 | rebase conflict while applying d6ec1dd6 |
| 01M4TNNJR0XR3BBRV7QDV4BBXV | bd-ib-6jkjzm | 10-13 13:42 | 20:16 | 6.6 | rebase conflict while applying 2dbd5f33 |
| 01M4TYK09SRPPT5W9EDG4VWGG0 | bd-ib-vlctc3 | 10-13 15:38 | 19:14 | 3.6 | stage time limit: clean rebase (4 commits), then the push ran past the 1800 s script limit |

## Tally by cause, and each cause's carrier

| cause | runs | hours | carrier |
|---|---|---|---|
| rebase conflict onto a moved origin/master | 7 | 30.0 | bd-ib-tzj9x (spec-change tier: routes through propose-change, then implementation children) |
| post-refresh gate red after a clean rebase onto a moved master | 1 | 3.3 | bd-ib-tzj9x's proposal (the same "master moved under a green run" class; the proposal must cover a red gate after a clean refresh as well as a conflict) |
| push or pre-push hook outruns the 1800 s publish_draft limit on a loaded host | 2 | 7.4 | bd-ib-xi63mq |
| push HTTP 401, expired GitHub App token | 1 | 3.4 | bd-ib-s22sg (plan stall-watchdog-false-kills; coordinate, do not duplicate) |

The total is 11 runs and 44.0 hours. Rebase onto a moved master, conflicting or turning a
gate red, accounts for 8 of 11 runs and 33.3 of 44.0 hours. It is the dominant cause.

## Outside this plan's 11, found by the population control

- bd-ib-wdl577 run 01M4S4E9WH5FKSD7QVRZWBD1RF, started 2026-10-12 22:41Z. Its push failed
  with "Invalid username or token" after a clean refresh. This is the credential class owned
  by bd-ib-s22sg.
- overseer-3n64mb run 01M4S4H0YG27DD3STA3DC2RHFH (livespec-overseer). Push HTTP 401, the
  same class. It is a sibling-repo instance, recorded for bd-ib-s22sg's evidence only.
- Several janitor-green runs passed publish_draft and failed later, at proof_capture, pr or
  fix: bd-ib-c3txja, mnuo5n, 6pdigz, mqevnt, mhqj3h, ex35cb (01M4V3RR), jqvqlf (01M4TFM5),
  and overseer-3brqwk. Those are NOT publish_draft losses and are out of this plan's scope.

## Related, owned elsewhere

- bd-ib-s22sg: the 401 from an expired App token at publish_draft. Owned by plan
  stall-watchdog-false-kills (epic bd-ib-laf735). Assertion 3 of this plan names only the
  rebase-conflict and hook-time-limit causes, so it does not depend on bd-ib-s22sg.
- bd-ib-zddbkq: the needs_human handler's run id. Owned by plan fabro-currency (epic
  bd-ib-6tcjfx). It is what turned these losses from "preserved on a ref" into "only in the
  run dump"; fixing it does not prevent any loss.

## Open question carried into the proposal

The post-refresh gate red (bd-ib-l55d7e) is attributed to master's movement by inference.
Janitor's `just check` was green before the refresh, and the same coverage targets failed
after it. That inference has not been confirmed by re-running coverage on the pre-refresh
head. The proposal should treat "gate red after refresh" as a case to route to repair rather
than to needs_human, whatever its root cause.
