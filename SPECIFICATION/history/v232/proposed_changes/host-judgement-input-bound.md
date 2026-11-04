---
topic: host-judgement-input-bound
author: claude-opus-5-5
created_at: 2026-10-26T21:57:26Z
---

## Proposal: A host Definition-of-Done judgement bounds each candidate's total model input at 100,000 tokens

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

In 'Host judgements take the resolved dod_gate chain': each host taking of the Definition-of-Done judgement ends a candidate whose requests together report 100,000 input tokens, treats it as no verdict so the next candidate runs, and records the deciding candidate's total input tokens.

### Motivation

Routed by petri-factory-on-gmktec under the coordinator's standing direction, spec-first for work-item bd-ib-jp2qr2 of plan anthropic-burn-mitigation (epic bd-ib-b2jzxw), whose dispatch screen found that its only reference, Scenario 239, does not govern its two assertions. Measured 2026-10-26 on one host taking launched as `claude -p --model opus --allowedTools Read,Grep,Glob` from this repository: three API requests, each re-sending a context of about 128,000 tokens, so one grading consumed about 380,000 input tokens for a 116,806-character prompt. Nothing in the ratified text bounds a taking's input. The bound is placed in "Host judgements take the resolved `dod_gate` chain" because it already defines no-verdict fallback along the chain; an over-bound candidate is one more no-verdict case. Usage is counted by request (a Claude transcript repeats one request's usage on every content-block record), and cache reads count, because they are what the measured re-sending consumed.
A first read-only Codex review raised three blockers, folded in: when the bound is checked (every usage report and the final one before a verdict is accepted) and what ending a candidate means; scoping to the pre-admission and pre-dispatch fallback chains, leaving the preflight's independently graded chain alone; and the record's shape (complete, partial or unreported totals, and no deciding candidate when the chain exhausts).
A second pass required that the Dispatcher enable and consume every per-request usage reporting a candidate supports, so the unreported exception cannot be reached by leaving reporting off; that is folded in.
A third pass required counting aggregate usage reports (for example a turn-level total) without double-counting, and reserving unreported for a candidate that reports no input usage at all; that is folded in, with an aggregate-only scenario case.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance", paragraph "**Host judgements take the resolved `dod_gate` chain.**", insert immediately after the sentence ending "or one that returns no verdict (a timeout or an unparseable reply), passes the judgement to the next candidate." the following sentences:

```
In the pre-admission and pre-dispatch takings of the Definition-of-Done judgement, which take their verdict from the first candidate that returns one, the Dispatcher MUST bound the total model input of each candidate it runs; a repository preflight's independently graded chain is outside this bound. A candidate's input is the input tokens its output reports for its model requests, uncached, cache-written and cache-read alike, whether reported per request or as an aggregate covering several requests; each request is counted once however many times its report is repeated, and never both in its own report and in an aggregate that covers it. The Dispatcher MUST check the running total at every usage report the candidate's output makes available while it runs, and again on its final usage before it accepts the candidate's verdict. When the total reaches or exceeds 100,000 tokens, the Dispatcher MUST end the candidate, that is, cancel its active turn, terminate its remaining processes, never resume its session, and discard any verdict it returned, and MUST treat it as having returned no verdict, so the judgement passes to the next candidate. The Dispatcher MUST enable and consume every usage reporting the candidate supports, per-request, aggregate and streaming alike. A candidate whose reporting so enabled supplies no input usage at all cannot be bounded and runs unbounded, and its usage is recorded as unreported; that exception never applies because the Dispatcher omitted to enable or consume reporting the candidate supports. The record of a pre-admission or pre-dispatch taking whose chain returned a verdict MUST name the total input tokens its deciding candidate's requests reported, marked complete when the reports cover every request, partial when they cover only some, and unreported when there are none. The record of a taking whose chain returned no verdict names no deciding candidate and lists each candidate the bound ended. A taking that reuses a recorded verdict runs no candidate, so neither the bound nor the field applies to it. Measured 2026-10-26, one host taking launched as `claude -p` made three requests that each re-sent a context of about 128,000 tokens, so one grading consumed about 380,000 input tokens.
```

2. In `SPECIFICATION/scenarios.md`, inside the gherkin block of "## Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric", append after its last scenario, "A host judgement falls back along the resolved dod_gate chain":

```gherkin

  Scenario: A host judgement candidate that reaches its input bound falls back
    Given a governed repository whose resolved dod_gate chain has two candidates
    When the pre-dispatch Definition-of-Done judgement is taken and the first candidate's requests together report 100,000 input tokens or more, counting each request once
    Then the first candidate's turn is cancelled, its processes end, and any verdict it returned is discarded
    And the second candidate is run and its verdict decides the judgement
    And the judgement record names the total input tokens the second candidate's requests reported, marked complete, partial or unreported

  Scenario: A bound reached on the final usage report still discards the verdict
    Given a candidate whose usage is reported only alongside its verdict
    When the pre-admission Definition-of-Done judgement is taken and that final report brings its requests' input to 100,000 tokens or more
    Then its verdict is discarded and the judgement passes to the next candidate

  Scenario: An aggregate usage report is counted against the bound
    Given a candidate whose output reports its input usage only as an aggregate for its turn
    When the pre-dispatch Definition-of-Done judgement is taken and the aggregate reports 100,000 input tokens
    Then its verdict is discarded and the judgement passes to the next candidate
    When the aggregate instead reports 99,999 input tokens
    Then its verdict decides the judgement and the record names 99,999 input tokens, marked complete

  Scenario: A chain that exhausts records no deciding candidate
    Given a resolved dod_gate chain whose every candidate is ended by the bound
    When the pre-dispatch Definition-of-Done judgement is taken
    Then the taking follows its did-not-run route
    And its record names no deciding candidate and lists each candidate the bound ended
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.
