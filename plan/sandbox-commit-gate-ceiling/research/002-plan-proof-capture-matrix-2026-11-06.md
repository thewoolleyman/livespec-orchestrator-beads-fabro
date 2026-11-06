# Plan Proof of Done capture matrix (2026-11-06)

Written by the sandbox-commit-gate-ceiling plan session on 2026-11-06, while a
bd-ib ledger write hold (S5 claim-token cutover) and the dispatch freeze were
both in force. Its purpose is to make the plan's own Proof of Done capture
mechanical: for each plan assertion it names the run evidence that proves it,
the marker or stage record that discriminates that evidence, and what is still
missing. The carrier map itself lives only in the epic's scope events (latest
carrier-map event 2026-11-05T14:09:50Z); it is repeated here as a reading aid.

## How a plan assertion is proved

Every plan assertion that is not `human_attested` is `host_captured`. One
capture records all five against a released orchestrator build that contains
every carrier's merge, checked by ancestry against the release tag. A separately
started session then replays it and posts `verified` through
`dispatcher.py post-plan-record`. The replay must postdate the latest carrier-map
event. A closed carrier does not by itself discharge an assertion. Because the
verified record must cover every assertion and postdate the latest `captured`
record, capture once, after the last carrier ships, rather than assertion by
assertion.

Read runs with `dispatcher.py inspect --factory petri <run-id> -o <dir>`, never
with the host PATH `fabro` (see `.ai/fabro-dispatch-diagnosis.md`). Factory
`needs-human/` branches are named by the dispatch id, not the item or run id.

## The matrix

| # | Assertion (abridged) | Carriers, status on 2026-11-06 ~13:40Z | Discriminating evidence in a run export |
|---|---|---|---|
| 1 | An implement commit whose hook outlasts one tool call completes with the hook's own verdict | sufca7, xj3qqb, jzuryr closed; csbito in acceptance (merged #4528, in v0.294.0) | `implement_hook_route` prints `LIVESPEC_IMPLEMENT_COMMIT_RUN_SETTLED_REENTER` ("the implement turn ended while a commit run it started was still running and that commit run has PASSED"), or `implement_commit_settle` logs `{"settled": [{"run_id": "commit-…", "state": "passed"}]}` for a run the turn left running |
| 2 | That commit carries every trailer the hook wrote, and the run publishes it with no human finishing it | sufca7 closed; csbito in acceptance | the same run's published pull request: the commit carries both `TDD-Red-*` and `TDD-Green-*` blocks, and the run reaches `pr`/`verify_pr` with no hand step in its record |
| 3 | A commit leg that ends without a hook verdict is reported as having none and is not treated as a commit | sufca7, xj3qqb, jzuryr closed | `implement_hook_route` prints `LIVESPEC_IMPLEMENT_COMMIT_RUN_NO_VERDICT_REENTER` ("the commit run the implement turn left running ended without a verdict and made no commit"), and the next `implement` brief names no commit for that run |
| 4 | An implement turn ending incomplete after a hook refusal, with re-entry budget left, re-enters implement with the hook's failed targets in its brief | y7372n closed | `implement_hook_route` prints `LIVESPEC_IMPLEMENT_HOOK_REFUSED_REENTER` ("… naming failed targets: <targets>"), and the following `implement@N+1` brief carries those targets. `LIVESPEC_IMPLEMENT_INCOMPLETE_REENTER` ("no recorded failing gate") is NOT this case |
| 5 | Every needs-human ending names its failing stage's recorded cause, and after a hook-refused commit names the hook's exit status and failed targets | 36d3x5, k3nmbi, 2h512 closed; lraacg ready (blocked on csbito by a code-ordering edge) | the needs-human cause on the item names the stage and its recorded cause; after `LIVESPEC_IMPLEMENT_HOOK_REFUSED_BUDGET_EXHAUSTED` it carries `hook exit status:` and `failed targets:` |

## Candidate runs already read

- `livespec-dev-tooling-4pchid` run `01M6Q6KDJN6A` (v0.291.0). Its
  `implement_hook_route@1` printed `LIVESPEC_IMPLEMENT_INCOMPLETE_REENTER`, so it
  does NOT prove assertion 4. Its `implement_hook_route@2` budget-exhausted
  cause names `hook exit status: 1` and `failed targets: unknown, because the
  hook's recorded output names no failed target`. That is a candidate for
  assertion 5's second half on a build that predates lraacg, so re-read it on
  the capture build rather than citing it.
- `bd-ib-mr7673` run `01M6RACSCPAA` (v0.294.0, green). Its implement turn waited
  out both of its own commits, so no settle happened. It proves neither 1 nor
  csbito's host leg. Cause: a `workflow.fabro`-only Green amend takes the
  commit hook's doc-only path (bd-ib-w5yzzt).
- `bd-ib-csbito` runs `01M6QQWJQXZN` and `01M6R220BS7E` predate v0.294.0 and are
  failure evidence, not proof.

## What is still missing

1. A run on v0.294.0+ whose implement turn ends with its runner commit still
   running and that settles to PASSED. That run is csbito's host-leg proof
   AND the evidence for plan assertions 1 and 2. Screen candidate runs by
   grepping their exports for `COMMIT_RUN_SETTLED_REENTER` or a non-empty
   `implement_commit_settle` `settled` list.
2. A run on the capture build showing `HOOK_REFUSED_REENTER` (assertion 4) and
   one showing `COMMIT_RUN_NO_VERDICT_REENTER` (assertion 3). Either may come
   from any fleet repository's run on that build.
3. lraacg merged and released, then a needs-human ending on that build for
   assertion 5.

Only after those exist: one `captured` plan record, a replay by a separate
session, the independent completeness review, then archive.
