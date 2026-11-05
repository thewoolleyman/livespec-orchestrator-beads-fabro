---
topic: a-template-poisoned-item-is-superseded
author: seat:fleet-flaky-tests
created_at: 2026-11-05T18:01:24Z
---

## Proposal: drive names the stage and detail of a pre-run refusal

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When an `impl:` action ends in a Dispatcher refusal before any factory run is created, `drive`'s human summary MUST name the refusing stage and the outcome detail the Dispatcher reported. A goal-template preflight refusal then names every offending goal source, each ledger comment by its id and creation instant. Today the summary says only that the Dispatcher did not report green.

### Motivation

bd-ib-it2d, measured 2026-09-04 (livespec-dev-tooling-npsqeu), 2026-09-06 (livespec-console-beads-fabro-4jb3kl.3) and 2026-11-05 (bd-ib-v4gghg). On a goal-template preflight refusal, `drive` printed "Dispatcher did not report green for <id>." The stage appeared only in a reflection warning on stderr and the detail only in `tmp/fabro-dispatch-journal.jsonl`, so an operator had to know the journal existed to learn why. contracts.md `#### drive` says the operator summarizes `status`, exit code, stdout JSON and stderr, but it names no requirement on the human summary line. The dispatch-time tier classification of bd-ib-it2d (spec version 308) found the behaviour stated by no clause.

### Proposed Changes

In SPECIFICATION/contracts.md, section `#### drive`, after the paragraph that begins "`drive` executes only the selected action. For a selected impl dispatch action", insert this new paragraph:

**A pre-run refusal names its stage and detail.** When `drive` executes an `impl:<work-item-id>` action and the Dispatcher's outcome is a refusal that ended the dispatch before any factory run was created, `drive`'s human summary MUST name the refusing stage and the outcome detail the Dispatcher reported for it. It MUST NOT reduce them to a statement that the Dispatcher did not report green. The `--json` payload is unchanged. For a refusal at stage `goal-minijinja-preflight` (§"A template-poisoned item is superseded, never repaired in place"), the detail MUST name every offending goal source: each field by name, and each ledger comment by its id and its creation instant.

In SPECIFICATION/scenarios.md, append (renumber at revise if the number is taken):

## Scenario 321 — drive names the stage and offending sources of a goal-template preflight refusal

Given a `ready` work item one of whose ledger comments carries a goal-template opening delimiter
When an operator runs `drive --action impl:<work-item-id>` without `--json`
Then the Dispatcher refuses the dispatch at stage `goal-minijinja-preflight` before any factory run is created
And drive's human summary names the stage `goal-minijinja-preflight`
And the summary names the offending ledger comment by its id and its creation instant
And the summary does not consist only of a statement that the Dispatcher did not report green

## Proposal: A template-poisoned item is superseded, never repaired in place

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Ratify the dispatch-time goal-template preflight that already refuses an item whose goal sources carry a template opening delimiter. Add `dispatcher.py supersede-contaminated`, the sanctioned remedy for an item poisoned by an opener in an append-only ledger comment. It files one clean successor through the capture filing seam, carries the instruction comments forward with every opener rewritten to the shared bracket form, re-points the original's edges, and closes the original as a duplicate with the basis recorded on both items.

### Motivation

§"The human answer route: marker, poison preflight, run account, and write-before-transition ordering" ratifies that an opener in an append-only comment costs an item its dispatchability permanently. bd offers no comment edit or delete. Nothing ratifies a remedy, so each poisoned item has been superseded by hand: livespec-dev-tooling-npsqeu (2026-09-04), livespec-console-beads-fabro-4jb3kl.3 (2026-09-06), and bd-ib-v4gghg to bd-ib-nsw25x (2026-11-05). Each hand remedy re-derived which fields and comments to carry, and each risked copying the opener forward. Option (a) of bd-ib-it2d, dropping the refusal and trusting the escape, is NOT proposed. It would contradict the ratified posture, and bd-ib-ai9a's measurement that the engine rejects the escaped construct falsifies it. This proposal keeps the posture and makes the permanent cost recoverable by a successor. The dispatch-time preflight itself is current behaviour (`goal-minijinja-preflight`, the ledger check `goal-source-minijinja-opener`), and no clause yet states it.

### Proposed Changes

In SPECIFICATION/contracts.md, section `## Dispatcher policy settings`, insert a new subsection immediately after `### The human answer route: marker, poison preflight, run account, and write-before-transition ordering`:

### A template-poisoned item is superseded, never repaired in place

**The dispatch-time goal-template preflight.** Before rendering an item's goal brief, the Dispatcher MUST run the shared template-opener detector over every goal source: the item's title, description, acceptance criteria, notes, injected lessons and every ledger comment the brief would carry. When any source carries a goal-template opening delimiter, the Dispatcher MUST refuse the dispatch at stage `goal-minijinja-preflight`, before any factory run is created, and its outcome detail MUST name each offending source. An opener in an item FIELD is recoverable by editing that field. An opener in a ledger COMMENT is permanent, because a ledger comment is append-only. That is the posture the human answer route's poison preflight protects.

**The supersede verb.** An operator or a delegated coordinator MAY replace a comment-poisoned item by running `dispatcher.py supersede-contaminated --repo <path> --item <work-item-id> --reason <text>`. The command MUST:

1. Refuse with exit 3, writing nothing, when the item is closed, when none of the item's ledger comments carries an opener, or when any item field carries one. The field case names each field to edit instead, because a field opener is recoverable in place and would also poison the successor.
2. File exactly one successor through the filing seam the `capture-work-item` operation uses, never by a raw `bd create`. The successor carries the original's title, type, priority, description, acceptance criteria, labels other than lifecycle, claim and dispatch-record labels, `blocks` dependencies, and plan parent edge.
3. Re-point every `blocks` edge on which the original is the blocker so that the successor is the blocker.
4. Copy each of the original's instruction comments to the successor in their original order. Each copy MUST open with one provenance line naming the original's id, the source comment's id and its creation instant. An uncontaminated comment is copied verbatim. A contaminated comment is copied with every opener rewritten by the shared bracket-form sanitizer that the Dispatcher's own ledger-comment writers already apply. Record comments, those opening with a `livespec-` marker line, MUST NOT be copied, because the successor's own dispatches re-derive them. They stay readable on the closed original.
5. Write one ledger comment on the successor naming the original, the reason and the source ids of the record comments left behind. Write one on the original naming the successor and the reason. Append one `supersede-contaminated` journal record carrying both ids, the invoker and the UTC instant. Then close the original with resolution `duplicate`.
6. When a step after the successor is filed fails, exit non-zero naming the successor's id and the step reached, and leave the original open.

No text the command writes may carry a goal-template opening delimiter, so its successor passes the dispatch-time goal-template preflight on its next dispatch.

In SPECIFICATION/scenarios.md, append (renumber at revise if the number is taken):

## Scenario 322 — A comment-poisoned item is superseded by a successor that passes the goal-template preflight

Given an open work item with a plan parent, one `blocks` dependent, one instruction comment carrying a goal-template opening delimiter, one clean instruction comment and one `livespec-dod-judgement` record comment
When an operator runs `dispatcher.py supersede-contaminated --item <work-item-id> --reason <text>`
Then exactly one successor is filed with the original's title, type, priority, description, labels and plan parent
And the dependent's `blocks` edge names the successor as the blocker
And the successor carries both instruction comments in order, each opening with a provenance line, the poisoned one with its opener rewritten to the bracket form and the clean one verbatim
And the successor does not carry the record comment
And the original is closed with resolution `duplicate`, and each item carries a comment naming the other
And a dispatch of the successor passes stage `goal-minijinja-preflight`

## Scenario 323 — supersede-contaminated refuses an item it cannot or need not supersede

Given a work item that is closed, or whose ledger comments carry no goal-template opening delimiter, or one of whose fields carries one
When an operator runs `dispatcher.py supersede-contaminated --item <work-item-id> --reason <text>`
Then the command exits 3 naming the reason, and for the field case naming each field to edit
And no item, comment, edge, journal record or status change is written
