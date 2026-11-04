---
topic: transient-infra-release-and-re-dispatch
author: claude-opus-5-5
created_at: 2026-11-01T01:58:55Z
---

## Proposal: Transient infrastructure release and re-dispatch, bounded and backed off

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add, beside the two existing release routes of contracts.md "## Factory-configurable ACP fallback priority" ("Provider-limit release and re-dispatch" and "Adapter launch release and re-dispatch"), a third bounded route: a run whose unrecovered failing node attempt the Dispatcher classifies `transient_infra` — after every reclassification of §"Provider-limit permanence and root-cause surfacing", and excluding eligible provider-limit failures, adapter launch failures and node-timeout cuts, which keep their own routes — is released to `ready` and re-admitted without a human after an exponential backoff, up to a committed per-item consecutive limit; exhausting the limit keeps the existing `blocked / needs-human` rest, with a cause naming every run in the sequence and its category. It reuses the adapter launch release's four ordered steps, idempotency and predecessor rule instead of restating them, and amends the two clauses that enumerate the release routes ("A factory run never awaits a human" and "Across-dispatch required-result progress"). Adds Scenario 287.

### Motivation

Work-item bd-ib-cewr.6 ('Dispatcher re-dispatches automatically after a transient_infra failure, within a bounded retry budget'), owned by plan silent-failure-surfaces (epic bd-ib-cewr). Filed as one of the eight residual linked proposals of plan spec-implementation-lockstep (epic bd-ib-ax3rds) R1 work-item bd-ib-j6uvkj, under the coordinator ruling recorded on bd-ib-ax3rds at 2026-11-01T00:21:09Z; the revise of this topic belongs to the owning plan's reviewer.

Judgement: FEATURE. Revalidated against v261. Most of the item's 2026-09-08 evidence is ALREADY governed and is not re-specified here: the organisation spend-limit and five-hour session-limit kills are provider ceilings, which §"Provider-limit permanence and root-cause surfacing" classifies permanent (never `transient_infra`) and which "Provider-limit release and re-dispatch" releases to `ready` without a human, with the reset instant honoured through the hold's expiry under §"Factory-configurable ACP fallback priority". The item's acceptance criterion 2 (wait for a named reset time) is therefore governed by that route and dropped from this proposal. What no clause states is the residue: a failure that remains `transient_infra` after reclassification — an unattributed sandbox, DNS or transport failure — today keeps its existing route to `blocked / needs-human`, and the adapter launch paragraph explicitly says such failures "retain their existing routes". Releasing those automatically, bounded per item and backed off, is new behaviour (the batch-14 routing note on the item reached the same verdict at v176). Node-timeout cuts are deliberately excluded: re-dispatching with the same resolved timeout predictably repeats the cut, as the bd-ib-bbcj6 evidence measured, and the sibling proposal for bd-ib-bbcj6 (plan hp-factory-failure-follow-ups, epic bd-ib-qieqc6) governs the within-run retry and the needs-human cause that names the key to raise. Per the routing note, the route respects Scenario 151's causal-attempt rule: a release is a known host-attributable terminal that neither increments nor resets the across-dispatch item count, so it cannot mask an item-attributable non-progress sequence, and its own consecutive limit bounds it independently. It is written as a generalization of the existing adapter launch release, reusing its ordered steps, so the spec grows by one bounded paragraph and one scenario.

### Proposed Changes

In SPECIFICATION/contracts.md, under "## Factory-configurable ACP fallback priority":

1. In the paragraph that begins "Each release operation of this section -- a provider-limit release, or an adapter launch release below --", replace "a provider-limit release, or an adapter launch release below" with "a provider-limit release, an adapter launch release, or a transient infrastructure release below".

2. Immediately after the **Adapter launch release and re-dispatch.** paragraphs, insert this new paragraph:

> **Transient infrastructure release and re-dispatch.** A *transient infrastructure failure* is a run's unrecovered failing node attempt, responsible for its terminal disposition, whose category the Dispatcher derives as `transient_infra` after every reclassification of §"Provider-limit permanence and root-cause surfacing", and which is neither an eligible availability failure of "Provider-limit release and re-dispatch", nor an adapter launch failure, nor an ACP turn ended by its node's resolved timeout under §"ACP node timeouts"; each of those keeps its own route. When a run terminates through any terminal, the workflow's `needs_human` terminal included, with a transient infrastructure failure, and the item's consecutive transient infrastructure releases are fewer than the positive committed integer `dispatcher.transient_release_limit` (default **2**), the Dispatcher MUST take the four ordered steps of "Adapter launch release and re-dispatch", journaling a `transient-infra-release` record in place of `adapter-launch-release` that additionally names the failure's category and surfaced cause and the item's consecutive release count including this one, and MUST NOT re-admit the item before its *not-before* instant: the failure's terminal instant plus `dispatcher.transient_release_backoff_seconds` (a positive committed integer, default **300**) multiplied by two raised to the consecutive release count less one. The not-before instant MUST be journaled on the release record and written in its ledger comment. The *consecutive release count* is taken over the item's preceding dispatches as that paragraph defines them; any intervening dispatch that did not end in a transient infrastructure failure resets it. When the count has reached the limit, the failure keeps its existing route, including the `blocked / needs-human` rest of §"A factory run never awaits a human", and its needs-human cause record MUST name every run of the consecutive sequence with its category and surfaced cause and state that the transient release limit is exhausted. A non-positive or non-integer value of either key MUST be rejected before any run exists, naming the key; both are committed-configuration-only. A transient infrastructure release MUST NOT consume any budget of §"The three rework caps", is a known host-attributable terminal under §"Across-dispatch required-result progress", and MUST NOT be surfaced as a needs-human decision. A failure whose category or cause evidence is unreadable is unavailable, not a transient infrastructure failure: the Dispatcher MUST surface it and retry observation without releasing the item. Scenario 287 in `scenarios.md` exercises this paragraph.

Under "### A factory run never awaits a human", in its first bullet, after the sentence "Likewise a first consecutive adapter launch failure takes → \"Adapter launch release and re-dispatch\" of that section and does not rest at `blocked / needs-human`.", insert:

> A transient infrastructure failure within its release limit takes → "Transient infrastructure release and re-dispatch" of that section in the same way.

Under "### Across-dispatch required-result progress", in its second paragraph, replace "runs released under §\"Factory-configurable ACP fallback priority\" → \"Provider-limit release and re-dispatch\" or → \"Adapter launch release and re-dispatch\"" with "runs released under §\"Factory-configurable ACP fallback priority\" → \"Provider-limit release and re-dispatch\", → \"Adapter launch release and re-dispatch\" or → \"Transient infrastructure release and re-dispatch\"".

In SPECIFICATION/scenarios.md, append:

```markdown
## Scenario 287 — A transient infrastructure failure is released and re-dispatched within a bounded, backed-off limit

Governing clause: `contracts.md` §"Factory-configurable ACP fallback priority".

```gherkin
Feature: a sound item is not parked for a human by a passing infrastructure fault
  As an operator
  I want a transient infrastructure failure re-dispatched without me, but not forever
  So that mechanical recovery is automatic and a persistent fault still reaches a human

  Scenario: the first two transient failures are released with backoff
    Given dispatcher.transient_release_limit is 2 and dispatcher.transient_release_backoff_seconds is 300
    And a run of an item ends with an unattributed sandbox transport failure classified transient_infra
    When the Dispatcher classifies the terminal
    Then it journals a transient-infra-release record with consecutive count 1 and a not-before instant 300 seconds after the terminal
    And the item returns to ready with no blocked_reason and is not re-admitted before that instant
    And when the re-dispatched run fails the same way the next release's not-before instant is 600 seconds after its terminal

  Scenario: the limit exhausted rests the item for a human naming every run
    Given an item whose two preceding dispatches each ended in a transient infrastructure release
    When a third consecutive run ends with a transient infrastructure failure
    Then the item rests at blocked / needs-human
    And its needs-human cause names all three runs with their categories and states that the transient release limit is exhausted

  Scenario: controls keep their own routes
    Given runs ending with an eligible provider-limit failure, an adapter launch failure, a node-timeout cut, a failing check and unreadable failure evidence
    When the Dispatcher classifies each terminal
    Then none of them takes the transient infrastructure release
    And the unreadable evidence is surfaced as unavailable without releasing the item
```
```

The revise that ratifies this topic MUST add the Scenario 287 heading to `tests/heading-coverage.json` in the same change.

Note for the revise: two of the quoted replacement targets above (contracts.md lines ~9086 and ~7596-7598 at v261) are hard-wrapped across lines in the source; match them modulo line breaks.
