---
topic: pre-launch-reads-bounded-per-dispatch-pass
author: claude-opus-5-5
created_at: 2026-10-24T01:34:46Z
---

## Proposal: pre-launch-reads-bounded-per-dispatch-pass

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a **Pre-launch reads.** paragraph to §"Bounded Fabro event reads" (under §"Grooming and slice-size calibration" in contracts.md) that bounds the Dispatcher's work between the start of a dispatch pass and its `fabro run` submission: the dispatch journal MUST be parsed at most once per dispatch pass, each distinct factory run MUST be the subject of at most one `fabro inspect` per pass, every reader in the pass MUST share those results, and the number of such reads MUST NOT grow with the number of earlier runs, warnings, candidates or attempts the pass evaluates. Five new scenarios inside Scenario 227 state that behaviour as call counts a unit test can assert.

### Motivation

Work-item bd-ib-6bbcda measured, on 2026-10-23 on the operator host under plugin release 0.239.0, three dispatches to the gmktec production factory whose pre-launch phase (the work the Dispatcher does before it submits `fabro run`) dominated the dispatch. bd-ib-2b2uqa reached `fabro run` about 23 minutes after its dispatcher started and held 25m34s of CPU; bd-ib-57ss2n's dispatcher held 26m33s of CPU at the same instant; bd-ib-kyeor4's dispatcher had used 15m27s of CPU over 31m32s of wall time, at an RSS of 1.8 GB, had journaled no stage, and was running `fabro inspect <run> --json` serially over older gmktec runs. One such inspect takes about 1 s by hand, so the CPU is the Dispatcher's own processing. The dispatch journal was 306 MB at the time. The suspected mechanism is a re-read of that journal per factory run, per warning or per attempt, plus a per-older-run `fabro inspect` fan-out repeated by several readers (ACP hold evidence, availability confirmation, selection replay, cost sequence, session-headroom baseline); the work-item deliberately leaves the profile as its first step. The cost lands on every dispatch, ahead of the source-branch push, while the dispatch holds a fleet slot and a launch marker.

No ratified clause bounds this phase. Nothing limits journal reads or per-run `fabro inspect` calls to once per dispatch pass, so an implementation whose cost multiplies with run history conforms today. The generalization target is §"Grooming and slice-size calibration" in contracts.md, whose §"Dispatcher progress watchdog" already rules that "the cost of a poll MUST NOT grow with the factory's run history" and whose §"Bounded Fabro event reads" already rules that "One `reconcile-runs` pass MUST issue at most one `fabro events` read per run." This proposal extends that same bounded-read principle, in the same subsection, to the pre-launch phase's journal and `fabro inspect` reads. The clause is stated as call counts per dispatch pass rather than as a CPU or wall-clock budget, because a count is what a unit test can assert and it holds whichever module the host profile names as dominant; the measured minutes above are the motivation, not the bar. The work-item's own host-captured criteria (a cProfile naming the dominant functions, and under 3 CPU-minutes against a journal of at least 300 MB on the released build) remain its acceptance evidence and are not restated as specification.

### Proposed Changes

Two coordinated edits. Both MUST land together in a single revision.

**1. `SPECIFICATION/contracts.md` §"Grooming and slice-size calibration" → §"Bounded Fabro event reads".** Insert one new paragraph immediately after the paragraph that begins "**Concurrency.** One `reconcile-runs` pass MUST issue at most one `fabro events` read per run." and immediately before the existing sentence "Scenario 227 in `scenarios.md` exercises this subsection." That closing sentence is kept unchanged and therefore also covers the new paragraph. The new paragraph is:

```
**Pre-launch reads.** The same bounded-read principle governs the reads the
Dispatcher makes before it launches a run. A dispatch pass is the work one
Dispatcher invocation does for one work-item from the start of that item's
dispatch until it submits `fabro run` for it, or until it refuses, defers or
abandons the dispatch without submitting; under `dispatcher.py loop` each
item the loop dispatches is its own pass. Within one dispatch pass the
Dispatcher MUST read and parse the dispatch journal at most once, and every
reader that consults the journal during that pass — the ACP hold-evidence,
availability-confirmation and selection-replay readers, the cost-sequence
reader, the session-headroom baseline, and any other — MUST consume that one
parsed snapshot rather than reading the file again. A record the pass itself
appends to the journal MUST be visible to the pass's later readers without a
second read of the file. Within one dispatch pass the Dispatcher MUST issue
at most one `fabro inspect` for each distinct pair of factory and run id, and
every reader that needs that run's state during the pass MUST consume that
one result. A `fabro inspect` that fails, or whose answer cannot be
interpreted, MUST NOT be reissued within the same pass; each reader MUST
apply to it the rule it already applies to an unobservable read of that
run. The number of dispatch-journal reads and `fabro inspect` calls in one
dispatch pass MUST NOT grow with the number of earlier runs, warnings, ACP
candidates or attempts the pass evaluates. A parsed snapshot or an inspect
result MUST NOT be carried from one dispatch pass into the next, so each
pass observes the journal and the factory as they stand when it starts.
```

**2. `SPECIFICATION/scenarios.md` §"Scenario 227 — Fabro event reads are bounded in size, retries and concurrency".** Inside that scenario's single `gherkin` block, insert the following scenarios immediately after the existing scenario "A reconcile pass deduplicates reads of one run" and immediately before the existing scenario "Concurrent reads are capped across processes on one host":

```gherkin
  Scenario Outline: A dispatch pass parses the dispatch journal once however long the run history is
    Given a dispatch journal holding records for <earlier> earlier runs on the target factory
    And the pre-launch readers for hold evidence, availability confirmation, selection replay, cost sequence and session-headroom baseline each consult the journal
    When one dispatch pass runs from the start of the item's dispatch to its fabro run submission
    Then the dispatch journal is read and parsed exactly once in that pass
    And every one of those readers receives the same parsed snapshot

    Examples:
      | earlier |
      | 1       |
      | 50      |

  Scenario: A dispatch pass inspects each factory run at most once
    Given the target factory holds three earlier runs that the hold-evidence, availability-confirmation and selection-replay readers each need
    When one dispatch pass evaluates those readers before submitting fabro run
    Then exactly one fabro inspect is issued for each of the three runs
    And each reader receives that run's single inspect result

  Scenario: Records the pass appends are visible without re-reading the journal
    Given a dispatch pass that journals a session-headroom assessment before a later reader consults the journal
    When the later reader consults the journal in the same pass
    Then it sees the appended assessment
    And the dispatch journal file is still read only once in that pass

  Scenario: A failed inspect is not reissued within the pass
    Given a fabro inspect of an earlier run fails during a dispatch pass
    When two further readers in the same pass need that run's state
    Then no second fabro inspect of that run is issued in the pass
    And each of those readers treats the run as unobservable under its own existing rule

  Scenario: Each loop pass reads afresh
    Given dispatcher.py loop dispatches two work-items in succession
    When the second item's dispatch pass starts
    Then it reads the dispatch journal once for itself rather than reusing the first pass's snapshot
    And it issues its own fabro inspect for each run it needs rather than reusing the first pass's results
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit. The new paragraph lands inside the existing `### Bounded Fabro event reads` subsection and the new scenarios land inside the existing Scenario 227 H2.

