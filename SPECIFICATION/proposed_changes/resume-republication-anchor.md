---
topic: resume-republication-anchor
author: claude-opus-5-5-plan-publish-draft-green-work-loss
created_at: 2026-10-15T00:00:43Z
---

## Proposal: A run's own republication after its latest proof record anchors a resume at proof_capture

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When the earlier run itself published the pull request's current head after the latest proof record, and terminated at or before that head's proof_capture, the resume anchors on the pull request head at proof_capture instead of refusing on the moved-head rule. Fresh capture, review and replay then run on that head, so no proof is carried across trees.

### Motivation

Measured 2026-10-14 on bd-ib-xi63mq, hp run 01M4XKJE3GZKJ739SRE9VTRDX2. The run passed implement, janitor, publish_draft and proof_capture@1, which recorded head e86738cc on draft PR 2981, then review, disposition and review_fix. Its own publish_draft@2 pushed 450ece78, a one-commit descendant of e86738cc, and proof_capture@2 died on an Anthropic session limit. resume --item refused on the moved-head bullet, because the PR head 450ece78 did not equal the head the latest record names. The ratified remedy, a plain dispatch, reclaimed the branch and re-ran implement from scratch at about two more hours of provider quota, though every stage up to the second proof_capture had passed. The moved-head refusal exists because proof verified on one tree is not proof of another; that reason does not reach this case. The head did not move under the run: the run moved it itself and stopped before proving it, and a resume entered at proof_capture proves the new head afresh. The contract already accepts exactly this shape for a watchdog-stall-cancel or run-wall-budget-exceeded record, which anchors at proof_capture on the run's own published head when the run was between its last publish_draft and proof_capture. A run ending for any other reason at that same point, such as a provider usage limit or an ACP fault, has no anchor. This finding is aligned with the pending proposal pr-refresh-reproof-relevance, which also edits the resume sub-section to let a carried_forward record anchor a resume. The two anchors compose: a carried_forward record is a proof record, so it is the latest record this rule measures from.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Dispatcher loop invocation surface", sub-section "Resume from a published pull request (`resume --item`)":

(1) In the paragraph beginning "**What it resumes.**", insert after the sentence ending "... and the resume record MUST name it as the source." the following:

"When the pull request's current head differs from the head the latest proof record names, the earlier run's own republication anchors the resume instead, and only from the factory's own record of that run. That anchor applies when the factory that the earlier dispatch names still holds the earlier run and its record shows ALL of the following: (a) the run completed a `publish_draft` or `pr_refresh` visit after the visit that published the latest proof record; (b) the head of the run's terminal checkpoint equals the pull request's current head; (c) the head the latest proof record names is an ancestor of that head; and (d) the run terminated while executing `proof_capture`, or between that completed `publish_draft` or `pr_refresh` visit and `proof_capture`. Under this anchor the earlier run is that run, the published head is the pull request's current head, the resumed-at stage is `proof_capture`, and the resume record MUST name the factory record as the source that decided both. When the factory answers that it no longer holds the run, or cannot be read, this anchor does not apply and the moved-head refusal below stands. Because the resumed run enters at `proof_capture`, fresh capture, review and replay run on the published head, and the earlier record is never read as proof of it."

(2) In the refusal bullet beginning "the pull request's current head does not equal the published head", insert after "naming both shas" the words "and no republication anchor applies as above". Leave the remainder of the bullet unchanged.

In SPECIFICATION/scenarios.md:

(3) In Scenario 142, insert after the sub-scenario "A stall-cancelled run with no proof record resumes from its cancel record" the following sub-scenario:

```gherkin
  Scenario: A run that republished after its latest proof record resumes at proof_capture on the head it published
    Given a ready item whose earlier run published a captured record naming one head, then completed review_fix and a second publish_draft that pushed a descendant of that head, and terminated while executing proof_capture
    And the factory the earlier dispatch names still holds that run and its terminal checkpoint head equals the pull request's current head
    When the operator drives resume for the item
    Then the new run enters the workflow at proof_capture on the pull request's current head and no dod_gate, implement or janitor stage precedes it
    And the resume record names the pull request's current head as the published head and the factory record as the source that decided the stage
    And the dispatch journal carries neither a publish-branch-reclaim record nor a publish-branch-reclaim-held record for the resume
```

(4) In Scenario 143, sub-scenario "The pull request head no longer equals the head the record names", replace the Given line with "Given a ready item whose pull request head differs from the head its latest proof record names, and whose earlier run's factory record does not show that run publishing the pull request head after that record". Leave the remaining lines of the sub-scenario unchanged. Then insert after that sub-scenario:

```gherkin
  Scenario: A republication the factory can no longer show does not anchor a resume
    Given a ready item whose pull request head differs from the head its latest proof record names
    And the factory the earlier dispatch names answers that it no longer holds the earlier run
    When the operator drives resume for the item
    Then the resume refuses with exit code 3 before any run exists, naming both heads and a plain dispatch as the remedy
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` is unchanged.
