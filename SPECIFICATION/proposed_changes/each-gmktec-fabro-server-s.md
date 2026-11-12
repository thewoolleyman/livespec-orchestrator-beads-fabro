---
topic: each-gmktec-fabro-server-s
author: claude-opus-5-5
created_at: 2026-11-12T17:44:17Z
---

## Proposal: A live dispatch claim counts against wip_cap only while its factory run is live

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Today term 1 of the counted-claims rule (contracts.md §"Per-repo WIP cap") counts every `active` row whose dispatch lock belongs to a live process. The dispatching process stays alive through a run's post-run legs (merge wait, acceptance), so a repository's `wip_cap` binds on items that hold no factory run slot, and a repository with `wip_cap` N can be held at zero admissions while fewer than N of its runs are actually running. This proposal narrows term 1 to claims whose own dispatch journal records a factory run that has not yet reached a terminal outcome, or that has been admitted and not yet reached its run launch. A claim whose journaled factory run has ended, and a live lock that never routes a factory run, stop counting. Term 2 (unreadable journal counts) and the tenant scope stay as they are, so `wip_cap` becomes a per-repository fairness share of live factory runs while each Fabro server's own `max_concurrent_runs` remains the one fleet concurrency limit.

### Motivation

Work item bd-ib-rtzhfc, bullet 3 ("`dispatcher.wip_cap` can no longer bind on items that hold no factory run slot"). The item was refused at launch at 2026-11-12T17:10Z as spec-change tier, linked topic each-gmktec-fabro-server-s, verdict unstated, and legacy-coordinator-agent routed it as a genuine spec change: bullet 3 contradicts contracts.md:5797-5801 (term 1 counts any live-lock row) and :5851 (the value domain). This is the WIP-cap half of the maintainer's 2026-11-04 "one queue, one number" consolidation; the fleet-launch-scripts half (bullets 1-2, under ## Provisional fleet launch scripts) is drafted separately by legacy-dispatcher-agent under the same linked topic. Of the item's two alternatives, this proposal keeps `wip_cap` as an explicit per-repository share and changes what it counts, rather than retiring it to null: a null fleet-bound would remove the per-repository fairness the drain relies on, and the counted quantity is what made the cap bind on finished work. The tenant-scope clause (contracts.md §"Host concurrency belongs to the Fabro scheduler", "The counted-claim bound ... MUST be computed from this repository's own state ONLY") forbids asking the factory whether a run is live, so liveness is read from the repository's own dispatch journal. In-flight survey: 12 open spec proposals, none touching `wip_cap` or counted claims; no alignment relationship applies.

### Proposed Changes

**1. Term 1 counts a live claim only while its factory run is live (`contracts.md` §"Per-repo WIP cap").** Replace the numbered list and the paragraph that follows it (from "A row at status `active` counts against `wip_cap` when, and only when, either of the following holds:" through "... MUST NOT present \"rows at status `active`\" as if it were the counted quantity.") with:

> A row at status `active` counts against `wip_cap` when, and only when, either of the following holds:
>
> 1. it holds a dispatch lock whose recorded process identifier — that of the LOCAL dispatching process — belongs to a live process, AND its dispatch journal, read for this claim, records either (a) that the claim was admitted to a factory route and no factory run has yet been journaled for it, or (b) a factory run for the claim that has not yet reached a terminal outcome; or
> 2. it does NOT hold such a lock, is NOT classified rework-pending (a lock-less row carrying `rework:pending` is a sanctioned park, EXCLUDED unconditionally per §"Rework-pending re-dispatch" and Scenario 66's third sub-scenario — even when its journal is unreadable), and its dispatch journal could not be READ.
>
> A row holding a live dispatch lock whose dispatch journal could not be READ MUST be counted, under the same fail-closed rule as term 2.
>
> A row at status `active` that satisfies none of these MUST NOT be counted. In particular, a claim whose journaled factory run has reached a terminal outcome MUST NOT be counted while its dispatching process carries the run's post-run legs (publication, the merge wait, post-merge acceptance), and a live dispatch lock whose claim was never admitted to a factory route — a host-side or hand-built implementation that creates no factory run — MUST NOT be counted. A row whose dispatch reached a green terminal outcome is reclaimed and MUST NOT be counted. So a repository MAY hold more rows at status `active` than `wip_cap` without any admission having exceeded the bound, and a repository holding `wip_cap` rows at status `active` of which fewer than `wip_cap` have a live factory run MUST still be admitted. Every surface that reports capacity MUST NOT present "rows at status `active`" as if it were the counted quantity.

**2. What the share bounds (`contracts.md` §"Per-repo WIP cap", first paragraph).** After "... that ceiling belongs to the Fabro server's own scheduler (§\"Host concurrency belongs to the Fabro scheduler\").", add:

> `wip_cap` is therefore a per-repository FAIRNESS SHARE of live factory runs, not a fleet concurrency limit: the one limit on how many runs a factory executes at once is that Fabro server's own `max_concurrent_runs`. A repository that commits a `wip_cap` value SHOULD record the basis for that value in a comment beside the key in its `.livespec.jsonc`.

**3. Unchanged.** Term 2 and its fail-closed paragraph, the automatic-path scope and the hand-picked override, the tenant scope of term 1, and the value domain (a non-negative integer, `0` the dispatch-off posture) MUST remain as ratified. Liveness under the new term 1 MUST be read from the repository's own dispatch journal, consistent with §"Host concurrency belongs to the Fabro scheduler"'s tenant-scope clause; the counted-claim computation MUST NOT ask a factory whether a run is live.

**4. Scenario (`scenarios.md`).** Append the scenario below, numbered at revise time.

## Scenario <number assigned at revise> — A live dispatch claim counts against wip_cap only while its factory run is live

```gherkin
Feature: wip_cap is a share of live factory runs, not of live dispatch processes
  Scenario: a claim in its post-run legs does not count
    Given a per-repo wip_cap of 2
    And two work-items at status `active`, each holding a dispatch lock whose recorded pid is live
    And one item's dispatch journal records a factory run that has not reached a terminal outcome
    And the other item's dispatch journal records a factory run that reached a terminal outcome, while its dispatching process waits on the pull request's merge
    When the Dispatcher evaluates admission for an admission-eligible ready item
    Then the counted claim total is 1
    And the ready item is admitted
  Scenario: an admitted claim counts before its run is created
    Given a per-repo wip_cap of 1
    And one work-item at status `active` holding a live dispatch lock whose journal records its admission to a factory route and no factory run yet
    When the Dispatcher evaluates admission for another admission-eligible ready item
    Then the counted claim total is 1
    And the ready item is not admitted
  Scenario: a live lock with no factory route does not count
    Given a per-repo wip_cap of 1
    And one work-item at status `active` holding a live dispatch lock whose journal records no admission to a factory route
    When the Dispatcher evaluates admission for an admission-eligible ready item
    Then the counted claim total is 0
    And the ready item is admitted
  Scenario: an unreadable journal behind a live lock still counts
    Given a per-repo wip_cap of 1
    And one work-item at status `active` holding a live dispatch lock whose dispatch journal cannot be read
    When the Dispatcher evaluates admission for an admission-eligible ready item
    Then the counted claim total is 1
    And the ready item is not admitted
```

**5. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading, with `test: "TODO"`, `work_item: "bd-ib-rtzhfc"` and a non-empty `reason` naming the tier the owed test runs at (integration), and the matching `tests/heading-coverage-debt.json` entry, carried through `resulting_files[]` or edited directly in that commit. The row and entry MUST carry the heading as numbered at revise. Scenario 58 MUST remain as ratified: its counted row holds a live lock and, under the new term 1, is counted only while that claim's factory run is live or not yet launched, which its Given already implies.
