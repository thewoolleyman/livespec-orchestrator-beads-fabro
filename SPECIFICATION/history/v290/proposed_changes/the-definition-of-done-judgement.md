---
topic: the-definition-of-done-judgement
author: claude-opus-5-5
created_at: 2026-11-03T19:52:52Z
---

## Proposal: The Definition-of-Done judgement subject omits spec-change tier records and filing-time mechanical finding comments

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend the GOAL component of §"Effective acceptance criteria" → "One rubric, one subject" so that, beside the judgement records and the advisory finding comments it already omits, every taking's subject and the node's rendered goal also omit the Dispatcher's spec-change tier records and filing-time mechanical finding comments, and require every taking to resolve a References heading against the specification tree it grades against rather than from an earlier record. A later taking then never grades a filing verdict that a ratification has since superseded as if it were operator brief.

### Motivation

Work-item bd-ib-7zzm42 (plan spec-implementation-lockstep, epic bd-ib-ax3rds), routed by legacy-coordinator-agent. Measured 2026-11-03 on nine priority-1 livespec-dev-tooling children, livespec-dev-tooling-sh3vz3 among them. At filing (17:24Z) each item got a livespec-spec-change-tier record (spec-version 123, verdict-kind unstated) and a `definition-of-done finding (mechanical):` comment saying its References heading did not resolve, because its scenarios were not ratified yet. v125 then ratified exactly those headings (#3312, 19:14:42Z). The approve-time judge (19:17Z and 19:28Z) was handed both stale comments as operator riders. It refused every item, citing "spec-version 123" and "the mechanical finding reports the same", and it invented `## Scenario NN —` headings, although each References line matched a v125 H2 byte for byte. The cause is the clause as written: the GOAL carries every ledger comment except `livespec-dod-judgement` records and advisory finding comments, so a tier record and a mechanical finding comment are brief by specification, and the implementation (`is_judgement_record` in `_dispatcher_dod_judgement_markers.py`) follows it. Both are the Dispatcher's own records of a judgement taken against a particular spec version, which is the same reason judgement records are receipts. §"Dispatch-brief lessons injection" already says ledger comments that are records rather than instructions stay out of every brief; this names the two record kinds that slipped through. The coordinator worked around the incident with release-spec-tier and repaired References lines. Related items not covering this: bd-ib-40vz (goal size), and bd-ib-lxohlb and Scenario 273 (advisory findings in the run goal).

### Proposed Changes

Two edits, one in each target file. Every other sentence of the edited paragraph is kept unchanged.

**1. `SPECIFICATION/contracts.md`, §"Effective acceptance criteria" → "One rubric, one subject", the GOAL component bullet.**

Replace

> and except the filing-time ADVISORY FINDING COMMENTS: each comment whose first line begins with `definition-of-done finding (advisory):`, the prefix filing writes before each advisory finding. Those records are receipts, not brief, so the Dispatcher MUST omit them from the node's rendered goal as well, and recording a judgement record MUST NOT change any subject digest. A ledger comment added after filing that is neither a judgement record nor an advisory finding comment remains in the rendered goal's operator-rider section.

with

> and except the filing-time FINDING COMMENTS: each comment whose first line begins with `definition-of-done finding (advisory):` or `definition-of-done finding (mechanical):`, the prefixes filing writes before each advisory and each mechanical finding, and except the SPEC-CHANGE TIER RECORDS: each comment whose first line is `livespec-spec-change-tier`, whichever stage wrote it. Those records are receipts, not brief: each reports a judgement taken against one specification version, and a later revision can supersede it. The Dispatcher MUST omit them from the node's rendered goal as well, and recording any of them MUST NOT change any subject digest. A ledger comment added after filing that is none of these records remains in the rendered goal's operator-rider section. Omitting a record from the subject and the goal MUST NOT remove it from the item's ledger, where needs-attention and the filer still read it. Every taking MUST decide whether a References heading resolves against the specification tree it grades against, and MUST NOT take that answer, or the item's spec-change tier, from an earlier finding comment or tier record.

**2. `SPECIFICATION/scenarios.md`, §"Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric".**

Insert the following scenario immediately after the scenario "The subject carries rider comments and omits judgement receipts" and before the scenario outline "A reference line missing one of several governing headings is reported as advisory by every host taking". No H2 heading is added, removed or renamed, so `tests/heading-coverage.json` needs no change.

```gherkin
  Scenario: A filing-time tier record and mechanical finding are omitted after a revision ratifies the referenced heading
    Given an item whose ledger carries a livespec-spec-change-tier record and a definition-of-done finding (mechanical) comment, both written at filing against an earlier spec version that lacked its referenced heading
    And a rider appended after filing
    And a later revision ratified that heading verbatim
    When the pre-admission judgement is taken at approve
    Then the subject and the node's rendered goal carry the rider and omit the tier record and the mechanical finding comment
    And the judgement resolves the reference line against the ratified spec tree and reports no unresolved-reference finding for it
    And the tier record and the mechanical finding comment remain on the item's ledger
    And appending a further tier record leaves the item's subject digest unchanged
```
