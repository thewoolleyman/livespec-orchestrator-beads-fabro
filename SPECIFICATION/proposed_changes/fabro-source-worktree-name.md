---
topic: fabro-source-worktree-name
author: claude-opus-5-5
created_at: 2026-10-22T01:14:53Z
---

## Proposal: Ratify the staged source checkout's worktree and branch names

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State as a contract that the Dispatcher's staged source checkout for a Fabro run lives at `<worktree-root>/<repository-directory-name>/fabro-source-<id>` on the local branch `livespec/source/<id>`, where `<id>` is one fresh 32-character lowercase hexadecimal value shared by both names, and that these names are a stable cross-repository interface that changes only by ratification. Add a scenario that pins both names.

### Motivation

`_dispatcher_source_staging.py` mints both names today, but no ratified clause states them. livespec-dev-tooling's v083 reap-safety clause (contracts.md, the pack's `reap` verb) treats a worktree whose directory name is `fabro-source-<id>` as factory-owned and never removes it. That protection depends on this repository continuing to mint exactly that name. While the name is unratified, a refactor could rename the directory and pass every gate here, and dev-tooling's `reap` would then silently start treating live staged checkouts as ordinary reapable worktrees and delete one mid-run. Ratifying the names makes a rename a spec change that has to be coordinated across both repositories. Requested by coordinator ruling R541.

### Proposed Changes

1. contracts.md, under ### Dispatch preflight and post-merge step discipline: insert one new paragraph immediately BEFORE the paragraph that begins `**Members-and-adopters-identical audit of the step and preflight set.**` (that is, directly after the `**Sandbox commit-refuse exemption resolution.**` paragraph), reading:

**Staged source checkout names.** When the Dispatcher stages a Fabro run's source in a disposable worktree, so that the engine's pre-run push runs from a checkout that is not the primary, it MUST create that worktree at `<worktree-root>/<repository-directory-name>/fabro-source-<id>` on a new local branch named `livespec/source/<id>`. Here `<worktree-root>` is the per-user worktree root `~/.worktrees`, `<repository-directory-name>` is the final path component of the dispatching repository's checkout, and `<id>` is ONE value, freshly generated for each staging, written as 32 lowercase hexadecimal characters and shared by the directory name and the branch name. The staged branch is never the run's publish branch. These names are a stable interface that other repositories rely on: livespec-dev-tooling's worktree-pack `reap` verb identifies a factory-owned source checkout by the directory-name prefix `fabro-source-` and never removes one. The Dispatcher MUST NOT change either name, or the format of `<id>`, except by ratifying a change to this paragraph that names the consumers it affects.

2. scenarios.md: append a new scenario after the current last scenario, using the next free number (236 at the time of filing):

## Scenario 236 — A staged Fabro source checkout carries the ratified worktree and branch names

```gherkin
Feature: The staged source checkout's names are a stable interface
  As the maintainer of a tool that must recognise a factory-owned worktree
  I want the Dispatcher's staged source checkout to carry fixed, ratified names
  So that a worktree reaper can recognise and skip a live factory checkout by its name

  Scenario: Staging a run's source creates a fabro-source worktree on a livespec/source branch
    Given a governed repository checked out in a directory named "governed-repo"
    And a dispatch whose source the Dispatcher stages in a disposable worktree
    When the Dispatcher creates the staged source checkout
    Then the checkout's directory is "fabro-source-" followed by 32 lowercase hexadecimal characters
    And that directory sits under the per-user worktree root, inside a directory named "governed-repo"
    And the checkout is on a new local branch named "livespec/source/" followed by the same 32 characters
    And the staged branch is not the run's publish branch
```

3. tests/heading-coverage.json: add an entry for `## Scenario 236 — A staged Fabro source checkout carries the ratified worktree and branch names` (spec_file scenarios.md). Its `test` is "TODO", with a reason stating that a test is owed that asserts the exact directory-name and branch-name formats and the shared id, and a `work_item` naming the item filed to own that test.
