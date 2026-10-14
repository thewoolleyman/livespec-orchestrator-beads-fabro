---
topic: publish-refresh-repair
author: claude-opus-5-5-plan-publish-draft-green-work-loss
created_at: 2026-10-14T00:37:29Z
---

## Proposal: Repair a green run's refresh conflict or post-refresh gate failure inside the run instead of failing closed to needs-human

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A janitor-green run whose publish_draft or pr_refresh refresh onto a moved default branch conflicts, or whose refreshed head fails the repository gate, aborts the refresh with its green head intact and routes to the existing fix agent node with a refresh-repair brief, then re-enters janitor, publish_draft and proof_capture. At most two such rounds per run; a third fails closed to needs_human with the cause refresh-repair-exhausted. Unreachable-origin, foreign-head and authentication failures keep their existing fail-closed behaviour.

### Motivation

On hp on 2026-10-13, 11 factory runs passed janitor and then ended at needs_human after publish_draft failed, 44.0 slot-hours of finished work (plan publish-draft-green-work-loss, epic bd-ib-acrr56, research note 001, which classifies every run from its fabro inspect publish_draft output). Seven of the 11 (30.0 hours) were rebase conflicts against an origin/master that moved during the run, and one more (3.3 hours, bd-ib-l55d7e run 01M4T2KEGPQPAR1XS1KEK91P0E) rebased cleanly and then failed check-coverage in the pre-push gate. The ratified clause makes a conflicted rebase fail closed, and no agent stage is given the conflict, so the only remedy is a plain re-dispatch that repeats the whole implement turn against the same moving master; the exposure grows with implement duration and merge rate. Work-item bd-ib-tzj9x carries this filing. Alternatives considered: rebasing at the end of implement before janitor narrows the window but does not close it, because master keeps moving through janitor's ten minutes and the pre-push suite; seeding a re-dispatch from the failed run's preserved commit (the existing 'Recovery from the failed run's preserved work' clause) still discards the run's proof and repeats janitor and review, and depends on preservation that bd-ib-zddbkq shows can fail. Reusing the fix node rather than adding a new ACP node keeps the success-critical node set, the node-timeout table and the adapter tables unchanged. The fixed budget of two rounds bounds cost without a new configuration key; the fail-closed posture is kept for every cause an agent cannot repair.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Self-contained plugin dispatch":

(1) In the paragraph beginning "**The stages.**", replace the clause "it MUST be idempotent across janitor re-entries and MUST fail closed to `needs_human` when origin cannot be reached." with: "it MUST be idempotent across janitor re-entries and MUST fail closed to `needs_human` when origin cannot be reached; a refresh that conflicts, or a refreshed head that the repository's gate rejects, MUST instead take the refresh-repair route of \"Refresh repair\" below while that route's budget lasts."

(2) In the paragraph beginning "**Scripted publication and proof-head integrity.**", replace the sentence "A missing or unobservable remote, a foreign or unexpectedly changed publish head, or a conflicted rebase MUST fail closed with a named cause and recovery artifact pointer." with: "A missing or unobservable remote, or a foreign or unexpectedly changed publish head, MUST fail closed with a named cause and recovery artifact pointer. A conflicted rebase or merge, and a refreshed head that the repository-declared gate rejects, MUST take the refresh-repair route of \"Refresh repair\" below while its budget lasts, and MUST fail closed with a named cause and recovery artifact pointer once that budget is spent."

(3) Insert a new paragraph immediately after the paragraph that ends "An unchanged head proceeds to `pr`. All touched nodes MUST retain an unconditional outgoing edge accepted by the supported engine, and command nonzero exits MUST take their failure edge.":

"**Refresh repair.** When `publish_draft` or `pr_refresh` cannot refresh the run onto the advanced default branch — because the rebase or merge conflicts, or because the refreshed head fails the repository-declared gate that runs before or during the publishing push — the stage MUST abort any in-progress git operation so that the run's last janitor-green head is restored intact, MUST record a refresh-repair brief, and MUST route to the existing `fix` agent node. The brief MUST name the stage, the default-branch commit the refresh targeted, the run's base before the refresh, and either each conflicted path together with the run commit that was being applied, or each failed gate target. The stage MUST distinguish a refreshed head that the gate rejected from a push that origin refused or could not reach, and from an authentication failure; only a conflict or a gate rejection takes this route, and every other cause keeps its existing fail-closed behaviour. The `fix` turn integrates the default branch into the run's work, resolving the conflict or the gate failure inside its own turn. Hooks MUST run normally there, and the turn MUST NOT use `--no-verify`, bare force, or a rewrite of any ref other than the run's own publish branch under an explicit lease. After a refresh-repair round the run re-enters `janitor`, then `publish_draft`, then `proof_capture`, exactly as an accepted fix round does, so only proof for the repaired head can reach publication. A run MAY take at most two refresh-repair rounds; a refresh-repair round does not consume `dispatcher.review_fix_cap`, and repaired refreshes count toward `pr_refresh`'s three-refresh non-convergence bound. When a third refresh would need repair, the stage MUST fail closed to `needs_human` with the named cause `refresh-repair-exhausted` and a recovery artifact pointer naming the run's last janitor-green head. A refresh that applies cleanly and passes the gate is unchanged by this paragraph. Scenario 175 in `scenarios.md` exercises this paragraph."

In SPECIFICATION/scenarios.md, append a new scenario after the highest-numbered existing scenario:

## Scenario 175 — A green run whose refresh conflicts with a moved default branch is repaired and published instead of ending at needs-human

```gherkin
Feature: A janitor-green run survives a default branch that moved under it
  As the maintainer of a repository dispatched to the factory
  I want a refresh conflict or a post-refresh gate failure repaired inside the run
  So that hours of finished, green work are not discarded at publication

  Scenario: A conflicted publish_draft refresh routes to a repair turn
    Given a run whose janitor stage succeeded
    And origin's default branch has advanced with a commit that conflicts with the run's work
    When publish_draft refreshes the run onto the default branch
    Then publish_draft aborts the rebase and the run's janitor-green head is restored
    And a refresh-repair brief names the conflicted paths and the run commit being applied
    And the run enters the fix node rather than needs_human
    And after the fix turn the run re-enters janitor, then publish_draft, then proof_capture

  Scenario: A refreshed head that fails the gate routes to a repair turn
    Given a run whose janitor stage succeeded
    And the refresh onto the advanced default branch applies without conflict
    And the repository-declared gate rejects the refreshed head
    When publish_draft publishes
    Then the run enters the fix node with a brief naming each failed gate target
    And the run does not end at needs_human

  Scenario: The repair budget is bounded
    Given a run that has already taken two refresh-repair rounds
    When its next refresh conflicts again
    Then the stage fails closed to needs_human with the cause refresh-repair-exhausted
    And the recovery artifact pointer names the run's last janitor-green head

  Scenario: A push origin refuses is not repaired
    Given a run whose refresh applied cleanly and whose gate passed
    When origin refuses the push with an authentication failure
    Then publish_draft fails closed with its existing push-failure cause
    And the run does not enter the fix node
```

The revise pass MUST add a `tests/heading-coverage.json` entry for the new Scenario 175 heading (test "TODO" with a reason naming the carrying work-item) in the same change.
