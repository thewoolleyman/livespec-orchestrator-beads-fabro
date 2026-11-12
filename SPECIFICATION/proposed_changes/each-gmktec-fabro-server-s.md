---
topic: each-gmktec-fabro-server-s
author: claude-opus-5-5
created_at: 2026-11-12T17:44:17Z
---

## Proposal: A live dispatch claim stops counting against wip_cap only on positive journal evidence that it holds no factory run

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Today term 1 of the counted-claims rule (contracts.md §"Per-repo WIP cap") counts every `active` row whose dispatch lock belongs to a live process. The dispatching process stays alive through a run's post-run legs (the merge wait and acceptance), so a repository's `wip_cap` binds on items that hold no factory run slot. A repository with `wip_cap` N can then be held at zero admissions while fewer than N of its runs are actually running.

This proposal keeps term 1 counting every live-lock claim, and excludes one only on POSITIVE evidence in the claim's own dispatch journal. Either the latest factory run journaled for the claim has reached a terminal outcome, or the journal records a route for the claim that creates no factory run. A live lock whose journal records no route yet still counts, so the window between claim and route cannot over-admit. A live lock whose journal this checkout cannot read still counts, whether the journal belongs to this checkout or to another checkout of the tenant. Term 2 and the tenant scope stay as they are.

`wip_cap` thereby becomes a per-repository fairness share of live factory runs, and each Fabro server's own `max_concurrent_runs` remains the one fleet concurrency limit. The rule is FLEET-SCOPED: admission for every consumer tenant the Dispatcher serves inherits it, whichever factory that tenant's runs route to. It is not specific to the gmktec Fabro servers named in the topic.

### Motivation

Work item bd-ib-rtzhfc, bullet 3: "`dispatcher.wip_cap` can no longer bind on items that hold no factory run slot". The item was refused at launch at 2026-11-12T17:10Z as spec-change tier (linked topic each-gmktec-fabro-server-s, verdict unstated). legacy-coordinator-agent routed it as a genuine spec change, because bullet 3 contradicts contracts.md:5797-5801 (term 1 counts any live-lock row) and :5851 (the value domain).

This is the WIP-cap half of the maintainer's 2026-11-04 "one queue, one number" consolidation. The fleet-launch-scripts half (bullets 1-2, under ## Provisional fleet launch scripts) is drafted separately by legacy-dispatcher-agent under the same linked topic.

The item offers two alternatives. This proposal keeps `wip_cap` as an explicit per-repository share and changes what it counts, rather than retiring it to null. A null fleet bound would remove the per-repository fairness the drain relies on, and the counted quantity is what made the cap bind on finished work.

The tenant-scope clause (contracts.md §"Host concurrency belongs to the Fabro scheduler": "The counted-claim bound ... MUST be computed from this repository's own state ONLY") forbids asking the factory whether a run is live, so the exclusion evidence is read from the repository's own dispatch journal.

In-flight survey: the pending in-tree the-launcher-holds-one-wip-number (bd-ib-5k2yq2) edits the launcher repository WIP gate, which reads the counted-claims count through the capacity projection (contracts.md §"Provisional fleet launch scripts", "Repository WIP gate."). This proposal changes which claims that count holds, not how the launcher reads it or what it does at the cap, so the two compose in either revise order. Relation: `align`. No other pending proposal touches `wip_cap` or counted claims.

### Proposed Changes

**1. Term 1 excludes a live claim only on positive journal evidence (`contracts.md` §"Per-repo WIP cap").** Replace the numbered list and the paragraph that follows it (from "A row at status `active` counts against `wip_cap` when, and only when, either of the following holds:" through "... MUST NOT present \"rows at status `active`\" as if it were the counted quantity.") with:

> A row at status `active` counts against `wip_cap` when, and only when, either of the following holds:
>
> 1. it holds a dispatch lock whose recorded process identifier — that of the LOCAL dispatching process — belongs to a live process, UNLESS its dispatch journal, read for this claim, records POSITIVE evidence that the claim holds no factory run: either (a) the latest factory run journaled for the claim has reached a terminal outcome, or (b) the claim was routed to an implementation route that creates no factory run (a host-side or hand-built implementation); or
> 2. it does NOT hold such a lock, is NOT classified rework-pending (a lock-less row carrying `rework:pending` is a sanctioned park, EXCLUDED unconditionally per §"Rework-pending re-dispatch" and Scenario 66's third sub-scenario — even when its journal is unreadable), and its dispatch journal could not be READ.
>
> The exclusion in term 1 MUST rest on a journal record that is present and read. A live-lock claim whose journal records no route yet MUST be counted, so that the interval between claim and route cannot over-admit. A live-lock claim whose dispatch journal could not be READ MUST be counted, under the same fail-closed rule as term 2.
>
> A row at status `active` that satisfies neither term MUST NOT be counted. In particular, a claim whose latest journaled factory run has reached a terminal outcome MUST NOT be counted while its dispatching process carries the run's post-run legs (publication, the merge wait, post-merge acceptance). A row whose dispatch reached a green terminal outcome is reclaimed and MUST NOT be counted. So a repository MAY hold more rows at status `active` than `wip_cap` without any admission having exceeded the bound. A repository holding `wip_cap` rows at status `active`, of which fewer than `wip_cap` are counted, MUST still be admitted. Every surface that reports capacity MUST NOT present "rows at status `active`" as if it were the counted quantity.
>
> This rule governs the Dispatcher's admission for EVERY consumer tenant it serves, whichever factory that tenant's runs route to. No tenant and no Fabro server is exempt from it, and none MAY count claims by a different rule.

**2. What the share bounds (`contracts.md` §"Per-repo WIP cap", first paragraph).** Replace "Total LEDGER-level fleet concurrency is the sum of the per-repo caps." with:

> The sum of the per-repo caps bounds the live factory runs that the Dispatcher's automatic admission paths admit across the fleet.

After "... that ceiling belongs to the Fabro server's own scheduler (§\"Host concurrency belongs to the Fabro scheduler\").", add:

> `wip_cap` is therefore a per-repository FAIRNESS SHARE of live factory runs, not a fleet concurrency limit: the one limit on how many runs a factory executes at once is that Fabro server's own `max_concurrent_runs`. A repository that commits a `wip_cap` value SHOULD record the basis for that value in a comment beside the key in its `.livespec.jsonc`.

**3. Remote claims get no relief (`contracts.md` §"Per-repo WIP cap", the tenant-scope paragraph).** After "... tenant-scoping applies fully to term 1 and MUST NOT be read as extended to those by this section.", add:

> Term 1's journal-evidence exclusion is per-checkout in the same way. A checkout MAY exclude a live-lock claim only on its own read of that claim's dispatch journal. A live dispatch lock registered by ANOTHER checkout of the tenant, whose dispatch journal the evaluating checkout cannot read, MUST be counted. The exclusion therefore never lowers the count a checkout computes for a claim held elsewhere.

**4. Unchanged.** Term 2 and its fail-closed paragraph, the automatic-path scope and the hand-picked override, the tenant scope of term 1, and the value domain (a non-negative integer, `0` the dispatch-off posture) MUST remain as ratified. The counted-claim computation MUST NOT ask a factory whether a run is live.

**5. Scenario 58 (`scenarios.md` §"Scenario 58 — Rows at status active are not the counted quantity").** No H2 heading is added, renamed or removed.

In the existing scenario "A repo holding more active rows than wip_cap still admits a ready item", replace "And every dispatch journal is readable" with:

```gherkin
  And every dispatch journal is readable
  And the locked item's dispatch journal records a factory run that has not reached a terminal outcome
```

Then append the following four scenarios inside the same gherkin block, after that scenario's last step:

```gherkin
Scenario: A claim in its post-run legs does not count
  Given a per-repo wip_cap of 2
  And two work-items at status `active`, each holding a dispatch lock whose recorded pid is live
  And one item's dispatch journal records a factory run that has not reached a terminal outcome
  And the other item's dispatch journal records that its latest factory run reached a terminal outcome, while its dispatching process waits on the pull request's merge
  When the Dispatcher evaluates admission for an admission-eligible ready item
  Then the counted claim total is 1
  And the ready item is admitted

Scenario: A live claim with no route recorded yet counts
  Given a per-repo wip_cap of 1
  And one work-item at status `active` holding a live dispatch lock whose readable journal records neither a route nor a factory run for the claim
  When the Dispatcher evaluates admission for another admission-eligible ready item
  Then the counted claim total is 1
  And the ready item is not admitted

Scenario: A live lock routed to a route that creates no factory run does not count
  Given a per-repo wip_cap of 1
  And one work-item at status `active` holding a live dispatch lock whose journal records that the claim was routed to an implementation route that creates no factory run
  When the Dispatcher evaluates admission for an admission-eligible ready item
  Then the counted claim total is 0
  And the ready item is admitted

Scenario: An unreadable journal behind a live lock still counts
  Given a per-repo wip_cap of 1
  And one work-item at status `active` holding a live dispatch lock whose dispatch journal cannot be read by the evaluating checkout
  When the Dispatcher evaluates admission for an admission-eligible ready item
  Then the counted claim total is 1
  And the ready item is not admitted
```

**6. Revise co-edit.** None is owed. No H2 heading changes, and Scenario 58's existing `tests/heading-coverage.json` row (`test: "TODO"`, `work_item: "bd-ib-heat"`) and its `tests/heading-coverage-debt.json` entry continue to cover the extended scenario unchanged.
