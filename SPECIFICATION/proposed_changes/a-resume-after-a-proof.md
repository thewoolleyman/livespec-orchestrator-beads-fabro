---
topic: a-resume-after-a-proof
author: claude:factory-run-work-preservation plan seat session d387b8
created_at: 2026-11-13T10:30:48Z
---

## Proposal: A resume after an ended proof_verify that published no record re-enters at proof_verify on the same captured head

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add one paragraph to the resume section of contracts.md §"Dispatcher loop invocation surface": a resume re-enters at `proof_verify` when the latest proof record is a `captured` record on the pull request's current head and the earlier run's factory record shows `review` approving after that capture, then a `proof_verify` visit that published no record, then only a terminal. The resume record names the factory record as its source. When the factory no longer holds the run, or cannot be read, today's verdict fallback stands (captured enters at review). FLEET SCOPE: every resume after an ended proof_verify in every repository, including recovery routing's resume route. Add two Scenario 142 scenarios; no heading changes.

### Motivation

bd-ib-bwwkne (plan factory-run-work-preservation, epic bd-ib-nckst7) is at pending-approval at spec-change tier. Its filing-time tier record (spec version 367) reads verdict unstated, generalization target ## Dispatcher loop invocation surface, linked topic a-resume-after-a-proof. legacy-coordinator-agent (2026-11-13) ordered this seat to cut the proposal under that topic, FLEET SCOPE: every resume after an ended proof_verify, in every repository.

THE INCIDENT. On livespec-dev-tooling-5wybjq, run 01M7A2P35VZH8WYX5VBVJ3YH9R went proof_capture@2 (posted 09:46:03Z on publish head e49767e31, PR #4491), then review@2 (approve, posts nothing), then proof_verify@1. That visit failed on both attempts with "the agent answered session/prompt with an error: Authentication required" (failure_class retry_requested, acp.turns 0), and the run took needs_human. The owner's route was verify-only. `dispatcher.py resume` (build f4c05ab80e4e) journaled resumed_at=review, resumed_at_source=pull-request-latest-record, head e49767e31. Resume run 01M7A5Y9ZW3J re-ran review, which then routed to review_fix: a whole fix round spent to replay one capture that was already good. Measured by legacy-dispatcher-agent (seat 2b7119e1, 10:12:57Z) and fabro-currency (session 2032fcbc).

WHY THE SPEC PRODUCES IT. The resume section reads the resumed-at stage from the factory record only as "the node the earlier run was executing when it terminated", or the target of the edge its last succeeded node selected. A run that ended through the needs_human terminal after a failed proof_verify has neither pointing at proof_verify, so the stage falls to the latest record's verdict, and captured maps to review. The shipped reader matches: resume_anchor (_dispatcher_resume_anchor.py) prefers factory_reading's executing_node, which is None for an ended run. Nothing records that review approved after the capture, or that verify failed for a non-proof reason.

NARROWER FIX CONSIDERED (rule P5). proof_verify already carries max_retries=1 in implement-work-item/workflow.fabro, and the measured run spent both attempts on the same refusal; the credential read usable again only minutes later. A wider in-stage retry would not have helped, so the re-entry point is the fix.

PRECEDENT. contracts.md's republication anchor (spec v140, proposal resume-republication-anchor, bd-ib-elkb33) already lets the earlier run's factory record decide an anchor the posted records cannot, and it falls back when the factory no longer holds the run. This paragraph applies the same shape to the proof_verify ending. Re-entering at proof_verify repeats nothing completed, since the replay is read-only and reruns afresh against the same capture on the same head that review approved.

RELATIONSHIP TO IN-FLIGHT WORK (survey 2026-11-13: 22 open spec PRs, and every pending proposal on master). No open PR's proposal touches the resumed-at stage. Four pending proposals mention resume --item in passing (a-fleet-launcher-holds-its, a-plain-re-dispatch-of, the-fleet-launcher-serializes-each, the-fleet-launcher-reports-a); none changes the resumed-at rule. ALIGN with all of them.

### Proposed Changes

### 1. `SPECIFICATION/contracts.md` §"Dispatcher loop invocation surface", section "Resume from a published pull request (`resume --item`)": add one paragraph

Insert this paragraph directly AFTER the paragraph that begins "The *resumed-at stage* is the node the earlier run was executing when it terminated" and ends "as not live; only an unanswered or errored query is unobservable.", and BEFORE the paragraph that begins "**What a resume does.**", separated by one blank line on each side. No existing paragraph changes:

```markdown
**A resume after an ended `proof_verify` re-enters at `proof_verify`.** When the latest proof record on the pull request is a `captured` record, the head it names equals the pull request's current head, and the factory that the earlier dispatch names still holds the earlier run, the resumed-at stage MUST be `proof_verify` when that run's factory record shows ALL of the following: (a) a `review` visit, after the `proof_capture` visit that published the latest proof record, whose outcome selected `approve`; (b) a later `proof_verify` visit that ended without publishing a proof record, whether it failed, exhausted its retries, timed out, or succeeded without a verdict label; and (c) after that `proof_verify` visit, the run entered no stage other than a terminal node (`needs_human`, `non_converged` or `exit`). Under this anchor the earlier run is that run, the published head is the head the latest proof record names, and the resume record MUST name the factory record as the source that decided the stage. This anchor takes precedence over the verdict of the latest record, which would otherwise send a `captured` record to `review`, because the factory record shows that `review` already approved the same capture on the same head and that only its replay is unfinished. When the factory answers that it no longer holds the earlier run, or cannot be read, this anchor does not apply, and the resumed-at stage is derived from the latest record's verdict exactly as the preceding paragraph states. A resume this anchor decides MUST run the replay afresh against the capture the latest record carries and MUST NOT read the earlier `proof_verify` visit as a verdict. This anchor governs every resume this section governs, including recovery routing's `resume` route of §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work", in every repository whose implement workflow carries the `review -> proof_verify` edge on `approve`. It adds no resume refusal and leaves the two-resume limit unchanged. Scenario 142 in `scenarios.md` exercises this paragraph.
```

### 2. `SPECIFICATION/scenarios.md` §"Scenario 142 — A run that terminated after publishing is resumed at its first unfinished stage from its pull request, and nothing it completed runs again": add two scenarios

Append these two scenarios at the END of that heading's `gherkin` block, after the scenario "A resumed publication refreshes proof after a changed head" (whose last step is "And the existing two-resume host bound remains in force"), separated by one blank line. No existing scenario changes:

```gherkin
  Scenario: A resume after a proof_verify that ended on a credential fault re-enters at proof_verify
    Given a run whose proof_capture visit published a captured record naming head H on the item's open pull request
    And a later review visit of that run selected approve
    And the following proof_verify visit failed on "Authentication required" with no turn taken and published no proof record
    And the run then ended at needs_human, the pull request's head is still H, and the factory still holds the run
    When the Dispatcher resumes the item
    Then the resumed run enters at proof_verify on H and replays the capture the record carries
    And review, review_fix, the commit settles and proof_capture do not run again
    And the resume record names proof_verify as the resumed-at stage and the factory record as its source

  Scenario: A resume after an ended proof_verify keeps the verdict fallback when the factory has lost the run
    Given the same ending, but the factory answers that it no longer holds the earlier run
    When the Dispatcher resumes the item
    Then the resumed run enters at review, as the captured record's verdict decides
    And the resume record names the pull request's latest record as the source that decided the stage
```

### 3. Heading coverage

This proposal MUST NOT add, rename or remove any `## ` heading: change 1 adds a paragraph inside an existing section, and change 2 adds scenarios inside an existing scenario heading. `tests/heading-coverage.json` and `tests/heading-coverage-debt.json` therefore MUST NOT change in the revise that ratifies it.

