---
topic: the-roll-refuses-a-tag-without-canary-coverage-of-changed-workfl
author: claude:gmktec-factory-placement
created_at: 2026-11-13T00:29:21Z
---

## Proposal: The roll refuses a tag whose canary coverage record does not cover every changed workflow path

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

`fast-forward-release-branch.yml` MUST compute the workflow nodes and edges changed between the commit `release` names and the named tag, and MUST refuse to move `release` unless the tag's release carries a `canary-coverage.json` asset covering each changed path with a canary run-journal traversal citation or a named routing test. The same applies to a corrective roll-forward.

### Motivation

On 2026-11-12, 171ca17b2 (PR #4989, bd-ib-woiqjm) gave `fix_commit_settle` `output_schema="routing"` while its settled-success path still ended in a bare `exit 0`. Every run whose fix stage committed successfully then died RoutingBlocked, and six factory runs were lost (o4j3kg, lmuhvi, kjwanx, 7sqr36, wc6sxv, ehug6z) before a fleet-wide launch hold and the #5100 revert. The v0.321.0 canary passed without any sample traversing a successful fix stage; v0.312.3's canary missed the same way on 2026-11-10. A canary attests only the paths its samples traverse, and nothing today ties the roll to the paths the release changed. MAINTAINER DIRECTION, about 00:3xZ on 2026-11-13, recorded by legacy-coordinator-agent on livespec-dev-tooling-6tgd2z: "Ensure this doesn't happen again, and get things back on track ASAP." The coordinator named the rule CANARY-COVERS-CHANGED-PATHS and ruled that it be made mechanical at the roll. The roll is the one place every fleet clone's build moves, because every consumer installs whatever `release` names, so gating it covers every factory repository. The record is a release asset, not a committed file, so the roll needs no extra pull request and stays fast. The corrective roll-forward is included because the build that failed on 2026-11-12 would otherwise have been replaceable by an uncanaried corrective build. Implementation carrier: bd-ib-5psq3e. The livespec-dev-tooling sibling, livespec-dev-tooling-faetyh, closes the install-recipe route around this gate.

### Proposed Changes

Insert this paragraph into `contracts.md` §"Self-contained plugin dispatch", directly after the sentence "The dispatch command is `gh workflow run fast-forward-release-branch.yml -f tag=vX.Y.Z`." and before "Scenario 331 in `scenarios.md` exercises this paragraph.":

**Canary coverage.** A canary attests only the workflow paths its samples traversed. Before `fast-forward-release-branch.yml` moves `release`, at the roll step or in a corrective roll-forward, it MUST compute the *changed workflow paths* between the commit `release` names and the named tag's commit. These are every node of a workflow under `.claude-plugin/.fabro/workflows/` that was added, was removed, or has a changed attribute, script or prompt file, and every edge that was added or removed. The release that the tag names MUST carry a *canary coverage record*: a release asset named `canary-coverage.json` that lists every changed workflow path and gives each one either a run-journal citation or a routing test. A run-journal citation names the Fabro run id of a canary sample launched on that tag's build, the node or edge, and the journal event sequence at which the sample traversed it. A routing test is the name of a test, present in the tag's tree, that exercises exactly that node or edge. A removed edge cannot be traversed, so it MUST be covered by a routing test. The run MUST fail naming the tag and each uncovered changed path, and `release` MUST keep its commit, when the record is absent, when it omits a changed path, or when it gives a changed path neither a citation nor a routing test. When no workflow path changed, the record MUST still exist and MUST list no paths. A corrective roll-forward is held to the same record, because the build it carries is canaried no less than any other.

Then amend Scenario 331 (`scenarios.md` §"Scenario 331 — The release branch advances only on an operator dispatch that starts a canary"):

1. In the existing scenario "the roll step advances the release branch after the canary passes", add after "And release v1.1.0's canary samples were judged to pass":

    And release v1.1.0's `canary-coverage.json` asset covers every changed workflow path between v1.0.0's commit and v1.1.0's commit

2. Append these scenarios to the feature block:

  Scenario: the roll step refuses a tag whose canary coverage record leaves a changed workflow path uncovered
    Given the `release` branch names the commit of release tag v1.0.0
    And release v1.1.0's commit descends from v1.0.0's commit
    And release v1.1.0 changes the script of workflow node `fix_commit_settle` and removes the edge `fix_commit_settle -> needs_human`
    And release v1.1.0's `canary-coverage.json` asset cites a run-journal traversal for node `fix_commit_settle` and gives the edge neither a citation nor a routing test
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.1.0`
    Then the run fails naming v1.1.0 and the edge `fix_commit_settle -> needs_human`
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
    And release v1.1.0's `canary-coverage.json` asset cites a run-journal traversal for node `fix_commit_settle` and names a routing test present in v1.1.0's tree for the edge
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.1.0`
    Then the `release` branch names the commit of v1.1.0 when the run ends

  Scenario: a corrective roll-forward is held to the canary coverage record
    Given the `release` branch names the commit of release tag v1.0.0, a rolled build that has failed
    And release v1.0.1 is a corrective roll-forward that changes workflow node `fix_commit_settle`
    And release v1.0.1 carries no `canary-coverage.json` asset
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.0.1`
    Then the run fails naming v1.0.1 and the missing `canary-coverage.json` asset
    And the `release` branch still names the commit of v1.0.0

No `## ` heading is added or removed, so `tests/heading-coverage.json` needs no co-edit.
