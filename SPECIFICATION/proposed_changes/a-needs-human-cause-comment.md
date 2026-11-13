---
topic: a-needs-human-cause-comment
author: claude-opus-5-5:publish-draft-green-work-loss
created_at: 2026-11-13T01:53:14Z
---

## Proposal: A needs-human cause comment lists a run's failed stages in failure order and marks the stage the run ended on

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The ratified text says only that a needs-human cause comment names the run id and its innermost cause (Scenario 196). It says nothing about the comment's `failed stage:` line: not which failed stage visits it lists, not their order, and not which of them ended the run. Today that line lists the visits in whatever order the engine's record yields them. On a run that failed in several stages, a reader can then mistake an earlier, recovered failure for the cause of the ending. This proposal adds one bullet to §"Dispatcher policy settings" → "A factory run never awaits a human". The bullet states that the line lists every failed stage visit the run's own record reports, earliest failure first, ordered by the record's own failure instants. It marks the visit whose failure routed the run to the `needs_human` terminal, and states rather than guesses an order it cannot read. One scenario exercises it.

### Motivation

Split from bd-ib-qcshv6 on legacy-coordinator-agent's ruling of 2026-11-12 (session 959b2f8b, about 17:00Z). The coordinator ruled that qcshv6's first two Definition-of-Done bullets (the innermost cause and failed targets are taken from the stage the run ended on) are conformance under Scenario 196, which PR #5089 has since delivered. qcshv6's third bullet, the ordering and marking of the failed-stage list, is unstated presentation. It was filed as bd-ib-kdwv2b (plan publish-draft-green-work-loss, epic bd-ib-acrr56). The pre-dispatch tier judgement held it as spec-change tier: unstated, generalization target "## Dispatcher policy settings", linked proposal topic a-needs-human-cause-comment, spec v360. Measured motivation: livespec-dev-tooling-t5ct2q run 01M6V7WM77YBF43YP3B2DF46Y2 recorded "failed stage: fix@2, janitor@3, publish_draft@2". The visits actually failed in the order publish_draft@2, then janitor@3, then fix@2, and the run ended after fix@2. A reader of that comment cannot tell which stage ended the run, or that two of the three failures came before it and were routed onward. Placement: the cause comment is this orchestrator's Dispatcher realization, so it belongs in this repository's contracts.md. No code parses the line, so its shape is free to state. Fleet scope: every repository whose runs the Dispatcher rests at blocked / needs-human. Co-edit owed at revise, outside this spec target: tests/heading-coverage.json gains one row for the new scenario heading (test TODO, owner bd-ib-kdwv2b), and the debt register gains the matching entry. The revise assigns the scenario's number and writes it into both the heading and the bullet's closing sentence.

### Proposed Changes

1. contracts.md, §"Dispatcher policy settings" → "A factory run never awaits a human": insert this bullet IMMEDIATELY AFTER the bullet that begins "- Every reconciliation surface (loop, preamble, standalone sweep," and ends "is not a reconciliation of that factory.", and BEFORE the line that begins "Design record: plan `ledger-is-the-only-gate`":

- **The needs-human cause comment lists the run's failed stages in failure order and marks the stage the run ended on.** When a run rests its item at `blocked` / `needs-human` and the run's own record reports at least one failed stage visit, the needs-human cause comment MUST carry exactly one line beginning `failed stage: `. That line MUST list every failed stage visit the run's own record reports, each written `<node>@<visit>`, separated by `, `, in the order the visits failed, earliest first. The order MUST be read from the failure instants the run's own record carries for those visits, and never from the order in which the record or the engine's outcome map lists them. The visit whose failure routed the run to the `needs_human` terminal is the stage the run ended on. It MUST carry the suffix ` (run ended here)`, and it is the stage whose failure the comment's innermost cause and failed targets are taken from. When the record carries no readable failure instant for one or more failed visits, the line MUST first list, in failure order, the visits whose instants it can read. It MUST then append `; order unknown: ` followed by the remaining visits, separated by `, `, in the order the record lists them. It MUST still mark the ending stage wherever that stage appears, and MUST NOT present an order it did not read. A comment whose run's record reports no failed stage visit carries no `failed stage:` line. This bullet changes no route a run takes and no status the item rests at. Scenario <number assigned at revise> in `scenarios.md` exercises this bullet.

2. scenarios.md: append this new H2 section after the last ratified scenario. The revise assigns its number and writes the same number into the closing sentence of the bullet above:

## Scenario <number assigned at revise> — A needs-human cause comment lists the run's failed stages in the order they failed and marks the stage the run ended on

```gherkin
Feature: A needs-human cause comment shows which stage ended the run
  As a maintainer reading why an item rests at blocked / needs-human
  I want the failed stages listed in the order they failed, with the ending stage marked
  So that an earlier failure the run recovered from is not mistaken for the cause of its ending

  Scenario: Several failed stages are listed earliest first and the ending stage is marked
    Given a run whose record reports failed visits publish_draft@2, janitor@3 and fix@2, failing in that order
    And the engine's outcome map lists those visits as fix@2, janitor@3, publish_draft@2
    And the run ended at the needs_human terminal after fix@2 failed
    When the Dispatcher rests the item at blocked with blocked_reason needs-human
    Then the needs-human cause comment carries the line "failed stage: publish_draft@2, janitor@3, fix@2 (run ended here)"
    And the comment's innermost cause is taken from fix@2

  Scenario: A single failed stage is marked as the stage the run ended on
    Given a run whose record reports one failed visit, implement@1
    And the run ended at the needs_human terminal after implement@1 failed
    When the Dispatcher rests the item at blocked with blocked_reason needs-human
    Then the needs-human cause comment carries the line "failed stage: implement@1 (run ended here)"

  Scenario: A failure instant the record does not carry is stated rather than guessed
    Given a run whose record reports failed visits janitor@3 and fix@2
    And the record carries a failure instant for fix@2 and none for janitor@3
    And the run ended at the needs_human terminal after fix@2 failed
    When the Dispatcher rests the item at blocked with blocked_reason needs-human
    Then the needs-human cause comment carries the line "failed stage: fix@2 (run ended here); order unknown: janitor@3"
```

No existing H2 heading is renamed or removed. The revise that accepts this proposal MUST add one `tests/heading-coverage.json` row for the new scenario heading, owned by bd-ib-kdwv2b, and the matching debt-register entry, in the same change.
