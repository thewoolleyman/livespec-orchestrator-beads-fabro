---
topic: hand-finished-merge-factory-proof-pointer
author: claude-opus-5-5
created_at: 2026-10-30T20:34:08Z
---

## Proposal: The proof-only arm also re-proves a hand-finished merge and a merge whose run died after it

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Widen the proof-only resume of a merged pull request so it serves an item that no factory run merged and an item whose run died after the merge, and never re-enters the implement path.

### Motivation

Work item bd-ib-hbt5b6 was found UNGOVERNED by the 2026-10-20 governance disposition: no ratified clause gave a merge that no factory run produced a route to factory Proof of Done records or a pointer. Its second instance is bd-ib-5guqmt, whose PR 2990 was hand-finished, has a host_verified record, and could not be accepted because the description carried no pointer. A third case is bd-ib-c6va2d, whose PR 3836 merged on 2026-10-28 and whose run 01M5ZK73M2WS died in publish_draft/refresh_repair afterwards, so the proof stages never ran and resume re-dispatched the implement path to LIVESPEC_DEAD_IMPLEMENTER. The fleet coordinator, acting under the maintainer's 2026-10-30 delegation, directed that one clause serve both by generalizing Scenario 257 and its clause (work item bd-ib-opd3hq) rather than duplicating them, consistent with its R275 ruling of 2026-10-20 that a host_verified record is no substitute for a factory_captured assertion.

### Proposed Changes

In SPECIFICATION/contracts.md, "A proof-only resume of a merged pull request": after the sentence ending "`resume --item` MUST take the proof-only arm instead of refusing on the merged pull request." add: "The arm is not limited to an item that an earlier run published. For an item that no factory run merged, the merged pull request is the one "The host leg" of "Proof of Done record" defines as the pull request of its latest merged run, so a hand-finished merge qualifies, and the same holds for an item whose run ended in `publish_draft` or `refresh_repair` after the merge and never reached the proof stages. For any merged pull request in this case, `resume --item` MUST take the arm whatever ended the item's earlier run, if there was one, and MUST NOT re-enter the implement path." After the sentence "The refusals for a live earlier run, a live ownership lock, a measurement the resume cannot take, and the two-resume limit still apply." add: "The refusal for a live earlier run tests an earlier run only where one exists, so an item with no earlier run is not refused for the want of one." In SPECIFICATION/scenarios.md add one scenario, numbered at revise, titled "## Scenario NN (numbered at revise) — A merged pull request with no finished factory run, or whose run died after the merge, is re-proven by the proof-only arm" with this body:

```gherkin
Feature: A merged pull request that no finished factory run proved is re-proven by the proof-only arm
  Scenario: A hand-finished merge is re-proven on its merged head
    Given an item whose pull request was merged by hand with no factory run, and whose latest reconcile-merged moved it into acceptance parked NEEDS_ATTENTION on its proof leg
    When the operator drives resume for the item
    Then the resume takes the proof-only arm anchored on that pull request and its head commit at merge, and the refusal for a live earlier run does not fire for the want of an earlier run
    And the arm's verified record is posted on that pull request, after which reconcile-merged writes the item's Proof of Done pointer
    And no host_verified record is read as proof of a factory_captured assertion

  Scenario: A merged pull request whose run died after the merge is re-proven, not re-implemented
    Given an item whose pull request merged and whose run ended in publish_draft or refresh_repair after the merge, so the pull request carries no Proof of Done comment
    When the operator drives resume for the item
    Then the resume takes the proof-only arm against the pull request's head commit at merge
    And it does not re-enter the implement path and does not end at a dead implementer
```
