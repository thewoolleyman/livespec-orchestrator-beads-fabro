---
topic: a-needs-human-ref-carrying-no-change-is-not-preserved-work
author: claude-opus-5-5:publish-draft-green-work-loss
created_at: 2026-11-09T06:22:14Z
---

## Proposal: A needs-human ref that carries no work is not preserved work

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Recovery routing MUST treat a needs-human ref whose tip tree is identical to the tree of the tip's merge base with the default branch as carrying no work. Such a ref is never a seed and outranks nothing, including under the run-age bound, and the recovery-route record lists it in passed_over_needs_human with the reason no-change. This is the read-side complement of the existing write-side tree guard on preserving steps. Without it, a failed fresh relaunch, which always writes the newest and latest-run needs-human ref, displaces the real preserved work it failed to rebuild.

### Motivation

A needs-human ref can carry no work. It still outranks real preserved work.

Measured instance: bd-ib-so6fef, 2026-11-09.
- Run 01M6ZEQGVZDB29PWFTXFA9HQ2Q was routed FRESH, because a transient_infra FAILED ending is not released. It started from master.
- Its implement turn correctly declined, so nothing was built.
- The ending published needs-human/91744d6ff51541fdb50e5e4f0cb6ff77 at 4521d441, which carries no file changes against master.
- The item's real work sits elsewhere: preserve/run-01M6YVGGFC9KD99G70919PXFNW, and the preserved-publish ref, at 2861c50e4646.

The current text lets the empty ref win in two ways:
1. Under the run-age bound of "Recovery from the failed run's preserved work", a needs-human ref of a LATER run outranks a head published by an earlier run. A failed fresh relaunch is always the latest run.
2. Under bd-ib-qshcwc's newest-by-committer-time rule, now implementing, the newest ref wins, and a failed relaunch's ref is always the newest.

So a failed fresh relaunch can, by construction, displace the work it failed to rebuild.

The specification already has a WRITE-side guard for this, in §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref". A preserving step MUST NOT preserve a tip whose tree equals the run's base tree or the default branch head's tree, and the needs-human preservation step's `refs/heads/needs-human/<run-id>` commit falls under "the same tree guard". The READ side, recovery routing, has no corresponding exclusion. The shipped _dispatcher_recovery*.py has none either.

This proposal adds the READ-side complement. It is still needed for three reasons:
1. The write guard is unshipped (bd-ib-ofvsr3 carries it), and refs written before it ships, 91744d6f among them, persist.
2. 91744d6f is named under a DISPATCH id, not `needs-human/<run-id>`, so it lies outside the guard's literal scope even after it ships.
3. A reader cannot rely on every writer.

The two rules are complementary, not duplicates.

Filed by the publish-draft-green-work-loss plan seat (epic bd-ib-acrr56) on legacy-coordinator-agent's ruling (session 546979bb, 2026-11-09), for bd-ib-qshcwc; revise slot v333. Reviewed and approved by the factory-run-work-preservation plan seat (epic bd-ib-nckst7) as owner of the recovery clause.

### Proposed Changes

### contracts.md, §"Factory-configurable ACP fallback priority", paragraph "A needs-human tree is recognised by the run it carries, not only by its ref name."

INSERT after the sentence "A needs-human ref is any ref under `refs/heads/needs-human/`.":

> A needs-human ref CARRIES NO WORK when its tip commit's tree is identical to the tree of the tip's merge base with the default branch. This read-side rule complements the write-side tree guard of §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref", and applies whatever wrote the ref: a ref written before that guard, a ref named other than `needs-human/<run-id>`, and a ref any other writer produced are all outside the guard. Such a ref is not preserved work and is not any run's terminal tree. Routing MUST NOT take it as a seed, and MUST NOT let it outrank any other ref, published head or capture under this clause or its run-age bound. The default branch's tip for this comparison MUST be read once per routing pass, together with the identification below, and shared by every item the pass routes. The tip trees and merge bases MUST be read from that same per-pass identification. A comparison that cannot be taken is the existing unobservable-measurement hold, and MUST NOT be read either as a change or as the absence of one.

REPLACE in the same paragraph:

> Every `recovery-route` record of a `seeded`, `fresh` or `resume` route MUST carry a `passed_over_needs_human` field listing each needs-human ref that carries one of the item's earlier runs and was not the ref the route took, with its commit.

WITH:

> Every `recovery-route` record of a `seeded`, `fresh` or `resume` route MUST carry a `passed_over_needs_human` field. It lists each needs-human ref that carries one of the item's earlier runs and was not the ref the route took, with its commit and the reason it was passed over: `no-change` for a ref that carries no work, and `not-taken` for any other.

Why measured against the merge base, not the default branch's tip: a two-way comparison with the tip would count the default branch's own later commits as changes, so a ref whose run built nothing would read as carrying work whenever master had moved.

When every needs-human ref of an item carries no work and no other preserved work is verified, preserved work is confirmed absent. That is the clause's existing `fresh` route with the loss recorded.

### scenarios.md, Scenario 185 (heading unchanged). ADD after "A needs-human ref named outside the run id is honoured as the run's terminal tree":

```gherkin
  Scenario: A needs-human ref that carries no work is passed over
    Given an item released for recovery whose latest run L published ref needs-human/D at its ending
    And needs-human/D's tip tree is identical to the tree of its merge base with the default branch
    And an earlier run of the item left a verified preserved tree at ref P
    When the Dispatcher grades the item's recovery route
    Then the route is seeded from P, not from needs-human/D
    And the recovery-route record lists needs-human/D with its commit and the reason no-change in passed_over_needs_human

  Scenario: An item whose only needs-human ref carries no work is routed fresh with the loss recorded
    Given an item released for recovery whose only needs-human ref, needs-human/D, carries no work
    And no other preserved work of the item is verified
    When the Dispatcher grades the item's recovery route
    Then the route is fresh
    And the recovery-route record lists needs-human/D with its commit and the reason no-change in passed_over_needs_human
```

Placement: Scenario 185, not 319. 185 holds the "recognised by the run it carries" cases and every passed_over_needs_human case. 319 governs work-in-progress refs, and its coverage entry is bd-ib-v6br5b's. No ## heading changes, so tests/heading-coverage.json needs no co-edit.

### Implementation consequence

After ratification, bd-ib-qshcwc, which already adds passed_over_needs_human and still waits behind bd-ib-so6fef, gains one Definition-of-Done bullet:

> When a needs-human ref of an item carries no work, recovery routing does not seed from it, and the recovery-route record lists it in passed_over_needs_human with its commit and the reason no-change.
