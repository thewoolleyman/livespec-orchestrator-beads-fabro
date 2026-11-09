---
topic: the-release-branch-advances-only
author: claude:gmktec-factory-placement
created_at: 2026-11-09T01:44:33Z
---

## Proposal: The release branch advances only at the roll step

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State the release-channel contract in contracts.md §"Self-contained plugin dispatch": `release` advances only when the roll step dispatches fast-forward-release-branch.yml with a published tag, after canary samples, fast-forward-only; a published release does not move it. Add one scenario exercising it.

### Motivation

Every fleet clone's committed `.claude/settings.json` pins this plugin's marketplace at `ref: release`, and so does this host's single `~/.claude/plugins/known_marketplaces.json` entry. `.github/workflows/fast-forward-release-branch.yml` advanced the unprotected `release` branch on EVERY `release: published` event, so each session start installed a release the moment it was published, with no canary.

Measured incidents:
- livespec-dev-tooling's registration moved at 2026-11-08T21:17Z.
- This repository's registration moved c0b28ad85bab -> 35cdda22389c (v0.307.0) at 2026-11-09T01:28:45Z, seven minutes after the release was published at 01:21:09Z.

This specification never states the `release` contract: the only mention, in §"pi skill surface", calls it "the same moving `release` channel". That is why the implementing item bd-ib-sghxlk was tiered spec-change (record 01:37:38Z, linked topic the-release-branch-advances-only). The basis is livespec-dev-tooling spec v155, option D (topic orchestrator-build-explicit-adoption): a member adopts a build only when a committed fleet record names it. The livespec core contract calls `release` "the moving release channel" and does not require it to equal the newest release, so this realization detail belongs in this repository's specification. legacy-coordinator-agent requested the proposal (session e8d70af3, 2026-11-09 ~01:5xZ). The implementation is already gated in a worktree and is additive only.

### Proposed Changes

In `contracts.md` §"Self-contained plugin dispatch", insert this paragraph directly after the paragraph that ends "the orchestrator's own source is never a dispatch-time prerequisite.":

> **The release channel.** Fleet members and adopters resolve this plugin through the moving `release` branch: every consumer's marketplace registration names `ref: release`, and a session-start plugin refresh installs whatever commit `release` names. So the commit `release` names IS the build the fleet adopts. `release` MUST advance only when the roll step dispatches `.github/workflows/fast-forward-release-branch.yml` with a `tag` input naming a published release tag of this repository, after that release's canary samples. A `release: published` event MUST NOT advance `release`, and the workflow's job MUST NOT run for that event. The advance MUST be fast-forward-only: when the named tag's commit does not descend from the commit `release` names, the run MUST fail, and `release` MUST keep its commit. The roll step's command is `gh workflow run fast-forward-release-branch.yml -f tag=vX.Y.Z`. Scenario <next free number> in `scenarios.md` exercises this paragraph.

Append to `scenarios.md`:

```gherkin
## Scenario <next free number> — The release branch advances only at the roll step

Scenario: a published release does not move the release branch
  Given the `release` branch names the commit of release tag v1.0.0
  When release v1.1.0 of this repository is published
  Then the `fast-forward-release-branch.yml` run for that event finishes with its job skipped
  And the `release` branch still names the commit of v1.0.0

Scenario: the roll step advances the release branch to a canaried tag
  Given the `release` branch names the commit of release tag v1.0.0
  And release v1.1.0's commit descends from v1.0.0's commit
  When the roll step runs `gh workflow run fast-forward-release-branch.yml -f tag=v1.1.0`
  Then the `release` branch names the commit of v1.1.0 when the run ends

Scenario: a tag that does not descend from the release branch moves nothing
  Given the `release` branch names the commit of release tag v1.1.0
  When the roll step dispatches the workflow with tag v1.0.0, whose commit is an ancestor of v1.1.0's
  Then the run fails
  And the `release` branch still names the commit of v1.1.0

Scenario: a tag that does not exist moves nothing
  Given the `release` branch names the commit of release tag v1.1.0
  When the roll step dispatches the workflow with a tag this repository does not carry
  Then the run fails naming the tag
  And the `release` branch still names the commit of v1.1.0
```

The revise that ratifies this adds the new heading to `tests/heading-coverage.json` in the same commit.
