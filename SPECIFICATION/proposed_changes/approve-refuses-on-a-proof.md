---
topic: approve-refuses-on-a-proof
author: claude-opus-5-5
created_at: 2026-11-12T07:33:05Z
---

## Proposal: Every route to ready takes the Definition-of-Done judgement before it moves the item

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The pre-admission Definition-of-Done judgement (all six dod_gate checks, so check 4's coherence and check 5's proof-surface feasibility included) is stated today for intake, approve and groom routes from `backlog` or `pending-approval` only, and the approve paragraph of §"Work-item state semantics" contradicts it for an effective-manual item by calling the goal-template check "the only check added". This proposal removes the contradiction, so `approve` on both admission policies refuses on the judgement's needs-human verdict, and extends the same pre-admission taking to the routes that bypass intake today: `resolve-blocked:<work-item-id>:ready`, and the `seed-ruling` and `fresh-ruling` commands. Each refuses before it moves or rules the item. `release-spec-tier` already routes through intake, and this proposal states that explicitly. The pre-dispatch wall is kept as the backstop for edits made after admission.

### Motivation

Work item bd-ib-ccl3wf (plan bd-ib-ax3rds, child of bd-ib-ynnykl), the unstated remainder of bd-ib-y4li25, split on legacy-coordinator-agent's (session c29d86f8) grade on 2026-11-12 and routed to this seat for a propose-change. Its spec-change tier record (spec 359, verdict partial, generalization target `## Work-item state semantics`) finds: the approve clause for an effective-manual item names only the goal-template check as added; nothing states that `resolve-blocked:<id>:ready` or the seed and fresh re-dispatch rulings apply the Definition-of-Done refusals; check 5 appears in Scenario 272 only as a dod_gate outcome.

Measured before drafting (ledger, 2026-11-12), and stated here so the grade can weigh it. Neither cited instance is a valve that skipped the check. livespec-dev-tooling-n277mo: its pre-admission taking on 2026-11-10 at 11:08Z and its pre-dispatch taking on 2026-11-12 at 05:48Z (claude-acp claude-sonnet-5-5) both returned `admitted`. The in-run dod_gate refused on check 5 at 05:55Z (run 01M774XA07Q3, the v0.321.0 canary-B slot), with the grading set [terminal, tmux, headless_browser, herdr] committed. livespec-dev-tooling-hlyayb: pre-admission returned `admitted` at 00:49Z, and the pre-dispatch wall refused on check 4 at 05:16Z with no claim and no factory run, as §"Effective acceptance criteria" → "Judged again before dispatch" requires. No resolve-blocked, seed or fresh ruling was involved; the re-queues were launcher tickets into that refusal. Both instances are a host taking admitting what a later taking refused. That is a judgement-consistency defect, which this proposal does NOT address. It is carried by work item bd-ib-lqjygl, which records both instances with their models and subject digests. The node's digest is unrecorded until bd-ib-67wnts lands; hlyayb's two takings graded different subject digests. What this proposal does close is the stated gap the tier record names: an effective-manual approve whose text contradicts the pre-admission paragraph, and three routes back into dispatchability that today are first judged only at the pre-dispatch wall, so an operator or coordinator learns of a Definition-of-Done refusal only after spending a ticket.

Design choice: each new taking is the WHOLE pre-admission judgement, not a check-4-plus-check-5 subset. A subset would be a second rubric and could disagree with approve and the node on the same bytes; the whole judgement shares their subject and rubric digests, so the cache-eligible record of one taking answers the next.

Fleet scope: these valves and commands are the orchestrator Dispatcher's, so every tenant the orchestrator drives inherits the change through the plugin; no consumer spec changes.

In-flight alignment (survey on 2026-11-12 ~07:50Z; relationship `align` for each): #5013 the-filing-display-recognises-only lists "the approve and release valves' Definition-of-Done judgement" among scenario-recognising surfaces, which these takings are; #5005 a-needs-human-rest-overwrites keeps `resolve-blocked:<id>:ready` label-preserving, and this proposal only adds a refusal before that move; pending a-plain-re-dispatch-of and a-stale-seed-is-rebased-before-it-runs change which items are released for recovery and how a seed starts, not whether the ruling commands judge. #5009 is unrelated. The topic is the item's recorded linked stem, so the hold links without a relink.

### Proposed Changes

**1. Remove the effective-manual contradiction (`contracts.md` §"Work-item state semantics").**

In the paragraph opening "**`approve` on an auto-admission item held by intake.**", replace the sentence "For an effective-manual item that is the only check added; `approve` on such an item is otherwise unchanged." with:

> On BOTH effective admission policies, `approve` is a route to `ready` that §"Effective acceptance criteria" → "Judged before admission" governs: before it moves the item it MUST take that pre-admission Definition-of-Done judgement. When the judgement would end a run through the structured needs-human ending, `approve` MUST leave the item in `pending-approval`, MUST refuse with a result naming each finding the judgement produced, and MUST append the verdict to the item as that paragraph requires. Such findings include an incoherent assertion (dod_gate check 4) and a `factory_captured` assertion whose proof surface no capability in the grading set provides (dod_gate check 5). The goal-template refusal, this judgement and, for an effective-auto item, the mechanical re-check above are the only checks `approve` adds; it is otherwise unchanged. Scenario 350 in `scenarios.md` exercises the check-5 refusal.

**2. Name every route to `ready` (`contracts.md` §"Effective acceptance criteria" → "Judged before admission").**

Replace the paragraph's opening "Before intake routes an implement-kind item to `ready` — from `backlog` or `pending-approval`, whether through intake, the approve valve, or groom — the Dispatcher MUST run the same Definition-of-Done judgement" with:

> Before any route moves an implement-kind item to `ready`, the Dispatcher MUST run the same Definition-of-Done judgement. The routes are: intake, the approve valve, or groom from `backlog` or `pending-approval`; the intake routing that `release-spec-tier` invokes; and `resolve-blocked:<work-item-id>:ready` from `blocked`, with or without `--answer`.

The rest of the paragraph applies to every one of those routes unchanged: the verdict comment, the cache-eligible reuse, the did-not-run route, and the `needs-attention` hygiene fact. Add immediately before the paragraph's sentence "When that judgement admits the item, intake MUST route it exactly as it would without the judgement.":

> For `resolve-blocked:<work-item-id>:ready`, a judgement that would end a run through the structured needs-human ending MUST refuse the press. The item MUST stay at `blocked` / `blocked_reason: needs-human`, the result MUST name each finding the judgement produced, and the verdict MUST be appended to the item. `resolve-blocked:<work-item-id>:backlog` MUST NOT take the judgement. Each of these takings is a pre-admission taking in the sense of "One rubric, one subject", and it is journaled as one.

**3. Judge a re-dispatch ruling before it is written (`contracts.md`, the "A ruled seed names the tree…" and "A fresh ruling routes…" paragraphs).**

In each paragraph, after the sentence that names the command's invocation, add:

> Before it writes anything, the command MUST take the pre-admission Definition-of-Done judgement of §"Effective acceptance criteria" → "Judged before admission" for an implement-kind item. When the judgement would end a run through the structured needs-human ending, the command MUST refuse (exit `3`), naming each finding the judgement produced. It MUST then write no ruling comment and journal no ruling record. The judgement record that every taking appends MUST still be appended. When the judgement cannot be run, the command MUST record that on the item and proceed as it would without the judgement.

**4. Keep the pre-dispatch wall as the backstop (`contracts.md` §"Effective acceptance criteria" → "Judged again before dispatch").**

Replace the opening "Admission is not the only route to `ready`: an item also reaches it through `resolve-blocked:<id>:ready` after a needs-human ending, and its Definition of Done MAY be edited after it was admitted. So before" with:

> Every route to `ready` is judged before it moves the item, but an item's Definition of Done MAY be edited after it reached `ready`, and a rework-pending re-dispatch starts from `active` rather than from `ready`. So before

The paragraph is otherwise unchanged; the pre-dispatch wall MUST still run on every dispatch path.

**5. Scenarios (`scenarios.md`).** Append the following two headings, each followed by its gherkin block. The revise pass MUST give each the next free scenario number at revise time if 350 or 351 is taken, updating the cross-references in changes 1 and 2 to match.

## Scenario 350 — approve refuses a manual-admission item whose factory-captured assertion needs a surface no listed capability provides

```gherkin
Feature: approve takes the pre-admission Definition-of-Done judgement on both admission policies
  Scenario: a manual-admission item with an unprovable factory-captured assertion stays at pending-approval
    Given a work-item in `pending-approval` whose effective `admission_policy` is `manual`
    And its Definition of Done carries a `factory_captured` assertion whose proof surface no capability in the committed `dispatcher.sandbox_capabilities` array provides
    When the operator drives `approve:<work-item-id>`
    Then the item stays in `pending-approval`
    And the result names the assertion and the capabilities the judgement read
    And the judgement's verdict is recorded on the item as a ledger comment
  Scenario: a manual-admission item the judgement admits moves to ready as before
    Given a work-item in `pending-approval` whose effective `admission_policy` is `manual`
    And the pre-admission judgement admits its Definition of Done
    When the operator drives `approve:<work-item-id>`
    Then the item moves to `ready` and the transition is journaled with its actor
```

## Scenario 351 — every release back toward dispatch takes the Definition-of-Done judgement before it moves or rules the item

```gherkin
Feature: release routes refuse an item the pre-admission judgement would hold
  Scenario Outline: a release route refuses on a needs-human verdict and changes nothing
    Given an implement-kind work-item whose Definition of Done the pre-admission judgement would end through the structured needs-human ending
    When the operator runs <route>
    Then the route refuses, naming each finding the judgement produced
    And <unchanged>
    And the judgement's verdict is recorded on the item as a ledger comment

    Examples:
      | route                                              | unchanged                                                              |
      | `drive --action resolve-blocked:<work-item-id>:ready` | the item stays at `blocked` / `blocked_reason: needs-human`            |
      | `dispatcher.py seed-ruling` for the item            | no `livespec-seed-ruling` comment is written and no record is journaled |
      | `dispatcher.py fresh-ruling` for the item           | no `livespec-fresh-ruling` comment is written and no record is journaled |

  Scenario: a release route on an item the judgement admits behaves as before
    Given an implement-kind work-item resting at `blocked` / `blocked_reason: needs-human` whose Definition of Done the pre-admission judgement admits
    When the operator drives `resolve-blocked:<work-item-id>:ready`
    Then the item moves to `ready` exactly as it did before this change
```

**6. Revise co-edit.** Scenarios 350 and 351 are two new `## ` headings, so the revise pass that accepts this proposal MUST, in the same commit and through `resulting_files[]`, add two `tests/heading-coverage.json` rows, one per heading. Each row MUST carry `test: "TODO"`, `work_item: "bd-ib-ccl3wf"`, and a non-empty `reason` naming the tier the owed test runs at, integration or above. The same commit MUST add one matching entry per row to `tests/heading-coverage-debt.json`, carrying the key three (`spec_root`, `spec_file`, `heading`), `work_item: "bd-ib-ccl3wf"` and `first_seen` set to the revise date. That is the spec-first admission the `check-heading-coverage-debt-register` gate allows, so neither the `unregistered_todo` nor the `register_grew` direction fires. If the revise renumbers either scenario, the rows and entries MUST carry the renumbered heading text.
