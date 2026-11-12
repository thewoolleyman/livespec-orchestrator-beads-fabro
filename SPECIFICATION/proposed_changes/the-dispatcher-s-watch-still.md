---
topic: the-dispatcher-s-watch-still
author: claude-opus-5-5:dispatcher-run-watch-cost
created_at: 2026-11-12T02:23:09Z
---

## Proposal: A bound run's watchdog poll reads status and stages by id and reads events only when the run changed or a cancel is near

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A bound run's watchdog poll reads the run's status and stage list by its id in one request. The stage list becomes a progress source of the same kind as the event stream, including for the open command node and for node completions. A poll whose status and stage list are unchanged issues no other read. Events are read only at a stage boundary, at a terminal state, when the run needs a human, and once before any stall cancel or not-progressing budget grading. Scenario 173 gains six cases; its heading is unchanged.

### Motivation

Owning work item bd-ib-22j24v, "The Dispatcher's watch still reads each bound run's full fabro inspect record and a fabro events read on every poll", under plan dispatcher-run-watch-cost (epic bd-ib-k7ymgx). spec-implementation-lockstep re-judged it spec-change tier on v0.320.0 with verdict partial, topic the-dispatcher-s-watch-still. That verdict is right. Scenario 173 and the "Observing the run" paragraph already state the by-id read and its terminal, disappeared and unobservable outcomes. Nothing states that the read is one status-and-stage-list request, that an unchanged poll makes no events read, or when events are read. The "Progress" paragraph names only the agent heartbeat and the event stream as sources, and "Progress past the budget" grades node completion from the event stream alone. Measured on the dev VPS (plan research notes 002 and 003): the per-poll full fabro events read cost 7.18 CPU-s per live run per minute. The released incremental read (bd-ib-u6llci) cut that to 3.61, still five times the plan's 0.72 target. Every poll still issues a fabro inspect (about 781 KB of JSON) and a fabro events read, whether or not the run changed. GET /api/v1/runs/{id}/stages returned 20.9 KB in 1.1 s for a 72-stage run. Each stage carries its handler, status, start instant and elapsed time, so the open command node and node completions read directly from it. Events stay necessary within a long agent stage, whose progress shows only in its events, so this proposal requires one incremental events read before any stall cancel or not-progressing budget grading, rather than none. In-flight survey: open spec PRs #4990 (plan-record artifact paths) and #4988 (reconcile-runs-prints-a-bare) touch other sections. The pending a-live-run-whose-dispatcher proposal (revise v357 in flight) applies the wall-budget paragraphs from reconciliation and does not change how a poll reads; this proposal aligns with it.

### Proposed Changes

1. contracts.md, §"Dispatcher progress watchdog", paragraph **Progress.**:
   a. Insert this sentence immediately after "A source that carries an older instant MUST NOT mask a source that carries a newer one.":
      "The run's stage list, read under "Observing the run" below, is a source of the same kind as the run's event stream: the newest start or completion instant it reports for any stage is a progress instant, and a command-node stage it reports started and not completed is an open command node whose start is that stage's start instant."
   b. Replace "While the run's event stream shows a command node started and not completed" with "While the run's stage list or its event stream shows a command node started and not completed". The rest of that sentence is unchanged.

2. contracts.md, same section, paragraph **Observing the run.**: insert these sentences immediately before "Scenario 173 in `scenarios.md` exercises this paragraph.":
   "The per-run read of a bound run MUST return the run's status and its stage list together, in one request to the factory. A poll whose status and stage list are both unchanged since the same Dispatcher process's previous poll of that run MUST issue no other read of the run, and in particular no `fabro events` read, unless clause (d) below applies. The watchdog MUST read the run's events only when (a) a stage of the run started or completed since that previous poll, the first poll after the run's id is bound counting as such a change; (b) the run is in a terminal state; (c) the run needs a human; or (d) the stall rule or the budget rule of this section would otherwise cancel the run at this poll. Before the watchdog cancels a run as `stalled-no-progress`, and before it grades a run past its budget as not progressing, it MUST read the run's events since the newest event instant it has observed, and MUST apply that read's progress instant and node completions before it decides. Every events read the watchdog issues remains governed by §"Bounded Fabro event reads", and a failed events read is treated as that subsection and the rules above already require."

3. contracts.md, same section, paragraph **Progress past the budget.**: in clause (b), replace "the run's own event stream records the completion of a workflow node that had not completed earlier in the same run" with "the run's stage list or its own event stream records the completion of a workflow node that had not completed earlier in the same run". No other text changes.

4. scenarios.md, "## Scenario 173 — The progress watchdog observes its bound run by id and never lists the factory's run history": the heading is unchanged. Append these cases inside its gherkin block, after the case "A failed per-run read is not a disappearance" and before the closing fence:

  Scenario: A bound run's poll reads its status and stage list in one request
    Given a dispatch whose run id the Dispatcher has bound
    When the watchdog polls the run
    Then the poll reads the run's status and its stage list by the run's id in one request to the factory
  Scenario: An unchanged poll issues no other read
    Given a dispatch whose run id the Dispatcher has bound
    And the run's status and stage list are unchanged since this Dispatcher process's previous poll of the run
    And neither the stall rule nor the budget rule would cancel the run at this poll
    When the watchdog polls the run
    Then the poll issues no fabro events read and no other read of the run
  Scenario: A stage boundary triggers an incremental events read
    Given a dispatch whose run id the Dispatcher has bound
    And a stage of the run started or completed since the previous poll
    When the watchdog polls the run
    Then the poll reads the run's events since the newest event instant this Dispatcher process has observed
  Scenario: A terminal run or a run needing a human triggers an incremental events read
    Given a dispatch whose bound run is in a terminal state or needs a human
    When the watchdog polls the run
    Then the poll reads the run's events since the newest event instant this Dispatcher process has observed
  Scenario: An open command node read from the stage list holds off the stall cancel
    Given a dispatch whose bound run's stage list reports a command-node stage started and not completed
    And every source has been unchanged for the whole stall window
    And the node's resolved timeout has not elapsed since that stage's start instant
    When the watchdog polls the run
    Then the run is not cancelled as stalled-no-progress
  Scenario: Events are read before a stall cancel
    Given a dispatch whose bound run's status and stage list have been unchanged for the whole stall window
    And no command node is open
    When the watchdog polls the run
    Then it reads the run's events since the newest event instant it has observed before it decides
    And it does not cancel the run when that read reports a progress instant inside the stall window

No H2 heading changes, so tests/heading-coverage.json is unchanged.
