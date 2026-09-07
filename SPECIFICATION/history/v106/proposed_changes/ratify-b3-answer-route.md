---
topic: ratify-b3-answer-route
author: claude-opus (control-plane-accounts-and-dispatch-policy)
created_at: 2026-09-07T13:20:00Z
---

## Proposal: Ratify the b3 answer-route mechanism the implementation already ships

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The human-answer route for a `blocked / needs-human` item shipped in two slices
(`bd-ib-aqith2` PR #2168, `bd-ib-uuohty` PR #2200). The ratified v105 contract
carries `resolve-blocked … --answer`, "lands the answer as a ledger comment", the
effective-answer-disposition gate, and Scenario 122. But FOUR mechanism facts a
consumer must rely on exist only in the implementation
(`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_drive_answer.py`,
`_needs_attention_needs_human_question.py`) and not in the ratified text: the
stable answer-comment marker, the poison preflight refusal, the terminated run's
account carried in the valve item's summary, and the comment-before-transition
ordering. This is spec drift (implementation ahead of ratified text), surfaced by
the console's v049 ratification doctor pass and its reviewer; livespec-console-beads-fabro
v049 (contracts.md §"Needs-human as a ledger valve", Scenario 32) consumes and
cites all four, and under its never-work-around-upstream rule it may not restate
them as its own requirements — so they must be ratified HERE. This proposal adds a
new `### ` clause under §"A factory run never awaits a human" ratifying each fact as
a MUST, plus scenario bindings. No implementation change: the ratified text
describes shipped behavior verbatim.

### Motivation

b5 leg of plan control-plane-accounts-and-dispatch-policy (epic `bd-ib-rh3iyd`,
child `bd-ib-rh3iyd.7`). The console proxy `livespec-console-beads-fabro-pzbdbo.20`
closes when `.7` closes. A downstream consumer that relies on the marker to find
the human answer in a re-dispatched goal brief, on the poison refusal to know a
poisoned answer never lands, on the valve account to render the run's fate, and on
the write-before-transition ordering to know a delivered answer precedes the
unblock, currently relies on facts no ratified clause guarantees.

### Proposed Changes

**contracts.md — add a new `### ` clause immediately AFTER §"A factory run never
awaits a human"** (before §"Temporary setting postures carry an owned restore
item"):

```
### The human answer route: marker, poison preflight, run account, and write-before-transition ordering

The human's answer to a `blocked / blocked_reason: needs-human` item travels one
route — a `resolve-blocked:<work-item-id>:ready|backlog` press carrying `--answer`
that lands the answer as a ledger comment (§"The five policy settings",
Scenario 122). Four mechanism facts of that route are load-bearing for a consumer
and are ratified here.

- **Answer marker.** The answer comment MUST open with the stable marker line
  `livespec-human-answer (<invoker> via <source>, <at>, <action-id>):` on its own
  line, followed by the operator's answer verbatim. The attribution and timestamp
  are written INTO the comment body — the invoker the drive surface resolved, its
  source, the write instant, and the answering valve action id — because the
  shared bd connection user in the tenant's own columns names no operator. The
  re-dispatched run's goal brief MUST carry this comment verbatim so the next run
  reads who answered and what they said.
- **Poison preflight refusal.** Before the answer comment is written, the answer
  MUST be preflighted with the shared template-opener detector. An answer carrying
  a goal-template opening delimiter MUST be REFUSED: nothing is written — not the
  comment, not the journal line — and the item does NOT transition. Because a
  ledger comment is append-only and the goal brief renders it verbatim, an opener
  admitted here would poison every future goal render and cost the item its
  dispatchability permanently; the writer that feeds the brief therefore refuses
  exactly what would refuse the dispatch.
- **Run account in the valve summary.** The `needs-attention` valve item for a
  `blocked / needs-human` item MUST carry the terminated run's account in its
  summary: the run id, the factory name and its server, that a `needs_human`
  termination routed the decision to this valve, why it terminated, what the run
  reported, the preserved reference to its work, and the available valve actions.
  The enrichment MUST fail soft: an unreadable config or an unreachable factory
  costs the ENRICHMENT and never the valve — the valve item is surfaced regardless,
  and each factory is addressed by its declared server target.
- **Write-before-transition ordering.** The answer comment MUST be written BEFORE
  the item's status transition. A comment write that is refused or fails MUST NOT
  transition the item, so a delivered answer always precedes the unblock and no
  transition is recorded for an answer that did not land.

Design record: the route shipped in `bd-ib-aqith2` (PR #2168) and `bd-ib-uuohty`
(PR #2200); ratified here per `bd-ib-rh3iyd.7`.
```

**scenarios.md — add two `## Scenario` headings binding the four facts.**

Add a scenario asserting the answer-write mechanics: given an operator presses
`resolve-blocked:<id>:ready` with `--answer`, when the answer is clean, then the
ledger comment opens with the `livespec-human-answer (<invoker> via <source>, <at>,
<action-id>):` marker line followed by the answer verbatim AND the comment is
written before the status transition; and given the answer carries a goal-template
opening delimiter, when the press is evaluated, then it is refused with nothing
written and the item stays `blocked` with no transition.

Add a second scenario asserting the valve account: given a `blocked / needs-human`
item whose run terminated on a `needs_human` outcome, when `needs-attention` renders
its `resolve-blocked` valve item, then the summary carries the run id, the factory
name and server, the termination reason, what the run reported, the preserved
reference, and the available actions; and given the factory is unreachable, when the
summary is rendered, then the enrichment is omitted and the valve item is still
surfaced.

The revise that ratifies these scenarios MUST update `tests/heading-coverage.json`
in the same commit so each new scenario heading is bound to its exercising tests.
