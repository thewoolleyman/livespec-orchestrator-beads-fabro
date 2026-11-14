---
topic: the-filing-display-shows-the
author: claude-opus-5-5
created_at: 2026-11-14T00:21:08Z
---

## Proposal: The filing display shows the missing-capability finding the pre-admission judgement grades

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The filing display already shows the mechanical wall's findings and the governing-heading verdict. It does not show the one judged finding that decides whether a factory run can prove the item: check 5 of the Definition-of-Done rubric, a factory_captured assertion whose proof surface no name in the committed grading set provides. This proposal requires every filing front-end's display to show that finding, naming the assertion and the missing surface. The finding comes from the same Definition-of-Done judgement taking, rubric and grading set that intake's pre-admission judgement uses. The display reuses a recorded verdict under the existing reuse rule, so it takes at most one judgement per unchanged subject. Filing stays consent-gated and is never refused on the finding.

### Motivation

Work item bd-ib-5l4au4 (plan factory-run-yield, epic bd-ib-ft26pi, assertion 1: report lever 1, stop admitting assertions the sandbox cannot prove). The 2026-11-13 throughput report names an assertion the sandbox cannot prove (it needs a git push, a live ledger tenant, a missing toolchain or another repository) as the most frequent visible failure class among 406 failed factory runs of 788 in 7 days. Measured on master 86e1b558a: `filing_display` renders the mechanical wall plus the governing-heading taking, and never check 5. So a filer confirms a filing without seeing the mode is wrong, and learns it only when intake, approve or a run's dod_gate holds the item. The spec-change-tier judgement graded the item PARTIAL against ## Dispatcher admission, WIP cap, and post-merge acceptance, because the display clause in §"Effective acceptance criteria" names only the findings 'the host-side wall can detect', and check 5 is a judged finding. In-flight alignment: ALIGN with PR #5180 (the-filing-display-pays-for, bd-ib-3h7dsf, plan anthropic-burn-mitigation), which makes the display reuse a recorded governing-heading verdict. This proposal applies the same reuse discipline to the check-5 verdict, so it adds no model call for an item whose verdict is already recorded and unchanged. Effect on the track metric (PRs per repository per hour merged to main and green): indirect. Intake and approve already stop the run. This moves the finding to the moment the filer can still fix the mode, which saves one hold-and-regroom round trip per such item.

### Proposed Changes

**1. Display the check-5 verdict (`contracts.md` §"Effective acceptance criteria").** In the paragraph listing what each filing front-end MUST display before the filing is confirmed, immediately before the sentence "Filing stays consent-gated and a front-end MUST NOT refuse on a finding.", insert:

> Each such front-end MUST also display the Definition-of-Done judgement's missing-capability verdict: for each `factory_captured` assertion whose proof surface no name in the committed `dispatcher.sandbox_capabilities` grading set provides, one finding naming the assertion and the missing surface. The verdict MUST come from a taking of the same Definition-of-Done judgement, by the same rubric and grading set, that intake's pre-admission judgement uses (§"Dispatcher admission, WIP cap, and post-merge acceptance"), so that for one subject digest and rubric digest the display and intake report the same verdict. Before taking it, the display MUST use a recorded verdict that the shared component's reuse rule allows, whoever recorded it, and a verdict the display takes MUST be recorded on the item for the pre-admission judgement to reuse. When the capability set is unknown, the display MUST report `sandbox-capabilities: unpublished` and MUST NOT show this finding. When the judgement cannot run, the display MUST show a line saying the missing-capability check did not run and why. The finding is advisory at the display: confirming the filing files the item, and intake then routes it as Scenario 174 prescribes.

The following sentence ("Filing stays consent-gated and a front-end MUST NOT refuse on a finding.") is kept unchanged and covers this finding.

**2. New scenario (`scenarios.md`, appended at the next free Scenario number when revised):**

```gherkin
## Scenario NNN — The filing display shows the missing-capability finding the pre-admission judgement grades

Feature: A filer sees an unprovable assertion before confirming
  As a filer capturing an implement-kind item
  I want to see that a factory_captured assertion needs a surface the sandbox lacks
  So that I can fix its mode before intake holds the item

Scenario: An assertion needing a surface outside the grading set is shown before confirmation
  Given a filer captures an item whose factory_captured assertion needs a surface no name in the committed grading set provides
  When the filing front-end displays the filing before confirmation
  Then the display shows a finding naming the assertion and the missing surface
  And confirming the filing files the item, which intake routes as Scenario 174 prescribes

Scenario: The display and intake grade one subject alike and judge it once
  Given an item whose missing-capability verdict for its current subject and rubric digests is already recorded
  When the filing display runs
  Then it shows the recorded verdict and takes no new judgement

Scenario: A judgement that cannot run is reported, not hidden
  Given the missing-capability judgement cannot run for a filing
  When the filing front-end displays the filing
  Then the display shows that the missing-capability check did not run and why
  And the filing is not refused
```

**3. Heading coverage.** The revise pass that adds the scenario MUST add its `## Scenario NNN` heading to `tests/heading-coverage.json` in the same change.
