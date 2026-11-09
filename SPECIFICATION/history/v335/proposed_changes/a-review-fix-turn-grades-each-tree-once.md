---
topic: a-review-fix-turn-grades-each-tree-once
author: claude-opus-5-5
created_at: 2026-11-08T16:26:36Z
---

## Proposal: A review_fix turn grades each tree once, and an open Red settled passed re-enters its stage for the Green

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend contracts.md "A fix turn grades each tree once, through its commit hook" from fix turns to fix and review_fix turns. State that when fix_commit_settle or review_fix_commit_settle settles an OPEN RED (TDD-Red trailers, no TDD-Green) as the turn's last commit, the run re-enters that same stage for its Green amend instead of routing to janitor_admission, and that at the stage's visit limit it ends at needs_human naming the open Red. Scenario 199 (heading unchanged) gains review_fix and open-Red routing cases.

### Motivation

legacy-coordinator-agent's rule K on bd-ib-7fdesc (2026-11-08), drafted by the plan seat publish-draft-green-work-loss on the coordinator's direction. sandbox-commit-gate-ceiling, the seat owning this paragraph, was restarting.

Measured defect, fix half: bd-ib-d2qm5d run 01M6XF3D578KTHHEJJWA106EZ8 on petri, build 0.305.0.
- fix@4 to @6 each ended with a Red-only commit. fix@5's own words, present in the run record: "no implementation changes were made while Red is in flight. fix_commit_settle must settle it before the Green implementation amendment".
- fix_commit_settle settled each commit passed, because the hook accepts a correctly failing Red, and the graph routed to janitor every time. Janitor visits 2 to 5 failed on the open Red. The run was preserved at 73e8f5b8 and cancelled.
- The cause is in the graph on master: workflow.fabro:2387 `fix_commit_settle -> janitor_admission` is unconditional.
- That half is ratified by this paragraph's Red-fast-path sentence and is carried by bd-ib-7fdesc.

Unratified, review_fix half: workflow.fabro:2525-2526 `review_fix -> review_fix_commit_settle -> janitor_admission` is the same unconditional shape, and it runs the same settle program, so a review_fix turn can hit the identical loop. It has not been measured yet. The paragraph today states "This paragraph governs only a `fix` turn", and no other clause sets a review_fix end-of-turn obligation. "A commit leg completes past one tool call" covers both stages' commit runners but sets no open-Red rule. A review_fix turn commits through the same Red-Green protocol and routes to the same janitor, so the same obligation and the same routing belong to it.

Why the routing is stated explicitly: the paragraph puts the obligation on the TURN, while the observed loss is a ROUTING decision of the commit-settle node. Naming the open-Red route and its visit-limit ending makes both stages' behaviour gradeable by the same scenario.

In-flight alignment: aligns with open PR #4679 (v324, a-dispatched-pull-request-whose), which touches only the merge-poll text. The spec/* branches that mention this paragraph (revise-v319-fix-turn-gate-and-janitor-merge, revise-a-publish-draft-push-the) have already landed as v319 and v323. No pending proposal touches this paragraph or Scenario 199. bd-ib-vy75ws leaves both settle paths unchanged, per the coordinator.

Fleet scope: fix and review_fix are nodes of the plugin's bundled implement-work-item workflow, so this amendment governs every repository dispatched through it. Forked workflow copies converge by their own re-sync.

### Proposed Changes

In `contracts.md` §"Self-contained plugin dispatch", in the paragraph headed **A fix turn grades each tree once, through its commit hook.**, make four edits. The paragraph's bold label and its H2 section are unchanged, so no heading changes.

1. The sentence "This paragraph governs only a `fix` turn that completes successfully and routes to `janitor`, whether it was a fix round or a refresh-repair round." MUST become:

"This paragraph governs a `fix` turn or a `review_fix` turn that completes successfully and routes to `janitor`, whether the `fix` turn was a fix round or a refresh-repair round."

2. The sentence "A `fix` turn that ends through the needs-human protocol, by its node's resolved timeout, or by any other failure keeps its existing handling, which this paragraph does not change." MUST become:

"A `fix` or `review_fix` turn that ends through the needs-human protocol, by its node's resolved timeout, or by any other failure keeps its existing handling, which this paragraph does not change."

3. "A successful `fix` turn MUST leave the run's working branch at a head whose last commit in that turn passed the gate ..." MUST read "A successful `fix` or `review_fix` turn MUST leave ...". "The `fix` prompt MUST NOT direct a run of the full check suite beyond what its commit hook runs, because the `janitor` visit that follows a successful `fix` turn runs the full check aggregate on the run's tree." MUST read "The `fix` and `review_fix` prompts MUST NOT direct ..., because the `janitor` visit that follows a successful `fix` or `review_fix` turn runs ...". Every other sentence of the paragraph is unchanged.

4. Directly after the sentence "A change to the tree after the last passing hook run MUST be committed through the commit hook again before a successful turn ends.", add:

"A turn whose last commit is an OPEN RED, a commit carrying the Red-Green commit protocol's `TDD-Red-*` trailers and no `TDD-Green-*` trailers, has not met this obligation, even when its commit-settle node settles that commit `passed`, because the commit hook accepts a correctly failing Red. When `fix_commit_settle` or `review_fix_commit_settle` settles an open Red as the turn's last commit, the run MUST re-enter that same stage, `fix` or `review_fix`, instead of routing to `janitor_admission`. The re-entered turn's brief MUST name the open Red commit and MUST direct the turn to complete that commit's Green amend rather than author a new Red commit. A last commit that carries both trailer sets, or no TDD trailers, routes to `janitor_admission` as before. When the stage's visit limit is reached while its last commit is still an open Red, the run MUST end at `needs_human` with a cause naming the open Red commit."

In `scenarios.md`, in `## Scenario 199 — A fix turn grades each tree once, through its commit hook` (heading unchanged), make two edits.

5. In the case "A hook run that did not grade the tree, or a later change, still requires a passing commit", change its first step to "Given a fix or review_fix turn whose only commit took the hook's Red fast path, or whose tree changed after its last passing hook run".

6. Add these cases at the end of the scenario's gherkin block:

```gherkin
  Scenario: A review_fix turn whose hook passed ends its grading obligation for that tree
    Given a review_fix turn that commits its change
    And the commit hook's gate passed on the committed tree
    When the review_fix turn completes successfully on that tree
    Then the review_fix prompt directs no run of the full check suite on that tree in the same turn

  Scenario: An open Red settled passed re-enters its stage for the Green
    Given a fix or review_fix turn whose last commit carries TDD-Red trailers and no TDD-Green trailers
    And its commit-settle node settles that commit passed
    When the run leaves the commit-settle node
    Then the run re-enters that same stage instead of janitor_admission
    And the re-entered turn's brief names the open Red commit and directs completing its Green amend

  Scenario: A completed Red-Green commit or an untrailered commit routes to janitor
    Given a fix or review_fix turn whose last commit carries both TDD-Red and TDD-Green trailers, or no TDD trailers
    And its commit-settle node settles that commit passed
    When the run leaves the commit-settle node
    Then the run routes to janitor_admission

  Scenario: An open Red at the stage's visit limit ends at needs_human naming it
    Given a fix or review_fix stage whose visit limit is reached
    And the stage's last commit is still an open Red
    When the run leaves the stage
    Then the run ends at needs_human with a cause naming the open Red commit
```

Scenario 199's heading is unchanged, so `tests/heading-coverage.json` needs no heading edit. The revise that accepts this proposal SHOULD leave Scenario 199's existing coverage row's test reference in place only where that test still exercises the amended cases, and otherwise mark it `TODO` with a reason naming the implementing work items: bd-ib-7fdesc for the fix half, and the review_fix item filed after ratification.
