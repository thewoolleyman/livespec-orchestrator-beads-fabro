---
topic: the-commit-runner-s-authored
author: claude:factory-run-work-preservation plan seat session d3d4ab
created_at: 2026-11-13T01:32:53Z
---

## Proposal: A commit run's commit carries an authored subject, and a refusal inside a stopped rebase leaves the rebase in progress and names the forms that pass

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add a paragraph to contracts.md §"ACP node timeouts", directly before "A commit run outlives a node-timeout cut.", stating the commit runner's authored-subject rule. The rule shipped in v0.317.0 (bd-ib-7cixf3) without spec text; the paragraph pins its definition to the shipped TRAILER_SUBJECT pattern, under which a Conventional Commits subject is authored. It extends the rule to a commit made while a rebase is stopped on a pick. The refusal MUST NOT end the rebase. The agent's in-turn wait report on the refused run MUST state that a rebase is in progress and name `git commit -C REBASE_HEAD` and `git commit -m <subject>` as the forms that pass; `--no-edit` MUST NOT be named. If the turn ends on the refused run, the settle node's existing abort and preservation apply, and the re-entry brief MUST NOT claim the rebase is open. Merges are out of scope. Add one numberless scenario plus its heading-coverage and debt-register rows.

### Motivation

Measured 2026-11-13 by dev-host-test-gate-load on livespec-dev-tooling-ie7fas, run 01M78JTN0ZZTBN9F6K9XY31ZYS. The janitor's refresh rebased the run's 88 commits onto a base 225 commits behind master and conflicted on the unrelated tests/livespec_dev_tooling/test_flake_retry.py. fix@1, fix@2 and fix@3 each resolved the conflict, and the focused suite passed 70 tests at 100% coverage. All three fix commit runs (commit-d82823b2fe7f440a8e9935ace9087f72, commit-b36edfc92b564358b50e5e18eb09ee53, commit-9a6053612d46426ca05bd2507a7e22d8) were refused with LIVESPEC_COMMIT_NO_AUTHORED_SUBJECT, because the commit recording the resolution carried a trailer as its first message line. The run ended at needs_human through woiqjm's exhausted cutoff. The item's own code was never at fault.

The refusal is the commit runner's authored-subject guard (`unauthored_commit` in `_dispatcher_commit_runner_program.py`, 8023b1034, bd-ib-7cixf3, shipped in v0.317.0). It exists so that a trailer-appending commit-msg hook cannot turn an empty authored message into a commit. SPECIFICATION/ states no authored-subject rule at all: contracts.md, constraints.md and scenarios.md were searched for authored subject, NO_AUTHORED and first message line, with zero hits. So the guard's handling of a merge or rebase in progress is unspecified, and the fix-stage brief never tells the agent how to record a resolution so that it passes. The coordinator (legacy-coordinator-agent, session 56ce1bcd) classified this as a deterministic class separate from the 171ca17b2 routing-schema defect that #5100 reverts. It filed the root fix as bd-ib-vpvdn4 at the expedited-incident-response-flag band, whose filing-tier judgement reads spec-change / UNSTATED with this linked topic. The judgement linked the item against `## Self-contained plugin dispatch`. The commit runner itself is specified in §"ACP node timeouts" ("A commit leg completes past one tool call."), so the clause is placed there.

On v0.325.0, which removes woiqjm's cutoff, this class loops fix → fix_commit_settle → fix until max_visits instead of resting at needs_human, so the forms the agent can use to pass are what end the loop.

How the resolution commit came to carry a trailer first is NOT measured: the refused commits and the runner's output files died with the sandbox, and the run's four wip refs carry no trailer-subject commit. The clause is therefore written over observable outcomes, whatever produced the empty authored message.

IN-FLIGHT ALIGNMENT: the pending proposals a-commit-settle-abort-preserves-the-in-progress-resolution (a settle preserves a resolution before aborting an operation whose commit run failed) and a-commit-settle-node-whose (a settle never routes onward over an operation it could not end) govern what the SETTLE node does after a commit run. This proposal governs only the commit RUN's verdict, the state the runner leaves, and the brief text. It changes no settle behaviour. Relationship to both: align.

GRADE MEASUREMENTS (coordinator grade of #5110 @ 14f4e5070, reproduced independently by this seat in a throwaway git 2.51.0 fixture whose only hook appends `Factory-Run-Id:`):
(1) The shipped guard's TRAILER_SUBJECT is `^[A-Z][A-Za-z0-9]*(-[A-Za-z0-9]+)+:(\s|$)`. It matches `Factory-Run-Id: 01RUN` and does NOT match `fix: run change`, so the paragraph pins that definition rather than a looser `<Token>: <value>` form that would refuse every Conventional Commits subject.
(2) Inside a stopped rebase, a commit with an empty message produced `Factory-Run-Id: 01RUN` as its subject. After `git reset --soft` to the start head, `.git/MERGE_MSG` was ABSENT, because the refused commit consumed it. A following `git commit --no-edit` therefore again produced `Factory-Run-Id: 01RUN`, while `git commit -C REBASE_HEAD` produced the picked commit's subject `fix: run change`, and `git rebase --continue` then finished. So `--no-edit` fails in exactly the state this paragraph addresses, and `-C REBASE_HEAD` is the form named. The same fixture shows `--no-edit` with MERGE_MSG absent reproduces the trailer-first commit exactly. Any successful commit or reset during the stop, an engine checkpoint commit included, removes MERGE_MSG, so this is the leading candidate for ie7fas's mechanism. It is unconfirmed: bd-ib-vpvdn4's implementer reads the run's fabro dump to check.
(3) Every commit-settle node aborts a merge or rebase still in progress after a failed commit run, and both pending settle proposals keep that abort. So "in progress and resumable" holds only within the turn: the statement and the named forms belong to the agent's in-turn wait report, and a re-entry brief written after the settle's abort MUST NOT claim the rebase is open.
(4) A refused merge commit consumes MERGE_HEAD, and the soft reset leaves no merge open, so the paragraph is scoped to a stopped rebase and states that it does not cover a merge.
ANCHOR: the pending a-commit-settle-node-whose also inserts directly after "A settled failed commit run is recorded with its cause.", so this paragraph is anchored directly BEFORE "A commit run outlives a node-timeout cut.", which is deterministic whichever revise lands first.

### Proposed Changes

### 1. `SPECIFICATION/contracts.md` §"ACP node timeouts": add one paragraph

Insert this paragraph directly BEFORE the paragraph that begins **A commit run outlives a node-timeout cut.**. No existing paragraph changes:

```markdown
**A commit run's commit carries an authored subject.** A commit has no
*authored subject* when its first message line is empty or matches
`^[A-Z][A-Za-z0-9]*(-[A-Za-z0-9]+)+:(\s|$)`, the shape of a hyphenated trailer
token such as `Factory-Run-Id:`; a Conventional Commits subject such as
`fix: ...` is an authored subject. When a commit run started through the commit
runner exits 0 and the commit it made has no authored subject, the runner MUST
settle that commit run `failed`. It MUST restore `HEAD` to the head the run
started from, keeping the index and the working tree, and the run's recorded
output MUST name that commit as having no authored subject line. The rule exists
because the repository's commit-msg hook may append trailers to an empty
message, and Git would then make a commit nobody authored. It applies to every
commit run, including one made while a rebase is stopped on a pick. For such a
commit run the refusal MUST NOT itself end the rebase: the rebase MUST still be
in progress, with the index and working tree holding the resolution. When the
agent's in-turn wait on that commit run reports it `failed`, the wait report
MUST state that a rebase is in progress and MUST name the two forms that record
the resolution with an authored subject: a commit run of
`git commit -C REBASE_HEAD`, which reuses the picked commit's own message, and a
commit run of `git commit -m <subject>`. The report MUST NOT name
`git commit --no-edit`, because the refused commit consumed the message Git had
prepared. A commit run of either named form whose commit has an authored subject
MUST settle `passed`. The `fix` and `review_fix` stage prompts MUST name both
forms for a commit made inside a stopped rebase. When the turn ends on the
refused commit run, the commit settle node's existing abort and preservation
apply unchanged, and the re-entry brief MUST NOT state that the rebase is still
in progress. This paragraph does not cover a merge, because a refused merge
commit consumes `MERGE_HEAD` and the soft reset leaves no merge open.
```

### 2. `SPECIFICATION/scenarios.md`: add one scenario, numbered at revise

The heading is numberless here. The revise pass MUST assign the next free scenario number and update the heading text in changes 3 and 4 to match.

~~~markdown
## Scenario: a commit run's commit carries an authored subject, and a refusal inside a stopped rebase leaves the rebase in progress and names the forms that pass

```gherkin
Feature: A resolved rebase conflict can always be committed
  As a maintainer whose factory runs refresh onto a moving default branch
  I want a fix turn's commit of a resolved rebase conflict to pass when it carries an authored subject
  So that a correct resolution is never refused on every visit until the run's budget is spent

  Scenario: A resolution committed with no authored subject is refused and the rebase stays in progress
    Given a fix turn whose rebase stopped on a conflict at picked commit C, which the agent resolved and staged
    And the repository's commit-msg hook appends a Factory-Run-Id trailer
    When the agent's commit run through the commit runner commits the resolution with an empty authored message
    Then the commit run settles failed and its recorded output names the commit as having no authored subject line
    And HEAD is the head the commit run started from
    And the rebase is still in progress with the index holding the resolution
    And the agent's in-turn wait report on that commit run states that a rebase is in progress and names git commit -C REBASE_HEAD and git commit -m <subject>

  Scenario: After a refusal, the resolution committed with the picked commit's own message passes
    Given the refused commit run of the previous scenario, with the rebase still in progress at picked commit C
    When the agent's next commit run through the commit runner is git commit -C REBASE_HEAD
    Then the commit run settles passed
    And the new commit's first message line is C's authored subject
    And the rebase moves past C to its next pick when it is continued

  Scenario: A Conventional Commits subject is an authored subject
    Given a repository whose commit-msg hook appends a Factory-Run-Id trailer
    When a commit run through the commit runner commits with the message "fix: resolve the conflict"
    Then the commit run settles passed
    And the new commit's first message line is "fix: resolve the conflict"

  Scenario: An ordinary commit with no authored subject is still refused
    Given a repository with no rebase in progress whose commit-msg hook appends a Factory-Run-Id trailer
    When a commit run through the commit runner commits with an empty authored message
    Then the commit run settles failed
    And HEAD is the head the commit run started from
    And the recorded output names the commit as having no authored subject line

  Scenario: A turn that ends on the refused commit run does not claim the rebase is open
    Given a fix turn that ends while its latest commit run inside a stopped rebase was refused for having no authored subject
    When the fix_commit_settle node settles that commit run
    Then the settle node's existing abort and preservation apply
    And the fix re-entry brief does not state that the rebase is still in progress
```
~~~

### 3. `tests/heading-coverage.json`: add the new heading in the same revise

The revise that ratifies this MUST add one entry, using the heading as numbered at revise:

```json
{"heading": "## Scenario: a commit run's commit carries an authored subject, and a refusal inside a stopped rebase leaves the rebase in progress and names the forms that pass", "spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "test": "TODO", "work_item": "bd-ib-vpvdn4", "reason": "A test at the integration tier or above is owed: the commit runner's own suite, delivered by bd-ib-vpvdn4, driving a real rebase stopped on a conflict in a local git fixture whose commit-msg hook appends a trailer."}
```

### 4. `tests/heading-coverage-debt.json`: add the matching row in the same revise

The register has no generator, so the row is authored. `check-heading-coverage-debt-register` admits it under its spec-first admission, because this same change introduces the heading:

```json
{"spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "heading": "## Scenario: a commit run's commit carries an authored subject, and a refusal inside a stopped rebase leaves the rebase in progress and names the forms that pass", "work_item": "bd-ib-vpvdn4", "first_seen": "<revise date>"}
```

No existing heading changes, per AGENTS.md §"Revise co-edit discipline".

### 5. Follow-through outside the spec (not part of this revise)

On ratification, bd-ib-vpvdn4's Definition of Done `References:` line SHOULD name the new scenario heading, as numbered at revise. Its spec-change tier is then re-classified, and it is approved for dispatch at the expedited-incident-response-flag band.
