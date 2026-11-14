---
topic: dispatch-journal-projection-and-retention
author: claude-opus-5-5
created_at: 2026-11-14T03:25:00Z
---

## Proposal: The dispatch journal keeps a maintained projection and archives rotated segments, so a dispatch pass reads a bounded window

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The Dispatcher maintains a projection beside the dispatch journal. The projection holds every fact a journal reader needs from beyond a bounded recent window: the latest record per item and per run, the append-only per-item lists, the global flags and dedupe sets, and the counters. When the active journal segment passes its bound, the Dispatcher rotates it into an archived segment and never deletes it. Within one dispatch pass, the Dispatcher still reads the journal at most once, but that one read covers the projection plus the active segment's records. Neither its bytes nor its CPU grow with the history that rotation has archived. A reader that needs history reads the projection, so no reader gives a different answer because rotation moved a record.

### Motivation

Work item bd-ib-dznxgv (plan gmktec-factory-placement, epic livespec-dev-tooling-me5aqz in the livespec-dev-tooling tenant). Its second Definition of Done bullet says the dispatch-preamble phase's CPU does not grow with journal records that belong to no item or run the pass reads. That is not met today. Its first bullet, one parse per pass, is met by the joined pass snapshot.

Measured 2026-11-14 by anthropic-burn-mitigation with py-spy at rate 50 (/var/tmp/livespec-dumps/5d5aue-profile/pyspy2/pyspy-2.raw: bd-ib-defs3b's dispatcher, build c1f8445faf3b, 02:09:28-02:11:51Z). The pass's one parse of the orchestrator's tmp/fabro-dispatch-journal.jsonl, pass_snapshot._extend, costs about 10.7 CPU-s at 413 MB, and 578 of the window's 1955 samples sit under _dispatcher_pass_snapshot. The file was 275 MB on 2026-11-05, 361 MB on 2026-11-11 and 413 MB on 2026-11-14, and nothing bounds it. Each launch holds a fleet cap slot through that pre-launch window.

The contract makes that growth mandatory. §"Bounded Fabro event reads" → "Pre-launch reads" says a parsed snapshot "MUST NOT be carried from one dispatch pass into the next, so each pass makes its own first read of the journal". With no retention, that first read is the whole history.

A pure time-window cut is NOT the answer. A read-only audit of origin/master 274c007dc found about 70 production read sites, and roughly two-thirds need more than a recent window. They fall into these classes:

- **Window-safe.** The selection-replay stamps (7 days), the session and codex headroom baselines (15-90 minutes), provider exhaustion (bounded by each record's expiry), the needs-attention journal fold (7 days), and the merge-poll rerun, run-turn guard and probe-cycle readers.
- **Latest-per-key, any age.** Admission claim accounting: a lost ledger-admit or outcome would record a false abandonment. Run attribution in the reconcile pass and sweeps: an old but live run would lose its item. The step gate: an uncleared degraded outcome would stop refusing. The rider claim instant: riders and the DoD subject digest would change. Also the latest proof rendering per repository, the latest acceptance park, and the stall and release rows.
- **Full per item.** Publish-branch liveness, the dispatch pull-request list, recovery routing and resume observation (every earlier run), and proof attribution (acceptance proof can cite an old or resumed run). Also the pre-run claim's fabro-run failure check and terminal preservation.
- **Global flags and dedupe sets.** The factory-size audit-started flag, the ACP observation ledger's "every observation ever carried" dedupe (a window brings back retired entries), and the ended-run collection refusals.
- **Aggregates.** The calibration fix_loop_count, counted across every dispatch of an item, and the reflection counters.
- **Offline history readers.** The fleet-launch evidence tools, calibration analysis, and the cross-repository reads of _dispatcher_fleet_run_collection.

This proposal makes no claim about the cost of three readers the audit found doing their own full read outside the snapshot (_dispatcher_step_persistence.py, _dispatcher_claim_reclaim.py, _dispatcher_claim_live_runs.py). They show no samples in the profiled preamble window, and a whole-pass profile that includes admission is owed before any claim is made. Either way, change 1 bars any such second read.

Track metric: PRs per repository per hour merged to main and green. This change shortens every launch's pre-launch window by the archived-history share of the parse, and that share grows every day.

In-flight alignment: default-align. No open spec pull request touches dispatch-journal reading or retention (surveyed 2026-11-14). Two items complement this one and do not overlap it. bd-ib-cwuxfi opens a pass snapshot in the standalone reconcile-runs command; it lands first by legacy-coordinator-agent's ruling. anthropic-burn-mitigation's pending propose-change under bd-ib-b2jzxw narrows the preamble's reconcile to the dispatched item, which concerns where the preamble reconciles, not how the journal is read. When this ratifies, bd-ib-dznxgv's Definition of Done names the new subsection beside its present references.

### Proposed Changes

**1. Pre-launch reads (`contracts.md` §"Bounded Fabro event reads" → "Pre-launch reads").** Replace the final sentence, "A parsed snapshot or an inspect result MUST NOT be carried from one dispatch pass into the next, so each pass makes its own first read of the journal and of each run it needs.", with:

> A parsed snapshot or an inspect result MUST NOT be carried from one dispatch pass into the next, so each pass makes its own first read of the journal and of each run it needs. That first read of the journal is a read of the journal projection together with the records of the active journal segment (§"Dispatch journal projection and retention"). Archived segments are not read during a dispatch pass. The bytes read and the CPU spent on the journal in one dispatch pass MUST NOT grow with the number of records in archived segments. No reader in the pass MAY open the journal file, an archived segment or the projection a second time to obtain records the pass's one read already holds.

**2. New subsection (`contracts.md`, a `### Dispatch journal projection and retention` subsection directly after §"Bounded Fabro event reads"):**

> ### Dispatch journal projection and retention
>
> The dispatch journal is an append-only audit record. A record, once written, is never edited or removed. Rotation moves records between files, and archiving keeps them.
>
> **Segments.** The journal is stored as one ACTIVE segment, which every append writes to, and zero or more ARCHIVED segments. When the active segment exceeds a configured size bound, the Dispatcher MUST rotate it: the active segment's file is replaced by a new, empty file, and the old file is kept as the newest archived segment. Several Dispatcher processes on one host append to the same journal; today the writer serializes appends only within one process, relying on append-mode writes across processes. Rotation MUST therefore be safe against concurrent appends from every Dispatcher process on the host: a record appended while a rotation runs MUST land in exactly one segment, and MUST NOT be lost or duplicated. The Dispatcher MUST NOT delete, truncate or rewrite an archived segment. Removing archived segments is an operator action outside the Dispatcher. Rotation MUST leave in the active segment at least the records any window-bounded reader consults: the longest fixed reader window plus a margin of at least one day, and every record whose own expiry has not yet passed.
>
> **Projection.** The Dispatcher MUST maintain a projection of the journal: a derived, versioned record of every fact that a journal reader consults and that may lie outside the active segment. The projection MUST carry at least:
>
> - per work-item: the latest ledger-admit, the latest outcome with its status, the latest dispatch-id, the latest claim instant, the latest run stamp with its factory, the latest rework-admit, the latest stall, release and cancel rows, the latest acceptance park, the merge mode, and the append-only lists of the item's run ids, dispatch ids, resume links and pull-request numbers;
> - per run: its owning work-item and its terminal-read, refusal and unavailable-attempt markers;
> - globally: the degraded outcomes not yet cleared, the factory-size audit flag, every ACP observation id ever journaled and the retired ids, the latest proof rendering per repository, and the calibration and reflection counters.
>
> The projection MUST reflect every record in every segment by the time any reader consumes it. It MAY be updated with each append, or folded forward by the reader from the projection's recorded coverage point to the end of the active segment. Either way, concurrent appends from several Dispatcher processes MUST NOT cause a record to be folded twice or skipped. A projection rebuilt by folding every segment in order MUST equal the projection maintained incrementally.
>
> **Reader classes.** A reader whose answer depends only on records inside a fixed recent window, or on records whose own expiry has not passed, MAY read the active segment alone. Every other reader MUST obtain the facts it needs beyond the active segment from the projection. That includes latest-record-per-key readers, full-history-per-item readers, dedupe-set readers and aggregate readers. No reader's answer MAY change because rotation moved a record from the active segment into an archived one.
>
> **Integrity.** If the projection is missing, cannot be parsed, carries a version the reading build does not know, or records a coverage point that does not lie within the journal's present segments, the Dispatcher MUST rebuild it from every segment before any reader consumes it, and MUST journal one `journal-projection-rebuilt` record naming the reason. A reader MUST NOT treat a projection that failed these checks as authoritative.
>
> **Offline readers.** Calibration analysis, the fleet-launch evidence tools and any cross-repository reader MAY read archived segments. A tool that needs the full record history MUST read every segment in order.
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
  Then the pass reads the projection and the active segment once
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

Scenario: A missing or stale projection is rebuilt before it is read
  Given a dispatch journal whose projection file is missing
  When a dispatch pass starts
  Then the Dispatcher rebuilds the projection from every segment before any reader consumes it
  And it journals one journal-projection-rebuilt record naming the reason

Scenario: Rotation archives and never deletes
  Given an active segment that has passed its size bound
  When the Dispatcher rotates the journal
  Then the old active segment is kept as the newest archived segment
  And no archived segment is deleted, truncated or rewritten
  And the new active segment still holds every record a window-bounded reader consults
```

**4. Heading coverage.** The revise pass that adds the scenario and the new `###` subsection MUST add the new `## Scenario NNN` heading to `tests/heading-coverage.json` in the same change. The subsection is a `###` heading under an existing `##` section, so it adds no H2 entry.
