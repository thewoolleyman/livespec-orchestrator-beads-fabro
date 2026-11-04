---
topic: agent-stage-test-discipline
author: claude-opus-5-5
created_at: 2026-10-26T16:56:29Z
---

## Proposal: Implement and review_fix prompts state three test-discipline rules

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

The implement and review_fix stage prompts state, and their turns follow, three further rules: run every touched test green before any non-Red commit and before the Green amend; a Red commit stages exactly one test file and no product file; and an edit to a stage prompt or to the Dispatcher's launch-overlay code updates the tests pinning it in the same commit.

### Motivation

Coordinator gitops-fleet-capacity-monitoring ruling R38 (from R36) routes this spec-first change so work-item bd-ib-v5f7fd, filed by petri-factory-on-gmktec, has a governing clause; its screen notes that the "An agent stage's instructions and its publication boundary" paragraph says the stage prompts MUST state three rules, and these rules extend that set. Measured 2026-10-26: three review_fix endings refused at the commit hook on check-per-file-coverage plus check-coverage: bd-ib-svm3fe run 01M5VYNE2N8S, bd-ib-atyefi run 01M5VK9D2241 and bd-ib-ytrpb5 run 01M5VT8SBEHX. kubernetes-sandbox-backend's diagnosis found real failing tests, not a gate artifact: on atyefi, review_fix edited fix.md, implement.md, review-fix.md and _dispatcher_overlay.py without updating the tests pinning them (5 failing tests); on ytrpb5 a new test failed at setup because the credential-use guard refused before the path under test; on svm3fe the Red commit staged two test files, so the hook ran the full gate on a deliberately failing Red. Each turn spent one or two 24-45 minute hook passes learning what a targeted pytest run would have shown in seconds.

The new rules are added as a fourth, fifth and sixth rule for the implement and review_fix prompts only, so the existing three rules (which apply to implement, fix and review_fix) and Scenario 202's bound prompt-tier test are unchanged. The green-before-commit rule exempts the Red commit itself, whose one test is required to fail by the repository's Red-Green-Replay protocol.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, §"Self-contained plugin dispatch", paragraph "An agent stage's instructions and its publication boundary", replace the paragraph's closing text

```
a turn MUST NOT end, wait or fail because such a mechanism is absent. Scenario 202 in `scenarios.md` exercises this paragraph.
```

with

```
a turn MUST NOT end, wait or fail because such a mechanism is absent. The prompts of the `implement` and `review_fix` stages MUST state three further rules, and a turn in those stages MUST follow them. Fourth, before any commit other than a Red commit, and before the Green amend that completes a Red commit, the turn MUST run every test file the change adds or modifies and see each pass; a Red commit's one test file is expected to fail and is exempt from this rule until its Green amend. Fifth, a Red commit MUST stage exactly one test file and no product file, and any further test files the change needs are staged at the Green amend. Sixth, a change to a stage prompt file under `.claude-plugin/.fabro/`, or to the code that renders the Dispatcher's launch overlay, MUST update, in the same commit, the tests that pin that prompt or that overlay, so the commit does not leave a pinning test failing. These three rules exist because a commit hook run is slow and reports a failing test only as a gate refusal: measured 2026-10-26, three `review_fix` turns (runs 01M5VYNE2N8S, 01M5VK9D2241 and 01M5VT8SBEHX) were refused by the commit hook's coverage gates because tests they committed genuinely failed. One had edited stage prompts and the overlay without updating the tests pinning them, one added a test that failed at setup, and one staged two test files on its Red commit. Each spent one or two hook runs of 24 to 45 minutes learning what a targeted test run would have shown in seconds. Scenario 202 in `scenarios.md` exercises the first three rules of this paragraph, and Scenario 249 exercises the fourth, fifth and sixth.
```

2. In `SPECIFICATION/scenarios.md`, append:

````
## Scenario 249 — Implement and review_fix turns run their touched tests green, stage one test per Red, and update pinning tests with prompt edits

```gherkin
Feature: An implement or review_fix turn does not hand the commit hook a test it never ran
  As the maintainer of a repository dispatched to the factory
  I want implement and review_fix turns to run their own touched tests before committing
  So that a slow hook run is not spent discovering a failing test a targeted run would have shown

  Scenario: The stage prompts state the three test-discipline rules
    Given the implement and review_fix prompts of the released implement-work-item workflow
    When each prompt is read
    Then each states that every test file the change adds or modifies is run and passes before any commit other than a Red commit and before the Green amend
    And each states that a Red commit stages exactly one test file and no product file
    And each states that a change to a stage prompt file or to the code rendering the Dispatcher's launch overlay updates, in the same commit, the tests that pin it

  Scenario: A Red commit's failing test is not run green first
    Given a review_fix turn that has written one new failing test and no product change
    When the turn makes its Red commit
    Then the commit stages that one test file alone
    And the turn is not required to see that test pass before the Red commit

  Scenario: A prompt edit carries its pinning test
    Given an implement turn whose change edits the review_fix stage prompt
    And a test pins that prompt's text
    When the turn makes the commit carrying the prompt edit
    Then the same commit updates the pinning test
    And the turn ran that test and saw it pass before committing
```
````

3. Add a TODO row for the new Scenario 249 heading to `tests/heading-coverage.json` and a matching debt row to `tests/heading-coverage-debt.json`, both owned by the implementing work-item bd-ib-v5f7fd.
