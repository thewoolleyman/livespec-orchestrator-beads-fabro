# Post-zi5ygh follow-up drafts (2026-10-15)

This note records the three observations from the handoff
`relay-handoff-2026-10-15-lhzpam-closed-zi5ygh-accepted`, made during the
bd-ib-zi5ygh host capture against v0.198.0. Each was checked against the
v0.198.1 source (plugin build `3e869a2266c3`) and the ratified spec. Two of
them are defects and are drafted below as plan children. The third is already
covered by an existing child.

None of the three has been filed. The session that wrote this note was
unattended. The capture front-end only files after the user answers "file?",
and an unattended session cannot get that answer. An attended session should
file the two drafts through `capture-work-item` as children of `bd-ib-lrik25`.
It should then add them to the carrier map in a new scope event.

## Prior-art scan

The scan covered all 1,392 records in the tenant (`bd list --status all --limit 0
--json`), including closed ones. It searched title, description and notes for
`max_handoffs`, for retry and operation-identity wording, for "carries no
authority chain", for `genesis` and for "execution receipt".

The hits were bd-ib-lhzpam, wdl577 and zi5ygh (all closed), plus 22yfvh,
jy23vh, ezuj43, s5idxj and t3znvw (all ready) and bd-ib-l114 (backlog). No
record describes observation 1 or observation 2. bd-ib-22yfvh already covers
observation 3.

## Observation 1: a retry of the handoff that consumes the last unit is refused, not recovered

### The rule

`SPECIFICATION/contracts.md` §"Required result, budget and progress epoch"
says: "retried calls with the same operation identity MUST recover the
original event rather than duplicate handoffs or extend a deadline".

### What the code does

In `commands/_plan_tracked_write.py`, `_tracked_write` calls
`decide_tracked_write` first. That call runs the expiry ladder (the
"the obligation … is expired at its … limit" refusal) against the observed
head. The operation-id lookup that recovers an already-committed transition
lives in `commit_transition` (`_plan_epoch_chain.py`, the receipt and event
scan keyed on `operation_id`), and it only runs after that decision has
admitted the write.

So when a handoff consumes the last `max_handoffs` unit and its caller retries
with the same operation identity:

1. The head the retry observes already shows consumed equal to max.
2. `decide_tracked_write` refuses the retry as expired.
3. The recovery path is never reached.

The original write committed, so nothing is duplicated. But the caller gets a
refusal for a write that succeeded. That is the confusing result the rule
exists to prevent, and a caller that treats the refusal as failure may go on
to register a causal recovery for an obligation it just met.

### Draft child

Title: "Recover a same-operation retry of the budget-exhausting handoff instead of refusing it as expired".

Draft Definition of Done. Hand-check it against the dod_gate rules before
filing. The fix and its proof run on pure package code with a fake store, so
it is `factory_captured`.

```markdown
## Definition of Done

References: ## Scenario 147 — A plan deadline survives pointer rewrites and permits causal recovery

- Retrying an accepted handoff with the same operation identity after that handoff consumed the final max_handoffs unit returns the original committed transition with idempotent set, instead of an expiry refusal.
- That recovered retry appends no second handoff comment and leaves the consumed handoff count and original deadline unchanged.
- A different operation identity submitted at the same exhausted budget is still refused as expired before any comment or pointer mutation.
```

## Observation 2: after genesis, the missing-tracking finding says the chain is absent

### What the code does

`commands/_plan_progress_resume.py` reaches `_missing_progress()` in two
different states:

- The chain read returns a `*missing` finding. The epic has no authority
  chain at all.
- The chain head reads fine, but `obligation_of(authority=...)` returns None.
  The chain exists, but no executable-kind write has placed an obligation on
  it yet. This is the state just after `create_genesis_token` or the
  `migrate-plan-records` genesis.

Both states produce the same text: "this plan epic carries no authority
chain, so no required result or budget is tracked;
remedy=migrate-plan-records". In the second state that text is false, and
the remedy it names has already run. Running the migration again cannot
clear the finding, because only an executable-kind pointer write with a
`required_result` and a `budget` creates an obligation.

This epic is a live instance of the trap. Its pointer is `kind: none`, so even
after `migrate-plan-records` gives it a chain, the finding will keep naming
the migration as the remedy.

### Draft child

Title: "Distinguish a chain with no obligation from a missing chain in the plan-progress finding".

```markdown
## Definition of Done

References: ## Scenario 148 — Unattended resume observes expired, legacy and unobservable progress

- resume_directive on a plan epic whose authority chain exists but carries no obligation reports a finding that names the chain as present and names an executable-kind next_action write carrying required_result and budget as the remedy.
- resume_directive on a plan epic with no authority chain still reports plan-progress-tracking: missing with remedy migrate-plan-records.
```

Scenario 148 ("legacy reads do not invent budgets") governs the
missing-tracking finding, so the draft names it rather than Scenario 147.

## Observation 3: running the authorized diagnosis records no execution receipt

This is by design. Receipts come from an observer, not from the writer.
bd-ib-22yfvh ("Record claim, execution and outcome receipts on an executed
causal recovery attempt") already owns the receipt legs, so nothing new is
drafted.
