---
topic: plan-resume-surfaces-rulings-and-timeline-omissions
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T16:16:20Z
---

## Proposal: The plan timeline read path reports every plan comment kind it does not return

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Ledger-held handoff persistence" makes the comment timeline read path the authoritative resume source, but says nothing about which plan comment kinds it returns. The package reader returns only handoff entries and scope events, while a plan epic also holds child-disposition, decision-record, completeness-review-evidence, progress and relay records. This proposal keeps the reader narrow, because handoffs and scope events are the resume-relevant kinds, and requires it to report a count for every other plan record kind it skips. An omitted kind then can never read as a missing or lost write.

### Motivation

Work-item bd-ib-p38r, measured 2026-08-23 on epic overseer-hgq4wi: read_timeline returned 69 entries while the epic held 104 typed plan comments across five kinds, so 35 comments, three whole kinds, were invisible through the reader named for the timeline. Because ledger comments are append-only, an absence that reads as a failed write invites a duplicate that can never be removed. The plan spec-implementation-lockstep (epic bd-ib-ax3rds) audit of 2026-10-19 classified the item UNGOVERNED, and its R1 batch 2 routes it here. Of the item's three options (widen the reader, rename it, or report omissions), reporting omissions changes no caller's input and adds the least surface, so it is the one proposed.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Planning Lane realization" → "Ledger-held handoff persistence", insert the following sentences immediately AFTER the sentence "Scope events (rulings, deferrals) remain comments, because they are the part a human reads back.":

> The timeline read path MUST return every handoff entry and every scope event of the epic, oldest first, each labelled with its kind. For every other plan record kind present on the epic, meaning a comment whose first line is a `plan-` record prefix such as `plan-child-disposition`, `plan-decision-record`, `plan-completeness-review-evidence`, `plan-progress-event` or `plan-relay-event`, it MUST report that kind's prefix and the count of such comments beside the entries it returns, and MUST NOT report them as absent. Scenario 213 in `scenarios.md` exercises this rule.

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 213 — The plan timeline reports the record kinds it does not return

```gherkin
Feature: A narrow timeline reader never manufactures an absence
  As a session verifying that a plan record was written
  I want the timeline to say which record kinds it left out
  So that an omitted kind is never mistaken for a lost write

  Scenario: Skipped record kinds are counted
    Given a plan epic holding handoff entries, scope events and two plan-child-disposition comments
    When the timeline is read
    Then the handoff entries and scope events are returned oldest first, each labelled with its kind
    And the result reports plan-child-disposition with a count of 2

  Scenario: An epic holding only returned kinds reports no omissions
    Given a plan epic holding only handoff entries and scope events
    When the timeline is read
    Then the result reports no omitted record kinds
```


## Proposal: A plan resume returns the epic's rulings and deferrals beside the typed next action

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Typed next_action and last_session" requires resume_directive to return the identity of the continuation ruling it acts under, and nothing about any other ruling. This proposal generalizes that sentence: every resume returns every scope event that is not a carrier-map event (the epic's rulings and deferrals), oldest first, beside the typed next_action, and the plan operation surfaces them before it acts. An epic with none returns an empty list and resumes exactly as before.

### Motivation

Work-item bd-ib-ghijrt, measured 2026-10-18 on plan epic bd-ib-fyozyd: resume_directive returned ask=False for an await pointer, the session read only the last three timeline entries, and it never saw two binding maintainer rulings recorded as scope events the day before. It then ran a large item alone as a canary while independent tracks sat idle, which the maintainer ruled a failure. The item itself records that no clause states this behaviour and that it needs a spec route first. The plan spec-implementation-lockstep audit of 2026-10-19 classified it UNGOVERNED, and R1 batch 2 routes it here as an amendment of the existing ruling-identity sentence rather than a new clause.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Planning Lane realization" → "Typed `next_action` and `last_session`", replace the clause "and `resume_directive` MUST return the ruling's identity in its `reason` whenever it acts under one." with:

> and `resume_directive` MUST return the ruling's identity in its `reason` whenever it acts under one. Every resume, attended or unattended and whether or not it asks, MUST ALSO return every scope event on the epic that is not a carrier-map event (its rulings and deferrals, continuation rulings included), oldest first, beside the typed `next_action`, and the `plan` operation MUST surface them to the resuming session before it acts on `next_action`. An epic with no such scope event MUST return an empty list. Scenario 214 in `scenarios.md` exercises this sentence.

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 214 — A plan resume returns the epic's rulings beside the typed next action

```gherkin
Feature: A resuming session reads the binding rulings before it acts
  As the maintainer whose rulings are recorded as scope events
  I want every resume to return them with the next action
  So that a session cannot act on the pointer while a ruling it never read binds it

  Scenario: Rulings are returned oldest first
    Given a plan epic carrying two maintainer-ruling scope events and one carrier-map event
    When resume_directive runs
    Then it returns the two ruling scope events oldest first beside the typed next_action
    And it does not return the carrier-map event among them

  Scenario: An epic without rulings resumes as before
    Given a plan epic carrying no scope event other than carrier-map events
    When resume_directive runs
    Then it returns an empty rulings list and the same next_action decision as before
```

