---
topic: a-preserve-descending-from-the-published-head-refuses-the-resume
author: claude-opus-5-5
created_at: 2026-11-11T04:28:51Z
---

## Proposal: A preserved tree that descends from the published head with different content refuses the resume, so recovery seeds from it

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a fallback-permitting refusal to "Resume from a published pull request (`resume --item`)". The resume MUST refuse when the item holds a preserved ref, or a run's latest preserved capture, that belongs to the run that published the pull request's current head or to a later run of the item, whose tip commit descends from that head and whose tree differs from that head's tree. The refusal names the ref, its tip and the head, and its remedy is a plain dispatch, which recovery routing seeds from that ref. The preserved ref is a needs-human ref or a failed-checkpoint preservation ref. Today an admissible resume 'keeps its precedence over any seed', so recovery resumes onto the older pull request head and silently drops every commit the preserve holds beyond it.

### Motivation

Three measured instances, each of which lost or nearly lost committed work without any error.

1. livespec-dev-tooling-fjpqqq. Pull request 4093 has head f70bda7b. The preserve tip 14e8cf26 descends from f70bda7b and holds open Red commit cc79bff1, which the head does not contain. Once resolve-blocked made the item ready, its route flipped from SEEDED from the preserve to RESUME at review onto 4093 (source pull-request-latest-record). The owner had to hand-route it with a cherry-pick rider.
2. livespec-dev-tooling-hmztez. Pull request 4092 has head 13ed21f4. The preserve tip d4af7da4 descends from 13ed21f4 and holds open Red commit 4da5cce0, which the head does not contain. The route flipped the same way, and the item is held by hand with its owner.
3. bd-ib-ofvsr3, in this repository. refs/heads/needs-human/b21921fb289e43799088da3371955b19 is at d98f53037, which descends from pull request 4671 head b94081709. It carries fix commit 85c4721b9, which has both TDD trailer blocks, and it passed the full declared aggregate at janitor@6 of run 01M6X173QWS677D3PHAMBEAZ89, the run that also published b94081709. On build 8348582ab96a (v0.315.1), route_recovery read resume at fix onto b94081709. Run 01M7423YJ9CMHF7QM5ZXX872MV then ended needs-human, and the item now runs on a hand-written cherry-pick rider.

The ancestry and the open-Red placement were verified with git merge-base --is-ancestor: for cases 1 and 2 in the livespec-dev-tooling clone on 2026-11-11, and for case 3 in this repository.

The router conforms to the ratified text. "Recovery from the failed run's preserved work" prefers a needs-human ref over the observed published head only when choosing a SEED, and states that 'A `resume` that every precondition of §"Resume from a published pull request (`resume --item`)" admits keeps its precedence over any seed.' None of that section's refusals covers a preserve that holds more work than the head. So the spec itself chooses the older tree.

The proposed refusal is confined to the case where nothing is lost by refusing. The preserve's tip DESCENDS from the head, so seeding from it keeps every byte the resume would have kept, plus the preserve's later commits. Its tree DIFFERS from the head's tree, so there is real extra work; an identical tree is already not a competing ref under spec v344. The refusal is limited to refs of the publishing run or a later run, matching the existing run-age bound, so an earlier run's tree can never displace a newer published head. It is fallback-permitting, so routing seeds exactly as it already does for the other fallback-permitting refusals, and every non-fallback refusal keeps its precedence. legacy-coordinator-agent accepted this shape on 2026-11-11 and asked for all three cases to be carried. The implementation item is filed under plan factory-run-work-preservation (epic bd-ib-nckst7) after ratification.

### Proposed Changes

Three edits.

**1. `SPECIFICATION/contracts.md`, §"Resume from a published pull request (`resume --item`)" → "Refusals".**

After the bullet

> - the pull request has already anchored two resumes, naming them (remedy: a plain dispatch).

change that bullet's terminating period to a semicolon and append:

> - the item holds a needs-human ref or a failed-checkpoint preservation ref, as §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work" defines them, or a run's latest preserved capture, that belongs to the run that published the pull request's current head or to a later run of the item, whose tip commit descends from that head and whose tip tree differs from that head's tree, naming the ref, its tip and the head (remedy: a plain dispatch, which recovery routing seeds from that ref). The run a ref belongs to is established exactly as that section establishes it. A ref whose run cannot be established is graded by that section's `publishing-run-unobservable` hold, not by this bullet. An ancestry or tree comparison this bullet needs that cannot be taken is the unreadable-measurement refusal below, and MUST NOT be read as the absence of such a ref.

**2. `SPECIFICATION/contracts.md`, §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work", the definition of a fallback-permitting refusal.**

Replace

> the Definition of Done changed; or the pull request already anchored two resumes.

with

> the Definition of Done changed; the pull request already anchored two resumes; or a preserved ref of the publishing run or a later run descends from the head with a different tree.

When that last refusal is the only one that applies, routing MUST seed from the ref it names. Every other sentence of the clause is unchanged, including the run-age bound and 'A `resume` that every precondition ... admits keeps its precedence over any seed', which now excludes this case because the precondition refuses.

**3. `SPECIFICATION/scenarios.md`, `## Scenario 323 — An earlier run's preserved ref never outranks a newer run's published head`.**

Append three scenarios to the Gherkin block, before the closing fence:

```gherkin
  Scenario: a preserve that descends from the published head with more work refuses the resume and seeds
    Given an item whose run R published head H on an open pull request that passes every other resume precondition
    And a needs-human ref N of run R whose tip descends from H and whose tip tree differs from H's tree
    When recovery routing grades the item
    Then the resume refuses naming N, its tip and H, with the remedy a plain dispatch
    And the route is seeded from N at its tip

  Scenario: a preserve of an earlier run that descends from a later run's head does not refuse the resume
    Given an item whose later run L published head H on an open pull request that passes every resume precondition
    And a needs-human ref N of an earlier run whose tip descends from H and whose tip tree differs from H's tree
    When recovery routing grades the item
    Then the route is resume onto H

  Scenario: a preserve that does not descend from the published head does not refuse the resume
    Given an item whose run R published head H on an open pull request that passes every resume precondition
    And a needs-human ref N of run R whose tip does not descend from H
    When recovery routing grades the item
    Then the route is resume onto H
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.
