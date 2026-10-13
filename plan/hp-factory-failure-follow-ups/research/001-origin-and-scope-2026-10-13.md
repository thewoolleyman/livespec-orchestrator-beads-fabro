## The maintainer's statement of what done means

Okay I want you to go ahead and adopt the three recommendations you gave me above into your plan and get them done. And anything that you listed that is not captured by a work item, go ahead and create a work item for it. / Yes I told them to add them to your epic, make them part of your plan, and get them done.

## Definition of Done assertions derived from that statement

- On hp, over a 24-hour window after the fix is released, no ImplementWorkItem run fails with the engine pre-run push refusal at a primary checkout.
- An item whose Definition of Done carries a references or authoring defect is held out of ready with the judgement's verdict recorded on it, and no run of it ends at dod_gate for that defect.
- A run whose disposition node reaches its visit limit ends through the structured needs-human ending rather than an engine cycle error.
- A dispatch whose run ended through the needs-human ending reports the outcome needs-human, distinct from failed.
- On hp, docker ps shows no fabro-run container whose run the fleet or candidate server reports in a terminal state.
- On hp, fabro ps -a --json against the fleet server returns in under 5 seconds while it holds at least 1,700 runs.

# hp-factory-failure-follow-ups — origin and scope

Opened 2026-10-13 by the hp storage session (livespec-dev-tooling-smrzsj, now closed), at the maintainer's direction.

## Where this came from

On 2026-10-12 hp-xubuntu's container stores and swap moved to a second disk, and the sandbox resource envelope went live. The before/after comparison (journaled on livespec-dev-tooling-smrzsj) showed the infrastructure failures largely gone:

- finished-run success rose from 27% to 50%;
- infrastructure-type failures fell from 14.5% to 6.2%;
- OOM kills dropped to 0.

What remains is failure classes the disk change could not touch. The session classified all 223 failed ImplementWorkItem runs on hp's fleet server since 2026-10-09 by their `fabro inspect` failure detail, then matched each class against the bd-ib, overseer and livespec-dev-tooling ledgers (closed items included).

## Failure classes and their carriers

| Class | Runs since 10-09 | Carrier |
|---|---|---|
| Engine pre-run push refused at a primary checkout that is behind origin | 9 (still recurring) | bd-ib-urhjxd (successor of livespec-dev-tooling-8qe6) |
| dod_gate rests an item at needs-human for an authoring defect (wrong References line, test-existence assertion, undeclared host surface) | ~45 | bd-ib-7f66ar |
| disposition node visit limit, reported as an engine cycle error | 6 | bd-ib-3xdhc6 |
| needs-human ending reported as failed/workflow_error (117 runs, 52% of failures) | 117 | bd-ib-y2dsjm |
| Sandbox containers of failed runs keep running in fabro-sandbox.slice | 2 observed | bd-ib-ln725y |
| `fabro ps -a` slows with run-store size (13.8 s at 1,696 runs) | n/a | bd-ib-h6wiif (held behind bd-ib-iud52v) |

Classes already in progress elsewhere, which are NOT this plan's:

- checkpoint-commit hook failures and timeouts: bd-ib-jb53pu, 6jkjzm, qhv7qs, plan checkpoint-commit-hook-failures;
- the needs_human handler's `no_run_id`: bd-ib-zddbkq;
- run-store-loss worker exits: bd-ib-l55d7e.

The hp sandbox envelope's remaining assertions (runbook record, over-allocation canary, Enemy Unit Test marking) belong to bd-ib-otyq6l, a child of plan fabro-currency, verified 2026-10-13 and recorded on that item. This plan tracks it as an external dependency rather than re-parenting it.
