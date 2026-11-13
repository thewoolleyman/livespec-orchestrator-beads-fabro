---
topic: the-commit-runner-s-authored
author: claude:factory-run-work-preservation plan seat session d3d4ab
created_at: 2026-11-13T00:56:29Z
---

## Proposal: A commit run's commit carries an authored subject, and a refusal inside a merge or rebase leaves that operation resumable and names the forms that record the resolution

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add a paragraph to contracts.md §"ACP node timeouts", directly after "A settled failed commit run is recorded with its cause.", that states the commit runner's authored-subject rule. The runner shipped the rule in v0.317.0 (bd-ib-7cixf3) without spec text. The paragraph extends the rule to commits made inside a merge or rebase. An exit-0 commit run whose resulting commit's first message line is empty or a trailer settles failed, and HEAD returns to the run's start head with the index and working tree kept. When a merge or rebase was in progress, the refusal leaves it in progress and resumable with the resolution intact. The run's recorded output then names the two forms that record the resolution with an authored subject, `git commit --no-edit` and `git commit -m <subject>`, and the fix and review_fix prompts name them too. A commit run of either form whose commit's first line is authored settles passed. Add one numberless scenario plus its heading-coverage and debt-register rows.

### Motivation

Measured 2026-11-13 by dev-host-test-gate-load on livespec-dev-tooling-ie7fas, run 01M78JTN0ZZTBN9F6K9XY31ZYS. The janitor's refresh rebased the run's 88 commits onto a base 225 commits behind master and conflicted on the unrelated tests/livespec_dev_tooling/test_flake_retry.py. fix@1, fix@2 and fix@3 each resolved the conflict, and the focused suite passed 70 tests at 100% coverage. All three fix commit runs (commit-d82823b2fe7f440a8e9935ace9087f72, commit-b36edfc92b564358b50e5e18eb09ee53, commit-9a6053612d46426ca05bd2507a7e22d8) were refused with LIVESPEC_COMMIT_NO_AUTHORED_SUBJECT, because the commit recording the resolution carried a trailer as its first message line. The run ended at needs_human through woiqjm's exhausted cutoff. The item's own code was never at fault.

The refusal is the commit runner's authored-subject guard (`unauthored_commit` in `_dispatcher_commit_runner_program.py`, 8023b1034, bd-ib-7cixf3, shipped in v0.317.0). It exists so that a trailer-appending commit-msg hook cannot turn an empty authored message into a commit. SPECIFICATION/ states no authored-subject rule at all: contracts.md, constraints.md and scenarios.md were searched for authored subject, NO_AUTHORED and first message line, with zero hits. So the guard's handling of a merge or rebase in progress is unspecified, and the fix-stage brief never tells the agent how to record a resolution so that it passes. The coordinator (legacy-coordinator-agent, session 56ce1bcd) classified this as a deterministic class separate from the 171ca17b2 routing-schema defect that #5100 reverts. It filed the root fix as bd-ib-vpvdn4 at the expedited-incident-response-flag band, whose filing-tier judgement reads spec-change / UNSTATED with this linked topic. The judgement linked the item against `## Self-contained plugin dispatch`. The commit runner itself is specified in §"ACP node timeouts" ("A commit leg completes past one tool call."), so the clause is placed there.

On v0.325.0, which removes woiqjm's cutoff, this class loops fix → fix_commit_settle → fix until max_visits instead of resting at needs_human, so the forms the agent can use to pass are what end the loop.

How the resolution commit came to carry a trailer first is NOT measured: the refused commits and the runner's output files died with the sandbox, and the run's four wip refs carry no trailer-subject commit. The clause is therefore written over observable outcomes, whatever produced the empty authored message.

IN-FLIGHT ALIGNMENT: the pending proposals a-commit-settle-abort-preserves-the-in-progress-resolution (a settle preserves a resolution before aborting an operation whose commit run failed) and a-commit-settle-node-whose (a settle never routes onward over an operation it could not end) govern what the SETTLE node does after a commit run. This proposal governs only the commit RUN's verdict, the state the runner leaves, and the brief text. It changes no settle behaviour. Relationship to both: align.

### Proposed Changes

### 1. `SPECIFICATION/contracts.md` §"ACP node timeouts": add one paragraph

Insert this paragraph directly after the paragraph that begins **A settled failed commit run is recorded with its cause.** No existing paragraph changes:

```markdown
**A commit run's commit carries an authored subject.** A commit's *authored subject* is its first message line when that line is neither empty nor a trailer line of the form `<Token>: <value>`. When a commit run started through the commit runner exits 0 and the commit it made has no authored subject, the runner MUST settle that commit run `failed`. It MUST restore `HEAD` to the head the run started from, keeping the index and the working tree, and the run's recorded output MUST name that commit as having no authored subject line. This rule exists because the repository's commit-msg hook may append trailers to an empty message, and Git would then make a commit that nobody authored. It applies to every commit run, including one made while a merge or rebase is in progress. When a merge or rebase was in progress when the commit run started, the refusal MUST leave that operation in progress and resumable, with the index and working tree still holding its resolution. The run's recorded output MUST then also state that the operation is in progress and MUST name the two forms that record the resolution with an authored subject: a commit run of `git commit --no-edit`, which keeps the message Git prepared from the picked or merged commit, and a commit run of `git commit -m <subject>`. A commit run of either form whose commit has an authored subject MUST settle `passed`. The `fix` and `review_fix` stage prompts MUST name both forms for a commit made inside a merge or rebase. This paragraph changes nothing that a commit settle node does after a commit run settles.
```

### 2. `SPECIFICATION/scenarios.md`: add one scenario, numbered at revise

The heading is numberless here. The revise pass MUST assign the next free scenario number and update the heading text in changes 3 and 4 to match.

~~~markdown
## Scenario: a commit run's commit carries an authored subject, and a refusal inside a rebase leaves it resumable and names the forms that pass

```gherkin
Feature: A resolved conflict can always be committed
  As a maintainer whose factory runs refresh onto a moving default branch
  I want a fix turn's commit of a resolved rebase conflict to pass when it carries an authored subject
  So that a correct resolution is never refused on every visit until the run's budget is spent

  Scenario: A resolution committed with no authored subject is refused and the rebase stays resumable
    Given a fix turn whose rebase stopped on a conflict at picked commit C, which the agent resolved and staged
    And the repository's commit-msg hook appends a Factory-Run-Id trailer
    When the agent's commit run through the commit runner commits the resolution with an empty authored message
    Then the commit run settles failed and its recorded output names the commit as having no authored subject line
    And HEAD is the head the commit run started from
    And the rebase is still in progress with the index holding the resolution
    And the recorded output states that a rebase is in progress and names git commit --no-edit and git commit -m <subject>

  Scenario: The resolution committed under the picked commit's own message settles passed
    Given a fix turn whose rebase stopped on a conflict at picked commit C, which the agent resolved and staged
    And the repository's commit-msg hook appends a Factory-Run-Id trailer
    When the agent's commit run through the commit runner is git commit --no-edit
    Then the commit run settles passed
    And the new commit's first message line is C's authored subject

  Scenario: An ordinary commit with no authored subject is still refused
    Given a repository with no merge or rebase in progress whose commit-msg hook appends a Factory-Run-Id trailer
    When a commit run through the commit runner commits with an empty authored message
    Then the commit run settles failed
    And HEAD is the head the commit run started from
    And the recorded output names the commit as having no authored subject line
```
~~~

### 3. `tests/heading-coverage.json`: add the new heading in the same revise

The revise that ratifies this MUST add one entry, using the heading as numbered at revise:

```json
{"heading": "## Scenario: a commit run's commit carries an authored subject, and a refusal inside a rebase leaves it resumable and names the forms that pass", "spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "test": "TODO", "reason": "A test at the integration tier or above is owed: the commit runner's own suite, delivered by bd-ib-vpvdn4, driving a real rebase stopped on a conflict in a local git fixture whose commit-msg hook appends a trailer."}
```

### 4. `tests/heading-coverage-debt.json`: add the matching row in the same revise

The register has no generator, so the row is authored. `check-heading-coverage-debt-register` admits it under its spec-first admission, because this same change introduces the heading:

```json
{"spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "heading": "## Scenario: a commit run's commit carries an authored subject, and a refusal inside a rebase leaves it resumable and names the forms that pass", "work_item": "bd-ib-vpvdn4", "first_seen": "<revise date>"}
```

No existing heading changes, per AGENTS.md §"Revise co-edit discipline".

### 5. Follow-through outside the spec (not part of this revise)

On ratification, bd-ib-vpvdn4's Definition of Done `References:` line SHOULD name the new scenario heading, as numbered at revise. Its spec-change tier is then re-classified, and it is approved for dispatch at the expedited-incident-response-flag band.
