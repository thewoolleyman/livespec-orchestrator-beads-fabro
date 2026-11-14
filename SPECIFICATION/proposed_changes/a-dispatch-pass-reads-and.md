---
topic: a-dispatch-pass-reads-and
author: claude-opus-5-5
created_at: 2026-11-14T03:25:00Z
---

## Proposal: A dispatch pass reads and parses the dispatch journal once, from a maintained projection and the active segment, so its cost does not grow with archived history

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The Dispatcher keeps a projection beside the dispatch journal. The projection holds every fact a journal reader needs from beyond a bounded recent window: the latest record per item, the outcome status per run, the append-only per-item lists, the global flags and dedupe sets, and the counters.

When the active journal segment passes its bound, the Dispatcher rotates it into an archived segment under a host-wide lock, and never deletes it. A dispatch pass still reads the journal at most once. That one read is the projection plus the active segment, so its bytes and CPU do not grow with archived history. A reader that needs history reads the projection, so rotation never changes any reader's answer.

### Motivation

Work item bd-ib-dznxgv (plan gmktec-factory-placement, epic livespec-dev-tooling-me5aqz in the livespec-dev-tooling tenant). Its second Definition of Done bullet is not met today: the dispatch-preamble phase's CPU must not grow with journal records that belong to no item or run the pass reads. Its first bullet, one parse per pass, is met by the joined pass snapshot.

The measurement, 2026-11-14, by anthropic-burn-mitigation with py-spy at rate 50 (/var/tmp/livespec-dumps/5d5aue-profile/pyspy2/pyspy-2.raw; bd-ib-defs3b's dispatcher, build c1f8445faf3b, 02:09:28-02:11:51Z):

- The pass's one parse of the orchestrator's tmp/fabro-dispatch-journal.jsonl, pass_snapshot._extend, costs about 10.7 CPU-s at 413 MB. 578 of the window's 1955 samples sit under _dispatcher_pass_snapshot.
- The file was 275 MB on 2026-11-05, 361 MB on 2026-11-11 and 413 MB on 2026-11-14. Nothing bounds it.
- Each launch holds a fleet cap slot through this pre-launch window.

The contract makes that growth mandatory. §"Bounded Fabro event reads" → "Pre-launch reads" says a parsed snapshot "MUST NOT be carried from one dispatch pass into the next, so each pass makes its own first read of the journal". With no retention, that first read is the whole history.

A pure time-window cut is NOT the answer. A read-only audit of origin/master 274c007dc found about 70 production read sites. About two-thirds need more than a recent window. Their classes:

- **Window-safe.** The selection-replay stamps (7 days); the session and codex headroom baselines (15-90 minutes); provider exhaustion (bounded by each record's own expiry); the needs-attention journal fold (7 days); the merge-poll rerun, run-turn guard and probe-cycle readers.
- **Latest per key, of any age.**
  - Admission claim accounting: a lost ledger-admit or outcome would record a false abandonment.
  - Run attribution in the reconcile pass and its sweeps: an old but live run would lose its item.
  - The step gate: an uncleared degraded outcome would stop refusing.
  - The rider claim instant: riders and the Definition-of-Done subject digest would change.
  - Also the latest proof rendering per repository, the latest acceptance park, and the stall and release rows.
- **Full per item.** Publish-branch liveness; the dispatch pull-request list; recovery routing and resume observation, which read every earlier run and its outcome; proof attribution, since acceptance proof can cite an old or resumed run; the pre-run claim's fabro-run failure check; terminal preservation.
- **Global flags and dedupe sets.** The factory-size audit-started flag; the ACP observation ledger's dedupe over "every observation the journal has EVER carried", where a window would bring back retired entries; the ended-run collection refusals.
- **Aggregates.** The calibration fix_loop_count, counted across every dispatch of an item, and the reflection counters.
- **Cross-repository in-pass readers.** _dispatcher_fleet_run_collection reads other repositories' journals inside the reconcile-runs pass (bd-ib-cwuxfi's surface), so it is a hot reader, not an offline one.
- **Offline history readers.** The fleet-launch evidence tools and calibration analysis.

This proposal makes no claim about the cost of three readers the audit found doing their own full read outside the snapshot: _dispatcher_step_persistence.py, _dispatcher_claim_reclaim.py and _dispatcher_claim_live_runs.py. They show no samples in the profiled preamble window. A whole-pass profile that includes admission is owed before any cost claim. Either way, change 1 bars any such second read.

Track metric: PRs per repository per hour merged to main and green. This change shortens every launch's pre-launch window by the archived-history share of the parse, and that share grows every day.

In-flight alignment: default-align. No open spec pull request touches dispatch-journal reading or retention (surveyed 2026-11-14). Two related items complement this one and do not overlap:

- bd-ib-cwuxfi opens a pass snapshot in the standalone reconcile-runs command. It lands first, by legacy-coordinator-agent's ruling.
- anthropic-burn-mitigation's pending propose-change under bd-ib-b2jzxw narrows the preamble's reconcile to the dispatched item. It concerns where the preamble reconciles, not how the journal is read.

When this ratifies, bd-ib-dznxgv's Definition of Done names the new subsection beside its present references.

### Proposed Changes

**1. Pre-launch reads (`contracts.md` §"Bounded Fabro event reads" → "Pre-launch reads").** Replace the final sentence, "A parsed snapshot or an inspect result MUST NOT be carried from one dispatch pass into the next, so each pass makes its own first read of the journal and of each run it needs.", with:

> A parsed snapshot or an inspect result MUST NOT be carried from one dispatch pass into the next, so each pass makes its own first read of the journal and of each run it needs. That first read of the journal reads the journal projection and folds the records from the projection's coverage point to the end of the active segment (§"Dispatch journal projection and retention"). Rotation always advances the coverage point to the boundary of the segment it archives (that subsection), so the fold never reads an archived segment. The bytes read and the CPU spent on the journal in one dispatch pass MUST NOT grow with the number of records in archived segments. The one exception is a projection rebuild that the integrity rules of that subsection require. Such a rebuild is the pass's one journal read, is journaled as a `journal-projection-rebuilt` record, and is exempt from that bound. No reader in the pass MAY open the journal file, an archived segment or the projection a second time to obtain records the pass's one read already holds.

**2. New subsection (`contracts.md`, a `### Dispatch journal projection and retention` subsection directly after §"Bounded Fabro event reads"):**

> ### Dispatch journal projection and retention
>
> The dispatch journal is an append-only audit record. A record, once written, is never edited or removed. Rotation moves records between files, and archiving keeps them.
>
> **Segments.** The journal is stored as one ACTIVE segment, to which every append is written, and zero or more ARCHIVED segments.
>
> **The journal lock.** Every Dispatcher process on a host serializes on one host-wide advisory lock: an exclusive `flock` on a lock file kept beside the journal. It is a cross-process lock, distinct from any in-process thread lock.
>
> - An append takes the lock for the whole of its open-write-close of the active segment.
> - A projection fold that writes the projection takes the lock for the whole of the fold and the projection write.
> - Rotation takes the lock exclusively and, while holding it, MUST: (1) fold every record up to the active segment's end into the projection, (2) record in the projection a coverage point at that boundary, naming the segment the next fold starts from, (3) rename the active segment's file to the newest archived segment, and (4) create a new, empty active segment.
>
> An append can therefore never open the old active segment after the rename. Every record lands in exactly one segment, and is neither lost nor duplicated.
>
> The Dispatcher MUST rotate when the active segment exceeds a configured size bound. It MUST NOT delete, truncate or rewrite an archived segment; removing archived segments is an operator action outside the Dispatcher. Rotation MUST leave in the active segment at least the records that any window-bounded reader consults: the longest fixed reader window plus a margin of at least one day, and every record whose own expiry has not yet passed.
>
> **Projection.** The Dispatcher MUST maintain a projection of the journal: a derived, versioned record of every fact that a journal reader consults and that may lie outside the active segment. The projection MUST carry at least:
>
> - per work-item: the latest ledger-admit; the latest outcome with its status; the latest dispatch-id; the latest claim instant; the latest run stamp with its factory; the latest rework-admit; the latest stall, release and cancel rows; the latest acceptance park; the merge mode; and the append-only lists of the item's run ids, dispatch ids, resume links and pull-request numbers;
> - per run: its owning work-item, its outcome status (so a reader of an item's earlier runs, such as recovery routing, can read each prior run's outcome), and its terminal-read, refusal and unavailable-attempt markers;
> - globally: the degraded outcomes not yet cleared; the factory-size audit flag; every ACP observation id ever journaled and the retired ids; the latest proof rendering per repository; and the calibration and reflection counters.
>
> The projection records a coverage point: the segment and byte offset up to which it reflects every record. A reader brings the projection current by folding forward from the coverage point to the end of the active segment, either holding the journal lock or reading without it and discarding the fold when the coverage point it began from has moved. Concurrent appends and folds from several Dispatcher processes MUST NOT cause any record to be folded twice or skipped. A projection rebuilt by folding every segment in order from empty MUST equal the projection maintained incrementally over the same records.
>
> **Reader classes.** A reader whose answer depends only on records inside a fixed recent window, or on records whose own expiry has not passed, MAY read the active segment alone. Every other reader MUST obtain the facts it needs from beyond the active segment through the projection. That covers latest-record-per-key readers, full-history-per-item readers, dedupe-set readers and aggregate readers. No reader's answer MAY change because rotation moved a record from the active segment into an archived one.
>
> **Integrity.** The Dispatcher MUST rebuild the projection from every segment, in order, before any reader consumes it, when the projection:
>
> - is missing;
> - cannot be parsed;
> - carries a version the reading build does not know; or
> - records a coverage point that does not lie within the journal's present segments.
>
> The rebuild runs under the journal lock. It MUST journal one `journal-projection-rebuilt` record naming the reason. A reader MUST NOT treat a projection that failed these checks as authoritative.
>
> **Cross-repository readers.** A pass that reads another repository's journal, as the fleet run collection does inside the reconcile-runs pass, MUST read that repository's projection plus its active segment, under the same rules, and MUST NOT read that repository's archived segments.
>
> **Offline readers.** Calibration analysis, the fleet-launch evidence tools and any other tool run outside a dispatch or reconcile pass MAY read archived segments. A tool that needs the full record history MUST read every archived segment, oldest first, and then the active segment.
>
> Scenario NNN in `scenarios.md` exercises this subsection.

**3. New scenario (`scenarios.md`, appended at the next free Scenario number when revised):**

```gherkin
## Scenario NNN — A dispatch pass reads the journal projection and active segment, and rotation changes no reader's answer

Feature: Dispatch-journal reads stay bounded as history grows
  As an operator whose factory launches wait on each dispatch pass's preamble
  I want the pass to read a bounded journal window plus a maintained projection
  So that the pre-launch cost does not grow with archived history and no reader loses a fact

Scenario: Archived history does not add to one pass's journal read
  Given a repository whose dispatch journal has archived segments totalling many times the active segment's size
  When one dispatch pass for a work-item runs to its fabro run submission
  Then the pass reads the projection and folds only the active segment, once
  And the pass opens no archived segment
  And the journal bytes the pass reads do not grow when further segments are archived

Scenario: An admission whose ledger-admit was rotated out is not an abandonment
  Given a work-item whose latest ledger-admit and outcome records lie in an archived segment
  When admission accounts the repository's claimed active items
  Then it reads that item's latest ledger-admit and outcome from the projection
  And it records no abandonment for that item

Scenario: A live run keeps its owning item after rotation
  Given a run still listed on a factory whose dispatch-run-stamp lies in an archived segment
  When the reconcile pass attributes the factory's runs
  Then the run is attributed to its owning work-item from the projection

Scenario: Recovery routing reads an earlier run's outcome after rotation
  Given a work-item whose earlier run's outcome record lies in an archived segment
  When recovery routing grades the item's next dispatch
  Then it reads that earlier run's outcome status from the projection's per-run record

Scenario: An append concurrent with rotation lands in exactly one segment
  Given two Dispatcher processes on one host, one appending a record while the other rotates the journal
  When both finish
  Then the appended record is in exactly one segment
  And it is reflected exactly once in the projection

Scenario: Concurrent folds neither double nor skip a record
  Given two Dispatcher processes that each fold the projection forward while a third appends records
  When all three finish
  Then every appended record is reflected in the projection exactly once

Scenario: A rebuilt projection equals the incrementally maintained one
  Given a journal with archived segments and an incrementally maintained projection
  When the projection is rebuilt by folding every segment in order from empty
  Then the rebuilt projection equals the incrementally maintained projection

Scenario Outline: An integrity failure rebuilds the projection before it is read
  Given a dispatch journal whose projection <defect>
  When a dispatch pass starts
  Then the Dispatcher rebuilds the projection from every segment before any reader consumes it
  And that rebuild is the pass's one journal read
  And it journals one journal-projection-rebuilt record naming <reason>

  Examples:
    | defect                                                   | reason                 |
    | is missing                                               | missing                |
    | cannot be parsed                                         | unparseable            |
    | carries a version the reading build does not know        | unknown-version        |
    | records a coverage point outside the present segments    | coverage-out-of-range  |

Scenario: Rotation archives, advances the coverage point and never deletes
  Given an active segment that has passed its size bound
  When the Dispatcher rotates the journal
  Then the old active segment is kept as the newest archived segment
  And the projection's coverage point is at that segment's end
  And no archived segment is deleted, truncated or rewritten
  And the new active segment still holds every record a window-bounded reader consults

Scenario: A cross-repository reader in the reconcile-runs pass reads no archives
  Given another repository whose dispatch journal has archived segments
  When the reconcile-runs pass collects that repository's runs
  Then it reads that repository's projection and active segment
  And it opens none of that repository's archived segments

Scenario: An offline reader reads every segment in order
  Given a journal with archived segments
  When calibration analysis reads the full record history
  Then it reads every archived segment oldest first and then the active segment
  And it sees every record exactly once
```

**4. Heading coverage.** The revise pass that adds the scenario and the new `###` subsection MUST add the new `## Scenario NNN` heading to `tests/heading-coverage.json` in the same change. The subsection is a `###` heading under an existing `##` section, so it adds no H2 entry.
