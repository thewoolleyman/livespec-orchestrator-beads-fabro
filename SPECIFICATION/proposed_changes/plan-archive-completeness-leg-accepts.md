---
topic: plan-archive-completeness-leg-accepts
author: claude-opus-5-5
created_at: 2026-11-13T01:34:38Z
---

## Proposal: Completeness-review evidence is judged against the plan as it stands at archive

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The archive's completeness leg requires an independent review attesting complete requirement-carrier coverage, but it states no recency for that evidence. The proof leg's record must postdate the last carrier-map event; the completeness leg's evidence has no such floor. Today a review written before a Definition of Done assertion was re-worded, or before a later round found a carrier missing, can still be handed to the archive and accepted. This proposal states when a completeness-review evidence record is STALE: its reviewed child set differs from the epic's current child set; it predates a current child's latest status change; or it predates the epic's last carrier-map event. It also states that a later record which does not attest complete coverage refuses every earlier one, including one named explicitly by comment id. A stale or refused record is handled as missing evidence, so a fresh reviewer is commissioned.

### Motivation

Implementation item bd-ib-t24wxz. Its filing-time tier record (spec v360) reads `partial` against ## Planning Lane realization: "It states a carrier-map-event recency floor only for the proof leg, not the completeness leg, and says nothing about a later non-attesting record refusing earlier evidence, including evidence passed as an explicit candidate comment id." legacy-coordinator-agent (session 56ce1bcd) routed the item to plan spec-implementation-lockstep (bd-ib-ax3rds) on 2026-11-13 as a filing-slug orphan. This proposal is filed under its recorded topic so the hold can read its ratification.

Measured instance: homelab plan secret-writer-stored-key-alias (epic hl-bvycoc).

- Round-2 evidence 01a1cdc2 attested complete coverage.
- Assertion 4 was then re-worded at 2026-11-12T19:59:39Z (scope event 01a1d158).
- An independent round-3 reviewer (comment 01a1d16e-cd40-77f6-808d-7c32a491e935, 2026-11-12T20:24:21Z) found the re-worded assertion had no carrier and recorded complete-coverage=false.
- Before any new child was filed, `archive_thread` could still have been given `completeness_review_comment_id` 01a1cdc2 and accepted it, because no child was added and no child status moved.

The child-set and status-change half of this recency is already implemented (bd-ib-0pf5: commits 8315cd184, 5b9c3948f, 6d0d4b581) and described in the plan operation's prose, but no ratified clause states it. It is stated here alongside the new floor so the leg's staleness rule has one statement.

### Proposed Changes

**1. `SPECIFICATION/contracts.md` §"Planning Lane realization".** Directly after the paragraph that ends "A self-review, a missing durable evidence reference, or a review that does not attest complete requirement-carrier coverage MUST NOT satisfy the completeness leg.", insert:

> **Completeness-review evidence is judged against the plan as it stands at archive.** Every completeness-review evidence record MUST name the child work-item ids its review read. `archive_thread` MUST grade a record STALE, and MUST NOT accept it, when any of the following holds, naming each cause that applies:
>
> - it names no reviewed child set, naming that cause;
> - its reviewed child set differs from the epic's child set at archive time, naming each child added and each child removed. The epic's child set is the same set of linked plan members the mechanical leg reads, enumerated once and used for both legs;
> - its comment's creation time is not strictly later than some current child's latest status instant, naming that child and that instant. A child's latest status instant is the latest of the `created_at`, `closed_at` and `updated_at` its ledger record reports. `updated_at` is included deliberately: a status change other than a close moves only `updated_at`, and the latest of the three over-reports rather than under-reports, which is the direction this gate fails in. A child reporting none of the three places no floor;
> - its comment's creation time is not strictly later than the epic's last carrier-map event, naming that event. A carrier-map event is a scope event carrying a `carriers:` block, per §"Plan Definition of Done and Proof of Done" → "The carrier map"; a ruling or deferral that is not a carrier-map event does not make a record stale.
>
> When the epic's timeline holds a completeness-review evidence record that does not attest complete requirement-carrier coverage, `archive_thread` MUST refuse every evidence record written before it, naming that later record. This applies whether the archive selects evidence from the timeline or is handed a record's comment id explicitly. A stale or refused record is handled exactly as missing evidence: the plan operation commissions a fresh independent completeness reviewer, and the plan remains unarchived until that reviewer records evidence the leg accepts.

**2. `SPECIFICATION/scenarios.md`, `## Scenario 55 — plan archive commissions a missing independent completeness review`.** Inside that scenario's Gherkin block, after the scenario `A mechanically complete plan without review evidence obtains a fresh review` and before the block's closing fence, add:

```gherkin

Scenario: Evidence written before the last carrier-map event is stale
  Given a mechanically complete plan epic whose completeness-review evidence attests complete coverage over its current child set
  And every child's latest status change predates that evidence
  And a later carrier-map event re-words one of the epic's plan assertions
  When archive_thread is given that evidence's comment id
  Then the archive refuses the evidence as stale, naming the carrier-map event
  And the plan directory and the epic are unchanged

Scenario: A later non-attesting review refuses every earlier evidence record
  Given a mechanically complete plan epic whose timeline holds an evidence record attesting complete coverage
  And a later evidence record on the same epic that does not attest complete coverage
  When archive_thread is given the earlier record's comment id
  Then the archive refuses it, naming the later non-attesting record
  And the plan operation commissions a fresh independent completeness reviewer

Scenario: Evidence written after the last carrier-map event over the current child set is accepted
  Given a mechanically complete plan epic whose last carrier-map event predates its newest evidence record
  And that record attests complete coverage over the epic's current child set
  And every child's latest status change predates that record
  When archive_thread runs
  Then the completeness leg accepts that record
```

This edits an existing scenario and adds no `## ` heading, so `tests/heading-coverage.json` is unchanged.
