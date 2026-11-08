---
topic: a-goal-template-opening-delimiter
author: claude-opus-5-5
created_at: 2026-11-08T03:56:25Z
---

## Proposal: The goal render neutralizes every ledger comment, and the goal-template preflight refuses only on an item field, with exit code 5

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Ledger comments stop being a refusal source for the goal-template preflight. The Dispatcher renders every ledger comment it puts into a goal brief through the shared neutralizer `comment_safe_external_text`, which rewrites each goal-template opening delimiter to its bracket form, so one comment can no longer make an item permanently undispatchable. The preflight keeps refusing an opener in an item field (title, description, acceptance criteria, notes) or in an injected lesson, because those can be edited. That refusal is permanent for the invocation that hit it, so it joins the code-5 list of the Dispatcher exit codes, and a fleet launcher therefore does not re-take the ticket.

### Motivation

Work item bd-ib-cfgtlo, filed by the radar-and-deterministic-admission seat on 2026-11-08 under a legacy-coordinator-agent routing. Measured 2026-11-08: bd-ib-ev3pbz (03:36:52Z) and bd-ib-s754le (03:38:47Z) each spent about 5.5 minutes of drive before goal-minijinja-preflight refused a literal opener, and the launcher re-took each ticket on its first retry, because the refusal does not exit 5 and §"Provisional fleet launch scripts" re-tickets every other early exit. The coordinator's own repair comments then poisoned both items for good, because the preflight reads every ledger comment and comments are append-only. Two alternatives were rejected. Refusing an opener on the comment-write path cannot cover a raw `bd comment`, which is how both items were poisoned. Escaping comment text for the template engine was measured failing in bd-ib-ai9a: the escaper ran and Fabro rejected the escaped goal. The bracket form needs no template parsing, and this specification already uses it for the supersede copy, the preserve-by-reference pointer and the needs-human cause record.

### Proposed Changes

In `contracts.md` §"Dispatcher policy settings" → "A template-poisoned item is superseded, never repaired in place", replace the paragraph **The dispatch-time goal-template preflight.** with:

> **The dispatch-time goal-template preflight.** Before it renders an item's goal brief, the Dispatcher MUST pass every ledger comment the brief would carry through `comment_safe_external_text`, the shared neutralizer that rewrites each goal-template opening delimiter to its bracket form, and MUST carry the neutralized text in the brief. It MUST then run the shared template-opener detector over the remaining goal sources: the item's title, description, acceptance criteria, notes and the injected lessons. When any of those sources carries a goal-template opening delimiter, the Dispatcher MUST refuse the dispatch at stage `goal-minijinja-preflight`, before any factory run is created. Its outcome detail MUST name each offending source by field name, or name the lesson. A ledger comment MUST NOT be a cause of this refusal. An opener in an item field is recoverable by editing that field. The neutralization concerns the rendered goal only: it MUST NOT alter the ledger comment, and the human answer route's poison preflight, which protects comments the Dispatcher itself writes, is unchanged.

In the same section, the supersede verb `dispatcher.py supersede-contaminated` MUST remain available, unchanged, for an operator who wants a successor whose ledger is free of openers. Its section heading and any sentence that calls a comment-poisoned item undispatchable MUST be reworded so that they no longer state that such an item cannot be dispatched.

In `contracts.md` §"The skill surface" → "A pre-run refusal names its stage and detail", replace "the detail MUST name every offending goal source: each item field by name, and each ledger comment by its id and its creation instant" with "the detail MUST name every offending goal source: each item field by name, and each offending injected lesson".

In `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Dispatcher exit codes", extend the description of code `5` with: "or the goal-template preflight refused the dispatch at stage `goal-minijinja-preflight` because an item field or an injected lesson carries a goal-template opening delimiter (§\"Dispatcher policy settings\" → \"A template-poisoned item is superseded, never repaired in place\")". The existing rule that every exit-`5` refusal writes exactly one `REFUSED: ` line naming the work item, the refusal and its remedy MUST apply to it, and the remedy MUST name the field to edit.

In `scenarios.md`, Scenario 321 MUST be amended. Its first Scenario MUST use a ready work item W whose description carries a goal-template opening delimiter, and MUST assert that drive's human summary names the stage `goal-minijinja-preflight` and the field `description`, and that the dispatch exits 5 with one `REFUSED: ` line naming W, the field and the remedy. The "field opener is named by the field" Scenario becomes redundant and MUST be removed.

A new scenario MUST be added, "A ledger comment carrying a goal-template opener is neutralized in the goal and does not refuse the dispatch", with these steps. Given a ready work item W whose fields carry no opener and one of whose ledger comments, C, carries a goal-template opening delimiter. When the Dispatcher renders W's goal for a dispatch. Then the dispatch passes stage `goal-minijinja-preflight`, and C's text appears in the rendered goal with each opener in bracket form. And the ledger comment C is unchanged.

Scenario 322's closing step "a dispatch of S passes stage goal-minijinja-preflight" MUST remain true. Its Feature narrative MUST NOT state that the original W is undispatchable.

The revise MUST co-edit `tests/heading-coverage.json` for the new scenario heading, with a `TODO` row whose owning work item is bd-ib-cfgtlo.

## Proposal: A goal-template opener in an item field is a mechanical filing finding, and approve refuses it

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The filing-time Definition-of-Done wall treats a goal-template opening delimiter in an item's title, description, acceptance criteria or notes as a MECHANICAL finding, found by the same shared template-opener detector the goal-template preflight uses. So an item carrying one rests at `pending-approval` instead of reaching `ready`, and `approve` refuses it, on both effective admission policies, until the field is edited. The opener is caught where it was made, before any dispatch time is spent.

### Motivation

Work item bd-ib-cfgtlo. On 2026-11-08 `filing_display` and capture-work-item reported no findings for bd-ib-ev3pbz and bd-ib-s754le, which were then refused at goal-minijinja-preflight after about 5.5 minutes of drive each. The opener is detectable with no model judgement, so a check that can only run first at launch spends a dispatch on a defect that filing already had in hand. The capture contract says capture never refuses on a finding, so the finding withholds `ready` rather than refusing the filing.

### Proposed Changes

In `contracts.md` §"Effective acceptance criteria", in the paragraph that divides the filing-time findings into MECHANICAL and ADVISORY ("The findings divide in two. A MECHANICAL finding — the section absent, a reference unresolved, a proof-mode declaration or `Reason:` line malformed — withholds `ready`"), add a fourth mechanical kind: "a goal-template opening delimiter in the item's title, description, acceptance criteria or notes, as the shared template-opener detector reports it". The finding MUST name the field and the offset of the first delimiter in it, and its remedy MUST name the field to edit. Like every mechanical finding, it MUST be displayed by `filing_display`, MUST be recorded on the item as a `definition-of-done finding (mechanical):` ledger comment, and MUST withhold `ready` at intake. That comment MUST itself pass the shared template-opener detector, so it MUST NOT quote the delimiter.

In `contracts.md` §"`approve` on an auto-admission item held by intake", `approve` MUST refuse an item whose title, description, acceptance criteria or notes carry a goal-template opening delimiter, on BOTH effective admission policies. It MUST leave the item in `pending-approval` and MUST return a result naming each such field. For an effective-manual item this is the only check added; `approve` on such an item is otherwise unchanged. A ledger comment MUST NOT be a cause of this refusal, because the goal render neutralizes comments.

In `scenarios.md`, a new scenario MUST be added, "A goal-template opener in an item field is a mechanical filing finding and approve refuses it", with these steps. Given a work item W filed through the capture filing seam whose description carries a goal-template opening delimiter. Then `filing_display` reports a `(mechanical)` finding naming the field `description`. And W rests at `pending-approval` even when its effective `admission_policy` is `auto`. And an `approve` of W leaves it at `pending-approval` with a result naming the field `description`. And once the description is edited to carry no delimiter, an `approve` of W routes it onward as it would any other item.

The revise MUST co-edit `tests/heading-coverage.json` for the new scenario heading, with a `TODO` row whose owning work item is bd-ib-cfgtlo.
