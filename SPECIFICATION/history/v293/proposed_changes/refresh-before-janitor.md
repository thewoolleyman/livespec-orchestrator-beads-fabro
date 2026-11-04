---
topic: refresh-before-janitor
author: claude-opus-5-5
created_at: 2026-11-04T05:52:57Z
---

## Proposal: Refresh onto the default branch before the janitor, and publish the janitor-passed head

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Move the run's refresh onto the advanced default branch from publish_draft to the start of the janitor visit that precedes publish_draft. The full check aggregate then runs once, on the refreshed tree, and publish_draft pushes exactly that janitor-passed head, so the pre-push gate honours the recorded green verdict instead of re-running the aggregate. Refresh repair applies to the janitor's refresh unchanged, and no check is removed.

### Motivation

A green factory run pays the repository's full check aggregate twice whenever the default branch moves during the run. The janitor runs it once on the pre-refresh tree. `publish_draft` then refreshes, which changes the tree, and its pre-push gate correctly runs the full aggregate again under §"Pre-push gate refinements" ("A push whose tree differs from the recorded verdict's tree, such as a `publish_draft` push after its own refresh rebase … MUST run the full pre-push gate").

Measured on 2026-11-04 over 24 h of gmktec petri ImplementWorkItem runs (103 runs, events read for 86):
- In the newer 12 h, the pattern appeared in 18 of 22 runs that reached `publish_draft`, with a typical cost of 26-28 min and a maximum of 58 min.
- All 7 of that half's `publish_draft` push hook-over-limit endings were this pattern. Each threw away a finished implement and janitor.
- Instances: run 01M6HJCFXKTB (bd-ib-oynkut; janitor passed 93/93 at 00:11:24Z, then the refresh 3a2436c4a->218c1e4be and a push killed at 3487910 ms), and run 01M6HWJFSTQX (bd-ib-2h512; publish_draft@2 refresh 218c1e4be->a3c597fdf, then the 3600 s script timeout).

No tier-none fix exists. Run 01M6JGRD7R4R's implementer for the carrier item bd-ib-fvgkw4 found that a verdict carry contradicts "Pre-push gate refinements" and Scenario 253, and that "Refresh repair" fixes the refresh's position after the janitor.

Moving the refresh before the janitor keeps every rule intact: the aggregate still runs in full, once, on the exact tree that is pushed. legacy-coordinator-agent accepted this design (rejecting verdict-carrying across a delta as the riskier gate change) on 2026-11-04. Carrier work item: bd-ib-fvgkw4 under plan sandbox-commit-gate-ceiling (epic bd-ib-qy5wol).

### Proposed Changes

Amend `SPECIFICATION/contracts.md` in three places and add one scenario.

**1. New paragraph, placed immediately BEFORE the paragraph that begins "**Refresh repair.**":**

> **The run refreshes before the janitor, and publish_draft pushes the janitor-passed head.** The `janitor` visit that is followed by a `publish_draft` visit MUST first refresh the run's working branch onto the default branch's current tip, using the same refresh mechanism `publish_draft` uses today, and only then run the repository's full check aggregate on the refreshed head. A green aggregate there records its green verdict for that exact tree under §"Pre-push gate refinements" ("A green aggregate on the exact tree carries to its push"). `publish_draft` MUST NOT refresh again. It MUST push exactly the head that `janitor` passed, so that the pre-push gate honours that verdict instead of re-running the aggregate. When the default branch advances after the janitor's refresh, `publish_draft` still publishes the janitor-passed head; integrating that later advance remains `pr_refresh`'s job. No check, target or gate is removed or weakened: the aggregate runs once, in full, on the tree that is pushed. A refresh that applies cleanly onto an unchanged tip is a no-op, and the janitor then runs exactly as before. Scenario 305 in `scenarios.md` exercises this paragraph.

**2. In the paragraph "**Refresh repair.**", replace the opening sentence and the pre-refresh-head sentence so that the janitor's pre-aggregate refresh takes the route `publish_draft`'s refresh takes today:**

- "When `publish_draft` or `pr_refresh` cannot refresh the run onto the advanced default branch" becomes "When the pre-aggregate refresh of a `janitor` visit, or `pr_refresh`, cannot refresh the run onto the advanced default branch".
- "because the refreshed head fails the repository-declared gate that runs before or during the publishing push" becomes "because the refreshed head fails the repository-declared gate: for `janitor`, its own full aggregate on a head whose refresh changed the tree; for `pr_refresh`, the gate that runs before or during its publishing push".
- "The pre-refresh head is the head the stage held when it began that refresh: for `publish_draft`, the head the most recent `janitor` passed;" becomes "The pre-refresh head is the head the stage held when it began that refresh: for `janitor`, the head the preceding `implement`, `fix` or `review_fix` stage left;".
- "After a refresh-repair round the run re-enters `janitor`, then `publish_draft`, then `proof_capture`" is unchanged.

A janitor aggregate failure on a head whose refresh was a no-op keeps its existing route, exactly as a janitor failure does today. Every other sentence of the paragraph, including the brief's contents, the generated-record-file `regenerate:` lines and the `LIVESPEC_REFRESH_REPAIR_ABSENT` prohibition, applies to the janitor's refresh exactly as it applied to `publish_draft`'s.

**3. Consistent edits elsewhere in `contracts.md`:**

- In "**The stages.**", the clause that describes `publish_draft`'s handling of a refresh that conflicts or whose commit the hook refuses applies to the janitor's pre-aggregate refresh. `publish_draft` keeps its push, its draft-open, its idempotence across janitor re-entries and its fail-closed behaviour when origin cannot be reached.
- In "**A publication that already landed is finished at publish_draft.**", "after its refresh and before it pushes" becomes "before it pushes".
- In "**A refreshed head carries its generated record files as generated.**", the head `publish_draft` refreshed becomes the head the janitor's pre-aggregate refresh produced.
- In "**Refresh-repair accounting.**", every mention of `publish_draft` refreshes or repairs refers to the janitor's pre-aggregate refresh. The bound of at most two refresh-repair rounds in total, now across the janitor's refresh and `pr_refresh`, is unchanged.

**4. `scenarios.md`: add a new scenario after Scenario 304:**

```gherkin
## Scenario 305 — The run refreshes before the janitor, so publish_draft pushes the janitor-passed head without a second aggregate

Feature: A green run pays the full check aggregate once, on the tree it pushes
  As the operator of a factory whose default branch moves during long runs
  I want the refresh onto the default branch to happen before the janitor
  So that publish_draft's push reuses the janitor's green verdict instead of re-running the aggregate

  Scenario: A moved default branch is integrated before the aggregate runs
    Given a run whose implement stage committed green on a base the default branch has since advanced past
    When the janitor visit that precedes publish_draft runs
    Then it refreshes the run's working branch onto the default branch's current tip before it runs the full check aggregate
    And the aggregate's green verdict is recorded for the refreshed tree

  Scenario: publish_draft pushes the janitor-passed head without refreshing
    Given a janitor visit passed the full check aggregate on a refreshed head
    And the default branch has advanced again since that refresh
    When publish_draft runs
    Then it pushes exactly the janitor-passed head without refreshing
    And the pre-push gate honours the recorded green verdict and does not run the tree-pure members again

  Scenario: A conflicting pre-aggregate refresh takes the refresh-repair route
    Given the default branch advanced with a change that conflicts with the run's commits
    When the janitor's pre-aggregate refresh conflicts
    Then the janitor restores the head the preceding agent stage left, records a refresh-repair brief naming the conflicted paths, and routes to fix
    And the run does not end at needs_human with LIVESPEC_REFRESH_REPAIR_ABSENT

  Scenario: An aggregate failure on a changed refreshed head takes the refresh-repair route
    Given the janitor's pre-aggregate refresh changed the tree
    When the full check aggregate fails on the refreshed head
    Then the janitor restores the pre-refresh head and records a refresh-repair brief naming each failed target
```

Co-edit `tests/heading-coverage.json` at revise time with an entry for the new `## Scenario 305 — …` heading, which MAY start as `"test": "TODO"` with a non-empty reason, per the repository's revise co-edit discipline.
