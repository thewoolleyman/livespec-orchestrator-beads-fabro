---
topic: a-recovery-held-item-whose
author: claude-opus-5-5:factory-run-work-preservation
created_at: 2026-11-14T03:24:37Z
---

## Proposal: A recovery-held item whose published head is a tree-identical copy of its preserved work is resumed, and a recapture-exhausted hold whose resume cannot start falls back to seeded

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Two clauses together deadlock a recapture-exhausted item whose open pull request head no run published. §"Resume from a published pull request (`resume --item`)" hands every ref whose run cannot be established to the `publishing-run-unobservable` reading before any tree is compared. §"Factory-configurable ACP fallback priority" makes the recapture-exhausted hold non-fallback and prescribes exactly that resume. So when the head is a hand-rebased copy of the run's preserved work (identical tree, no ancestry either way, named by no publication, proof or journal record), the prescribed resume refuses and recovery routing keeps the item held, and nothing else can move it. Closing the pull request does not free it either: the resume refuses a closed pull request, and the hold still prescribes the resume. This proposal makes three amendments. (1) The resume compares trees FIRST: a needs-human ref, failed-checkpoint preservation ref or run's latest preserved capture whose tip tree is identical to the pull request's current head's tree holds no work that head lacks, so it never refuses the resume, whatever the ancestry and whether or not either run can be established. A differing tree with an unattributable run still refuses exactly as today. (2) The recovery clause's existing identical-tree sentence, which already makes such a needs-human or failed-checkpoint ref non-competing, is extended to a run's latest preserved capture and to commits with no ancestry relation. (3) The recapture-exhausted hold gains exactly two exits to `seeded`, never `fresh`. The first is that the item has no open pull request. The second is that an explicit `resume --item` of it refused naming `publishing-run-unobservable`, which that refusal records on the item as a ledger comment so routing reads it without a remote measurement. With no verified preserved work the item stays held. Scenario 323 narrows its "a head that nothing attributes still refuses the resume" case to a differing tree and gains two cases. Scenario 343 gains four. No H2 heading changes.

### Motivation

Owning work item bd-ib-tefsim, "A recovery-held item whose published head is a tree-identical rebased copy of its preserved ref is resumed by tree comparison, or falls back to SEEDED from the preserve, instead of deadlocking", filed under plan factory-run-work-preservation (epic bd-ib-nckst7). legacy-coordinator-agent (session 719514f8) approved it at spec-change tier on 2026-11-14 and directed this seat to author this topic as a DRAFT for grade, joining the next orchestrator revise slot. The spec today states the identical-tree rule only for needs-human and failed-checkpoint refs in the recovery ROUTE, and forbids any fallback from the recapture-exhausted hold.

Measured instance, livespec-dev-tooling-cvef23 (dev-tooling tenant), 2026-11-14:
- The SEEDED dispatch at 02:56:25Z early-exited, rc=1 capacity-deferred: `recovery held: recapture-exhausted: implementation preserved on #4611 at 6054a2526324fed6194cd4ed3227e7e0347b0170 ; resume --item livespec-dev-tooling-cvef23 at proof_capture with a proof rider`.
- The prescribed resume at 03:09:16Z refused rc=3: `publishing-run-unobservable: the published head and preserved ref could not be ordered by run, so the preserved-descendant comparison could not be taken`.
- PR #4611's head 6054a2526 carries hand-made rebased copies (committed 01:50:28Z, by no factory run) of run 01M7BQSSB4YR's wip/2 commit 4217dbb28ecf700afa055427e325ebed21f3b4d5. The two commits have the SAME tree, 32edf3494e343503ebc5ddc4751efed818e10c3e, and `git merge-base --is-ancestor` is false both ways.
- The route owner then closed #4611 (about 03:1xZ) to lift the hold. The SEEDED dispatch at 03:17:55Z was still held with the same text naming the now CLOSED pull request (addendum by dev-host-test-gate-load, session cb3fae69, on the item). Closing the pull request is therefore not an operator escape.

Code cause, for the implementer (installed build c1f8445faf3b): `_dispatcher_resume_preserved_descendant.py` returns `publishing-run-unobservable` as soon as the run order is unknown, BEFORE it reads either tree. The later `head_tree == tip_tree` check is reached only after a proven run order and ancestry. The hold that names a closed pull request in place of the needs-human ref, contrary to Scenario 343's "No open pull request" case, is a separate implementation divergence, which the item's implementer should fix alongside this change.

Prior art: bd-ib-6szexa (closed) made identical-tree needs-human and preservation refs non-competing in the recovery route only. bd-ib-st4obs (blocked) and bd-ib-tsxt2e bind a run to the head its publish_draft pushed; a hand-rebased head is pushed by no run, so they never attribute it, and the spec keeps `publishing-run-unobservable` for an unnamed head (Scenario 323, "a head that nothing attributes still refuses the resume", added by the merged a-resume-refuses-the-resumed). This proposal keeps that refusal for a DIFFERING tree only.

Why the seeded exit is safe: the hold exists so an exhausted proof is not re-captured blindly. A seeded dispatch restores the captured code and still runs every stage, so the exhausted proof is captured again by a fresh run under any proof rider on the item. It is bounded by the pre-claim refusal of §"Across-dispatch required-result progress", which is graded before recovery routing exactly as for every released candidate. The alternative — a hold that prescribes a resume which cannot start — leaves the item stuck until someone edits it by hand.

In-flight survey (2026-11-14 about 03:45Z): 59 remote spec/* branches and 26 open spec-touching pull requests. The only branches whose diffs touch the amended sentences (spec/a-resume-refuses-the-resumed, PR #5165, and spec/revise-v364 through v369 and revise-the-verified-proof-result-observer) are already MERGED. Open #5213 (revise v374) and the pending in-tree proposals a-recapture-lap-must-answer, a-stale-preserved-seed-is, a-proof-captured-before-the and a-stale-seed-is-rebased-before-it-runs mention recapture or seeding but edit none of the sentences this proposal amends; this proposal aligns with all of them.

### Proposed Changes

1. contracts.md, §"Resume from a published pull request (`resume --item`)", in the bullet that begins "the item holds a needs-human ref or a failed-checkpoint preservation ref, as §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work" defines them, or a run's latest preserved capture,": REPLACE the sentence

"A ref whose run cannot be established is graded by that section's `publishing-run-unobservable` hold, not by this bullet."

with

"A ref whose tip commit's tree is identical to the pull request's current head's tree holds no work that head lacks and is not such a ref: the resume MUST NOT refuse on its account, under this bullet or by the `publishing-run-unobservable` reading, whether or not either commit is an ancestor of the other and whether or not the run of the ref or of the head can be established. The resume MUST take that tree comparison before it establishes the run of either, so a head whose commits are rebased copies of the ref's commits, with the same tree, is resumed even when no publication record, proof record or journal record names it. A ref whose tip tree differs from the head's tree and whose run cannot be established is graded by that section's `publishing-run-unobservable` hold, not by this bullet."

The bullet's last sentence, "An ancestry or tree comparison this bullet needs that cannot be taken is the unreadable-measurement refusal below, and MUST NOT be read as the absence of such a ref.", stays as it is, and so applies to the new tree comparison.

2. contracts.md, §"Factory-configurable ACP fallback priority", in the recovery clause: REPLACE the sentence opening

"A needs-human ref or failed-checkpoint preservation ref whose tip commit's tree is identical to the observed published head's tree holds no work that head lacks, so it is likewise not a competing ref:"

with

"A needs-human ref, a failed-checkpoint preservation ref, or a run's latest preserved capture under §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref", whose tip commit's tree is identical to the observed published head's tree holds no work that head lacks, so it is likewise not a competing ref, whether or not either commit is an ancestor of the other:"

The rest of that sentence, from "routing MUST NOT require its run, or the head's run, to be established on its account" onward, and the sentence after it on how the tree comparison is read, stay as they are.

3. contracts.md, §"Factory-configurable ACP fallback priority", in the recapture-exhausted sentences of the same clause:

3a. REPLACE

"A proof that exhausted its recapture bound is not re-captured until a person or an owning seat supplies a proof rider and resumes the item explicitly through §"Resume from a published pull request (`resume --item`)"."

with

"A proof that exhausted its recapture bound is not re-captured until a person or an owning seat supplies a proof rider and resumes the item explicitly through §"Resume from a published pull request (`resume --item`)", or until the item takes the seeded route below because that resume cannot start."

3b. REPLACE

"This hold is a non-fallback refusal: no fallback-permitting refusal can turn it into a `seeded` or `fresh` route."

with

"This hold is a non-fallback refusal: no fallback-permitting refusal can turn it into a `seeded` or `fresh` route, except as the following sentences state. The prescribed resume cannot start when the item has no open pull request, because the resume has no published head to resume, or when an explicit `resume --item` of the item has refused since the hold's `recovery-held` record was written naming the measurement `publishing-run-unobservable`. In either case recovery routing MUST route the item `seeded` from its preserved work, taken in the preference order this clause states and verified exactly as every `seeded` route's preserved work is verified, or from the seed a current seed ruling names. It MUST NOT route the item `fresh`. When no preserved work is verified and no seed ruling is current, it MUST keep the item `held`, and the detail's `<preserved>` MUST read `no preserved work observed`. When `resume --item` refuses a recapture-exhausted item naming `publishing-run-unobservable`, it MUST add one ledger comment to the item that opens with the marker line `livespec-recapture-resume-unobservable` and names the pull request, its head and the preserved ref it could not order. Deciding that the resume refused MUST read that comment only, so routing takes no remote measurement for it, and only a comment written after the hold's latest `recovery-held` record counts. The `seeded` route this exit takes MUST be journaled with the reason `no-open-pull-request` or `resume-refused-publishing-run-unobservable`. Its goal brief MUST carry any proof rider on the item. It restores the captured code, not the earlier run's position in the workflow, so every stage the workflow requires still runs, `proof_capture` among them."

The sentences after it ("It is graded after the pre-claim refusal of §"Across-dispatch required-result progress" ...", "An explicit `resume --item` of such an item is governed by that command's own preconditions ... and this hold MUST NOT add a precondition to that command." and "Scenarios 342 and 343 in `scenarios.md` exercise this hold.") stay as they are. The marker comment of 3b is written by the resume's refusal path and is not a precondition of the resume.

4. scenarios.md, §"Scenario 323 — An earlier run's preserved ref never outranks a newer run's published head", inside its gherkin block:

4a. REPLACE the scenario

```gherkin
  Scenario: a head that nothing attributes still refuses the resume
    Given run R's latest preserved capture on the item and an open pull request whose current head H no publication record, proof record or dispatch-journal record names
    When the Dispatcher resumes the item
    Then the resume refuses with publishing-run-unobservable, naming that measurement
```

with

```gherkin
  Scenario: a head that nothing attributes still refuses the resume
    Given run R's latest preserved capture on the item and an open pull request whose current head H no publication record, proof record or dispatch-journal record names
    And the capture's tip tree differs from H's tree
    When the Dispatcher resumes the item
    Then the resume refuses with publishing-run-unobservable, naming that measurement
```

4b. IMMEDIATELY AFTER that scenario and BEFORE `Scenario: a marker comment from another identity is not a publication record`, insert these two scenarios, each separated from its neighbours by one blank line:

```gherkin
  Scenario: a head whose tree is identical to the preserved capture is resumed though nothing attributes it
    Given run R's latest preserved capture W on the item and an open pull request whose current head H no publication record, proof record or dispatch-journal record names
    And W's tip tree is identical to H's tree
    When the Dispatcher resumes the item
    Then the resume does not refuse with publishing-run-unobservable
    And the resume does not refuse naming W
    And the run starts at the node the resume is anchored on

  Scenario: a rebased copy of a preserved capture is resumed
    Given run R's latest preserved capture W at commit C on the item
    And an open pull request whose head H was committed by hand as a rebased copy of C, with C's tree, and is named by no run's record
    And neither C nor H is an ancestor of the other
    When the Dispatcher resumes the item
    Then the resume does not refuse with publishing-run-unobservable
    And the run starts at the node the resume is anchored on
```

5. scenarios.md, §"Scenario 343 — A recapture-exhausted hold names the preserved implementation and the explicit resume route", inside its gherkin block: IMMEDIATELY AFTER `Scenario: No preserved work observed` (whose last step is `Then the detail reads "recapture-exhausted: implementation preserved on no preserved work observed ; resume --item <work-item-id> at proof_capture with a proof rider"`) and BEFORE the closing fence, insert these four scenarios, each preceded by no blank line, matching the block's existing layout:

```gherkin
  Scenario: A closed pull request lifts the hold to a seeded route
    Given an item held because its latest run exhausted its recapture bound, whose pull request is now closed
    And a work-in-progress ref of that run verified on origin at commit W
    When recovery routing grades the item
    Then the route is seeded from W, not held and not fresh
    And the journal records the seeded route with the reason no-open-pull-request
    And the seeded run runs every stage the workflow requires, proof_capture among them
  Scenario: A resume refused for an unordered head lifts the hold to a seeded route
    Given an item held because its latest run exhausted its recapture bound, whose open pull request's head H no run's record names
    And a work-in-progress ref of that run at commit W whose tip tree differs from H's tree
    When resume --item is taken for the item and refuses naming publishing-run-unobservable
    Then the item carries one livespec-recapture-resume-unobservable comment naming the pull request, H and the work-in-progress ref
    And the item's next recovery routing routes it seeded from its preserved work, with the reason resume-refused-publishing-run-unobservable
  Scenario: A recapture-exhausted item with no verified preserved work stays held
    Given an item held because its latest run exhausted its recapture bound, whose pull request is closed
    And no preserved work of the item is verified on origin and no seed ruling is current
    When recovery routing grades the item
    Then the item is routed held
    And its detail reads "recapture-exhausted: implementation preserved on no preserved work observed ; resume --item <work-item-id> at proof_capture with a proof rider"
  Scenario: A recapture-exhausted item never falls back to fresh
    Given an item held because its latest run exhausted its recapture bound, whose pull request is closed
    When recovery routing grades the item, whatever its preserved work
    Then the route is seeded or held, and never fresh
```

No `## ` heading is added, removed or renamed, so `tests/heading-coverage.json` needs no co-edit.
