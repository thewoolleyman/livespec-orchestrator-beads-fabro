---
topic: record-file-refresh-merge
author: claude-opus-5-5
created_at: 2026-10-18T22:05:57Z
---

## Proposal: A refresh whose conflicts lie only in declared record files merges them without a repair round

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Let a repository declare shared record files (dispatcher.record_files: path, format json-array with key fields, or markdown-insertions). When a publish_draft or pr_refresh rebase conflicts only in declared record files, the stage attempts an entry-wise three-way merge; when every file is resolvable it completes the rebase and proceeds as a clean refresh (gate, then the carry-forward decision), counting no refresh-repair round. Anything else keeps the refresh-repair route. Add Scenario 200.

### Motivation

Work item bd-ib-davaxq (finding F-be, admitted by driver ruling R210 of gitops-fleet-capacity-monitoring). On 2026-10-18 three factory runs were lost to conflicts in shared record files that carried no semantic conflict: bd-ib-sufca7 PR 3240 (tests/prompts/CLAUDE.md), bd-ib-sufca7 PR 3261 (tests/heading-coverage-debt.json, where each side removed a different object, and tests/integration/CLAUDE.md, where each side inserted a section at the same place), and bd-ib-jgedjo's first resume. Each record file is extended by nearly every revise and scenario-binding change, so collisions grow with factory throughput, and each one costs a refresh-repair fix round, or a needs-human rest and a resume when it arrives after arming. No ratified text lets a refresh resolve such a conflict mechanically, and Scenario 184 governs only the routing, so the item's references cannot govern a mechanical merge at dod_gate.

### Proposed Changes

In SPECIFICATION/contracts.md, section "## Self-contained plugin dispatch", immediately before the paragraph that begins "**Refresh-repair accounting.**", insert this paragraph:

**Declared record files merge without a repair round.** A repository MAY declare, in its committed `.livespec.jsonc` under `dispatcher.record_files`, the shared record files that many changes extend independently. Each entry names a repository-relative `path` and a `format`. The format is `json-array` for a file holding one JSON array of objects, and an entry of that format also names `key`, the list of fields whose values identify one object. The format is `markdown-insertions` for a Markdown file. An absent key declares no record files. When the rebase or merge of `publish_draft` or `pr_refresh` conflicts, and every conflicted path is a declared record file, the stage MUST first attempt an entry-wise three-way merge of each conflicted file. It compares the file at the merge base, at the default-branch side and at the run's side. For a `json-array` file, each object is identified by its `key` values. An object that one side added, changed or removed takes that side's result, and an object that both sides left alone stays as it is. The merge is resolvable only when no object was added, changed or removed differently by both sides, and when the merged array parses and holds no two objects with the same key. The merged array keeps the default-branch side's order, followed by the run's added objects in the run's order. For a `markdown-insertions` file, the merge is resolvable only when each conflicting region consists of lines that each side inserted at the same position, with no line of the merge base changed or removed by both sides. The merged region holds the default-branch side's inserted lines followed by the run's inserted lines. When every conflicted file is resolvable, the stage MUST write the merged files, MUST continue the rebase or merge to completion, and MUST then proceed exactly as after a refresh that did not conflict. The repository-declared gate runs on the refreshed head. In `pr_refresh`, a rebase whose only conflicts this paragraph resolved counts as applied without conflict for "Proof carry-forward across a refresh", and the deterministic decision of that paragraph then decides whether the verified proof covers the new head or the run re-proves. Such a merge is not a refresh-repair round and MUST NOT count toward "Refresh-repair accounting". The stage MUST record each file it merged this way, with its format and the number of objects or lines it took from each side, in the run's output for that stage. A conflict in any path that is not a declared record file, a declared file that is not resolvable, or a merged head that the gate rejects takes the refresh-repair route above unchanged, with the pre-refresh head restored. This paragraph changes no ratified behaviour of the Dispatcher's merge wait, including "Armed pull request overtaken by the default branch". Scenario 200 in `scenarios.md` exercises this paragraph.

In SPECIFICATION/scenarios.md, after Scenario 199, append:

## Scenario 200 — A refresh whose conflicts lie only in declared record files merges them without a repair round

```gherkin
Feature: Concurrent additions to shared record files do not cost a run a repair round
  As the maintainer of a repository dispatched to the factory
  I want conflicts confined to declared record files merged entry by entry during a refresh
  So that two changes that each add their own records do not send a run to the fix agent or to a human

  Scenario: Different objects changed by each side of a declared JSON record merge cleanly
    Given a repository whose committed dispatcher.record_files declares tests/heading-coverage-debt.json with format json-array and key spec_root, spec_file and heading
    And the default branch removed the object for one heading while the run removed the object for a different heading
    When pr_refresh rebases the run onto the default branch and the rebase conflicts only in that file
    Then the stage merges the file with both objects removed, completes the rebase and runs the repository-declared gate on the refreshed head
    And the stage records the merged file with its format and the count taken from each side
    And no refresh-repair round is counted and the run does not enter fix

  Scenario: Insertions by both sides at the same place in a declared Markdown record keep both
    Given a repository that declares tests/integration/CLAUDE.md with format markdown-insertions
    And the default branch and the run each inserted a section at the same position in that file
    When publish_draft or pr_refresh refreshes the run and the refresh conflicts only in that file
    Then the merged file holds the default branch's inserted lines followed by the run's inserted lines
    And the stage proceeds as after a refresh that did not conflict

  Scenario: The same object changed differently by both sides takes refresh repair
    Given a declared json-array record in which both the default branch and the run changed the object with the same key to different values
    When pr_refresh rebases the run and the rebase conflicts in that file
    Then the stage restores the pre-refresh head, records a refresh-repair brief naming the file, and routes to fix

  Scenario: A conflict outside the declared record files takes refresh repair
    Given a refresh that conflicts in a declared record file and in a Python module
    When pr_refresh rebases the run
    Then the stage merges nothing, restores the pre-refresh head, and routes to fix with a refresh-repair brief naming both paths

  Scenario: A merged head the gate rejects takes refresh repair
    Given a refresh whose conflicts were all resolved by the record-file merge
    When the repository-declared gate rejects the refreshed head
    Then the stage restores the pre-refresh head and routes to fix with a refresh-repair brief naming each failed gate target
```

The revise pass that accepts this proposal MUST add a tests/heading-coverage.json entry for the Scenario 200 heading in the same change, with test "TODO" and a reason stating that an integration-tier test is owed and that work-item bd-ib-davaxq implements it and owns that binding, plus the matching tests/heading-coverage-debt.json row.
