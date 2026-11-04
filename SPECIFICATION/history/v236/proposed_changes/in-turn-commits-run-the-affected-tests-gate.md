---
topic: in-turn-commits-run-the-affected-tests-gate
author: claude-opus-5-5
created_at: 2026-10-26T23:00:00Z
---

## Proposal: Commits inside implement and review_fix turns run the affected-tests gate, and the janitor runs the full aggregate once

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

In 'Definition-of-Done and Proof-of-Done stages': a commit inside an implement or review_fix turn runs just check-changed in its commit hook instead of the full aggregate, falling back to the full aggregate when the change cannot be scoped; the janitor still runs the full aggregate once; fix turns, the Red-Green hook checks and commits outside a factory turn are unchanged.

### Motivation

Routed by petri-factory-on-gmktec under coordinator ruling R69 (throughput, R67 ratification), spec-first for work-item bd-ib-72hvx5; its Codex-first Definition-of-Done screen found that the cited "### Definition-of-Done and Proof-of-Done stages" requires hooked commits but does not set the hook. Inside implement and review_fix turns every commit (Red, Green amend and each review_fix commit) pays the full aggregate in its pre-commit hook: measured on 2026-10-26 at about 24 minutes per pass at two workers and about 12.5 at four, repeated per commit, before the janitor runs the full aggregate again. Repeated Green amends on bd-ib-od7v54 run 01M5V5KVG8J7 spent its whole six-hour wall budget in roughly 20-minute hook passes. dev-tooling/just-check-changed.sh and the justfile's check-changed recipe already provide the scoped gate. This complements v227's rule that touched tests run green before a non-Red commit.
The first read-only Codex review raised blockers that are folded in here.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, §"Self-contained plugin dispatch" → "### Definition-of-Done and Proof-of-Done stages", after the paragraph "**A fix turn runs the check suite once per tree.**", insert immediately after the text

```
A change to the tree after the last passing full run means the suite MUST be run in full again before a successful turn ends. Scenario 199 in `scenarios.md` exercises this paragraph.
```

the following new paragraph (separated by one blank line):

```
**An implement or review_fix turn's commits run the affected-tests gate.** A commit made inside an `implement` or `review_fix` turn MUST run, in the repository's commit hook, the affected-tests gate (`just check-changed`) on the change being committed, in place of the full check aggregate. When the change touches a file whose affected tests that gate cannot determine, such as a shared configuration file, the commit hook MUST run the full check aggregate instead. At a Red commit the gate is Red-aware: the staged test MUST fail exactly as the Red-Green commit protocol requires, and no passing test or coverage is demanded of that commit; at the Green amend and every later commit in the turn, the scoped tests and their coverage MUST pass. This is a scoped exception to the aggregate selection of the inherited pre-commit step ordering, under which any staged `.py` file routes through the full aggregate: the pre-commit steps and their order are unchanged, and outside these two turns that selection is unchanged. The `janitor` stage MUST still run the full check aggregate once per visit on the run's tree before publication. This paragraph does not change the commit hook of a `fix` turn, which keeps the obligation of the preceding paragraph, nor the Red-Green commit protocol's own hook checks, nor the touched-test rules of "An agent stage's instructions and its publication boundary"; a commit made outside a factory turn keeps the repository's full commit hook. Measured 2026-10-26: every commit in these turns paid the full aggregate in its hook, about 24 minutes at two test workers and 12.5 at four, and repeated Green amends on bd-ib-od7v54 run 01M5V5KVG8J7 spent its whole six-hour wall budget in such passes. Scenario 255 in `scenarios.md` exercises this paragraph.
```

2. In `SPECIFICATION/scenarios.md`, append:

````
## Scenario 255 — A commit inside an implement or review_fix turn runs the affected-tests gate, and the janitor runs the full aggregate once

```gherkin
Feature: In-turn commits pay the scoped gate, and the full aggregate runs once per run
  As the operator of a factory
  I want implement and review_fix commits to run only the tests their change affects
  So that a run does not repeat the full check aggregate at every commit before the janitor runs it

  Scenario: An implement turn's commit runs the affected-tests gate
    Given an implement turn committing a change to product modules and their tests
    When its commit hook runs
    Then it runs just check-changed on the change and not the full check aggregate

  Scenario: A change the affected-tests gate cannot scope falls back to the full aggregate
    Given a review_fix turn committing a change to a shared configuration file
    When its commit hook runs
    Then it runs the full check aggregate

  Scenario: The janitor still runs the full aggregate once
    Given a run whose implement turn committed through the affected-tests gate
    When the run reaches the janitor stage
    Then the janitor runs the full check aggregate once on the run's tree before publication

  Scenario: A Red commit and its Green amend go through the affected-tests gate
    Given an implement turn staging one failing test alone for its Red commit
    When its commit hook runs
    Then the gate accepts the commit because the staged test fails, without demanding passing tests or coverage
    When the turn stages the implementation and amends to Green
    Then the commit hook runs the affected-tests gate and requires the scoped tests and their coverage to pass
```
````

3. Add a TODO row for the new heading to `tests/heading-coverage.json` and a matching debt row to `tests/heading-coverage-debt.json`, both owned by the implementing work-item bd-ib-72hvx5.
