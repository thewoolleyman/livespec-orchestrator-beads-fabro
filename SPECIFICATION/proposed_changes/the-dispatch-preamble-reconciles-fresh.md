---
topic: the-dispatch-preamble-reconciles-fresh
author: claude-opus-5-5:anthropic-burn-mitigation
created_at: 2026-11-14T03:07:42Z
---

## Proposal: The dispatch preamble reconciles its own item every time and the whole fleet only when no fresh fleet pass exists

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Today every dispatch, and every loop tick, runs the full fleet-wide reconciliation pass: every declared factory's run inventory, every stranded claim, every ended run's collection, and a full-ledger read. The host timer's standalone `reconcile-runs` sweep already does the same pass every ten minutes. This proposal keeps the standalone sweep fleet-wide. The dispatch preamble, which is also the loop's per-tick reconciliation, ALWAYS reconciles the work-items it is about to dispatch. It takes the fleet-wide pass only when this host's dispatch journal holds no FRESH fleet reconciliation record. A record is fresh when it completed within a new `dispatcher.reconcile_freshness_seconds` window (default 1200), surveyed every declared factory, and recorded no error. It also makes the one-record-per-pass journal entry a stated contract, with the scope and coverage fields the freshness test reads.

### Motivation

Plan anthropic-burn-mitigation (epic bd-ib-b2jzxw), carrier work item bd-ib-5d5aue ("A dispatch still spends about 3 CPU-minutes of drive process-tree CPU before its Fabro run starts"). Its host-captured bound is under 60 CPU-seconds before the Fabro run starts, and it FAILED on the released build v0.328.0 at 213.23 CPU-seconds (host_recorded on PR #5154).

Measured on vmi3006760, 2026-11-14, released build c1f8445faf3b:
- Process-tree profile of bd-ib-pqpgc5's dispatch. dispatch-preamble was 84.45 CPU-seconds by journal and 95.36 by profile, over 130 s wall.
- py-spy of bd-ib-defs3b's dispatcher (dispatch-preamble 110.59 CPU-seconds by journal). 87% of the dispatcher's in-process CPU was `reconcile_runs_pass` → `_survey`: one parse of the 413 MB dispatch journal, ACP selection replay, a full-ledger `bd list --status all --limit 0` read only to find merge-hold labels, and per-claim stranded-claim measurement.
- In pqpgc5's preamble window, that pass judged 13 stranded claims and collected another item's ended run (`fabro events`, inspect, sandbox termination). None of them was the item being dispatched.
- So the per-dispatch cost is O(fleet), not O(item), and it duplicates the host timer. `reconcile-runs.timer` fires the same fleet-wide pass with OnUnitActiveSec=10min, and its last four passes each consumed 5.5 to 6.2 CPU-minutes.
- Removing the preamble's fleet-wide pass when a fresh one exists saves an estimated 75 to 95 CPU-seconds of an 85 to 110 CPU-second dispatch-preamble.

The cut changes ratified text, which is why it is a proposal rather than a rework rider:
- contracts.md §"A factory run never awaits a human": "Reconciliation runs on every Dispatcher loop tick and in the dispatch preamble".
- §"Stranded claim release", the **Survey** bullet: "Every reconciliation surface named in §\"A factory run never awaits a human\" (the loop tick, the dispatch preamble, and the standalone `reconcile-runs` sweep) MUST also survey...".
- §"Stale publish-branch reclaim before a re-dispatch": "It runs AFTER the dispatch preamble's orphan reconciliation".

The complementary non-spec cuts are bd-ib-5d5aue's second-rework rider: a label-filtered merge-hold read, batched shows and one metadata projection.

Freshness is per host because only the owning host may recover a claim (§"Stranded claim release" → "Only the owning host recovers a claim"). A fleet pass on another host proves nothing about this host's claims, and the dispatch journal is a per-host file.

In-flight survey, 2026-11-14:
- The pending in-tree proposal a-needs-human-cause-comment inserts a bullet AFTER the "Every reconciliation surface (loop, preamble, standalone sweep," bullet, which this proposal does not edit. Aligned.
- No open spec pull request touches these clauses; checked 22 open `spec/*` pull requests.
- The remote `spec/*` branches touching them are stale revise branches 1,156 to 3,860 commits behind master, carrying text master already holds.
- Topic the-reconcile-runs-host-timer (bd-ib-cwuxfi) adds "Reconciliation-pass reads" to §"Bounded Fabro event reads" for the standalone sweep. It is compatible: this proposal keeps the standalone sweep fleet-wide and changes no journal-read rule.

### Proposed Changes

1. contracts.md, §"A factory run never awaits a human": REPLACE the bullet that begins "- Reconciliation runs on every Dispatcher loop tick and in the dispatch preamble, and MUST also be runnable standalone" with the following two bullets. The tail of the existing bullet, from "A run whose item is `active` with a matching journaled run id is NOT an orphan even when no Dispatcher process is watching it." to its end, MUST be kept unchanged as the last sentence of the first new bullet.

"- Reconciliation runs in the dispatch preamble, which is also the Dispatcher loop's per-tick reconciliation, and MUST also be runnable standalone (a scheduled sweep). The standalone sweep exists so that an item closed by any route while no Dispatcher process is alive (a hand landing, a hand `bd close`, another session) still releases its run. The standalone `reconcile-runs` sweep MUST always take the FLEET pass: every declared factory's non-terminal run inventory, every claim §\"Stranded claim release\" → **Survey** names, and every ended-run collection, stale-assignee clearance and hold this section and the next require of a reconciliation pass. The dispatch preamble MUST always take the ITEM pass for each work-item it is about to dispatch. The item pass applies every one of those obligations restricted to that work-item: its non-terminal runs on every declared factory, its stranded claim and its stale assignee. The dispatch preamble MUST also take the fleet pass unless this host's dispatch journal holds a FRESH fleet reconciliation record (\"Reconciliation-pass record\" below). A run whose item is `active` with a matching journaled run id is NOT an orphan even when no Dispatcher process is watching it."

"- **Reconciliation-pass record.** Every reconciliation pass, whichever surface runs it, MUST append exactly ONE `reconcile-runs-pass` record to this repository's dispatch journal on the host that ran it, when the pass ends. The record MUST name its `scope` (`fleet` or `item`), the declared factories it surveyed, and the number of errors it met. An item pass MUST additionally name the work-items it covered. A fleet reconciliation record is FRESH for a dispatch preamble when ALL of the following hold: it was appended by a pass on the preamble's own host; its `scope` is `fleet`; it surveyed every factory declared under `dispatcher.factories` at the time the preamble reads it; it records zero errors; and it is no older than `dispatcher.reconcile_freshness_seconds` (non-negative number, default `1200` when absent) at the moment the preamble reads it. An item pass's record MUST NOT count as a fresh fleet record. A record the preamble cannot read, or a journal it cannot read, MUST be treated as no fresh record, and the preamble MUST take the fleet pass. A `dispatcher.reconcile_freshness_seconds` of `0` MUST make every dispatch preamble take the fleet pass. When the preamble takes the item pass alone, it MUST still append its own `item`-scoped record, and that record MUST NOT refresh the window."

2. contracts.md, §"Stranded claim release", the **Survey** bullet: REPLACE the opening clause "Every reconciliation surface named in §\"A factory run never awaits a human\" (the loop tick, the dispatch preamble, and the standalone `reconcile-runs` sweep) MUST also survey the ledger's `active` items assigned `fabro`, and every stale assignee as \"Stale assignee clearance\" below defines one." with:

"Every FLEET reconciliation pass named in §\"A factory run never awaits a human\" (the standalone `reconcile-runs` sweep, and the dispatch preamble whenever it takes the fleet pass) MUST also survey the ledger's `active` items assigned `fabro`, and every stale assignee as \"Stale assignee clearance\" below defines one. An ITEM pass MUST survey exactly the work-items it covers, under the same exclusions and with the same measurements."

The remainder of the bullet MUST be kept unchanged. That is the `merge-hold:` and `rework:pending` exclusions, the handed-off-rework reading, and the four measurements.

3. contracts.md, §"Stale publish-branch reclaim before a re-dispatch", its opening paragraph: REPLACE "It runs AFTER the dispatch preamble's orphan reconciliation (§\"A factory run never awaits a human\"), so a run that reconciliation terminated is already terminal when the reclaim asks;" with "It runs AFTER the dispatch preamble's reconciliation of that item, the item pass of §\"A factory run never awaits a human\", so a run of that item that reconciliation terminated is already terminal when the reclaim asks;". The rest of the sentence MUST be kept unchanged.

4. scenarios.md, §"Scenario 196 — Reconciliation releases or completes a stranded dispatch claim on its owning host, and holds with a named reason every claim it cannot prove stranded":

(a) In the `Scenario Outline: Every reconciliation surface releases a qualifying absent-run claim`, REPLACE its `Given` line with "Given a freshly prepared claim that satisfies every condition of the first absent-run release scenario" followed by "And this host's dispatch journal holds no fresh fleet reconciliation record". Leave its `When`, `Then` and `Examples` unchanged.

(b) IMMEDIATELY AFTER that outline's `Examples` table, and separated from it by one blank line, insert:

```gherkin
  Scenario: A dispatch preamble with a fresh fleet record reconciles only the items it dispatches
    Given this host's dispatch journal holds a fleet reconciliation record from this host, 300 seconds old, that surveyed every declared factory and recorded zero errors
    And dispatcher.reconcile_freshness_seconds is absent
    And item A, which the preamble is about to dispatch, has a non-terminal orphan run on a declared factory
    And item B, which the preamble is not dispatching, holds a qualifying absent-run claim
    When the dispatch preamble runs
    Then item A's orphan run is exported and terminated
    And item B keeps its claim and changes no status
    And the journal gains one reconcile-runs-pass record with scope item naming item A

  Scenario Outline: A dispatch preamble without a fresh fleet record takes the fleet pass
    Given this host's newest fleet reconciliation record <condition>
    And item B, which the preamble is not dispatching, holds a qualifying absent-run claim
    When the dispatch preamble runs
    Then item B is ready with no fabro assignee and one stranded-claim-release record names the reason run-absent
    And the journal gains one reconcile-runs-pass record with scope fleet

    Examples:
      | condition                                                        |
      | is 1500 seconds old with dispatcher.reconcile_freshness_seconds absent |
      | recorded one error                                               |
      | did not survey one of the declared factories                     |
      | was written by a pass on another host                            |
      | is absent                                                        |
      | is 10 seconds old with dispatcher.reconcile_freshness_seconds set to 0 |

  Scenario: An item pass's record never refreshes the window
    Given this host's newest fleet reconciliation record is 1500 seconds old
    And a dispatch preamble 60 seconds ago appended a reconcile-runs-pass record with scope item
    When the next dispatch preamble runs
    Then it takes the fleet pass

  Scenario: The standalone sweep always takes the fleet pass
    Given this host's dispatch journal holds a fresh fleet reconciliation record
    And item B holds a qualifying absent-run claim
    When the standalone reconcile-runs sweep runs
    Then item B is ready with no fabro assignee
    And the journal gains one reconcile-runs-pass record with scope fleet
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` does not change.
