## The maintainer's statement of what done means

"Regarding all of this report - I want to do a holistic review of all the existing plans which may cover all of these items, and then consolidate / deduplicate / fill gaps so we have a focused, achievable track of work to address all of these items, with a laser focus on increasing throughput. This should be de-scattered, under a new workspace on hetzher herder, with a tab for each plan which is actively focused on this. Unrelated work should be omitted or moved to other/new plans. This is going to be a priority track, third after the expideted incident and hetzner move tracks."

"The goal of the overall track will be to move ONE METRIC: THROUGHPUT AS MEASURED IN PRS PER REPO PER HOUR MERGED TO MAIN BRANCH AND PASSING AS GREEN. Reported as a table of each repo and its throughput, and with a corresponding honeycomb item for me to monitor real-time as the first item on the existing livespec board"

## Definition of Done assertions derived from that statement

- The filing display shows, and intake, approve and every release-to-ready path hold out of ready, a work item whose factory_captured assertion needs a surface that no name in the committed sandbox capability grading set provides, each naming the assertion and the surface.
- Every factory run that ends in a terminal failure has a livespec-dispatcher span carrying its fabro run id and a fabro.failure.category drawn from a closed set, so a Honeycomb query breaks the week's failed runs down by cause with no empty or 'None' group.
- Every ended factory run's terminal dispatch span carries its repository, run class, execution target and sandbox CPU-seconds, so a Honeycomb query attributes factory CPU by repository.

# Charter — factory-run-yield

Opened 2026-11-13 by plan throughput-track-organization (livespec-dev-tooling-q26e3c) as part of the maintainer's throughput track. The assertions above are SESSION-DERIVED from the maintainer's statement and the 2026-11-13 throughput report; the first session to resume this plan with the maintainer present confirms or re-words them.

Re-worded 2026-11-14 by the factory-run-yield seat, and recorded as a scope event on bd-ib-ft26pi. Assertion 1 originally said filing refuses, but contracts.md §"Effective acceptance criteria" says "a front-end MUST NOT refuse on a finding", and the grading set is the committed dispatcher.sandbox_capabilities array. Assertion 2 now covers runs that end in a terminal failure, because a succeeded run has no failure category. Assertion 3 is confirmed as written. These are conformance re-words; the maintainer has not yet confirmed them. The full carrier map is the epic's latest carrier-map scope event.

## Why this plan exists

The 2026-11-13 report (ci-runtime-and-cost): of 788 factory runs that ended in 7 days, 382 succeeded and 406 did not (Honeycomb query kurpKF7PJY6). The most frequent visible failure class is an assertion the sandbox cannot prove (it needs a git push, a live ledger tenant, a missing toolchain or another repository), and the breakdown cannot be counted because the failure category field is empty.

Those two levers were scattered: the refusal sat in bd-ib-ccl3wf (legacy-dispatcher-agent), bd-ib-lqjygl (spec-implementation-lockstep), bd-ib-rowuou (hp-factory-failure-follow-ups) and the unparented bd-ib-vhx5vl and bd-ib-hxkikj; the failure category sat in bd-ib-2h6cfl (legacy-dispatcher-agent) with its attribution neighbour bd-ib-faprof unparented. legacy-dispatcher-agent and spec-implementation-lockstep each ACCEPTED releasing their item (coordinator record on livespec-dev-tooling-q26e3c, 2026-11-13T23:02:44Z).

## Scope

- Report lever 1: stop admitting assertions the sandbox cannot prove; make the refusal mechanical at filing, approve and release-to-ready. Carriers: bd-ib-ccl3wf, bd-ib-lqjygl, bd-ib-vhx5vl, bd-ib-hxkikj, bd-ib-rowuou. Gap: the refusal at FILING has no item yet.
- Report lever 7: make failures countable, and attribute factory CPU. Carriers: bd-ib-2h6cfl, bd-ib-faprof.

Not in scope: failure classes after admission (timeouts, in-run gate failures, open-Red re-entry), which sandbox-commit-gate-follow-ups (bd-ib-3goerg) owns; launch-path defects; work recovery.

## How it is judged

The track's one metric is PRs per repository per hour merged to main and green. Measured basis for this plan's share: the factory bot authored 226 of 492 PRs merged in livespec-orchestrator-beads-fabro and 166 of 754 in livespec-dev-tooling over 7 d to 2026-11-13T22:05Z; each 10 points of factory yield at the same run count is about 79 more factory PRs a week (+0.47 per hour fleet-wide). The share of failed runs in the unprovable-assertion class is NOT measured; assertion 2 is what measures it.

Track map and baseline: livespec-dev-tooling `plan/throughput-track-organization/research/005-track-map-2026-11-13.md` and `003-the-one-metric-definition-and-baseline.md`.
