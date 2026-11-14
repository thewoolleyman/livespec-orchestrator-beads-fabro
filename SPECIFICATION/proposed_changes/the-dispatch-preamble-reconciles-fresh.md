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

Today every dispatch, and every loop tick, runs the full fleet-wide reconciliation in its preamble. That covers every declared factory's run inventory, every stranded claim, every ended run's collection, and a full-ledger read. The host timer's standalone `reconcile-runs` sweep already does the same work about every ten minutes.

This proposal names two kinds of pass:
- The FLEET pass is the whole obligation set.
- The ITEM pass is that set restricted to the work-items being dispatched.

The standalone sweep always takes the fleet pass. The dispatch preamble takes the fleet pass only when this host's dispatch journal holds no FRESH fleet-pass record. A record is fresh when it is on this host, scoped `fleet`, not a dry run, covers every declared factory, records zero errors, and is no older than a new `dispatcher.reconcile_freshness_seconds` (default 1800).

The item pass always runs for the items being dispatched:
- For `dispatch`, it covers the requested items, in the preamble.
- For `loop`, it covers the items admission selected, after admission and before the publish-branch reclaim.

The proposal also makes the one-record-per-pass journal entry a stated contract, with the scope, dry-run, coverage and error fields the freshness test reads.

### Motivation

Plan anthropic-burn-mitigation (epic bd-ib-b2jzxw), carrier work item bd-ib-5d5aue ("A dispatch still spends about 3 CPU-minutes of drive process-tree CPU before its Fabro run starts"). Its host-captured bound is under 60 CPU-seconds before the Fabro run starts. It FAILED on the released build v0.328.0 at 213.23 CPU-seconds (host_recorded on PR #5154).

Measured on vmi3006760, 2026-11-14, released build c1f8445faf3b:
- Process-tree profile of bd-ib-pqpgc5's dispatch. dispatch-preamble was 84.45 CPU-seconds by journal and 95.36 by profile, over 130 s wall.
- py-spy of bd-ib-defs3b's dispatcher (dispatch-preamble 110.59 CPU-seconds by journal). 87% of the dispatcher's in-process CPU was `reconcile_runs_pass` → `_survey`: one parse of the 413 MB dispatch journal, ACP selection replay, a full-ledger `bd list --status all --limit 0` read only to find merge-hold labels, and per-claim stranded-claim measurement.
- In pqpgc5's preamble window, that pass judged 13 stranded claims and collected another item's ended run (`fabro events`, inspect, sandbox termination). None of them was the item being dispatched.
- So the per-dispatch cost is O(fleet), not O(item), and it duplicates the host timer. `reconcile-runs.timer` runs the same fleet-wide work, now OnUnitInactiveSec=10min with AccuracySec=1min. Its passes each consumed 5.5 to 6.2 CPU-minutes, and the measured gaps between its pass records are 1,047 to 1,081 s.
- Removing the preamble's fleet pass when a fresh one exists saves an estimated 75 to 95 CPU-seconds of an 85 to 110 CPU-second dispatch-preamble.

The cut changes ratified text, which is why it is a proposal rather than a rework rider:
- contracts.md §"A factory run never awaits a human": "Reconciliation runs on every Dispatcher loop tick and in the dispatch preamble".
- §"Stranded claim release", the **Survey** bullet: "Every reconciliation surface named in §\"A factory run never awaits a human\" (the loop tick, the dispatch preamble, and the standalone `reconcile-runs` sweep) MUST also survey...".
- §"Stale publish-branch reclaim before a re-dispatch": "It runs AFTER the dispatch preamble's orphan reconciliation".

The complementary non-spec cuts are bd-ib-5d5aue's second-rework rider: a label-filtered merge-hold read, batched shows and one metadata projection.

Freshness is per host because only the owning host may recover a claim (§"Stranded claim release" → "Only the owning host recovers a claim"). A fleet pass on another host proves nothing about this host's claims, and the dispatch journal is a per-host file.

Why the default is 1800 s: with the timer at OnUnitInactiveSec=10min plus AccuracySec=1min, a 10-minute pass puts the worst-case gap between fleet-pass records at about 1,260 s. 1800 s clears that with margin. The window SHOULD exceed the timer interval plus the longest pass plus the timer's accuracy. This is not a MUST, because the Dispatcher cannot observe the timer's configuration.

Terms: the topic the-reconcile-runs-host-timer uses "a reconciliation pass" for the standalone sweep, so this proposal says "fleet pass" and "item pass" throughout and never redefines that term.

In-flight survey, 2026-11-14:
- The pending in-tree proposal a-needs-human-cause-comment inserts a bullet AFTER the "Every reconciliation surface (loop, preamble, standalone sweep," bullet, which this proposal does not edit. Aligned.
- No open spec pull request touches these clauses; checked 22 open `spec/*` pull requests.
- The remote `spec/*` branches touching them are stale revise branches 1,156 to 3,860 commits behind master, carrying text master already holds.
- Topic the-reconcile-runs-host-timer (bd-ib-cwuxfi) adds "Reconciliation-pass reads" to §"Bounded Fabro event reads" for the standalone sweep. It is compatible: this proposal keeps the standalone sweep a fleet pass and changes no journal-read rule.

Graded PASS-WITH-FIXES by legacy-coordinator-agent (session 719514f8) on draft PR #5228. This revision applies its five fixes:
1. the item set for `dispatch` and for `loop`;
2. a dry-run record is never fresh;
3. default 1800 s, with the informative window guidance;
4. an unreadable record or journal, and a record with no scope field, are not fresh;
5. "fleet pass" and "item pass" as the terms throughout.

### Proposed Changes

1. contracts.md, §"A factory run never awaits a human": REPLACE the bullet that begins "- Reconciliation runs on every Dispatcher loop tick and in the dispatch preamble, and MUST also be runnable standalone" with the following two bullets. The tail of the existing bullet, from "A run whose item is `active` with a matching journaled run id is NOT an orphan even when no Dispatcher process is watching it." to its end, MUST be kept unchanged as the last sentence of the first new bullet.

"- Reconciliation takes one of two passes:
  - The FLEET pass is every obligation this section and the next place on reconciliation: every declared factory's non-terminal run inventory, every claim §\"Stranded claim release\" → **Survey** names, and every ended-run collection, stale-assignee clearance and hold.
  - The ITEM pass is those same obligations restricted to a named set of work-items: their non-terminal runs on every declared factory, their stranded claims and their stale assignees.

  Reconciliation MUST also be runnable standalone (a scheduled sweep), so that an item closed by any route while no Dispatcher process is alive (a hand landing, a hand `bd close`, another session) still releases its run. The standalone `reconcile-runs` sweep MUST always take the fleet pass.

  The dispatch preamble, which `dispatch` and every `loop` tick run before any candidate is selected, MUST take the fleet pass unless this host's dispatch journal holds a FRESH fleet-pass record (\"Fleet-pass and item-pass records\" below).

  Every dispatched work-item MUST be covered by an item pass before its publish-branch reclaim (§\"Stale publish-branch reclaim before a re-dispatch\") and before its run is submitted:
  - Under `dispatch`, the preamble MUST take the item pass for the requested work-items.
  - Under `loop`, the Dispatcher MUST take the item pass for the work-items the admission valve selected to launch, after admission and before the reclaim.

  A preamble that took the fleet pass has already covered every work-item, and MUST NOT be required to repeat the item pass for them.

  A run whose item is `active` with a matching journaled run id is NOT an orphan even when no Dispatcher process is watching it."

"- **Fleet-pass and item-pass records.** Every fleet pass and every item pass, whichever surface takes it, MUST append exactly ONE `reconcile-runs-pass` record to this repository's dispatch journal, on the host that took it, when the pass ends. The record MUST name:
  - its `scope` (`fleet` or `item`);
  - whether it was a dry run;
  - the declared factories it surveyed;
  - the number of errors it met.

  An item-pass record MUST additionally name the work-items it covered.

  A fleet-pass record is FRESH for a dispatch preamble only when ALL of the following hold:
  - a pass on the preamble's own host appended it;
  - its `scope` is `fleet`;
  - it was not a dry run;
  - it surveyed every factory declared under `dispatcher.factories` when the preamble reads it;
  - it records zero errors;
  - it is no older than `dispatcher.reconcile_freshness_seconds` (non-negative number, default `1800` when absent) when the preamble reads it.

  No other record is fresh:
  - A record that carries no `scope` field MUST NOT count as fresh. That includes every record written before this contract.
  - An item-pass record MUST NOT count as fresh.
  - A record the preamble cannot parse, or a journal it cannot read, MUST be treated as holding no fresh record, and the preamble MUST take the fleet pass.

  A `dispatcher.reconcile_freshness_seconds` of `0` MUST make every dispatch preamble take the fleet pass. An item-pass record MUST NOT refresh the window. The window SHOULD exceed the host's scheduled-sweep interval plus its longest fleet pass plus the scheduler's accuracy, so that a healthy schedule always leaves a fresh record. This is guidance, because the Dispatcher cannot observe the scheduler."

2. contracts.md, §"Stranded claim release", the **Survey** bullet: REPLACE the opening clause "Every reconciliation surface named in §\"A factory run never awaits a human\" (the loop tick, the dispatch preamble, and the standalone `reconcile-runs` sweep) MUST also survey the ledger's `active` items assigned `fabro`, and every stale assignee as \"Stale assignee clearance\" below defines one." with:

"Every fleet pass of §\"A factory run never awaits a human\" (the standalone `reconcile-runs` sweep's, and the dispatch preamble's whenever it takes one) MUST also survey the ledger's `active` items assigned `fabro`, and every stale assignee as \"Stale assignee clearance\" below defines one. Every item pass MUST survey exactly the work-items it covers, under the same exclusions and with the same measurements."

The remainder of the bullet MUST be kept unchanged. That is the `merge-hold:` and `rework:pending` exclusions, the handed-off-rework reading, and the four measurements.

3. contracts.md, §"Stale publish-branch reclaim before a re-dispatch", its opening paragraph: REPLACE "It runs AFTER the dispatch preamble's orphan reconciliation (§\"A factory run never awaits a human\"), so a run that reconciliation terminated is already terminal when the reclaim asks;" with:

"It runs AFTER the pass of §\"A factory run never awaits a human\" that covers that item, so a run of that item that the pass terminated is already terminal when the reclaim asks. Under `dispatch` that pass is the preamble's item or fleet pass. Under `loop` it is the preamble's fleet pass, or the item pass taken for the items admission selected;"

The rest of the sentence MUST be kept unchanged.

4. scenarios.md, §"Scenario 196 — Reconciliation releases or completes a stranded dispatch claim on its owning host, and holds with a named reason every claim it cannot prove stranded":

(a) In the `Scenario Outline: Every reconciliation surface releases a qualifying absent-run claim`, REPLACE its `Given` line with "Given a freshly prepared claim that satisfies every condition of the first absent-run release scenario", followed by "And this host's dispatch journal holds no fresh fleet-pass record". Leave its `When`, `Then` and `Examples` unchanged.

(b) IMMEDIATELY AFTER that outline's `Examples` table, separated from it by one blank line, insert:

```gherkin
  Scenario Outline: With a fresh fleet-pass record only the dispatched items are reconciled
    Given this host's dispatch journal holds a fleet-pass record from this host, 300 seconds old, not a dry run, that surveyed every declared factory and recorded zero errors
    And dispatcher.reconcile_freshness_seconds is absent
    And item A has a non-terminal orphan run on a declared factory
    And item B holds a qualifying absent-run claim
    When <invocation> dispatches item A
    Then item A's orphan run is exported and terminated before the publish-branch reclaim for item A
    And item B keeps its claim and changes no status
    And the journal gains one reconcile-runs-pass record with scope item naming item A

    Examples:
      | invocation                                          |
      | dispatcher.py dispatch requesting item A            |
      | a dispatcher.py loop pass whose admission selects item A |

  Scenario Outline: A dispatch preamble without a fresh fleet-pass record takes the fleet pass
    Given this host's newest fleet-pass record <condition>
    And item B, which is not being dispatched, holds a qualifying absent-run claim
    When the dispatch preamble runs
    Then item B is ready with no fabro assignee and one stranded-claim-release record names the reason run-absent
    And the journal gains one reconcile-runs-pass record with scope fleet

    Examples:
      | condition                                                               |
      | is 2000 seconds old with dispatcher.reconcile_freshness_seconds absent  |
      | recorded one error                                                      |
      | did not survey one of the declared factories                            |
      | was written by a pass on another host                                   |
      | was written by a dry-run pass                                           |
      | carries no scope field                                                  |
      | cannot be parsed                                                        |
      | is absent                                                               |
      | is 10 seconds old with dispatcher.reconcile_freshness_seconds set to 0  |

  Scenario: An unreadable dispatch journal makes the preamble take the fleet pass
    Given this host's dispatch journal exists but cannot be read
    And item B, which is not being dispatched, holds a qualifying absent-run claim
    When the dispatch preamble runs
    Then it takes the fleet pass
    And item B's claim is surveyed and measured

  Scenario: An item-pass record never refreshes the window
    Given this host's newest fleet-pass record is 2000 seconds old
    And a dispatch 60 seconds ago appended a reconcile-runs-pass record with scope item
    When the next dispatch preamble runs
    Then it takes the fleet pass

  Scenario: The standalone sweep always takes the fleet pass
    Given this host's dispatch journal holds a fresh fleet-pass record
    And item B holds a qualifying absent-run claim
    When the standalone reconcile-runs sweep runs
    Then item B is ready with no fabro assignee
    And the journal gains one reconcile-runs-pass record with scope fleet
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` does not change.
