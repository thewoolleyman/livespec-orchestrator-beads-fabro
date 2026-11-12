---
topic: concurrent-git-fetches-into-one
author: claude-opus-5-5
created_at: 2026-11-12T17:35:00Z
---

## Proposal: Every orchestrator fetch into a primary checkout serializes behind one lock in that checkout's git common directory

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Provisional fleet launch scripts" serializes only the launcher's checkout-at-the-origin-tip refresh, and only against other launchers. The launch-time preflight, the Dispatcher's source staging and the janitor and reconcile refreshes fetch into the same primary checkout with no lock. Concurrent fetches then race on `refs/remotes/origin/<branch>` and `FETCH_HEAD`. This proposal puts every one of those fetches behind ONE exclusive lock in the checkout's git common directory. The wait is bounded and fails without touching refs. A committed `fleet-launch/` helper takes the same lock for any other caller.

### Motivation

Work item bd-ib-zyu2ug, a child of plan bd-ib-ynnykl (legacy-dispatcher-agent), routed to this seat for its deposit by legacy-coordinator-agent (session 959b2f8b) on 2026-11-12. Its launch was refused as a genuine spec-change partial under `## Provisional fleet launch scripts`; the refusal rationale is on the item. The coordinator (session ec00b770) routed the defect on 2026-11-11 as fleet-class and stop-the-line-grade. Concurrent fetches failed with `incorrect old value provided` on `refs/remotes/origin/master` and with `Cannot fast-forward to multiple branches`; the measured instances are on the item. The topic is the item's linked stem, so the hold links without a relink.

Design choices, stated for the grade:
- **One lock, in the common directory.** Every worktree of a checkout shares the common directory and the remote-tracking refs a fetch updates, so the lock lives there, not in a per-worktree directory.
- **Held through the ref updates.** The race is between ref-update transactions, so releasing the lock before the fetch's updates complete would not remove it. For the launcher, the hold extends through its fast-forward.
- **Fail without side effects.** A caller that times out never ran its fetch, so it leaves refs and `FETCH_HEAD` exactly as the holder will.
- **A helper, so callers outside the orchestrator can join.** Seats and scripts fetch into the same checkouts; a committed command is the only way they can take the same lock.

Fleet scope: every repository's primary checkout on the control node, because launchers, preflights, janitors, `reconcile-merged` and seats all fetch into the same checkouts. livespec-orchestrator-git-jsonl has no `fleet-launch/` launchers, so this proposal's launcher rules do not reach it. Any of its paths that fetch into a shared primary checkout can join through the helper, which needs its own item in that tenant. In-flight alignment, all `align`: #5058, #5060, #5067 and #5068 touch no fetch path.

### Proposed Changes

**1. One fetch lock per checkout (`contracts.md` §"Provisional fleet launch scripts").** Change the sentence "The refresh MUST be serialized per checkout, so that two launchers for one repository never fetch or merge in that checkout at once." in the "Checkout at the origin tip" bullet to "The refresh MUST be serialized under the checkout's fetch lock, as the next bullet states.", and add after that bullet:

> - **One fetch lock per checkout.** Every `git fetch` the orchestrator runs in a repository's primary checkout MUST hold an exclusive lock on the file `livespec-fetch.lock` in that checkout's git common directory. It acquires the lock before the fetch starts and releases it only after the fetch's ref updates complete. This covers the launcher's checkout-at-the-origin-tip refresh, whose hold extends through its fast-forward, the launch-time Definition-of-Done preflight's fetch, the Dispatcher's source-staging fetch of §"Dispatch pre-launch step attribution and concurrency", and the post-merge and reconcile janitor's refresh of that checkout. A caller that has waited longer than its configured bound for the lock MUST exit non-zero, without fetching, with a message naming the lock file and the pid that holds it, and MUST leave the checkout's refs and `FETCH_HEAD` unchanged. The repository MUST commit one `fleet-launch/` helper command that runs a given git command in a given checkout under that same lock, with the same bounded wait, so that a seat or script outside the orchestrator that fetches into a primary checkout takes the same lock. With any number of these callers started at once against one checkout, including while the remote's default branch advances between them, each caller MUST either complete its fetch or make the bounded-wait exit above; no fetch may fail on a concurrent ref update. Scenario 363 in `scenarios.md` exercises this bullet.

**2. Scenario (`scenarios.md`).** Append the scenario below. Its number is the next free one at revise time; 350 to 362 are claimed by pending proposals and peer drafts.

## Scenario 363 — Concurrent fetches into one primary checkout serialize behind one lock and all succeed

```gherkin
Feature: concurrent fetches into one checkout never race on its refs
  Scenario: eight concurrent fetch callers all exit zero
    Given one primary checkout whose remote's default branch advances while the callers run
    And eight fetch callers, among them launcher refreshes, preflight fetches, source-staging fetches and janitor refreshes, started at once against it
    When every caller runs to completion within its wait bound
    Then every caller exits zero
    And none fails with "incorrect old value provided" on the remote-tracking ref of the default branch
    And none fails with "Cannot fast-forward to multiple branches"

  Scenario: a caller that outwaits its bound fails without side effects
    Given a process holding the checkout's fetch lock past another caller's wait bound
    When that caller's bound expires
    Then the caller exits non-zero naming the lock file and the holder's pid
    And the checkout's refs and FETCH_HEAD are unchanged by that caller

  Scenario: the helper takes the same lock
    Given a process holding the checkout's fetch lock
    When the fleet-launch helper is asked to run a git fetch in that checkout
    Then the helper's fetch starts only after the lock is released
```

**3. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading. The row is carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit, with `test: "TODO"`, `work_item: "bd-ib-zyu2ug"`, and a non-empty `reason` naming integration or above as the owed test's tier. It also adds one matching `tests/heading-coverage-debt.json` entry. If the revise renumbers Scenario 363, the row, the entry and the bullet's scenario reference MUST carry the renumbered heading text.
