---
topic: node-timeout-cut-retry-carries-the-cut-state
author: claude-opus-5-5
created_at: 2026-11-01T01:58:47Z
---

## Proposal: A retry after a node-timeout cut is told it was cut, and an exhausted cut names the key to raise

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md "## ACP node timeouts" so that (1) when an ACP node's turn is ended by its resolved timeout and the node's within-run retry budget is not exhausted, the retried turn's brief MUST state that the previous attempt was cut, with its resolved timeout, its last tool call and that call's state, and the sandbox paths outside the repository the cut attempt created, so the retry resumes from that state instead of repeating orientation and fixture-building from scratch; and (2) the needs-human cause sentence of "A commit run outlives a node-timeout cut", today scoped to implement, fix and review_fix turns that started a commit run, is generalized to every ACP node whose cut is the cause of the run's needs-human ending, and additionally names the `dispatcher.node_timeouts.<node>` key that sizes the cut limit. Adds Scenario 286.

### Motivation

Work-item bd-ib-bbcj6 ('A proof_capture retry after a working-to-the-limit timeout repeats the capture from scratch and predictably times out again'), owned by plan hp-factory-failure-follow-ups (epic bd-ib-qieqc6). Filed as one of the eight residual linked proposals of plan spec-implementation-lockstep (epic bd-ib-ax3rds) R1 work-item bd-ib-j6uvkj, under the coordinator ruling recorded on bd-ib-ax3rds at 2026-11-01T00:21:09Z; the revise of this topic belongs to the owning plan's reviewer.

Judgement: FEATURE. Revalidated against v261, no clause states what a within-run retry after a node-timeout cut carries (the item's own batch-12 routing note reached the same verdict at v176). Measured on hp 2026-10-14 (runs 01M4X1WS4F86RQJW5XFSH3WN22 and 01M4X1WPMQKSGYJCYB86D68NW4): three of five cut proof_capture attempts were turns still actively working at 1797-1799 s of 1800 s, and every retry opened a fresh ACP session that re-oriented and rebuilt the same harness inside the same limit, so the run ended needs_human after about 60 minutes with nothing captured. The item asked the owning plan to choose among (a) retry with carry-over, (b) skip the retry and end needs-human naming the node-timeout key, or (c) split the capture into bounded turns. This proposal takes (a) and the naming half of (b): carry-over keeps the retry for the two measured cases where a single hung command, not the work's size, consumed the limit, while the generalized needs-human cause tells the operator which committed key to raise when a capture genuinely needs a longer turn. Option (c) is rejected here as a workflow-graph redesign that no measured case requires. It generalizes two existing rules rather than adding a mechanism: the re-entered implement brief of "An implement turn that ends incomplete does not succeed" (which already carries the prior turn's recorded failing gate) and the `node-timeout` needs-human cause of "A commit run outlives a node-timeout cut". Across-dispatch re-dispatch after a cut is deliberately NOT covered here; the sibling proposal for bd-ib-cewr.6 excludes node-timeout cuts from its automatic release for the same reason.

### Proposed Changes

In SPECIFICATION/contracts.md, under "## ACP node timeouts":

1. In the paragraph **A commit run outlives a node-timeout cut.**, replace its final sentence ("When such a cut is the cause of the run's needs-human ending, the needs-human cause recorded on the item MUST name `node-timeout`, the node whose turn was cut, that node's resolved timeout in seconds, and, for each commit run the cut turn had started, its identity and its terminal state when preservation began.") with:

> When the cut of any ACP node's turn, whether or not it started a commit run, is the cause of the run's needs-human ending, the needs-human cause recorded on the item MUST name `node-timeout`, the node whose turn was cut, that node's resolved timeout in seconds, the `dispatcher.node_timeouts.<node>` key that sizes it and the layer that supplied it, and, for each commit run the cut turn had started, its identity and its terminal state when preservation began.

2. Immediately after that paragraph, insert this new paragraph:

> **A retry after a node-timeout cut is told it was cut.** When an ACP node's turn is ended by its node's resolved timeout and that node's within-run retry budget is not exhausted, the retried turn's brief MUST state that the previous attempt was ended by its node timeout, MUST name that resolved timeout in seconds, the previous attempt's last tool call and that call's state (`completed`, `failed` or `in_flight`, as §"Factory step span attributes" defines them), and MUST list the paths outside the repository's tracked tree that the cut attempt created in the sandbox and that still exist when the retry starts. Those facts MUST be taken from the run's recorded events and the sandbox's own state, never from the cut attempt's reply, which a cut turn does not send. The brief MUST direct the retried turn to reuse that state rather than rebuild it, and to avoid repeating a tool call that was `in_flight` at the cut unless it first bounds that call. A retry MUST NOT be started with a timeout shorter than the cut attempt's. This paragraph does not change the node's retry budget, and when the budget is exhausted the run takes its existing failure edge, with the needs-human cause the preceding paragraph requires. The mechanism that carries the brief is left to the implementation. Scenario 286 in `scenarios.md` exercises this paragraph.

In SPECIFICATION/scenarios.md, append:

```markdown
## Scenario 286 — A retry after a node-timeout cut resumes from the cut attempt's state, and an exhausted cut names the key to raise

Governing clause: `contracts.md` §"ACP node timeouts".

```gherkin
Feature: a turn cut by its node timeout is not silently repeated from scratch
  As an operator whose capture needs longer than one turn
  I want the retry to know it was cut and the final ending to name the limit
  So that a retry continues the work and a genuine sizing problem names its remedy

  Scenario: the retried turn's brief carries the cut attempt's state
    Given a proof_capture turn ended by its node's resolved timeout of 1800 seconds
    And the cut attempt created a capture harness outside the repository's tracked tree
    And its last tool call was in_flight at the cut
    And the proof_capture node's retry budget is not exhausted
    When the run retries proof_capture
    Then the retried turn's brief states that the previous attempt was cut at 1800 seconds
    And it names the in_flight last tool call and lists the harness paths
    And it directs the turn to reuse that harness rather than rebuild it

  Scenario: an exhausted cut names the node-timeout key
    Given a proof_capture turn ended by its node's resolved timeout
    And the proof_capture node's retry budget is exhausted
    When the run ends at needs_human
    Then the item's needs-human cause names node-timeout, proof_capture, the resolved timeout in seconds, the dispatcher.node_timeouts.proof_capture key and the layer that supplied it

  Scenario: control — a turn that ends with a final message is not described as cut
    Given a proof_capture turn that ended with its final message before its node timeout
    When the run retries proof_capture for another reason
    Then the retried turn's brief does not state that the previous attempt was cut
```
```

The revise that ratifies this topic MUST add the Scenario 286 heading to `tests/heading-coverage.json` in the same change.
