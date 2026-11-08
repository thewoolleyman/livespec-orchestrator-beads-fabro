---
topic: fix-turn-commits-run-the-affected-tests-gate
author: claude-opus-5-5
created_at: 2026-11-07T22:26:16Z
---

## Proposal: A fix turn's commits run the affected-tests gate

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend the affected-tests gate, which today covers commits made by commit_red, commit_green and review_fix turns, to commits made inside a fix turn. Reword the fix turn's once-per-tree obligation so a passing affected-tests gate on the committed tree discharges it, because the janitor visit that follows a successful fix turn runs the full check aggregate anyway.

### Motivation

Work item bd-ib-fde4ie, plan sandbox-commit-gate-ceiling, filed on legacy-coordinator-agent's R301 ruling of 2026-11-07. In this repository at 2026-11-07's load, a full aggregate run inside a fix turn's commit hook cannot finish before the fix node's 3600 s limit. Measured cases: bd-ib-tcfwol run 01M6VRQMXSRD, where the check-per-file-coverage leg alone took 3654.8 s and the fix turn timed out with no change made, although the real repair was two lines; and bd-ib-akxkza, where check-per-file-coverage alone took 3765 s. Coverage refusals on the item's own new files cost bd-ib-azhnw5 run 01M6V78PQ953 a full suite run of 1960-3746 s per missing-line discovery, four discoveries in all, while its suite had no failing test. A per-file check on the touched files names each missing line in seconds. The same roughly 14,000-test suite took 1079-1286 s on 2026-11-06 and 1960-3860 s on 2026-11-07. Today contracts.md's affected-tests paragraph excludes fix turns explicitly, and the preceding paragraph obliges a fix turn to leave a head on which the full suite passed during that turn.

### Proposed Changes

In SPECIFICATION/contracts.md, replace the paragraph that begins "**A fix turn runs the check suite once per tree.**" with:

"**A fix turn grades each tree once, through its commit hook.** This paragraph governs only a `fix` turn that completes successfully and routes to `janitor`, whether it was a fix round or a refresh-repair round. A `fix` turn that ends through the needs-human protocol, by its node's resolved timeout, or by any other failure keeps its existing handling, which this paragraph does not change. A successful `fix` turn MUST leave the run's working branch at a head whose last commit in that turn passed the gate its commit hook ran under the next paragraph: the affected-tests gate's scoped tests and their coverage, or the full check aggregate when that gate cannot scope the change. The `fix` prompt MUST NOT direct a run of the full check suite beyond what its commit hook runs, because the `janitor` visit that follows a successful `fix` turn runs the full check aggregate on the run's tree. A hook run that did not grade the committed tree, such as a Red commit on the hook's fast path, does not satisfy the obligation. A change to the tree after the last passing hook run MUST be committed through the commit hook again before a successful turn ends. Measured 2026-11-07: the check-per-file-coverage leg of the full aggregate took 3654.8 s in a fix turn's commit hook on bd-ib-tcfwol run 01M6VRQMXSRD, and 3765 s on bd-ib-akxkza, both longer than the fix node's 3600 s limit. Scenario 199 in `scenarios.md` exercises this paragraph."

In the paragraph that begins "**An implement or review_fix turn's commits run the affected-tests gate.**":

(1) Replace the bold title with "**An implement, fix or review_fix turn's commits run the affected-tests gate.**".

(2) Replace "A commit made by the implement stage's `commit_red` or `commit_green` node, or inside a `review_fix` turn, MUST run" with "A commit made by the implement stage's `commit_red` or `commit_green` node, or inside a `fix` or `review_fix` turn, MUST run".

(3) Replace the sentence "This paragraph does not change the commit hook of a `fix` turn, which keeps the obligation of the preceding paragraph, nor the Red-Green commit protocol's own hook checks, nor the touched-test rules of \"An agent stage's instructions and its publication boundary\"; a commit made outside a factory turn keeps the repository's full commit hook." with "This paragraph does not change the Red-Green commit protocol's own hook checks, nor the touched-test rules of \"An agent stage's instructions and its publication boundary\"; a commit made outside a factory turn keeps the repository's full commit hook."

(4) Append: "Measured 2026-11-07: a full aggregate in a `fix` turn's commit hook outlasted the 3600 s `fix` node limit twice in this repository (3654.8 s and 3765 s for its check-per-file-coverage leg alone)."

In SPECIFICATION/scenarios.md, replace the Scenario 199 heading with "## Scenario 199 — A fix turn grades each tree once, through its commit hook". Replace its Feature body with:

```gherkin
Feature: A fix turn does not spend its time limit on a duplicate check suite
  As the maintainer of a repository dispatched to the factory
  I want a fix turn's commit hook to be the turn's only grading of each tree
  So that a full suite run does not exhaust the fix node's time limit before the janitor runs it again

  Scenario: A commit whose hook passed ends the turn's grading obligation for that tree
    Given a fix turn that commits its change
    And the commit hook's gate passed on the committed tree
    When the fix turn completes successfully on that tree
    Then the fix prompt directs no run of the full check suite on that tree in the same turn

  Scenario: A hook run that did not grade the tree, or a later change, still requires a passing commit
    Given a fix turn whose only commit took the hook's Red fast path, or whose tree changed after its last passing hook run
    When the fix turn is to complete successfully
    Then the turn first commits its tree through the commit hook to a passing result

  Scenario: A refresh-repair round applies the same rule to the integrated tree
    Given a fix turn entered with a refresh-repair brief
    And its commit on the integrated tree passed the commit hook's gate
    When the turn completes the repair successfully
    Then the fix prompt directs no run of the full check suite on that integrated tree in the same turn
```

Replace the Scenario 255 heading with "## Scenario 255 — A commit inside an implement, fix or review_fix turn runs the affected-tests gate, and the janitor runs the full aggregate once". In its Feature, replace "I want implement and review_fix commits to run only the tests their change affects" with "I want implement, fix and review_fix commits to run only the tests their change affects", and add these two scenarios after "A review_fix turn's commit runs the affected-tests gate":

```gherkin
  Scenario: A fix turn's commit runs the affected-tests gate
    Given a fix turn committing a change to product modules and their tests
    When its commit hook runs
    Then it runs just check-changed on the change and not the full check aggregate

  Scenario: A fix turn's commit that leaves a changed module's lines uncovered is refused with those lines
    Given a fix turn committing a change that leaves lines of a product module it changed uncovered
    When its commit hook runs
    Then the commit is refused with a per-file coverage failure naming that module and each missing line
    And the full check aggregate is not run
```

In the same Scenario 255, replace "Given a review_fix turn committing a change to a shared configuration file" with "Given a fix or review_fix turn committing a change to a shared configuration file".

In SPECIFICATION/contracts.md, in the `dispatcher.janitor.merge_gate_suite` paragraph, replace "The obligation of \"A fix turn runs the check suite once per tree\" covers `sandbox_check_suite` only and does NOT extend to the merge-gate command, because the janitor visit that follows a successful `fix` turn runs both." with "The obligation of \"A fix turn grades each tree once, through its commit hook\" does NOT extend to the merge-gate command, because the janitor visit that follows a successful `fix` turn runs both `sandbox_check_suite` and the merge-gate command."

Explicitly NOT changed by this proposal: the commit-msg `red_green_replay` suite-green leg, governed by livespec-dev-tooling's contracts.md. That leg MUST still run the FULL pytest suite for a `fix`-turn commit that stages product `.py` with no Red awaiting a Green, exactly as it does today for a `review_fix`-turn commit. So this proposal bounds a fix turn's REFUSAL path, where the affected-tests gate names the failing module and lines without a full run. It does not bound the passing path, which still pays that leg's full suite. That remaining cost is the one-suite-per-tree question, which covers the janitor refresh merge commit too (measured on bd-ib-hap62u run 01M6VBZF4371: a 1611.80 s full-suite hook on the merge, then the janitor's own full aggregate). It is carried by its own plan child of sandbox-commit-gate-ceiling and its own proposal against livespec-dev-tooling's suite-green clause, and is reconsidered there.

The revise that accepts this proposal MUST update the `tests/heading-coverage.json` entries of Scenarios 199 and 255 to their new headings. Every work item whose Definition of Done References line names either old heading verbatim, bd-ib-fde4ie at least, MUST be updated to the new heading in the same pass.

## Proposal: A workflow.fabro change selects the tests that read the graph

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Make the affected-tests gate scope a change to the implement-work-item workflow graph to the tests that read that graph, instead of reporting nothing to gate because no .py changed.

### Motivation

Work item bd-ib-fde4ie. Three of the five measured runs behind it changed workflow.fabro. bd-ib-ofvsr3 run 01M6S83KZH54 made an 8-line workflow.fabro change that broke integration tests (2, then 20, then 4 failed), each failure found by a full suite run. Today dev-tooling/just-check-changed.sh prints 'no changed .py vs origin/master (and none staged); nothing to gate' and exits 0 when no .py changed, so a graph-only commit passes the scoped gate with no test run. The contract says the gate falls back to the full aggregate for a change it cannot scope, but it does not say how a graph change is scoped.

### Proposed Changes

In SPECIFICATION/contracts.md, in the paragraph titled "An implement, fix or review_fix turn's commits run the affected-tests gate" (renamed by the companion proposal in this file), after the sentence that begins "When the change touches a file whose affected tests that gate cannot determine", insert:

"A change to the implement-work-item workflow graph, the bundled `workflow.fabro` or a repository's own fork of it, is a scoped change. Its affected tests are every test module that reads that graph file: one that names the file by its repository path or its file name `workflow.fabro`, or that imports a test-support module that names it. Selecting a test module that names a different `workflow.fabro` is permitted, because over-selection only runs more tests. The gate MUST run those test modules on the change, together with any tests its `.py` changes select. It MUST NOT report the change as having nothing to gate. When the gate cannot determine which test modules read the graph, the commit hook MUST run the full check aggregate instead."

In SPECIFICATION/scenarios.md Scenario 255, after the scenario "A change the affected-tests gate cannot scope falls back to the full aggregate", add:

```gherkin
  Scenario: A workflow graph change runs the tests that read the graph
    Given a fix turn committing a change to the implement-work-item workflow.fabro and no .py file
    When its commit hook runs
    Then the affected-tests gate runs every test module that reads that workflow graph
    And it does not report the change as having nothing to gate
```
