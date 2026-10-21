---
topic: terminal-claim-remedies-read-the-forge
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-21T16:35:47Z
---

## Proposal: A resume refusal on an active item names a remedy that changes that item's state

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Re-filed from merge-poll-exhaustion-rests-for-resume, whose revise into v191 adopted only its first proposal. A resume of a non-ready item refuses naming a remedy, and for an active item whose run has ENDED and which stranded-claim release does not reconcile (a succeeded run), the named remedy reconcile-runs is a no-op. The refusal names reconcile-merged when the forge reports the item's pull request merged, otherwise move:<id>:ready, and never a remedy that leaves the item unchanged. Amended by the 2026-10-21 gpt-6-astra ratification review: the Status changes bullet of Stranded claim release is qualified to match, the active-lane verb set and door rules gain the terminal-claim recovery move, and Scenario 221's merged case specifies a succeeded run.

### Motivation

Work-items bd-ib-mzyhn2, bd-ib-l6rleb (its third assertion) and bd-ib-ddu6wq (its third assertion). Measured on build 3a2a826a8ac4 (v0.201.0): bd-ib-un7ch2 sat active/fabro after run 01M4ZMYSHNE6 succeeded; its resume refused naming reconcile-runs, and a tenant-wide reconcile-runs dry run returned reconciled [] and held [] for it. The valve that released it was move:<id>:ready. bd-ib-dbmoeh shows why the forge must be read first. The 2026-10-21 review of the original filing (plan spec-implementation-lockstep, epic bd-ib-ax3rds) found that move from active conflicts with the ratified per-lane verb set, which is why this proposal now carries the vocabulary change and a decision note for its revise.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Resume from a published pull request (`resume --item`)", paragraph "**Refusals.**", in the bullet beginning "the item is not `ready`", replace the remedy parenthetical "(remedy: `resolve-blocked:<id>:ready` for an item resting at `blocked / needs-human`, or `reconcile-runs` for a stranded claim)" with:

> (remedy: `resolve-blocked:<id>:ready` for an item resting at `blocked / needs-human`; `reconcile-runs` for a stranded claim that §"Stranded claim release" reconciles; and, for an `active` item whose run is terminal and which that release does not reconcile, `reconcile-merged` when the forge reports the item's pull request merged, otherwise `move:<id>:ready`)

and, after the bullet's clause "— a resume never steps around the ledger's human decision.", add: "The named remedy MUST be one that changes that item's state; a refusal MUST NOT name a remedy that would leave the item unchanged. Scenario 221 in `scenarios.md` exercises the remedy rule."

In the same file, section "Stranded claim release", bullet "**Status changes.**", replace "name `reconcile-runs` as the remedy for a stranded claim; this subsection is what makes that remedy work." with "name `reconcile-runs` as the remedy for a stranded claim this subsection reconciles, and this subsection is what makes that remedy work; for an `active` item whose run is terminal and which this subsection does not reconcile, the resume refusal names the remedy of §\"Resume from a published pull request (`resume --item`)\" instead."

In the same file, section "Per-lane valid operator verb sets", in the `active` row, add after "observe only": "except the terminal-claim recovery `move→ready`, valid only for an `active` item whose run is terminal, which §\"Stranded claim release\" does not reconcile, and whose pull request the forge does not report merged". In "Door rules — every transition has exactly one journaled owner", in the bullet beginning "`ready` is entered by", add the terminal-claim recovery move from `active` as a third journaled door.

DECISION NEEDED AT REVISE: the `active` row says "observe only", and the verb-set table and door rules come from the work-item state-machine design. Adding a `move→ready` door out of `active` changes that ratified vocabulary, so the revise MUST check it against the design record that table cites and, if it departs from it, take the maintainer's explicit confirmation per the intent-preservation gate. (Note that the `drive` clause already says `move` guards only its target, not its source, so the two ratified texts disagree today.)

In SPECIFICATION/scenarios.md, add at the end of the file (the number is provisional until revise; tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 221 — A resume refusal on an active item names a remedy that changes it

```gherkin
Feature: A refusal never sends the operator to a valve that does nothing
  As an operator resuming an item
  I want the refusal's remedy to act on the item as it stands
  So that following the remedy releases the item

  Scenario: An active item with a succeeded run and an unmerged pull request
    Given an item at active with assignee fabro whose run succeeded and is terminal
    And the forge reports its pull request open
    When dispatcher resume is invoked for it
    Then the refusal names move:<id>:ready and does not name reconcile-runs

  Scenario: An active item with a succeeded run whose pull request merged
    Given an item at active with assignee fabro whose run succeeded and is terminal
    And the forge reports its pull request merged
    When dispatcher resume is invoked for it
    Then the refusal names reconcile-merged
```

## Proposal: A capacity handoff reads the forge before advertising a status move for a claim with no recorded pull request

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Re-filed from merge-poll-exhaustion-rests-for-resume, whose revise into v191 adopted only its first proposal. When the dispatch evidence names no pull request, a capacity handoff reads the forge for the item's publish branch before advertising any status move. Amended by the 2026-10-21 gpt-6-astra ratification review: a merged pull request found there is advertised as reconcile-merged only when that command's preconditions hold (including no live ownership lock), so the handoff stays executable as advertised; otherwise no status move is advertised and the blocking condition is named. A failed forge read advertises no status move.

### Motivation

Work-item bd-ib-dbmoeh, measured 2026-08-22 on bd-ib-62xaj3: run 01M0M9DEHMC4 succeeded and PR #1741 merged, but the dispatch died before writing the pull request back, and needs-attention recommended move:bd-ib-62xaj3:ready. bd-ib-gajho2 records what that produces: a second, empty PR that becomes the item's merge evidence. The 2026-10-21 review found that a capacity hold can keep a live dispatch lock after its run ends, so an unconditional reconcile-merged handoff would be refused.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Orchestrator-owned attention facts", replace the sentence "No capacity handoff MAY advertise a status-move action against a claim whose dispatch evidence shows a merged pull request — the ratified reconciliation route is `reconcile-merged`, and a move-to-`ready` handoff would re-queue merged work." with:

> No capacity handoff MAY advertise a status-move action against a claim whose dispatch evidence, or the forge, shows a merged pull request — the ratified reconciliation route is `reconcile-merged`, and a move-to-`ready` handoff would re-queue merged work. When the dispatch evidence names no pull request, the handoff MUST read the forge for the item's publish branch before it advertises any status move. When the forge reports a merged pull request there, the handoff MUST advertise `reconcile-merged` only when that command's own preconditions hold for the item, including no live ownership lock, so that the handoff stays executable as advertised; otherwise it MUST advertise no status move and name the condition that blocks reconciliation. A forge read that fails MUST NOT be read as no pull request: the handoff MUST then advertise no status move and name the failed read. Scenario 222 in `scenarios.md` exercises this sentence.

In SPECIFICATION/scenarios.md, add at the end of the file (the number is provisional until revise; tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 222 — A capacity handoff for a claim with no recorded pull request reads the forge first

```gherkin
Feature: An attention handoff never re-queues merged work
  As an operator following a needs-attention handoff
  I want a merged pull request found on the forge to route to reconcile-merged
  So that a dispatch that died before recording its pull request is not rebuilt

  Scenario: A merged pull request found only on the forge
    Given a stranded claim whose dispatch evidence names no pull request
    And the forge reports a merged pull request on the item's publish branch
    And no live process holds the item's ownership lock
    When needs-attention composes its capacity handoff
    Then the handoff advertises reconcile-merged and no status move

  Scenario: A live ownership lock blocks the reconcile handoff
    Given a stranded claim whose dispatch evidence names no pull request
    And the forge reports a merged pull request on the item's publish branch
    And a live process holds the item's ownership lock
    When needs-attention composes its capacity handoff
    Then the handoff advertises no status move and names the live ownership lock

  Scenario: An unreadable forge advertises no status move
    Given a stranded claim whose dispatch evidence names no pull request
    And the forge read fails
    When needs-attention composes its capacity handoff
    Then the handoff advertises no status move and names the failed forge read
```
