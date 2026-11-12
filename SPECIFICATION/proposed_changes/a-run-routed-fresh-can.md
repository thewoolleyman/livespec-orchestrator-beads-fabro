---
topic: a-run-routed-fresh-can
author: claude-opus-5-5:factory-run-work-preservation
created_at: 2026-11-12T14:39:27Z
---

## Proposal: A run routed fresh keeps its start commit in every commit it settles and publishes

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

No clause stops a run routed fresh from replacing its own branch history with one that no longer contains the commit it was dispatched from. Measured on bd-ib-22j24v: an implement agent followed an outdated rider and ran `git reset --hard` onto a 2026-11-08 seed, 383 commits behind master. The run spent 76 minutes, then failed a gate for a file master had added after that seed, and nothing named the real cause: the run had left its route. This proposal adds one paragraph to §"Dispatcher admission, WIP cap, and post-merge acceptance". For a run routed fresh, every commit an agent-stage commit-settle step settles, and the tip publish_draft would publish, MUST have the run's start commit as an ancestor. The start commit is the base commit the dispatch checked out, or the tip of the latest refresh. Otherwise the step fails, naming both commits, and publish_draft publishes nothing. Five scenarios in Scenario 185 exercise it, including the named refusal when the latest refresh tip cannot be determined. Seeded and resume routes are out of scope; bd-ib-azhnw5 is the seeded counterpart.

### Motivation

Owning work item bd-ib-dvv2ge, "A run routed fresh can have its branch history replaced inside the sandbox by a rider's git reset --hard onto an old seed ref, and nothing refuses work that no longer descends from the dispatched source head", a child of plan factory-run-work-preservation (epic bd-ib-nckst7). Its spec-change-tier judgement (2026-11-11T21:13Z, spec v354) holds it at tier spec-change, verdict unstated, linked topic a-run-routed-fresh-can. The ratified text states the recovery route but not that a fresh run must stay on it. No proposal for the topic existed on any branch or pull request when this seat authored this one.

Measured 2026-11-11 on bd-ib-22j24v run 01M75X4ESAGVMA87KR3WZBKFQB (petri, orchestrator v0.319.0 canary sample A). The host routed it fresh: the recovery-route record had preservation_ref null and source origin/master bbd3392ea, and start.base_sha was bbd3392ea. In implement@1 the agent followed two retired seed-rider comments and ran git reset --hard onto f141cc59a and later 9ea0774d2. The branch then sat on base 9f88daaaf, 383 commits behind master. The run ended at implement_hook_route@2 with LIVESPEC_IMPLEMENT_HOOK_REFUSED_BUDGET_EXHAUSTED, because check-doctor-static failed on .github/workflows/disarm-on-hold-label.yml, which master added after that base. The fault surfaced 76 minutes in, as an unrelated-looking gate failure.

Why a hard refusal is safe: a ruled seed has its own carrier (dispatcher.py seed-ruling), which routes the run seeded. So a fresh-routed history that omits its start commit is never legitimate. A refresh that rebuilds onto a newer default-branch head is the one sanctioned way a fresh run's base moves, and the start commit follows it.

In-flight survey (2026-11-12 about 13:45Z): remote spec/* branches and the open spec-touching pull requests #5050, #5048, #5035 and #5005 do not touch preserving steps' ancestry or publish_draft's tip. #5035 (a-commit-settle-node-whose) makes an unresolved settle operation fail the stage; this proposal adds a different failure cause on the same steps, and the two align. Pending in-tree a-commit-settle-abort-preserves-the-in-progress-resolution inserts a paragraph after the same preserving-step paragraph; this proposal anchors before the following paragraph, so the two compose in either revise order. This seat's own an-operator-preserve-writes-a, staged but not yet pushed, adds scenarios elsewhere in Scenario 185; these are appended at the block's end, so they do not collide.

### Proposed Changes

1. contracts.md, §"Dispatcher admission, WIP cap, and post-merge acceptance": insert this paragraph IMMEDIATELY BEFORE the paragraph that begins "**A run's ending names its latest preserved capture on the item.**", separated from its neighbours by one blank line. When the pending proposal a-commit-settle-abort-preserves-the-in-progress-resolution has been revised first, this paragraph therefore follows the paragraph it inserted after "**Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref.**"; otherwise it follows that paragraph directly. Either order is intended:

"**A run routed fresh keeps its start commit in every commit it settles and publishes.** This paragraph governs a run whose recovery route is `fresh`, including every run of an item that is not released for recovery. That run's *start commit* is the run's base commit — the default-branch commit its dispatch checked out, which the dispatch record names — until a refresh step of the run rebuilds the run branch onto a newer head of the default branch; from then on it is the run branch's tip that the latest such refresh produced. At its end, each preserving step of the paragraph "Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref" that settles an agent stage's commits (`implement_commit_settle`, `fix_commit_settle` and `review_fix_commit_settle`) MUST read whether the run's start commit is an ancestor of the commit it settled, where a commit is its own ancestor. When it is not, or when that ancestry cannot be read, the step MUST settle the stage as failed with a recorded cause that names the start commit and the settled commit, and the run MUST NOT route onward as though the stage had settled. Before it pushes or opens a pull request, `publish_draft` MUST make the same read against the run branch's tip. When the start commit is not an ancestor of that tip, or that ancestry cannot be read, `publish_draft` MUST push nothing, MUST NOT open or update a pull request, and MUST fail with a cause that names the start commit and the tip. When a refresh step of the run has rebuilt the run branch but the tip that the latest such refresh produced cannot be determined, the run has no readable start commit: the commit-settle step MUST settle the stage as failed, and `publish_draft` MUST push nothing and fail, each with a recorded cause `LIVESPEC_FRESH_START_COMMIT_UNAVAILABLE` naming the refresh step whose tip is missing. Neither step MAY fall back to the base commit or pass. A run routed fresh has no legitimate reason to carry a history that omits its start commit, because a tree that must start elsewhere is carried by a seed ruling and routed `seeded`; such a history MUST therefore be treated as the run having left its route, never as work to publish. A run refused under this paragraph has still done work. So before a step fails under this paragraph, it MUST preserve the commit it read — the settled commit, or for `publish_draft` the run branch's tip — to the run's needs-human ref, under the write rule of the paragraph "A writer that finds a run's needs-human ref behind the tree it preserves moves that ref forward rather than writing a second one" (proposed as an-operator-preserve-writes-a), in addition to the preservation its own paragraph requires. Its recorded cause MUST then name the needs-human ref that holds that commit. When that preservation fails, the cause MUST say so, naming the failed write, and the step MUST still fail. This paragraph does not govern a run routed `seeded` or `resume`."

No other paragraph changes.

2. scenarios.md, §"Scenario 185 — A released item's recovery route is decided before admission and executed per item, and a deferred item keeps its branch": inside that section's gherkin block, append these five scenarios at its END, IMMEDIATELY AFTER `Scenario: One needs-human identification serves every item of a routing pass` (whose last step is "Then the needs-human refs and their tip commit messages are listed once for the pass") and BEFORE the block's closing fence, separated from that scenario by one blank line:

```gherkin
  Scenario: A commit-settle step of a run routed fresh fails when the settled commit has left the run's start commit
    Given a run routed fresh whose base commit is B, with no refresh yet
    And its implement stage replaced the run branch's history, so the settled commit C does not have B as an ancestor
    When implement_commit_settle settles C
    Then the stage is settled as failed with a cause that names B and C
    And before it fails, the step preserves C to the run's needs-human ref, and the cause names that ref
    And the run does not route onward as though implement had settled

  Scenario: A commit-settle step of a run routed fresh passes a settled commit that descends from its start commit
    Given a run routed fresh whose base commit is B, with no refresh yet
    And the settled commit C has B as an ancestor
    When fix_commit_settle settles C
    Then the step passes

  Scenario: After a refresh, a run routed fresh is checked against the refreshed tip
    Given a run routed fresh whose refresh step rebuilt the run branch onto a newer default-branch head, producing tip R
    And a later settled commit C has R as an ancestor
    When review_fix_commit_settle settles C
    Then the step passes

  Scenario: publish_draft refuses a run routed fresh whose branch tip has left its start commit
    Given a run routed fresh whose start commit is B
    And the run branch tip T does not have B as an ancestor
    When publish_draft runs
    Then it pushes nothing and opens or updates no pull request
    And it fails with a cause that names B and T

  Scenario: A run routed fresh whose latest refresh tip cannot be determined is refused by name
    Given a run routed fresh whose refresh step rebuilt the run branch
    And the tip that refresh produced cannot be determined
    When fix_commit_settle settles a commit C
    Then the stage is settled as failed with the cause LIVESPEC_FRESH_START_COMMIT_UNAVAILABLE naming that refresh step
    And the step does not compare C against the run's base commit instead
```

No H2 heading is added, removed or renamed, so `tests/heading-coverage.json` needs no co-edit.
