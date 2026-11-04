---
topic: generated-record-file-regeneration
author: claude-opus-5-5
created_at: 2026-10-22T06:58:55Z
---

## Proposal: A declared record file may name its generator, and a refresh resolves it by regeneration rather than by merging its text

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Some shared record files are not authored by hand. Each is generated from another committed file, as `tests/heading-coverage-debt.json` is generated from `tests/heading-coverage.json` by `just generate-heading-coverage-debt-register`. When a refresh conflicts in such a file, merging its text is the wrong operation, because the file's correct content is whatever its generator produces over the refreshed tree. This proposal adds an optional `generator` field to a `dispatcher.record_files` entry: an argv run from the repository root that rewrites the file from the tree. A conflicted file whose entry declares a generator is resolved by running that generator after every other conflicted path is resolved, never by an entry-wise merge or a hand edit. That holds on the entry-wise merge route and on the refresh-repair route. A refreshed head therefore carries each such file byte-identical to its generator's output over that head's tree. The stage checks that before the repository-declared gate and reports a mismatch as a failed gate target naming the file. The refresh-repair brief gains a `regenerate:` line per generator-declared file it routes, naming the file and its generator, so the `fix` turn is told which files to regenerate rather than edit.

### Motivation

Measured 2026-10-22 and filed as bd-ib-ze7xxj (P1, coordinator R564/R570). Three chase-master re-runs hit the same class on one day: livespec-dev-tooling-ouk27x, livespec-dev-tooling-ltkxq2 (run 01M5GWSFZPN6 on hp, build b63a9548019c), and livespec-dev-tooling-7kvh2d (PR #2751). In ltkxq2, the pull request and the default branch had both edited `tests/heading-coverage-debt.json`: the PR removed one row and master added rows for two newly ratified scenarios. `pr_refresh` routed to `refresh_repair` and `fix`; the fix turn merged the register's text by hand and lost master's added rows; `check-heading-coverage-debt-register` then failed and the run ended at `needs_human` in ten minutes. The ratified entry-wise merge ("Declared record files merge without a repair round", Scenario 200) does not reach this case: it applies only when EVERY conflicted path is a declared record file, and here `tests/heading-coverage.json` conflicted too. Even where it applies, an entry-wise merge of a generated file can disagree with the generator's output over the merged source. The R265 dod-preflight of bd-ib-ze7xxj (gate 20261022T063931Z-2917963) refused the item because no ratified text declares a generated register, its generator, its conflict route, or a refresh-repair brief field for it; this proposal supplies exactly those. Note that no fleet repository declares `dispatcher.record_files` today, so adopting the generator route for a register is a per-repository configuration change that each owning repository makes after ratification.

### Proposed Changes

In `SPECIFICATION/contracts.md`, in the paragraph **Declared record files merge without a repair round.**, after the sentence that defines the `markdown-insertions` format, insert:

> Any entry MAY also name `generator`, a non-empty argv array run from the repository root that rewrites the file at `path` from the repository's tree. A file whose entry names a generator is a GENERATED record file. Its correct content is its generator's output over the tree it sits in, so a conflict in it is never resolved by merging its text, on any route.

Then, in the same paragraph, after the sentence "When every conflicted file is resolvable, the stage MUST write the merged files, MUST continue the rebase or merge to completion, and MUST then proceed exactly as after a refresh that did not conflict.", insert:

> A conflicted generated record file is not merged entry by entry. The stage MUST first resolve every other conflicted path by this paragraph, then MUST run the file's generator over that tree and write its output as the resolution. The file is resolvable exactly when the generator exits zero. The stage MUST record each file it resolved this way, with the generator it ran, in the run's output for that stage.

In the paragraph that defines the refresh-repair brief ("Refresh repair"), after the enumeration of the brief's contents, add:

> When the conflicted paths include a generated record file, the brief MUST carry one line `regenerate: <path> via <generator argv>` per such file. The `fix` turn MUST resolve every other conflicted path first and MUST then resolve each named file by running its generator, never by editing its text. When a failed gate target's failure names a generated record file, the brief MUST carry the same `regenerate:` line for that file beside the failed target.

And add, as a new paragraph immediately after the paragraph **Declared record files merge without a repair round.**:

> **A refreshed head carries its generated record files as generated.** Before the repository-declared gate runs on a head that `publish_draft` or `pr_refresh` refreshed, by any route, the stage MUST run the generator of every declared generated record file over that head's tree and compare its output with the committed file. A file whose committed bytes differ from its generator's output MUST fail the stage as a failed gate target named `generated-record-file:<path>`, which takes the refresh-repair route with that target in the brief. A head that passes this check therefore carries every row its generator derives from the merged source, including rows the default branch added while the run was in flight.

In `SPECIFICATION/scenarios.md`, add after the last scenario:

```gherkin
## Scenario 238 — A refresh resolves a conflicted generated record file by running its generator

Feature: A generated register is regenerated, never hand-merged, when a refresh conflicts
  As the maintainer of a repository with a generated coverage register
  I want a refresh conflict in that register resolved by its generator
  So that rows the default branch added while a run was in flight are not lost

  Scenario: A conflict only in record files regenerates the generated one
    Given a repository whose committed dispatcher.record_files declares tests/heading-coverage.json as json-array and tests/heading-coverage-debt.json as json-array with a generator
    And the default branch added two registry rows and their register rows while the run removed a different row from both files
    When pr_refresh rebases the run and the rebase conflicts only in those two files
    Then the stage merges tests/heading-coverage.json entry by entry and then runs the generator to write tests/heading-coverage-debt.json
    And the refreshed register carries the default branch's two added rows and omits the row the run removed
    And the stage records the regenerated file with the generator it ran and no refresh-repair round is counted

  Scenario: A repair brief tells fix to regenerate the generated file
    Given a refresh that conflicts in a Python module and in a generated record file
    When pr_refresh rebases the run
    Then the stage restores the pre-refresh head and routes to fix with a brief carrying one regenerate line naming that file and its generator

  Scenario: A refreshed head whose generated file was edited by hand fails before the gate
    Given a refreshed head whose committed generated record file differs from its generator's output over that head
    When the stage checks the head before the repository-declared gate
    Then the stage fails with a failed gate target named generated-record-file followed by that file's path
    And the refresh-repair brief carries that target and a regenerate line for the file
```

(Place the `## Scenario 238` heading outside the gherkin fence, matching the file's house format; if a concurrent revise has taken 238, renumber to the next free number.)

In `tests/heading-coverage.json`, add an entry for that scenario heading with `test` set to `"TODO"`, a `reason` naming bd-ib-ze7xxj as the owning work-item that adds the exercising integration test, and add the matching row to `tests/heading-coverage-debt.json`.
