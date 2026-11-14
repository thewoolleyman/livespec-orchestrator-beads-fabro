---
topic: archive-thread-matches-completeness-review
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-11-14T16:03:19Z
---

## Proposal: An archive names its completeness-review evidence by its evidence-id or by the comment that carries it, and an unmatched name refuses on its own terms

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

`archive_thread`'s evidence parameter is named `completeness_review_comment_id`, but the archive matches its value against the evidence record's `evidence-id` field. A caller who passes the ledger comment id of a valid, independent, current evidence record is refused with "independent completeness-review evidence is required". That refusal is meant for a timeline with NO evidence, so it sends the caller looking for a review that already exists. This proposal states that a caller MAY name the evidence by either identifier, its `evidence-id` or the id of the comment carrying it, and that both resolve to the same record, which is then graded by the unchanged rules. It also gives a named value that matches nothing its own refusal, which quotes the value, names both identifier kinds and commissions no reviewer. The no-evidence refusal is unchanged.

### Motivation

Work item bd-ib-hzwxbv ("archive_thread matches completeness_review_comment_id against the evidence-id, and an unmatched candidate refuses as if no evidence existed"). Its dispatch was held at 2026-11-14T07:35:35Z at the spec-change tier: `partial`, generalization target `## Planning Lane realization`, topic archive-thread-matches-completeness-review. legacy-coordinator-agent (session 7e9a4d1c) made plan spec-implementation-lockstep (bd-ib-ax3rds) its owner on 2026-11-14. The ratified section requires valid evidence and rejects "a missing durable evidence reference". It states neither which identifier a caller names evidence by nor a distinct refusal for a named value that matches nothing.

Measured on homelab epic hl-bvycoc at 2026-11-13T19:09Z:
- Round-4 evidence `homelab-hl-bvycoc-independent-review4-2026-11-13` sat in ledger comment `01a1d64d-c04a-7044-a5f9-854b6fb6a21c`. It was complete, independent (reviewer 01c74860, archiver eee67b17) and current over all five children.
- `archive_thread(completeness_review_comment_id="01a1d64d-...")` refused "independent completeness-review evidence is required". The same call with the evidence-id archived cleanly.

Design choices, stated for the grade:
1. **Accept both identifiers rather than rename the parameter.** The parameter's name, the plan operation prose and the pending topic `plan-archive-completeness-leg-accepts` all say a caller hands the archive a COMMENT id. That topic's two new Scenario 55 scenarios read "When archive_thread is given that evidence's comment id". Accepting both makes them true without re-wording a pending proposal, and it keeps every evidence-id caller working.
2. **An unmatched value is a caller's mistake, not an evidence gap.** It therefore commissions no reviewer. Commissioning one would spend a review on a plan whose valid evidence already exists.
3. **Grading is unchanged.** A resolved record meets the same self-review, recency and coverage tests as one selected from the timeline. Naming evidence explicitly never bypasses them.

In-flight alignment: ALIGN with `plan-archive-completeness-leg-accepts` (pending on master, same plan); its staleness and later-non-attesting rules apply to a named record unchanged, and this paragraph is placed after it. ALIGN with `attended-human-publishing-identity` (pending on master), which governs how the reviewer's identity is computed, not how the record is named. No open spec pull request touches the archive leg.

Fleet scope: every tenant whose plans archive through this plugin's `plan` operation.

### Proposed Changes

**1. `SPECIFICATION/contracts.md` §"Planning Lane realization".** Directly after the paragraph that ends "A self-review, a missing durable evidence reference, or a review that does not attest complete requirement-carrier coverage MUST NOT satisfy the completeness leg.", insert the paragraph below. When `plan-archive-completeness-leg-accepts` is ratified before this topic, insert it instead directly after the paragraph that topic inserts at the same place ("Completeness-review evidence is judged against the plan as it stands at archive."), so the identification rule follows the staleness rule it feeds.

> **An archive names its evidence by either identifier.** A caller of `archive_thread` MAY name the completeness-review evidence record the archive grades, by the record's `evidence-id` value or by the ledger comment id of the comment that carries the record, and `archive_thread` MUST resolve either to the record it identifies. When one `evidence-id` is carried by more than one comment, every carrying comment is a candidate, graded exactly as when the archive selects evidence from the timeline. A named record that resolves MUST be graded exactly as a record selected from the timeline: the self-review, recency and coverage rules apply to it unchanged. When the named value matches no completeness-review evidence record on the epic by either identifier, `archive_thread` MUST refuse, MUST quote the value it was given, MUST state that no completeness-review evidence record on the epic carries that `evidence-id` or comment id, and MUST NOT report that evidence is required. That refusal names a caller's mistake rather than an evidence gap, so it MUST NOT commission a completeness reviewer, and it MUST leave the plan directory and the epic unchanged. When no value is named and the epic carries no evidence record, `archive_thread` MUST still refuse with the report that independent completeness-review evidence is required.

**2. `SPECIFICATION/scenarios.md`, `## Scenario 55 — plan archive commissions a missing independent completeness review`.** Inside that scenario's Gherkin block, after its last scenario and before the block's closing fence, add the three scenarios below. They MUST follow any scenario `plan-archive-completeness-leg-accepts` adds there.

```gherkin

Scenario: Evidence named by the comment that carries it is graded as that evidence
  Given a mechanically complete plan epic whose timeline holds one independent, current completeness-review evidence record attesting complete coverage
  When archive_thread is given the ledger comment id of the comment carrying that record
  Then the archive grades that record and its completeness leg passes

Scenario: Evidence named by its evidence-id is graded as that evidence
  Given a mechanically complete plan epic whose timeline holds one independent, current completeness-review evidence record attesting complete coverage
  When archive_thread is given that record's evidence-id
  Then the archive grades that record and its completeness leg passes

Scenario: A named evidence value that matches no record refuses with its own message
  Given a mechanically complete plan epic whose timeline holds one completeness-review evidence record
  When archive_thread is given a value that is neither that record's evidence-id nor the comment id carrying it
  Then the archive refuses, quoting the value it was given
  And the refusal states that no completeness-review evidence record on the epic carries that evidence-id or comment id
  And the refusal does not report that evidence is required
  And no completeness reviewer is commissioned
  And the plan directory and the epic are unchanged
```

No heading is added, removed or renamed, so `tests/heading-coverage.json` needs no edit.
