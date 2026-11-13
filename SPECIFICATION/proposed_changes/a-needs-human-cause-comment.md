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

Split from bd-ib-qcshv6 on legacy-coordinator-agent's ruling of 2026-11-12 (session 959b2f8b, about 17:00Z). The coordinator ruled that qcshv6's first two Definition-of-Done bullets (the innermost cause and failed targets are taken from the stage the run ended on) are conformance under Scenario 196, which PR #5089 has since delivered. qcshv6's third bullet, the ordering and marking of the failed-stage list, is unstated presentation. It was filed as bd-ib-kdwv2b (plan publish-draft-green-work-loss, epic bd-ib-acrr56). The pre-dispatch tier judgement held it as spec-change tier: unstated, generalization target "## Dispatcher policy settings", linked proposal topic a-needs-human-cause-comment, spec v360. Measured motivation: livespec-dev-tooling-t5ct2q run 01M6V7WM77YBF43YP3B2DF46Y2 recorded "failed stage: fix@2, janitor@3, publish_draft@2". The visits actually failed in the order publish_draft@2, then janitor@3, then fix@2, and the run ended after fix@2. A reader of that comment cannot tell which stage ended the run, or that two of the three failures came before it and were routed onward. Placement: the cause comment is this orchestrator's Dispatcher realization, so it belongs in this repository's contracts.md. No code parses the line, so its shape is free to state. Fleet scope: every repository whose runs the Dispatcher rests at blocked / needs-human. Co-edit owed at revise, outside this spec target: tests/heading-coverage.json gains one row for the new scenario heading (test TODO, work_item bd-ib-kdwv2b, reason naming the integration tier or above), and the debt register is regenerated, never authored. The revise assigns the scenario's number and writes it into both the heading and the bullet's closing sentence.

### Proposed Changes

1. contracts.md, §"Dispatcher policy settings" → "A factory run never awaits a human": insert this bullet IMMEDIATELY AFTER the bullet that begins "- Every reconciliation surface (loop, preamble, standalone sweep," and ends "is not a reconciliation of that factory.", and BEFORE the line that begins "Design record: plan `ledger-is-the-only-gate`":

- **The needs-human cause comment lists the run's failed stages in failure order and marks the stage the run ended on.** When a run rests its item at `blocked` / `needs-human` and the run's own record reports at least one failed stage visit, the needs-human cause comment MUST carry exactly one line beginning `failed stage: `. That line MUST list every failed stage visit the run's own record reports, each written `<node>@<visit>`, separated by `, `, in the order the visits failed, earliest first. The order MUST be read from the failure instants the run's own record carries for those visits, and never from the order in which the record or the engine's outcome map lists them. Visits whose failure instants are equal MUST keep the order in which the record lists them. The visit whose failure routed the run to the `needs_human` terminal is the stage the run ended on. It MUST carry the suffix ` (run ended here)`, and it is the stage whose failure the comment's innermost cause and failed targets are taken from. When the run was routed to the `needs_human` terminal by something other than a failed stage visit, such as a stall bound, a wall budget or a refused resume, no listed visit routed the run: no visit MUST carry the suffix, and the comment's innermost cause MUST still be taken from that routing reason, as it is without this bullet. When the record carries no readable failure instant for one or more failed visits, the line MUST first list, in failure order, the visits whose instants it can read. It MUST then append `; order unknown: ` followed by the remaining visits, separated by `, `, in the order the record lists them. It MUST still mark the ending stage wherever that stage appears, and MUST NOT present an order it did not read. A comment whose run's record reports no failed stage visit carries no `failed stage:` line. This bullet changes no route a run takes and no status the item rests at. Scenario <number assigned at revise> in `scenarios.md` exercises this bullet.

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

  Scenario: A run routed to needs_human by something other than a failed visit marks no visit
    Given a run whose record reports failed visits janitor@3 and fix@2, failing in that order
    And the run was routed to the needs_human terminal by its wall budget rather than by a failed visit
    When the Dispatcher rests the item at blocked with blocked_reason needs-human
    Then the needs-human cause comment carries the line "failed stage: janitor@3, fix@2"
    And the comment's innermost cause is taken from the wall budget routing reason
```

No existing H2 heading is renamed or removed. The revise that accepts this proposal MUST add, in the same change, one `tests/heading-coverage.json` row for the new scenario heading with `"test": "TODO"`, `"work_item": "bd-ib-kdwv2b"` and a `reason` that names the owed test's tier as "integration tier or above". It MUST then REGENERATE the debt register with `uv run python -m livespec_dev_tooling.heading_coverage_debt`, and never author its entry by hand.

## Proposal: Repeated visits of one node are read by visit, not by node, wherever a run's ending is judged

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The successful-terminal evidence and the needs-human cause both read a node's outcome from the run's record, but the ratified text never says which visit decides when one node ran more than once. The readers today key on the node, so an earlier failed visit can stand in for a later successful one, or for the visit that actually reached the terminal, depending only on the order the record lists them. This proposal adds one paragraph to "## Dispatcher successful terminal evidence". A node's outcome is that of its latest visit, the stage a run reached a terminal from is the visit that executed immediately before the terminal, and an earlier failed visit of a node whose latest visit succeeded is history. One scenario exercises it.

### Motivation

Found while grading bd-ib-qcshv6 (legacy-coordinator-agent, 2026-11-13). Filed as bd-ib-xkvdzp under plan publish-draft-green-work-loss (epic bd-ib-acrr56), whose tier judgement (spec v364) reads partial against "## Dispatcher successful terminal evidence": "The requirement that repeated visits of one node are ordered by visit, not by node or by outcome-map order, is not stated in any visible text". Measured on master, three readers key on the node: `_ordered_failures` and `_successful_terminal_predecessor` in `_fabro_terminal_evidence`, and the node-keyed outcome dictionary in `_dispatcher_successful_terminal`. The first proposal of this file states the cause comment's ordering; this one states the successful-terminal half, so ratifying the topic releases both bd-ib-kdwv2b and bd-ib-xkvdzp. Co-edit owed at revise: one tests/heading-coverage.json TODO row for the new scenario heading (work_item bd-ib-xkvdzp, reason naming the integration tier or above), and the debt register regenerated, never authored.

### Proposed Changes

1. contracts.md, "## Dispatcher successful terminal evidence": insert this paragraph IMMEDIATELY BEFORE the paragraph that begins "The dispatch journal MUST identify the run, the structured completion":

**Repeated visits of one node are read by visit.** When a run's record carries more than one visit of a node, every reading of that node's outcome that this section or the needs-human cause comment makes MUST distinguish the node's visits. A stage's outcome is the outcome of its latest visit, whatever order the record or the engine's outcome map lists the visits in. The stage from which a run reached a terminal is the visit that executed immediately before that terminal, never the first-listed visit of the same node. An earlier failed visit of a node whose latest visit succeeded is history: it MUST NOT by itself disqualify the checkpoint, and MUST NOT be read as the route by which the run reached its terminal. Scenario <number assigned at revise> in `scenarios.md` exercises this paragraph.

2. scenarios.md: append this new H2 section after the last ratified scenario (after the scenario the first proposal of this file adds). The revise assigns its number and writes it into the paragraph above:

## Scenario <number assigned at revise> — A node visited more than once is judged by its latest visit and by the visit that reached the terminal

```gherkin
Feature: A run's ending is judged by visit, not by node
  Scenario: A node whose latest visit succeeded counts as succeeded whatever order its visits are listed in
    Given a run whose record carries visits janitor@1, which failed, and janitor@2, which succeeded
    And the engine's outcome map lists janitor@2 before janitor@1
    When the Dispatcher reads the run's successful-terminal evidence
    Then janitor counts as a succeeded required stage

  Scenario: The visit immediately before the terminal is the route the run reached it by
    Given a run whose record carries pr_refresh_head@1, which failed, and pr_refresh_head@2, which succeeded
    And pr_refresh_head@2 executed immediately before the needs_human terminal
    And the engine's outcome map lists pr_refresh_head@1 first
    When the Dispatcher judges the route by which the run reached needs_human
    Then it judges it from pr_refresh_head@2, a successful stage
```

No existing H2 heading is renamed or removed.
