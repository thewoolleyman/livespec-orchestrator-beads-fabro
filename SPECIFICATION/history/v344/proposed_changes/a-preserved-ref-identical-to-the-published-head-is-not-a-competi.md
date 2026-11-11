---
topic: a-preserved-ref-identical-to-the-published-head-is-not-a-competi
author: claude-opus-5-5
created_at: 2026-11-11T03:00:45Z
---

## Proposal: A preserved ref whose tree is identical to the observed published head is not a competing ref

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Recovery routing MUST NOT hold an item as publishing-run-unobservable merely because it carries a needs-human ref or failed-checkpoint preservation ref whose tip tree is identical to the observed published head's tree. Such a ref holds no work the head lacks, so, like the preserved-publish ref the stale publish-branch reclaim writes, it is not a competing ref, and routing proceeds as it would without that ref. The hold still fires when the trees differ and the run of the head or of the ref cannot be established, and a tree comparison that cannot be taken remains the existing unobservable-measurement hold.

### Motivation

Measured 2026-11-10 on seven account-fault items: bd-ib-rzkhqv, bd-ib-nceul6, bd-ib-ajtmgf, bd-ib-dpsiwz, bd-ib-ce7gbe, livespec-dev-tooling-7salp4 and livespec-dev-tooling-7g5qba. Each died after implement and left an open draft pull request, plus a needs-human preserve whose tree was byte-identical to the pull request head's tree. Recovery routing held each one as publishing-run-unobservable: bd-ib-ce7gbe was refused before listing at 20:17:54Z, and bd-ib-rzkhqv read held on build f0b6f8909cc4 at about 20:41Z. A coordinator seat then archived each identical preserve by hand to refs/archive/needs-human/<ref> so the items could route. The identity was measured again on 2026-11-11 for bd-ib-ofvsr3: refs/heads/needs-human/5de55a9556a84bd69d80faf8a4ea2b23 has the same tree object as pull request 4671's head b94081709.

The current clause requires the hold whenever an item holds both an observed published head and a needs-human or failed-checkpoint preservation ref whose run, or whose head's run, cannot be established. The hold exists to stop routing from choosing between two DIFFERENT trees without knowing which run is newer. When the two trees are identical there is no choice to make: resuming the published head keeps every byte the ref preserves. The clause already exempts the preserved-publish ref for the same reason ('stands for the published head it preserves and is ranked as that head, not as a competing ref'). This proposal extends that exemption to any preserved ref whose tree equals the head's tree.

The comparison is plain tree identity with no path exclusion. That matches the existing 'A needs-human ref CARRIES NO WORK when its tip commit's tree is identical to ...' convention, and it can only exempt a ref whose entire content the head already holds. The hold therefore still fires whenever the contents differ.

Work item held for this change: bd-ib-6szexa ('A preserved ref whose tree equals the published head's tree is not a competitor in the recovery route, so it no longer holds the item publishing-run-unobservable'), filed under plan factory-run-work-preservation (epic bd-ib-nckst7) at legacy-coordinator-agent's direction. Its first assertion contradicts the current MUST, so it waits for this ratification.

### Proposed Changes

Two edits.

**1. `SPECIFICATION/contracts.md`, §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work".**

In the paragraph on the run-age bound, between the sentence

> A preserved-publish ref written by §"Stale publish-branch reclaim before a re-dispatch" stands for the published head it preserves and is ranked as that head, not as a competing ref.

and the sentence

> When the item holds both an observed published head and a needs-human ref or failed-checkpoint preservation ref, and the run of the head or of that ref cannot be established, routing MUST route the item `held`, and the `recovery-held` record MUST name the measurement `publishing-run-unobservable`.

insert:

> A needs-human ref or failed-checkpoint preservation ref whose tip commit's tree is identical to the observed published head's tree holds no work that head lacks, so it is likewise not a competing ref: routing MUST NOT require its run, or the head's run, to be established on its account, and MUST route the item as it would if that ref were absent. The tree comparison MUST be read from the same per-pass identification that supplies the tip trees for "A needs-human tree is recognised by the run it carries"; a comparison that cannot be taken is the existing unobservable-measurement hold, and MUST NOT be read as identity.

Every other sentence of the paragraph is unchanged. In particular the following `publishing-run-unobservable` hold, and the sentence 'An item holding no such competing ref is routed as this clause otherwise states, whether or not its head's run can be established', now apply with an identical-tree ref counted as no competing ref.

**2. `SPECIFICATION/scenarios.md`, `## Scenario 323 — An earlier run's preserved ref never outranks a newer run's published head`.**

Append two scenarios to the Gherkin block, after 'Scenario: an item with no competing ref is not held for attribution' and before the closing fence:

```gherkin
  Scenario: a preserved ref whose tree is identical to the published head is not a competing ref
    Given an item whose latest run published head H, whose run no record names, and whose pull request on the publish branch is open
    And a needs-human ref N of the item whose name names no run and whose tip commit carries no run trailer
    And N's tip commit's tree is identical to H's tree
    When recovery routing grades the item
    Then the item is not routed held for publishing-run-unobservable
    And the route is the one recovery routing reads for the same item with N absent

  Scenario: a preserved ref whose tree differs from the published head still holds when its run cannot be established
    Given an item whose latest run published head H
    And a needs-human ref N of the item whose name names no run and whose tip commit carries no run trailer
    And N's tip commit's tree differs from H's tree
    When recovery routing grades the item
    Then the item is routed held and stays ready
    And the recovery-held record names the measurement publishing-run-unobservable
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.
