---
topic: a-janitor-green-run-cancelled
author: claude-opus-5-5:publish-draft-green-work-loss
created_at: 2026-11-04T10:07:08Z
---

## Proposal: Preserve a janitor-green run's tree before a restart cancel and when reporting an external cancel

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Extend the Scenario 183 preserved-publish rule so that a run which already passed janitor is published to refs/livespec/preserved-publish/<work-item-id>/ before a restart cancel lands. The cancel goes through a new Dispatcher cancel-for-restart command. A janitor-green run that was cancelled outside the Dispatcher gets the same publication attempt when it is reported. A re-dispatch starts from the preserved tree.

### Motivation

On 2026-11-04 the planned petri :32276 engine restart for c39bdbd cancelled all 13 active runs through POST /api/v1/runs/<id>/cancel at 09:56:18-27Z, under R301, per livespec-dev-tooling .ai/factory-restart-cancels-runs.md. One was bd-ib-uq2ocd run 01M6JSNVH32S8CDNX0P4TS7DWB: implement committed a8bc61900 (the commit hook passed 90/90), janitor PASSED, and publish_draft had rebased cleanly and was pushing. Nothing reached origin, the sandbox was torn down and the run dump carries no patch, so the green commit was lost and a re-dispatch must redo implement. bd-ib-xuo54m run 01M6JC00SX2G was lost the same way at 04:36Z. The maintainer's 2026-10-24 direction requires a restart to cancel runs rather than wait for them, so the cancel itself must preserve finished work. Scenario 183 already defines a hookless preservation publication, but only for checkpoint-failed runs. Work item: bd-ib-vraou4 (plan publish-draft-green-work-loss, epic bd-ib-acrr56).

### Proposed Changes

In `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Failed engine checkpoint commit attribution", insert this paragraph directly after the paragraph that opens "**A tree that nothing else carries is published to a preservation ref.**":

> **A janitor-green run cancelled outside the Dispatcher is published to a preservation ref.** A run is JANITOR-GREEN when its `janitor` stage has succeeded. Its committed branch head then carries work that passed the full check suite, and only its sandbox holds that head until `publish_draft` pushes it. When a factory operator must cancel active runs to idle a factory server for a restart or upgrade, the operator MUST cancel through the Dispatcher's `cancel-for-restart --factory <name>` command rather than the server's cancel endpoint alone. For each active run of that factory that is janitor-green and that has not reported its branch published, the command MUST first read the run's changed files, with their contents, from the run's factory target, and publish them exactly as the preceding paragraph publishes a checkpoint-failed tree: one commit at `refs/livespec/preserved-publish/<work-item-id>/<commit-sha>`, parented on the run's base commit, created through the forge's Git Data API with no `git push` and no repository hook. Only then MUST it cancel that run. A run that is not janitor-green MUST be cancelled without a publication. When the read or any publication step fails, the command MUST still cancel the run, and it MUST record the failed step as the next sentence requires; the preservation is best effort and MUST NOT hold a factory restart. When the Dispatcher reports a run that was cancelled outside the Dispatcher and that was janitor-green, and no `livespec-preserved-tree` comment already names that run, it MUST attempt the same read and publication from the dispatch's resolved factory target. In both cases it MUST add the `livespec-preserved-tree` ledger comment of the preceding paragraph, naming the run id, the factory name, the preservation ref and its commit id, or stating that the tree was not preserved and naming the step that failed. A later dispatch of that item MUST carry the newest such preservation ref in its brief as the tree to start from, under the same preference order that §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work" gives a checkpoint-failed run's preserved tree. These rules change no dispatch outcome, exit code or `blocked_reason` that a cancelled run already receives. Scenario 306 in `scenarios.md` exercises this paragraph.

Append to `scenarios.md`:

## Scenario 306 — A janitor-green run cancelled for a factory restart has its committed tree published to a preservation ref

Governing clause: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Failed engine checkpoint commit attribution".

```gherkin
Feature: A factory restart does not cost a run's finished work
  As the maintainer of a repository dispatched through the factory
  I want a run that already passed janitor preserved before it is cancelled
  So that a restart window re-dispatches from the green tree instead of redoing implement

  Scenario: the restart cancel preserves a janitor-green run before cancelling it
    Given an active run on factory petri whose janitor stage succeeded and whose publish_draft stage has not published its branch
    When the operator runs cancel-for-restart for factory petri
    Then the forge carries a ref refs/livespec/preserved-publish/<work-item-id>/<commit-sha> whose commit's parent is the run's base commit and whose tree reflects the run's committed changes
    And no git push and no repository hook ran for that publication
    And the run is cancelled after the ref exists
    And a livespec-preserved-tree ledger comment names the run id, the factory, the preservation ref and its commit id

  Scenario: a run that has not passed janitor is cancelled without a publication
    Given an active run on factory petri whose janitor stage has not succeeded
    When the operator runs cancel-for-restart for factory petri
    Then the run is cancelled
    And no ref under refs/livespec/preserved-publish/<work-item-id>/ is created for that run

  Scenario: a failed preservation still cancels the run and is recorded
    Given an active janitor-green run on factory petri whose changed files the factory refuses to return
    When the operator runs cancel-for-restart for factory petri
    Then the run is cancelled
    And a livespec-preserved-tree ledger comment states that the tree was not preserved and names the files read as the step that failed

  Scenario: a janitor-green run cancelled outside the Dispatcher is preserved when it is reported
    Given a janitor-green run that was cancelled through the factory server's cancel endpoint
    And no livespec-preserved-tree comment names that run
    When the Dispatcher reports the run as cancelled outside the Dispatcher
    Then it attempts the publication of the run's changed files to a ref under refs/livespec/preserved-publish/<work-item-id>/
    And a livespec-preserved-tree ledger comment records the ref or the step that failed

  Scenario: the next dispatch starts from the preserved tree
    Given an item whose ledger carries a livespec-preserved-tree comment naming a preservation ref for its cancelled run
    When the item is dispatched again
    Then the dispatch brief names that preservation ref as the tree to start from
```

Add a `tests/heading-coverage.json` entry for the new `## Scenario 306 — ...` heading (test `"TODO"` with a non-empty reason naming bd-ib-vraou4) in the same revise pass.
