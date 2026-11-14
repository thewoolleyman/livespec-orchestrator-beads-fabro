---
topic: the-reconcile-runs-host-timer
author: claude-opus-5-5:dispatcher-run-watch-cost
created_at: 2026-11-12T04:46:24Z
---

## Proposal: A standalone reconcile-runs pass reads and parses each dispatch journal at most once

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Bounded Fabro event reads" → "Pre-launch reads" makes a dispatch pass read and parse the dispatch journal at most once and hand every reader that one snapshot, and "Once per loop pass" keeps that rule per pass. No clause gives the standalone `reconcile-runs` sweep the same guarantee, and the host timer's passes re-read and re-parse each multi-hundred-megabyte journal once per stranded claim and once per reader. This proposal adds a "Reconciliation-pass reads" paragraph to the same subsection: within one standalone `reconcile-runs` pass the Dispatcher MUST read and parse this repository's dispatch journal at most once, every journal reader in the pass MUST consume that snapshot, a record the pass appends MUST be visible to its later readers without a second read, and the fleet run collection MUST read and parse each other dispatching repository's journal at most once per pass. The read count MUST NOT grow with the number of claims, runs or readers the pass evaluates, and no snapshot is carried into the next pass. Four new scenarios in Scenario 227 exercise it.

### Motivation

Owning work item bd-ib-cwuxfi, "The reconcile-runs host timer re-parses each dispatch journal many times per pass, because its standalone command opens no pass snapshot". Its restart re-dispatch was refused at the dispatch-time spec-tier wall at 2026-11-12T04:30:10Z on spec v357, held for this topic: the spec-stated judgement reported the asked-for behaviour unstated ("The visible text bounds `fabro events` reads per `reconcile-runs` pass and requires the survey to read the dispatch journal. It never says a standalone pass reads and parses each dispatch journal at most once or that readers share one snapshot") and named "## Dispatcher policy settings" as the heading to generalize. This proposal places the rule in §"Bounded Fabro event reads" instead, beside the "Pre-launch reads" paragraph that already states the identical rule for a dispatch pass, so the two pass kinds read as one principle; the stranded-claim survey under §"Dispatcher policy settings" is one of the readers it governs.

Measured on vmi3006760, plugin build 37e012335ed2, 140 `reconcile-runs.service` passes from 2026-11-10 21:00Z to 2026-11-11 20:53Z: median 264 CPU-seconds and 3.5 GB memory peak per pass, one pass at the 1,800 s start timeout. A py-spy profile put 60% of active samples inside `json.loads`, reached once per claim from `survey_stranded_claims`, from the fleet collection's reads of other repositories' journals, from `read_journaled_runs` and from `read_journal_tail`. One read of this repository's 361 MB journal costs 9.9 CPU-seconds and 1.8 GB RSS. Cause: `run_reconcile_runs_command`, the timer's entry point, never opens the pass snapshot that the dispatch and loop paths open, so every reader falls back to its own full read, and `read_dispatching_repository` reads each other repository's journal the same way. bd-ib-6bbcda fixed the same defect class for the dispatch paths, which is what "Pre-launch reads" ratifies. The pass's CPU and memory targets stay on the item as host-captured proof, not in this requirement.

Routed to plan dispatcher-run-watch-cost (epic bd-ib-k7ymgx) on legacy-coordinator-agent's ruling (session b3a6daf9, 2026-11-11). In-flight survey: open PR #4998 (attended-human-publishing-identity), the open v358 revises (#4999 and the-dispatcher-s-watch-still) and the eight remote `spec/*` branches touch no reconciliation-pass journal text. The pending in-tree proposals reconcile-runs-prints-a-bare and a-needs-human-rest-overwrites edit §"Dispatcher policy settings" and are compatible and aligned with; the-dispatcher-s-watch-still edits the run watch's Fabro reads, not the journal.

### Proposed Changes

1. contracts.md, §"Bounded Fabro event reads": IMMEDIATELY AFTER the "Pre-launch reads" paragraph (which ends "A parsed snapshot or an inspect result MUST NOT be carried from one dispatch pass into the next, so each pass makes its own first read of the journal and of each run it needs."), and BEFORE the line "Scenario 227 in `scenarios.md` exercises this subsection.", insert this paragraph, separated from each by one blank line:

"**Reconciliation-pass reads.** The same principle governs the standalone reconciliation sweep. A reconciliation pass is one run of the standalone `dispatcher.py reconcile-runs` command, whether an operator or a host timer starts it. Within one reconciliation pass the Dispatcher MUST read and parse this repository's dispatch journal at most once, and every reader that consults that journal during the pass — the stranded-claim survey of §\"Stranded claim release\", the journaled-runs reader, the journal-tail reader, and any other — MUST consume that one parsed snapshot rather than reading the file again. A record the pass itself appends to the journal MUST be visible to the pass's later readers without a second read of the file. When the pass collects runs across every dispatching repository it reaches, it MUST read and parse each other dispatching repository's dispatch journal at most once in that pass, and every reader of that repository's journal in the pass MUST consume that one parsed snapshot. The number of dispatch-journal reads in one reconciliation pass MUST NOT grow with the number of claims, runs, holds or readers the pass evaluates; it MUST NOT exceed one for this repository plus one for each other dispatching repository the pass reaches. A journal read that fails MUST NOT be reissued within the same pass; each reader MUST apply to that journal the rule it already applies to a journal that cannot be read. A parsed snapshot MUST NOT be carried from one reconciliation pass into the next, so each pass makes its own first read of each journal."

No other paragraph of the subsection changes, and the closing line "Scenario 227 in `scenarios.md` exercises this subsection." stays as it is.

2. scenarios.md, §"Scenario 227 — Fabro event reads are bounded in size, retries and concurrency": inside that section's gherkin block, insert these four scenarios IMMEDIATELY AFTER `Scenario: Each loop pass reads afresh` (whose last step is "And it issues its own fabro inspect for each run it needs rather than reusing the first pass's results") and BEFORE `Scenario: Concurrent reads are capped across processes on one host`, each separated from its neighbours by one blank line:

```gherkin
  Scenario Outline: A standalone reconcile-runs pass parses this repository's journal once however many claims it surveys
    Given a dispatch journal holding records for <claims> active items assigned fabro
    And the stranded-claim survey, the journaled-runs reader and the journal-tail reader each consult the journal
    When one standalone reconcile-runs pass runs
    Then this repository's dispatch journal is read and parsed exactly once in that pass
    And every one of those readers receives the same parsed snapshot

    Examples:
      | claims |
      | 1      |
      | 35     |

  Scenario: A standalone reconcile-runs pass parses each other dispatching repository's journal once
    Given the pass reaches two other dispatching repositories whose runs it collects
    And more than one reader in the pass consults each of those repositories' journals
    When one standalone reconcile-runs pass runs
    Then each of those repositories' dispatch journals is read and parsed exactly once in that pass

  Scenario: Records a reconcile-runs pass appends are visible without re-reading the journal
    Given a standalone reconcile-runs pass that journals a stranded-claim-hold record before a later reader consults the journal
    When the later reader consults the journal in the same pass
    Then it sees the appended record
    And this repository's dispatch journal file is still read only once in that pass

  Scenario: Each reconcile-runs pass reads afresh
    Given the host timer starts two standalone reconcile-runs passes in succession
    When the second pass starts
    Then it reads each dispatch journal once for itself rather than reusing the first pass's snapshot
```

No H2 heading is added, removed or renamed, so `tests/heading-coverage.json` needs no co-edit.
