---
topic: the-release-branch-advances-only-after-its-canary-passes
author: claude:gmktec-factory-placement
created_at: 2026-11-09T14:35:20Z
---

## Proposal: The release branch advances only after its canary passes; canary clones adopt the release tag by a named-build adopt

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Reverse the ordering that v327 ratified in contracts.md §"Self-contained plugin dispatch", paragraph "The release channel". A release's canary clones adopt the release by a named-build adopt: an operator step that installs the build of the named release tag at project scope in one named clone, and moves neither `release` nor any other clone. `release` advances, through the existing fast-forward-only dispatch of `fast-forward-release-branch.yml`, only at the roll step, after the canary samples pass. A canary that fails therefore leaves `release` on the last rolled build, and no launch hold is needed to contain the advance. Scenario 331 is amended to match, and its heading text changes.

### Motivation

v327 (livespec-orchestrator-beads-fabro#4708, ratified 2026-11-09T03:54Z) made the fast-forward dispatch START the canary. Because every clone's session-start refresh installs whatever `release` names, it contained the advance with one rule: an operator MUST hold factory launches from every clone outside the canary until the samples are judged. The 0.308.0 canary on 2026-11-09 measured that containment failing four times, and measured the cost of a failed canary under it.

Timeline:
- `release` was fast-forwarded to v0.308.0 (a52c6ee034d1) by run 42592309372 at about 09:16Z, with canary-hold-repo-* holds set for 8 repositories at about 09:17Z.
- LEAK 1, 09:22:35Z: a seat's own SessionStart hook (`mise exec -- just ensure-plugins`) moved livespec-dev-tooling's install 35cdda22389c -> a52c6ee034d1 while its hold was in place. A hold stops launches; it does not stop a session start from installing the tip.
- LEAKS 2-4, 13:34:43Z-13:35:56Z: the coordinator lifted the holds on livespec, livespec-overseer and livespec-runtime, which were all still on 35cdda22389c (good 0.307.0). The petri launcher's launch-time Definition-of-Done preflight starts a headless Claude session in the member clone, and that session's SessionStart refresh pulled the broken tip into all three within 2 minutes. The launcher reads build= after the preflight, so a launch would have run the broken build. A rehold tripwire caught all three within about 30 s; overseer-lx5l7i reached the gmktec mutex 7 s after its re-hold.
- A launch ahead of the designated sample: bd-ib-7owmkq launched at 09:19:34Z on a52c6ee034d1, seconds after the exempt orchestrator clone moved.
- The canary FAILED at about 12:3xZ. Commit 6f90584d4 added fail-closed conformance-hook reinstall sites that exit 127 in the sandbox, so every run reaching publish_draft or pr_refresh ended needs_human.
- With `release` already on the broken tip, every session start anywhere could only land on it, and no committed route back existed. livespec-dev-tooling-tv7obt (a pin-to-ancestor rollback recipe) was filed for that gap, and `fast-forward-release-branch.yml` refuses an ancestor tag by design.
- By 13:36Z all six orchestrator-enabling projects on the host sat on a52c6ee034d1. The only route out was a corrective roll-forward: revert livespec-orchestrator-beads-fabro#4744, v0.309.2 tagged at 14:20:14Z, `release` fast-forwarded at 14:21Z, and the six projects adopted at 14:21Z-14:23Z.
- During the five hours before that, launches from the held repositories stood paused (2 of 11 fleet slots live at one read).

The defect is the ordering, not the hold. While `release` names a build that has not passed its canary, every Claude session start in every clone is a route onto that build, including session starts that no operator thinks of as an install: a seat start, a resume, a compact, and a launcher's preflight. Holds can only chase those routes one at a time. If `release` instead advances only after the canary passes, a failed canary never reaches a session-start refresh, the non-canary clones need no hold for the release, and rolling back a failed canary touches only the canary clones.

The named-build adopt is the step that makes this possible. A canary clone must run the release's build while `release` still names the previous one, so the canary clone cannot get there by a session-start refresh. It must be moved by an explicit operator step that names the tag.
- livespec-dev-tooling-7upzav carries the fleet-side realization: `just adopt-orchestrator-build <clone> <build>`, and session-start refresh never moving an existing orchestrator install record.
- livespec-dev-tooling-tv7obt carries the way back for a canary clone.
This repository's specification owns the release-channel contract that these recipes serve, which is why the change lands here (placement split (iii)).

REALIZATION, stated so the revise can weigh it. Today no recipe can take the named-build adopt this contract requires. livespec-dev-tooling-7upzav, as filed, lets `just adopt-orchestrator-build` name ONLY the commit the host's marketplace clone holds at `origin/release`, and it exits non-zero for any other commit. livespec-dev-tooling-tv7obt lets `just rollback-orchestrator-build` name only an ANCESTOR of that commit. Under this contract a canary clone must install a published tag that is AHEAD of `release`, so ratifying it obliges one realization change in livespec-dev-tooling. The adopt step must accept a published release tag of this repository whose commit descends from the commit `release` names, and install it from that tag rather than from the marketplace clone's `release` checkout, at project scope in the one named clone. The proposing seat owns livespec-dev-tooling-7upzav (coordinator ruling, 2026-11-09) and amends that item's Definition of Done when this proposal is ratified. 

Alternative weighed and not proposed: keep v327's order and rely on 7upzav alone. After 7upzav, a session-start refresh never moves an existing orchestrator install record, so `release` could lead the canary without leaking into held clones. That closes the four leaks measured on 2026-11-09, but it leaves `release` naming an unjudged build for the whole canary. During that time, any clone with no install record yet, any host-wide Codex or pi install tracking `release`, and any adopter takes the unjudged build, and a failed canary still needs a corrective roll-forward before `release` is safe again. This proposal removes those cases by construction, at the cost of the realization change above. The two are compatible, and 7upzav's held-record rule stays useful under either order.

In-flight alignment:
- The pending proposal `the-committed-fleet-launcher-lacks-2` (canary repository hold in the committed launcher, bd-ib-4xqmqh) is ALIGNED. Canary repository holds stay useful for sequencing which items launch first. This change only removes the hold's role as the containment of a `release` advance.
- The open livespec-orchestrator-beads-fabro#4747 (janitor time-out) is unrelated.

Requested by legacy-coordinator-agent, which accepted the route at about 13:5xZ on 2026-11-09 and will carry the PR to the maintainer. The source is plan gmktec-factory-placement (epic livespec-dev-tooling-me5aqz in the livespec-dev-tooling tenant).

### Proposed Changes

In `contracts.md` §"Self-contained plugin dispatch", replace the whole paragraph that begins "**The release channel.**" and ends "Scenario 331 in `scenarios.md` exercises this paragraph." with:

> **The release channel.** Fleet members and adopters resolve this plugin through the moving `release` branch: every consumer's marketplace registration names `ref: release`, and a session-start plugin refresh installs whatever commit `release` names. So the commit `release` names IS the build every fleet clone adopts by default, and it MUST be a build whose canary has passed. A *canary* of a release is the set of factory runs launched on that release's build from the clones an operator moved to it first: this repository's clone for orchestrator work, and a named other repository's clone for a non-orchestrator leg. Its *canary samples* are those runs' observed outcomes. A canary clone MUST be moved to the release by a *named-build adopt*: an operator step that names one clone and one published release tag of this repository, installs that tag's build at project scope in that clone, and leaves the commit `release` names, the host's marketplace registration, and every other clone's install record unchanged. The *roll step* is the operator step that, after the canary samples are judged to pass, adopts that release's build in every fleet clone. `release` MUST advance only at the roll step, when an operator dispatches `.github/workflows/fast-forward-release-branch.yml` with a `tag` input naming the release tag whose canary passed. While a release's canary runs, `release` MUST keep naming the build of the last release that was rolled, so a session-start refresh in any clone installs no build from an unjudged canary. When the canary samples fail, `release` MUST NOT advance to that release, and the canary clones return to the build `release` names by an operator step that names that build. A `release: published` event MUST NOT advance `release`, and the workflow's job MUST NOT run for that event. The advance MUST be fast-forward-only: when the named tag's commit does not descend from the commit `release` names, the run MUST fail, and `release` MUST keep its commit. The dispatch command is `gh workflow run fast-forward-release-branch.yml -f tag=vX.Y.Z`. Scenario 331 in `scenarios.md` exercises this paragraph.

In `scenarios.md`, replace the whole of Scenario 331, from its `## ` heading to the end of its gherkin block, with:

```markdown
## Scenario 331 — The release branch advances only at the roll step, after its canary passes

Governing clause: `contracts.md` §"Self-contained plugin dispatch".

```gherkin
Feature: The release branch advances only at the roll step, after its canary passes

  Scenario: a published release does not move the release branch
    Given the `release` branch names the commit of release tag v1.0.0
    When release v1.1.0 of this repository is published
    Then the `fast-forward-release-branch.yml` run for that event finishes with its job skipped
    And the `release` branch still names the commit of v1.0.0

  Scenario: a canary clone adopts a release tag while the release branch keeps its commit
    Given the `release` branch names the commit of release tag v1.0.0
    And fleet clones A and B each have this plugin installed at project scope at v1.0.0's commit
    When an operator takes the named-build adopt naming clone A and tag v1.1.0
    Then clone A's install record names v1.1.0's commit
    And clone B's install record still names v1.0.0's commit
    And the `release` branch still names the commit of v1.0.0

  Scenario: a session start outside the canary installs no unjudged build
    Given the `release` branch names the commit of release tag v1.0.0
    And clone A is a canary clone of release v1.1.0, adopted by the named-build adopt
    When a Claude Code session starts in fleet clone B and its session-start plugin refresh runs
    Then clone B's install record names v1.0.0's commit

  Scenario: the roll step advances the release branch after the canary passes
    Given the `release` branch names the commit of release tag v1.0.0
    And release v1.1.0's commit descends from v1.0.0's commit
    And release v1.1.0's canary samples were judged to pass
    When an operator runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.1.0`
    Then the `release` branch names the commit of v1.1.0 when the run ends

  Scenario: a failed canary leaves the release branch on the last rolled build
    Given the `release` branch names the commit of release tag v1.0.0
    And clone A is a canary clone of release v1.1.0
    When release v1.1.0's canary samples are judged to fail
    Then the `release` branch still names the commit of v1.0.0
    And an operator returns clone A to v1.0.0's commit by naming that build

  Scenario: a tag that does not descend from the release branch moves nothing
    Given the `release` branch names the commit of release tag v1.1.0
    When an operator dispatches the workflow with tag v1.0.0, whose commit is an ancestor of v1.1.0's
    Then the run fails
    And the `release` branch still names the commit of v1.1.0

  Scenario: a tag that does not exist moves nothing
    Given the `release` branch names the commit of release tag v1.1.0
    When an operator dispatches the workflow with a tag this repository does not carry
    Then the run fails naming the tag
    And the `release` branch still names the commit of v1.1.0
```
```

The revise that ratifies this changes the Scenario 331 heading text, so it updates that heading's entry in `tests/heading-coverage.json` in the same commit. It adds and removes no other `## ` heading.
