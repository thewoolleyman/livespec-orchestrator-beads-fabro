## The maintainer's statement of what done means

The follow-ups - put them all under a single epic and plan if they are not already under one.

## Definition of Done assertions derived from that statement

- Every follow-up defect this plan collects is a child of this plan's epic or of another live plan's epic, and the research note names which.
- A healthy run launched after a reconcile sweep's journal snapshot is not cancelled by that sweep as superseded.
- A run whose workflow completed with status succeeded is not recorded by the Dispatcher as a failed dispatch when the engine lost its run store after the terminal event.
- A post-merge janitor red names the check target that actually failed, not the last target whose stderr the log tail happened to carry.
- A reconcile-merged invocation given a repository name instead of a path is refused with a message naming the path requirement, not a missing connection prefix.

# Run lifecycle false verdicts, 2026-10-09

Four faults measured while driving plan fabro-currency's P4 wave on 2026-10-09. Each one produced a WRONG VERDICT about a run or a dispatch at the surface an operator reads, and each had a plausible, healthy-looking explanation that was not the cause. They are collected here because none of them belongs to the plan that found them, and two of them were filed nowhere.

## The faults

1. **Orphan sweep cancels a run stamped after its journal snapshot.** `bd-ib-gh5xwq`. The fabro-currency dispatch of `bd-ib-227cbw` launched run `01M4FRSXDJX27VJCSCH6F52284` and journaled its stamp at 07:26:18Z; a sibling session's dispatch of `bd-ib-4ouajy` had started its pre-dispatch reconcile pass at 07:26:00Z, read the journal before that stamp, and at 07:26:30Z cancelled the new run as `superseded-run` (journal rows `dispatch-run-stamp`, `orphan-run-reconciled`, `reconcile-runs-pass`; hp server log `POST /api/v1/runs/01M4FRSXDJX27VJCSCH6F52284/cancel` from the dev-token principal). Mechanism: `_dispatcher_reconcile_runs_attribution.py` takes the journal's newest `dispatch-run-stamp` per item and returns `superseded-run` for any inventory run whose id differs; the snapshot is read once at pass start.

2. **Engine loses its run store after success; the Dispatcher reports failed.** Not yet filed before this plan. hp run `01M4EWVTGAH7MYP6XJH5DMHM7Z` for `bd-ib-qytzf4` completed every node through `verify_pr` with outcome succeeded and the hp journal logged `Workflow run completed ... status="succeeded"` at 03:15:21Z, but the same journal logged `Failed to write run event error=worker lost canonical run store during append run event` twice, so the run record carries `Worker exited before emitting a terminal run event: exit status: 0` and `fabro ps -a` shows failed/0ms. The Dispatcher took the record at face value and reported the dispatch failed; the work had already published PR 2683, which merged. Engine side is the 0.254 carrier (`8869e88`); whether the Petri candidate shares it is a fabro-currency cutover question.

3. **Post-merge janitor red names the wrong target.** Not yet filed before this plan. `reconcile-merged` for `bd-ib-qytzf4` reported `post-merge janitor red ... : python dev-tooling/check-spec-governance-default-block.py`, a target that passes. `_dispatcher_engine_janitor.py` renders `tail(text=janitor.stderr)`, and the aggregate runner prints its `Failed targets (N):` list to stdout, which neither the detail nor the journal keeps. The real failing targets (`check-per-file-coverage`, `check-coverage`, five credential tests reading the host token pool, now `bd-ib-656k7i`) were recoverable only by re-running the aggregate in the kept checkout under the credential wrapper.

4. **A repository name on `--repo` is refused as a missing connection prefix.** Not yet filed before this plan. `reconcile-merged --repo livespec-orchestrator-beads-fabro` (the name, as the runbook bullet's `<repo>` placeholder reads) resolved the store config against a relative path that does not exist, read an empty block, and raised `ConnectionPrefixMissingError: connection.prefix is required ... set it explicitly in .livespec.jsonc` for a repository whose config declares it. `_config.py` already carries a comment that this refusal names the wrong cause when the block is empty.

## Where each follow-up lives

- `bd-ib-gh5xwq` orphan sweep race: this plan.
- Engine run-store loss after success: this plan, filed at creation.
- Janitor red misattribution: this plan, filed at creation.
- `--repo` name refusal: this plan, filed at creation.
- `bd-ib-k627ja` no-auto-background environment: plan `pr-stage-backgrounded-push-fault` (`bd-ib-ctagnf`), Definition of Done item 3, filed and dispatched 2026-10-09.
- `bd-ib-656k7i` credential-test isolation from the host token pool: owned by the overseer's bounded recovery of `bd-ib-n44n4e`, no orchestrator plan; it blocks every `reconcile-merged` on this tenant because the janitor runs under the credential wrapper.

## Why one plan

Each fault converts a healthy or completed run into a false failure, a false cancellation, or a false cause. A session that trusts the surface re-dispatches finished work, hunts a target that passes, or edits a config key that is already set. The common repair shape is the same: the verdict must be computed from evidence at least as new as the thing it judges, and must name what it actually measured.
