---
topic: a-dispatch-routed-seeded-from
author: claude-opus-5-5:factory-run-work-preservation
created_at: 2026-11-14T16:09:25Z
---

## Proposal: A run routed seeded keeps its seed in every commit it settles and publishes, and stops before implement when its sandbox lacks the seed

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The ratified text requires a run routed fresh to keep its start commit in every commit it settles and publishes, and it states that this rule does not govern a run routed seeded. Nothing states the seeded counterpart, so a seeded run can start its sandbox from a tree that lacks the seed, or settle and publish a history that dropped the preserved work, and nothing refuses it. This proposal adds one paragraph to contracts.md section "Dispatcher admission, WIP cap, and post-merge acceptance", directly after the fresh-run paragraph. Before the implement node, the run MUST check that the seed commit is an ancestor of the sandbox HEAD and stop by name when it is not. At each commit-settle step and at publish_draft, the settled commit or branch tip MUST descend from the seed commit, the tip of the run's latest refresh, or the commit last passed on carried content. A settled commit that left that lineage but still carries every line the seed added and none it removed passes on carried content, with a ledger comment naming the broken lineage, and becomes an accepted ancestor for later steps. For a seed taken from a preserved-publish ref that was not re-seeded, the seed commit is a default-branch commit, so it is not an accepted ancestor and the content test decides until a commit passes on carried content. Lines are compared by count, an unreadable ancestry or content test fails closed under its own cause, and a refresh advances the accepted ancestor only when the rebuilt branch descended from one. Scenario 185 gains twelve cases. No heading is added, removed or renamed.

### Motivation

Owning work item bd-ib-azhnw5, "A dispatch routed seeded from a preservation ref can start its sandbox from a tree that lacks the seed, and nothing refuses it before implement", a child of plan factory-run-work-preservation (epic bd-ib-nckst7) that carries the plan assertion "a re-dispatch starts from the earlier run's preserved tree". On 2026-11-14T16:02Z its dispatch was refused at the spec-change tier (livespec-spec-change-tier record: verdict-kind partial, generalization-target "## Factory-configurable ACP fallback priority", linked-proposal-topic a-dispatch-routed-seeded-from, spec-version 376). The judge's rationale is accurate. The ratified text states that a seeded run checks out the recorded seed commit and carries the preserved work through the commit gates. It states the commit-settle and publish_draft start-commit ancestry checks only for runs routed fresh ("This paragraph does not govern a run routed seeded or resume"). Nothing states the seeded-run behaviour: refusing before implement when the sandbox head lacks the seed, the seed-ancestry check at each commit-settle step and at publish_draft, the reference advancing on refresh, or the carried-content fallback with its ledger comment. This proposal ratifies exactly that behaviour, as the item's Definition of Done states it, so the tier record can read none and the held item can be dispatched. The plan seat owns the hold and chose to ratify rather than ask for a tier release, because a release would dispatch behaviour the spec does not require.

Design choices:
- The paragraph mirrors the fresh-run paragraph's shape, cause discipline and fail-closed reads, so a reader finds the two routes stated side by side.
- The seed commit is the commit the seeded route starts from, the same commit "A stale seed is re-seeded by diff-applying its work onto the default branch's tip" names. After such a reseed it is the reseed commit. For a seed taken from a refs/livespec/preserved-publish/ ref that was not re-seeded, whose hookless commit is never carried, it is the seed record's immutable commit SHA, the failed run's base commit, and the seed's changes are those that ref's commit makes to it. That base commit is on the default branch, so ANY history built on the default branch contains it: an agent that resets to origin/master would pass a pure ancestry test while dropping the preserved tree. Such a seed commit is therefore not an accepted ancestor, and the carried-content test decides each commit-settle step until a settled commit passes on carried content, which then anchors publish_draft (legacy-coordinator-agent's grade of #5298, blocking finding 1).
- Carried content is compared by line COUNT, not presence: a removed line such as a blank line, a closing brace or `return None` routinely also occurs elsewhere in the file, so a presence test would fail a commit that carries the seed exactly.
- An ancestry or content test that cannot be read is not a lost lineage. It fails closed under its own cause, LIVESPEC_SEED_LINEAGE_UNREADABLE, mirroring the fresh route's LIVESPEC_FRESH_START_COMMIT_UNAVAILABLE.
- A refresh advances the accepted ancestor only when the branch it rebuilt descended from an accepted ancestor, so a refresh cannot launder a branch that had already lost the seed.
- The carried-content fallback exists because a legitimate refresh or conflict resolution can rebuild history without the seed commit while keeping its content. Refusing that would lose the preserved work this plan exists to keep. The fallback is recorded on the item rather than passed silently.
- Preserving the refused commit to the needs-human ref before the failure, which the fresh paragraph requires, is NOT added here. The item's Definition of Done does not ask for it, and the refusing step's own work-in-progress capture, required by "Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref", still runs before the failure, so the refused commit stays fetchable. It is deferred to a follow-up if a seeded refusal is measured to lose a tree.

In-flight survey (2026-11-14 about 16:05Z): open spec PRs #5292 (revise v377, adds an unrelated commit-refusal re-entry paragraph; aligned), #5291, #5281, #5257, #5180, #5120, #5061 and #5048 (unrelated sections), and #5083 (recovery-routing-reads-a-rework, held do-not-merge; it touches recovery routing's rework read, not commit-settle or publish_draft; aligned). In-tree pending proposal a-plain-re-dispatch-of names a seed commit for a re-dispatch and is compatible (aligned). No in-flight item edits the fresh-run paragraph or Scenario 185's fresh-run cases.

### Proposed Changes

1. contracts.md, section "Dispatcher admission, WIP cap, and post-merge acceptance": IMMEDIATELY AFTER the paragraph that begins "**A run routed fresh keeps its start commit in every commit it settles and publishes.**" and ends "This paragraph does not govern a run routed `seeded` or `resume`.", insert this paragraph, separated from its neighbours by one blank line:

"**A run routed seeded keeps its seed in every commit it settles and publishes.** This paragraph governs a run whose recovery route is `seeded`. That run's *seed commit* is the commit its seeded route starts from: the seed that §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work" or a ruled seed selects, or, after the paragraph "A stale seed is re-seeded by diff-applying its work onto the default branch's tip" re-seeds it, the reseed commit. For a seed taken from a `refs/livespec/preserved-publish/` ref that was not re-seeded, whose hookless commit is never carried, the seed commit is the seed record's immutable commit SHA, the failed run's base commit. The *seed's version* of a file is that file in the seed commit, or, for a preserved-publish seed that was not re-seeded, that file in the preserved-publish ref's commit. The *seed's changes* are the lines added and removed, file by file with the top-level `.fabro` directory excluded, between the seed commit's merge base with the default branch and the seed's version, or, for a preserved-publish seed that was not re-seeded, between the base commit and the seed's version. A commit *carries the seed's content* when, in every file the seed changes, every line the seed added occurs at least as many times as in the seed's version of that file, and every line the seed removed occurs no more times than in the seed's version of that file. The run's *accepted ancestors* are: the seed commit, except for a preserved-publish seed that was not re-seeded, whose seed commit is a default-branch commit that any history built on the default branch contains; once a refresh step rebuilds onto a newer head of the default branch a run branch whose tip had an accepted ancestor as an ancestor, the tip that the latest such refresh produced; and once a commit-settle step passes a settled commit on carried content as below, the most recent such settled commit. The run's *expected commit* is its most recent accepted ancestor, or the seed commit while it has none. A commit is its own ancestor. Before the implement node starts, the run's preparation MUST read whether the seed commit is an ancestor of the sandbox's checked-out `HEAD` and, for a preserved-publish seed that was not re-seeded, whether the working tree carries the seed's content. When either does not hold, the run MUST stop before the implement node with a recorded cause `LIVESPEC_SEED_ABSENT_AT_START` that names the seed commit and the checked-out head, and MUST run no agent node. At its end, each commit-settle step that settles an agent stage's commits (`implement_commit_settle`, `fix_commit_settle` and `review_fix_commit_settle`) MUST read whether any accepted ancestor is an ancestor of the commit it settled. When one is, the step passes. When none is, the step MUST pass only when the settled commit carries the seed's content; for a preserved-publish seed that was not re-seeded, this content test therefore decides every commit-settle step until a settled commit passes on carried content. Such a pass MUST add one ledger comment to the item that opens with the marker line `livespec-seed-lineage-broken` and names the seed commit and the settled commit and states that the seed's content is carried; the comment MUST obey the template-opener and failure rules the checkpoint-failed paragraph states for its own comment, and writing it MUST NOT change the step's outcome. Otherwise the step MUST settle the stage as failed with a recorded cause `LIVESPEC_SEED_LINEAGE_LOST` that names the expected commit, the settled commit, and the first seed change, in path order and then line order, that the settled commit lacks, and the run MUST NOT route onward as though the stage had settled. Before it pushes or opens a pull request, and before any rebase it performs, `publish_draft` MUST read whether any accepted ancestor is an ancestor of the run branch's tip. When none is, `publish_draft` MUST push nothing, MUST NOT open or update a pull request, and MUST fail with a recorded cause `LIVESPEC_SEED_LINEAGE_LOST` that names the expected commit and the tip; for a preserved-publish seed that was not re-seeded, `publish_draft` therefore fails unless a commit passed on carried content is an ancestor of the tip. When an ancestry or a content test that the preparation, a commit-settle step or `publish_draft` needs cannot be read, or a refresh step has rebuilt the run branch but the tip it produced cannot be determined, the preparation MUST stop the run before the implement node, the commit-settle step MUST settle the stage as failed, and `publish_draft` MUST push nothing and fail, each with a recorded cause `LIVESPEC_SEED_LINEAGE_UNREADABLE` naming what could not be read; none of them MAY pass on a weaker comparison. Scenario 185 in `scenarios.md` exercises this paragraph."

The fresh-run paragraph is NOT edited by this proposal. Its closing sentence, "This paragraph does not govern a run routed `seeded` or `resume`.", stays as it is, and the new paragraph covers the `seeded` route.

2. scenarios.md, section "Scenario 185 — A released item's recovery route is decided before admission and executed per item, and a deferred item keeps its branch": inside that section's gherkin block, IMMEDIATELY AFTER the scenario `A run routed fresh whose latest refresh tip cannot be determined is refused by name`, whose last step is "And the step does not compare C against the run's base commit instead", and BEFORE the closing fence, insert these twelve scenarios, each preceded by one blank line. The section carries no governing-clause line, so none is edited.

```gherkin
  Scenario: A run routed seeded starts from a sandbox that carries its seed
    Given a run routed seeded whose seed commit is S
    When its preparation leaves the sandbox for the first agent node
    Then S is an ancestor of the sandbox's checked-out HEAD

  Scenario: A run routed seeded stops before implement when its sandbox lacks the seed
    Given a run routed seeded whose seed commit is S
    And the sandbox's checked-out HEAD H does not have S as an ancestor
    When the run reaches the implement node
    Then it stops before the implement node with the cause LIVESPEC_SEED_ABSENT_AT_START naming S and H
    And no agent node runs

  Scenario: A commit-settle step of a run routed seeded passes a settled commit that descends from its seed
    Given a run routed seeded whose seed commit is S, with no refresh yet
    And the settled commit C has S as an ancestor
    When implement_commit_settle settles C
    Then the step passes

  Scenario: A commit-settle step of a run routed seeded fails when the settled commit has lost the seed
    Given a run routed seeded whose seed commit is S, with no refresh yet
    And the settled commit C has no accepted ancestor as an ancestor
    And C lacks a line S added
    When fix_commit_settle settles C
    Then the stage is settled as failed with the cause LIVESPEC_SEED_LINEAGE_LOST naming the expected commit S, C, and the first seed change, in path order and then line order, that C lacks
    And the run does not route onward as though fix had settled

  Scenario: A settled commit that left the seed's history but carries its content passes and is recorded
    Given a run routed seeded whose seed commit is S, with no refresh yet
    And the settled commit C does not have S as an ancestor but carries every line S added and none it removed
    When implement_commit_settle settles C
    Then the step passes
    And the item carries a livespec-seed-lineage-broken comment naming S and C and stating that the seed's content is carried
    And a later commit-settle step passes a settled commit that has C as an ancestor

  Scenario: After a refresh, a run routed seeded is checked against the refreshed tip
    Given a run routed seeded whose seed commit is S
    And its refresh step rebuilt the run branch, whose tip had S as an ancestor, onto a newer default-branch head, producing tip R that does not have S as an ancestor
    And a later settled commit C has R as an ancestor
    When review_fix_commit_settle settles C
    Then the step passes

  Scenario: publish_draft refuses a run routed seeded whose branch tip has lost every accepted ancestor
    Given a run routed seeded whose accepted ancestors are its seed commit S, its latest refresh tip R and its last carried-content commit K
    And the run branch tip T, before any rebase publish_draft performs, has none of S, R or K as an ancestor
    When publish_draft runs
    Then it pushes nothing and opens or updates no pull request
    And it fails with the cause LIVESPEC_SEED_LINEAGE_LOST naming the expected commit and T

  Scenario: A settled commit that keeps more copies of a line the seed removed fails
    Given a run routed seeded whose seed commit is S, with no refresh yet
    And the settled commit C has no accepted ancestor as an ancestor
    And a line S removed from file F occurs more times in C's F than in S's F
    When implement_commit_settle settles C
    Then the stage is settled as failed with the cause LIVESPEC_SEED_LINEAGE_LOST naming S, C and that removed line of F as the first seed change C lacks

  Scenario: A preserved-publish seed stops a run whose sandbox lacks the published tree
    Given a run routed seeded from a preserved-publish ref P that was not re-seeded, whose seed commit is the failed run's base commit B
    And the sandbox's checked-out HEAD has B as an ancestor
    But the working tree does not carry the seed's content that P's commit adds to B
    When the run reaches the implement node
    Then it stops before the implement node with the cause LIVESPEC_SEED_ABSENT_AT_START naming B and the checked-out head
    And no agent node runs

  Scenario: A preserved-publish seed's base commit does not pass a commit built on the default branch
    Given a run routed seeded from a preserved-publish ref P that was not re-seeded, whose seed commit is the default-branch commit B
    And the settled commit C was built on the default branch, so it has B as an ancestor, but does not carry the seed's content
    When implement_commit_settle settles C
    Then the stage is settled as failed with the cause LIVESPEC_SEED_LINEAGE_LOST naming B, C and the first seed change C lacks
    And when a later settled commit K carries the seed's content, the step passes and the item carries a livespec-seed-lineage-broken comment naming B and K

  Scenario: publish_draft refuses a preserved-publish seed's run until a carried-content commit anchors its tip
    Given a run routed seeded from a preserved-publish ref P that was not re-seeded, whose seed commit is the default-branch commit B
    And no settled commit of the run has passed on carried content
    And the run branch tip T has B as an ancestor
    When publish_draft runs
    Then it pushes nothing and opens or updates no pull request
    And it fails with the cause LIVESPEC_SEED_LINEAGE_LOST naming B and T

  Scenario: A run routed seeded whose ancestry cannot be read is refused by name
    Given a run routed seeded whose seed commit is S
    And whether any accepted ancestor is an ancestor of the settled commit C cannot be read
    When fix_commit_settle settles C
    Then the stage is settled as failed with the cause LIVESPEC_SEED_LINEAGE_UNREADABLE naming what could not be read
    And the step does not pass C on a weaker comparison
```

No `## ` heading is added, removed or renamed, so `tests/heading-coverage.json` needs no co-edit.
