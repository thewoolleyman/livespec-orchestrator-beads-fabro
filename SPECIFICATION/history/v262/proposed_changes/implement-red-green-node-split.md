---
topic: implement-red-green-node-split
author: claude-opus-5-5
created_at: 2026-11-01T03:11:41Z
---

## Proposal: The implement stage runs Red and Green as separate nodes and makes its commits in model-free nodes

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Replace the single `implement` ACP node with four nodes: a `red` ACP node that writes the failing test and makes no commit, a `commit_red` command node that makes the Red commit, a `green` ACP node that implements and makes no commit, and a `commit_green` command node that folds any engine checkpoint commits above the Red commit back into the index and makes the Green amend, whose hook runs the whole suite once. The nodes pass context through one append-only handoff file inside the git directory. `green` may route back to `red` when it finds the Red test wrong. The detached commit runner, the commit-settle wait and the incomplete-turn re-entry no longer apply to the implement stage; they keep governing `fix` and `review_fix`. Adds one scenario and rewrites Scenario 204 for the `green` node.

### Motivation

Plan implement-test-performance (livespec-dev-tooling tenant, epic livespec-dev-tooling-sv6m5p), DoD assertions 7 and 8, under the maintainer's 2026-11-01 rulings that the plan owns the implement commit and test-performance problem holistically and runs autonomously. Design: livespec-dev-tooling plan/implement-test-performance/research/004-red-green-node-split-design.md; measurements in notes 001-002 there. Measured: 78-92% of every implement turn is the agent polling a commit hook or suite run (Green amend 5-17 min in the sandbox); in 5 of 6 analysed turns the turn ended 20-30 s after its own commit run had failed; since f8340c7ae (2026-10-12, `[run.checkpoint] skip_git_hooks = true`) the engine's checkpoint commit after every node commits whatever a turn left staged with no hooks, which splits the Red test from its implementation (Red-without-Green on green runs rose from 2/63 to 9/96) and hides a refused commit from the re-entry route. The run dumps of 01M69Z9YFYV9 show a distinct checkpoint commit after every node, script nodes included, landing on the working branch. The commit runner, settle and re-entry clauses reconstruct after the fact what a commit started inside a turn did; moving both commits into command nodes removes the in-turn commit they patch, spends no model tokens while a hook runs, and makes the turn boundary coincide with the ritual boundary. Separate contexts for Red and Green with a file handoff and a test the implementer cannot change are the configuration the research in plan token-spend-analysis note 008 found measured gains for (AgentCoder ablation, TDFlow). Relationship to pending topic node-timeout-cut-retry-carries-the-cut-state: align — its generalized node-timeout cause applies unchanged to the `red` and `green` ACP nodes.

### Proposed Changes

In SPECIFICATION/contracts.md, under "## Self-contained plugin dispatch":

1. Insert, immediately before the paragraph **An implement turn that ends incomplete does not succeed.**, a new paragraph:

> **The implement stage runs Red and Green as separate nodes.** The implement-work-item workflow MUST realize the implement stage as four nodes in this order: a `red` ACP node, a `commit_red` command node, a `green` ACP node and a `commit_green` command node. The `red` prompt MUST direct the agent to write the failing test the work item's Definition of Done needs, to run only that test, and to make no commit. The `green` prompt MUST direct the agent to make that test pass by changing implementation files, to run only the tests its change touches, to make no commit, and never to change the Red test file. `commit_red` MUST stage the Red test and run `git commit` with the repository's commit hooks running exactly as for a foreground commit. Before it commits, `commit_green` MUST fold every commit above the Red commit that the engine made at a node boundary back into the index, so that its amend lands on the Red commit; it MUST then stage the implementation and run `git commit --amend` with the repository's commit hooks running exactly as for a foreground commit. Neither command node may pass `--no-verify`, set any variable that skips or relaxes a check, or change the severity of any hook. When `commit_red` refuses, the run MUST re-enter `red`; when `commit_green` refuses, the run MUST re-enter `green`; each re-entry is bounded by its ACP node's `max_visits`. A `green` turn that finds the Red test wrong MUST be able to end with a declared test-wrong outcome that routes the run back to `red`, bounded by the `red` node's `max_visits`. No agent turn of the implement stage makes a commit, so no agent turn of the implement stage waits on a commit hook.

> **The implement nodes hand off through one append-only file.** The `red`, `commit_red`, `green` and `commit_green` nodes MUST pass context through a single handoff file at the git path `livespec-implement-handoff.md`, which no checkpoint commit can carry into the branch. Each node MUST append a section and MUST NOT rewrite an earlier one. The `red` section MUST name the Red test file, the Definition of Done assertion it proves, the command that ran it and that run's failure output, what the test verifies and does not verify, and the code locations the Red turn identified for the change. A command node's section MUST carry its exit status and, when it refused, the hook's failed target names and the last 80 lines of the hook's own output, taken from the recorded output and never from an agent's reply. A `green` section MUST state what changed and which tests ran, or the test-wrong declaration and its reason. Each ACP node of the implement stage MUST start a fresh agent session whose carried context is the work item, its Definition of Done and the handoff file, never the transcript of another node.

2. In the paragraph **An implement turn that ends incomplete does not succeed.**, apply its completion-field rule to the `green` node's turn and the failure edge to `green`'s failure edge; delete the sentences defining a refused commit attempt for the implement stage, the re-entry brief's failing-gate order and the commit-run wait, and in their place state: "A `green` turn whose completion field reports the work incomplete re-enters `green` while its `max_visits` remains, with the handoff file carrying the previous turn's section; the `fix` and `review_fix` stages keep the commit-run wait and refused-attempt rules of 'A commit leg completes past one tool call' unchanged."

3. In the paragraph **A commit leg completes past one tool call.**, replace "for every stage whose ACP agent commits (`implement`, `fix` and `review_fix`)" with "for every stage whose ACP agent commits (`fix` and `review_fix`)", and in **A commit run outlives a node-timeout cut.** and **The recorded hook verdict outranks the agent's account of it.** replace "`implement`, `fix` or `review_fix`" with "`fix` or `review_fix`", adding to the latter: "For the implement stage, the needs-human cause after an exhausted `commit_red` or `commit_green` re-entry MUST name that command node's recorded exit status and failed target names."

In SPECIFICATION/scenarios.md:

4. Rewrite Scenario 204 so that its Given/When/Then steps name the `green` node and the handoff file in place of the `implement` stage's refused-commit and check-suite briefs; keep its partial-progress and exhausted-budget outcomes.

5. Add a new scenario, numbered at revise as the next free number, titled "Red and Green run as separate nodes and every implement commit is made by a command node":

```gherkin
Feature: The implement stage separates Red from Green and commits outside agent turns
  Scenario: A Red test and its implementation commit as one Red-Green pair
    Given a dispatched work item whose Definition of Done needs a new behaviour
    When the red node writes a failing test and ends its turn
    Then commit_red makes the Red commit with the repository's commit hooks running
    And the green node starts a fresh session whose context is the work item and the handoff file
    When the green node implements the behaviour and ends its turn
    Then commit_green folds any engine checkpoint commits above the Red commit into the index
    And commit_green amends the Red commit with the repository's commit hooks running
    And the branch carries one commit with the Red test, the implementation and both trailer sets

  Scenario: A refused Green amend re-enters green with the hook's recorded failure
    Given commit_red has made the Red commit
    When commit_green's hook refuses naming a failed target
    Then the run re-enters green
    And the handoff file's newest section carries that failed target and the hook's own output lines

  Scenario: Green finds the Red test wrong
    Given commit_red has made the Red commit
    When the green turn ends with a test-wrong declaration and its reason
    Then the run re-enters red with that reason in the handoff file
    And the Red test file is unchanged by the green turn
```

6. Add the matching entries to `tests/heading-coverage.json` in the revise commit.
