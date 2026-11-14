---
topic: a-stale-seed-is-rebased-before-it-runs
author: claude-opus-5-5:publish-draft-green-work-loss
created_at: 2026-11-11T21:05:46Z
---

## Proposal: A seed is rebased onto the current default branch before its run starts

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The recovery-routing clause routes a released item `seeded` whenever verified preserved work or a current seed ruling exists, and the sandbox checks out the seed's commit exactly as preserved. Nothing bounds how far that commit's base may lag the default branch. A seed whose base predates a requirement the default branch has since gained runs against the old tree and fails a master-level check that no work by the run can repair. This proposal adds one paragraph that governs every route the clause would otherwise make `seeded`. Before the run starts, the Dispatcher MUST rebase the seed's work onto the default branch's current tip, read from the repository, and the run starts from the rebased commit. A rebase conflict holds the item and names every conflicting path. A seed whose tree equals its merge base carries no work and routes `fresh`. A seed already based on the current tip is used unchanged. A run MUST NOT start from a base behind the default branch. Scenario 348 exercises the paragraph.

### Motivation

Measured 2026-11-11: three factory runs died on one master-level requirement that their stale seed bases lacked. bd-ib-7e4d7t run 01M760B5SBVK was seeded from needs-human/01M6NPC7RGB7EV5MKQJ765WR24 at 63aa48822, base 30a2cfd1f (2026-11-05), 544 commits behind master. It ended at implement_hook_route@2 failing check-doctor-static, because .github/workflows/disarm-on-hold-label.yml, which master gained at e1075b5c4 (2026-11-11T02:04Z, bd-ib-jdaawy), was absent. The same two seed commits cherry-picked onto master pass that check. bd-ib-mztpy7 had to be reseeded fresh for the same cause, and bd-ib-22j24v, the v0.319.0 canary, also started from a leftover seed ref. Earlier, on 2026-11-05, bd-ib-i4cylq run 01M6M9MET3ZX ended at a canonical-hook body_mismatch from a base that predated a dev-tooling pin bump, and bd-ib-a7zpxy's preserve 3f478b6f had to be hand-routed fresh. The trigger class is any default-branch requirement that a check grades against live, shared state, not only a dev-tooling pin bump. legacy-coordinator-agent (session 9555a239) ruled the shape on 2026-11-11. REBASE rather than route fresh, because rebasing keeps the preserved work and routing fresh discards it. Hold on a rebase conflict, naming the paths. Read the default branch from the repository and never assume `master`. Route fresh a seed with zero diff against its merge base, because there is nothing to rebase (bd-ib-mztpy7's case). Owning work item: bd-ib-zzhy5t, plan publish-draft-green-work-loss (epic bd-ib-acrr56). Fleet scope: every factory repository's seeded recovery route. Co-edit owed at revise, outside this spec target: tests/heading-coverage.json gains one row for the new `## Scenario 348` heading (test `TODO`, reason naming bd-ib-zzhy5t), per the repository's heading-coverage co-edit rule.

### Proposed Changes

1. contracts.md: insert this new paragraph IMMEDIATELY AFTER the paragraph that begins "The seed record MUST name the source run, remote, immutable commit SHA, and preservation reference." and ends "... whose current state the agent inspects before continuing.", and BEFORE the paragraph that begins "**A ruled seed names the tree a released item's next dispatch starts from.**":

**A seed is rebased onto the current default branch before its run starts.** This paragraph governs every route this clause would otherwise make `seeded`, whether the seed comes from the preference order above or from a current seed ruling. The Dispatcher MUST read the repository's default branch from the repository's forge remote, and MUST NOT assume its name. It MUST read that branch's tip commit once per routing pass, shared by every item the pass routes, exactly as the needs-human identification below reads it. The seed's WORK is the sequence of commits reachable from the seed's immutable commit and not from that tip. Routing MUST apply the following rules in the order written, and the first that matches decides:

- When the seed's tree is identical to the tree of its merge base with the default branch, the seed carries no work. The route MUST be `fresh` rather than `seeded`, and the `recovery-route` record MUST name the seed's ref and commit as passed over with the reason `no-change`. When that seed came from a current seed ruling, the dispatch MUST consume the ruling exactly as a dispatch seeded from it would, so the ruling cannot govern the next dispatch.
- When the seed's merge base with the default branch is that tip, the seed MUST be used unchanged, and the run MUST start from the seed's immutable commit, as today.
- Otherwise the Dispatcher MUST rebase the seed's work onto the default branch's tip before the run starts. The rebase MUST NOT move, delete or rewrite the seed's ref, any needs-human ref, any preservation ref, or any checkout. The Dispatcher MUST publish the rebased commit to a ref under `refs/heads/seed-rebased/` named for the dispatch, and MUST verify by one remote read that the ref stands at that commit before the run starts. The new sandbox MUST check out the rebased commit. The seed record MUST name the seed's original ref and immutable commit, the rebased commit, its ref, and the default-branch commit it was rebased onto. The goal brief MUST name the rebased commit as the interrupted prior attempt.
- When the rebase conflicts, the route MUST be `held`. The `recovery-held` record MUST name the refusal `seed-rebase-conflict`, the seed's ref and immutable commit, the default-branch commit, and every path that conflicted. No run is launched, and a current seed ruling MUST stay current. Holding for a seed-rebase conflict is a `held` cause in its own right. Routing MUST NOT then fall through to another preserved tree, to the observed published head, or to `fresh`.

A default branch, a tip or a rebase that cannot be read or attempted is the existing unobservable-measurement hold, and MUST NOT be read as a conflict or as a clean rebase. A run routed `seeded` MUST NOT start from a commit whose merge base with the default branch is not the tip this pass read. Scenario 348 in `scenarios.md` exercises this paragraph.

1b. contracts.md, in the paragraph "**A ruled seed names the tree a released item's next dispatch starts from.**", the sentence "When the ruled ref exists at the ruled SHA and no non-fallback refusal applies, the route MUST be `seeded`, and the seed record MUST name the ruled ref as its preservation reference and the ruled SHA as its immutable commit." MUST become: "When the ruled ref exists at the ruled SHA and no non-fallback refusal applies, the route MUST be `seeded`, and the seed record MUST name the ruled ref as its preservation reference and the ruled SHA as its immutable commit, subject to the paragraph \"A seed is rebased onto the current default branch before its run starts\", which routes a ruled seed that carries no work `fresh` and holds one whose rebase conflicts." No other sentence of that paragraph changes.

2. scenarios.md: append this new H2 section after the last ratified scenario:

## Scenario 348 — A seeded recovery dispatch rebases its seed onto the current default branch, holds on a rebase conflict, and routes a seed carrying no work fresh

```gherkin
Feature: A seeded run never starts behind the default branch
  Scenario: A stale seed is rebased and the run starts from the rebased commit
    Given a repository whose default branch is named main
    And an item released for recovery whose seed's merge base is behind main's tip and whose seed's work rebases onto that tip without conflict
    When the item is dispatched
    Then the route is seeded
    And the run's sandbox checks out a commit whose parent chain reaches main's tip
    And that commit is published under refs/heads/seed-rebased/ before the run starts
    And the seed record names the original seed ref and commit, the rebased commit and its ref, and main's tip
    And the original seed ref still stands at its original commit
  Scenario: A rebase conflict holds the item and names every conflicting path
    Given an item released for recovery whose seed's work conflicts with the default branch's tip in two paths
    When the item is dispatched
    Then the route is held
    And the recovery-held record names the refusal seed-rebase-conflict, the seed ref and commit, the default-branch commit and both paths
    And no run is launched
    And the seed ref still stands at its original commit
  Scenario: A seed carrying no work routes fresh
    Given an item released for recovery whose seed's tree is identical to its merge base with the default branch
    When the item is dispatched
    Then the route is fresh
    And the recovery-route record lists the seed ref and its commit as passed over with the reason no-change
  Scenario: A seed from a ruling that carries no work consumes the ruling
    Given an item carrying a current seed ruling whose ruled commit's tree is identical to its merge base with the default branch
    When the item is dispatched and its run exists
    Then the route is fresh
    And the item gains one livespec-seed-ruling-consumed comment naming the ruling
  Scenario: A seed already on the default branch's tip is used unchanged
    Given an item released for recovery whose seed's merge base with the default branch is that branch's tip
    When the item is dispatched
    Then the route is seeded
    And the run's sandbox checks out the seed's immutable commit
    And nothing is published under refs/heads/seed-rebased/
```

No existing H2 heading is renamed or removed. The revise that accepts this proposal MUST add one `tests/heading-coverage.json` row for the new `## Scenario 348` heading in the same change.
