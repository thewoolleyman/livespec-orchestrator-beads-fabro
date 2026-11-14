---
topic: a-regroomed-parent-s-preserved
author: claude-opus-5-5:factory-run-work-preservation
created_at: 2026-11-14T08:36:59Z
---

## Proposal: A regroomed parent's preserved work is pinned to a seed ref its slices restore from, and that ref outlives the parent until its last slice closes

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Regroom files the approved slices of a parent and closes that parent as regroomed-out in the same pass. Closing it triggers §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Preservation refs are deleted when the Dispatcher closes or collects an item's runs", which deletes every `refs/livespec/wip/<parent>/` ref. The slices' restore steps name exactly those refs, so the first slice dispatched finds nothing to restore and stops before its first commit. This proposal adds one paragraph after that deletion paragraph. When `file_approved_slices` files the approved slices of a parent that holds preserved work, it MUST first create `refs/livespec/seed/<parent-id>` on origin at the commit a seeded re-dispatch of the parent would take, through the forge's refs interface rather than a git push, and read it back. Every slice it files MUST name that seed ref and its commit as the ref to restore from, and never a ref the parent's closure deletes. A seed ref that cannot be created or read back refuses the filing, leaving the parent and its preservation refs as they were. The seed ref is not a preservation ref of the parent, so closing the parent does not delete it. The Dispatcher MUST delete it once every slice filed from that parent is closed, MUST NOT delete it earlier, and journals and retries a failed deletion. A parent with no preserved work gets no seed ref. Scenario 320 gains four cases. The deletion paragraph itself and every heading are unchanged.

### Motivation

Owning work item bd-ib-7iztzv, "Closing a regroomed parent deletes the preserved wip ref its slices are told to restore from, so the first slice dispatched stops before its first commit". It was filed by address-honeycomb-alerts on legacy-coordinator-agent's ruling of 2026-11-14 about 00:4xZ, and adopted by plan factory-run-work-preservation (epic bd-ib-nckst7), which owns seeds and preservation. It is spec-change tier, because a new ref namespace and its deletion moment are contract text, and it was sequenced after this plan's v374 revise, which merged as PR #5213 at 2026-11-14T08:30:55Z.

Measured trap, 2026-11-13/14 (from the item):
- bd-ib-z2y4ca non-converged (run 01M7A8J6MSQ0) and was regroomed through groom.file_approved_slices into six slices: bd-ib-pqpgc5, bd-ib-defs3b, bd-ib-d3pdrv, bd-ib-cbn6vw, bd-ib-es2exq and bd-ib-5k6eal.
- Each slice's restore steps named refs/livespec/wip/bd-ib-z2y4ca/01M7A8J6MSQ01N90NZVHZFZ5PB/10 at e91a5ffc0f61.
- The same filing closed z2y4ca as regroomed-out, and the Dispatcher's preservation-ref deletion removed every refs/livespec/wip/bd-ib-z2y4ca/ ref, exactly as Scenario 320 requires for a closed item.
- The first slice dispatched, bd-ib-defs3b (run 01M7BK5VK32DBA9CM8157ZTADT), found no ref, stopped before its first commit, and ended blocked with LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS. legacy-dispatcher-agent confirmed that no z2y4ca wip ref remained among the 93 on origin.
- The interim hand repair pinned the commit to refs/heads/seed/bd-ib-z2y4ca-regroom through the forge refs API and repointed all six slice descriptions to it. This paragraph makes that repair the mechanism, under a refs/livespec/ name.

Design choices:
- The ref lives outside every namespace the deletion paragraph deletes: not refs/livespec/wip/, refs/livespec/preserved-publish/, refs/heads/needs-human/ or (per the pending a-commit-settle-abort-preserves-the-in-progress-resolution proposal) refs/livespec/resolution/. So the parent's closure leaves it standing without any exception carved into that paragraph.
- It is created through the forge refs interface, because the primary checkout's pre-push hook refuses a git push from the host, as the reclaim's preserved-publish write already records.
- The commit is the one a seeded re-dispatch of the parent would take, by the recovery clause's preference order. That is the parent's latest preserved capture unless a needs-human or failed-checkpoint ref of the same run outranks it, which is what the item's Definition of Done names as the latest preserved capture in the measured case.
- Creating and reading back the seed ref BEFORE any slice is filed makes a failure safe: nothing is filed, the parent is not closed, and its wip refs survive.
- The deletion moment is keyed on the approval record that file_approved_slices already stamps on every filed slice and on the regroomed-out original, so no new linkage field is needed.

In-flight survey (2026-11-14 about 08:45Z): one pending in-tree proposal, a-commit-settle-abort-preserves-the-in-progress-resolution, edits the deletion paragraph's first two sentences to add refs/livespec/resolution/. This proposal does not edit that paragraph and only adds the next one, so the two compose; it aligns with that proposal. The remote spec branches whose diffs mention these clauses (codex-floor-reset-proximity #4208, revise-attention-item-answer-policy #2286, revise-v330-goal-template-opener-modify #4721, red-turn-changes-no-product-file) are closed or long-merged. Open PR #5231 (a-recovery-held-item-whose) touches neither Scenario 320 nor this paragraph.

### Proposed Changes

1. contracts.md, §"Dispatcher admission, WIP cap, and post-merge acceptance": IMMEDIATELY AFTER the paragraph that begins "**Preservation refs are deleted when the Dispatcher closes or collects an item's runs.**" and ends "Scenario 320 in `scenarios.md` exercises this paragraph.", insert this paragraph, separated from its neighbours by one blank line:

"**A regroomed parent's preserved work is pinned to a seed ref its slices restore from.** A parent's *regroom seed ref* is the ref `refs/livespec/seed/<parent-work-item-id>` on the parent's repository. When `file_approved_slices` files the approved slices of a parent work item that holds preserved work — a work-in-progress ref, a needs-human ref, or a failed-checkpoint preservation ref, as §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work" defines them — it MUST, before it files any slice, create the parent's regroom seed ref on origin at the commit a `seeded` re-dispatch of the parent would take, chosen in that clause's preference order. It MUST create the ref through the forge's refs interface and MUST NOT create it by a git push. It MUST then read the ref back from origin. When the ref cannot be created, or does not read back at that commit, `file_approved_slices` MUST refuse the filing, naming the ref, the commit and the failure. It MUST then file no slice and MUST NOT close the parent, so the parent and its preservation refs stay exactly as they stood. Every slice it files from such a parent MUST name the regroom seed ref and its commit as the ref to restore from. It MUST NOT name a ref under `refs/livespec/wip/<parent-work-item-id>/`, `refs/livespec/preserved-publish/<parent-work-item-id>/` or `refs/heads/needs-human/`, which the parent's closure deletes. A parent that holds no preserved work gets no regroom seed ref, and its slices name none. A regroom seed ref is not a preservation ref of the parent under the preceding paragraph, so the Dispatcher's closure of the parent and its ended-run collection MUST NOT delete it. The Dispatcher MUST delete a parent's regroom seed ref once every slice filed from that parent is `closed`, where a slice is filed from the parent when the approval record `file_approved_slices` stamped on it is the one stamped on the parent. It MUST NOT delete the ref while any such slice is not `closed`. A deletion that fails MUST be journaled with the ref and retried on the Dispatcher's next pass, and MUST NOT change any item's state. Scenario 320 in `scenarios.md` exercises this paragraph."

The paragraph that begins "**Preservation refs are deleted when the Dispatcher closes or collects an item's runs.**" is NOT edited by this proposal.

2. scenarios.md, §"Scenario 320 — Preservation refs are deleted when the Dispatcher closes or collects an item's runs":

2a. REPLACE the governing-clause line

"Governing clause: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Preservation refs are deleted when the Dispatcher closes or collects an item's runs"."

with

"Governing clauses: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Preservation refs are deleted when the Dispatcher closes or collects an item's runs" and → "A regroomed parent's preserved work is pinned to a seed ref its slices restore from"."

2b. Inside that section's gherkin block, IMMEDIATELY AFTER `Scenario: a failed deletion is retried` (whose last step is "Then it attempts the deletion again and the item's state is unchanged") and BEFORE the closing fence, insert these four scenarios, each preceded by one blank line:

```gherkin
  Scenario: regroom pins the parent's preserved work before it closes the parent
    Given a parent work item P whose latest preserved work is the work-in-progress ref refs/livespec/wip/P/R/10 at commit C
    And an approved regroom draft of P with three slices
    When file_approved_slices files the slices and closes P as regroomed-out
    Then refs/livespec/seed/P exists on origin at C
    And each filed slice names refs/livespec/seed/P and C as the ref to restore from, and names no ref under refs/livespec/wip/P/
    And after the Dispatcher deletes P's preservation refs, fetching refs/livespec/seed/P from origin resolves to C

  Scenario: a seed ref that cannot be created refuses the filing
    Given a parent work item P with preserved work at commit C and an approved regroom draft
    And the forge refuses the creation of refs/livespec/seed/P
    When file_approved_slices runs
    Then no slice is filed and P is not closed
    And P's refs under refs/livespec/wip/P/ still exist on origin
    And the refusal names refs/livespec/seed/P, C and the failure

  Scenario: the seed ref stays while any slice is open
    Given refs/livespec/seed/P created when P's slices S1, S2 and S3 were filed
    And S1 and S2 are closed and S3 is ready
    When the Dispatcher's next pass runs
    Then refs/livespec/seed/P still exists on origin

  Scenario: the seed ref is deleted once the last slice closes
    Given refs/livespec/seed/P created when P's slices S1, S2 and S3 were filed
    When the Dispatcher closes S3, the last of them still open
    Then refs/livespec/seed/P does not exist on origin
```

No `## ` heading is added, removed or renamed, so `tests/heading-coverage.json` needs no co-edit.
