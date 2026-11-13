---
topic: the-release-branch-roll-refuses
author: claude:gmktec-factory-placement
created_at: 2026-11-13T00:29:21Z
---

## Proposal: The release-branch roll refuses a tag whose canary coverage record does not cover every changed workflow path through its success edge

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

`fast-forward-release-branch.yml` MUST compute the workflow paths changed between the last rolled build and the named tag, and MUST refuse to move `release` unless the tag's release carries a `canary-coverage.json` asset that covers each changed path. Changed paths are nodes, edges, and the success edge of every changed node. Coverage is either an embedded canary run-journal row or a factory-captured routing test of exactly that node or edge. A citation for a changed node MUST show a sample completing it through its success edge, so a failure-edge traversal never covers it. A removed node or edge is covered only by a routing test. A corrective roll-forward is excepted from the canary's pass judgement, not from this record.

### Motivation

On 2026-11-12, 171ca17b2 (PR #4989, bd-ib-woiqjm) gave `fix_commit_settle` `output_schema="routing"` while its settled-success path still ended in a bare `exit 0`. Every run whose fix stage committed successfully then died RoutingBlocked, and six factory runs were lost (o4j3kg, lmuhvi, kjwanx, 7sqr36, wc6sxv, ehug6z) before a fleet-wide launch hold and the #5100 revert. The v0.321.0 canary passed without any sample completing a fix stage successfully; v0.312.3's canary missed the same way on 2026-11-10. A canary attests only the paths its samples traverse, and the path that matters is the one taken on success: `fix_commit_settle` has a failure edge (`-> fix`, `outcome=failed`) and an unconditional success edge (`-> fix_open_red_route`), and a sample that took only the failure edge would have said nothing about the defect. Nothing today ties the roll to the paths a release changed.

MAINTAINER DIRECTION, about 00:3xZ on 2026-11-13, recorded by legacy-coordinator-agent on livespec-dev-tooling-6tgd2z: "Ensure this doesn't happen again, and get things back on track ASAP." The coordinator named the rule CANARY-COVERS-CHANGED-PATHS and ruled that it be made mechanical at the roll.

The roll is the one place every fleet clone's build moves, because every consumer installs whatever `release` names, so gating it covers every factory repository. The record is a release asset, not a committed file, so the roll needs no extra pull request and stays fast. GitHub Actions cannot reach the Fabro servers, so the record embeds each cited journal row rather than pointing at a server. The corrective roll-forward is held to the record because the build that failed on 2026-11-12 would otherwise have been replaceable by a corrective build whose changed paths no sample exercised.

Implementation carrier: bd-ib-5psq3e, whose tier record names this topic. The livespec-dev-tooling sibling, livespec-dev-tooling-faetyh (topic the-fleet-install-recipes-refuse), binds the base below to `release` and closes the install-recipe route around this gate.

### Proposed Changes

Amend `contracts.md` §"Self-contained plugin dispatch" as follows.

1. In the **The release channel.** paragraph, replace "and it MUST be a build whose canary has passed, or a corrective roll-forward under the exception below." with:

"and it MUST be a build whose canary has passed, or a corrective roll-forward under the exception below, and, either way, whose canary coverage record satisfies **Canary coverage.**"

2. Insert this text directly after the sentence "The dispatch command is `gh workflow run fast-forward-release-branch.yml -f tag=vX.Y.Z`.", inside the same paragraph and before its closing sentence "Scenario 331 in `scenarios.md` exercises this paragraph.", so that pointer covers it:

"**Canary coverage.** A canary attests only the workflow paths its samples completed. The *workflow scope* is, for each workflow directory under `.claude-plugin/.fabro/workflows/`, the graph `workflow.fabro`, its run configuration `workflow.toml`, and every file in that directory a node loads, such as a prompt under `prompts/` or a file under `proof-capture-bin/` or `proof-capture-hooks/`. `workflow.pre-petri.fabro` is a rollback graph that no factory run executes, so it is outside the scope; restoring it as `workflow.fabro` changes `workflow.fabro`. The *base* is the last rolled build: the commit `release` names when the run starts, which is the live launch build of every fleet clone. Before the workflow moves `release`, at the roll step or in a corrective roll-forward, it MUST compute the *changed workflow paths* between the base and the named tag's commit within the workflow scope:

- every node that was added, was removed, or has a changed attribute or script;
- every node that interpolates a `workflow.toml` input whose value changed, or loads a workflow-directory file whose content changed;
- every edge that was added, was removed, or has a changed attribute, such as its condition or label;
- for every changed node that remains, its *success edge*: the edge it takes on a successful outcome or, when it has none, its unconditional edge.

The release that the tag names MUST carry a *canary coverage record*, a release asset named `canary-coverage.json`, that lists every changed workflow path and covers each one by a journal citation or a routing test.

- A *journal citation* embeds one row of the *run journal*, the event stream of the Fabro run a canary sample executed, naming the node or edge, the build commit the run launched on, the run id, and the event's sequence number in that stream. The build commit MUST be the tag's commit. A citation for a changed node MUST show the sample completing that node with a successful outcome and taking its success edge; a row showing only a failure edge does not cover the node.
- A *routing test* is a test of exactly that node and edge, named by its path and test id, present in the tag's tree and passing in a recorded `factory_captured` proof on the tag's commit.

A removed node and a removed edge cannot be traversed, so each MUST be covered by a routing test. The run MUST fail, naming the tag and each uncovered changed path, and `release` MUST keep its commit, in any of these cases: the record is absent; it omits a changed path; it gives a changed path neither a citation nor a routing test; a citation names a build commit other than the tag's commit; a citation for a changed node shows no successful completion through its success edge; or a cited routing test is absent from the tag's tree. When no path in the workflow scope changed, the record MUST still exist and MUST list no paths. A corrective roll-forward is excepted from the canary's pass judgement, not from this record: each path it changes is covered by a journal citation from a canary sample on its build or by a routing test."

Amend `scenarios.md` §"Scenario 331 — The release branch advances only on an operator dispatch that starts a canary", adding no `## ` heading and no scenario number:

3. In the existing scenario "the roll step advances the release branch after the canary passes", add after "And release v1.1.0's canary samples were judged to pass":

    And release v1.1.0's `canary-coverage.json` asset covers every changed workflow path between v1.0.0's commit and v1.1.0's commit

4. Append these scenarios to the feature block:

  Scenario: the roll step refuses a tag whose canary coverage record leaves a changed workflow path uncovered
    Given the `release` branch names the commit of release tag v1.0.0
    And release v1.1.0's commit descends from v1.0.0's commit
    And release v1.1.0 changes the script of workflow node `fix_commit_settle` and removes the edge `fix_commit_settle -> needs_human`
    And release v1.1.0's `canary-coverage.json` asset embeds a journal row of a v1.1.0 sample completing node `fix_commit_settle` with a successful outcome through its success edge, and gives the removed edge neither a citation nor a routing test
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.1.0`
    Then the run fails naming v1.1.0 and the edge `fix_commit_settle -> needs_human`
    And the `release` branch still names the commit of v1.0.0

  Scenario: the roll step refuses a changed node whose only citation is a failure-edge traversal
    Given the `release` branch names the commit of release tag v1.0.0
    And release v1.1.0's commit descends from v1.0.0's commit
    And release v1.1.0 changes the script of workflow node `fix_commit_settle`, whose failure edge leads to `fix` and whose success edge leads to `fix_open_red_route`
    And release v1.1.0's `canary-coverage.json` asset cites for `fix_commit_settle` only a journal row of a v1.1.0 sample that took the edge `fix_commit_settle -> fix` with a failed outcome
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.1.0`
    Then the run fails naming v1.1.0 and the node `fix_commit_settle` with its success edge `fix_commit_settle -> fix_open_red_route`
    And the `release` branch still names the commit of v1.0.0

  Scenario: the roll step refuses a tag whose release carries no canary coverage record
    Given the `release` branch names the commit of release tag v1.0.0
    And release v1.1.0's commit descends from v1.0.0's commit
    And release v1.1.0 carries no `canary-coverage.json` asset
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.1.0`
    Then the run fails naming v1.1.0 and the missing `canary-coverage.json` asset
    And the `release` branch still names the commit of v1.0.0

  Scenario: the roll step advances when every changed workflow path is covered
    Given the `release` branch names the commit of release tag v1.0.0
    And release v1.1.0's commit descends from v1.0.0's commit
    And release v1.1.0 changes the script of workflow node `fix_commit_settle` and removes the edge `fix_commit_settle -> needs_human`
    And release v1.1.0's `canary-coverage.json` asset embeds a journal row of a v1.1.0 sample completing node `fix_commit_settle` with a successful outcome through its success edge
    And it names, for the removed edge, a routing test present in v1.1.0's tree that passed in a recorded `factory_captured` proof on v1.1.0's commit
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.1.0`
    Then the `release` branch names the commit of v1.1.0 when the run ends

  Scenario: a corrective roll-forward is held to the canary coverage record
    Given the `release` branch names the commit of release tag v1.0.0, a rolled build that has failed
    And release v1.0.1's commit descends from v1.0.0's commit
    And release v1.0.1 is a corrective roll-forward that changes workflow node `fix_commit_settle`
    And release v1.0.1 carries no `canary-coverage.json` asset
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.0.1`
    Then the run fails naming v1.0.1 and the missing `canary-coverage.json` asset
    And the `release` branch still names the commit of v1.0.0

No `## ` heading is added or removed, so `tests/heading-coverage.json` needs no co-edit.
