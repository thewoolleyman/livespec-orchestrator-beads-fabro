---
topic: a-stale-preserved-seed-is
author: claude:factory-run-work-preservation plan seat session 8a6b35
created_at: 2026-11-13T05:02:32Z
---

## Proposal: A stale preserved seed is re-seeded by diff-applying its work onto the current default-branch tip as one authored commit, never by rebase

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Add one paragraph to contracts.md §"Factory-configurable ACP fallback priority", directly after the paragraph "A ruled seed names the tree a released item's next dispatch starts from.". It defines the diff-apply reseed, and makes it the only way the Dispatcher moves a seed onto the default branch's current tip. Given a seed whose merge base with the default branch is not that tip, the Dispatcher computes the seed's diff against its merge base, applies it to the tip's tree in a scratch clone, records ONE commit whose parent is the tip and whose subject is authored and names the work item and the source seed ref, publishes it at `refs/livespec/reseed/<work-item-id>/<reseed-commit>`, verifies the ref by one remote read, and seeds the dispatch from it. A seed that carries no work is never reseeded, and nothing is published. An apply conflict publishes nothing, holds the item with the refusal `seed-reseed-conflict` naming every conflicting path, and leaves a ledger comment for the owner. A rebase, a cherry-pick sequence or a janitor refresh MUST NOT be used to move a seed. When the pending proposal a-stale-seed-is-rebased-before-it-runs is ratified in the same or an earlier pass, its rebase and rebase-conflict bullets are replaced by this paragraph. Add one numberless scenario, its heading-coverage entry, and the regenerated debt-register row.

### Motivation

bd-ib-5xihdt (plan factory-run-work-preservation, epic bd-ib-nckst7) is at pending-approval at spec-change tier. Its filing-time tier record (spec version 364) names the linked topic a-stale-preserved-seed-is and the generalization target ## Factory-configurable ACP fallback priority. legacy-coordinator-agent (session f8c15059, 2026-11-13) ordered this seat to cut the proposal, FLEET SCOPE: every preserve writer and every seeded relaunch path. This proposal is filed under exactly that topic.

THE INCIDENT, measured by legacy-coordinator-agent at about 04:08Z on 2026-11-13. Six seeded relaunches had to be hand-built, because every recorded seed base was past the coordinator's threshold of about 50 commits behind origin/master: livespec-dev-tooling-7sqr36 (wip/5 at 8e6cd938c, 94 behind and 66 ahead), livespec-dev-tooling-64ik6g (wip/4 at dda5c9bc8, 77 behind), livespec-dev-tooling-wc6sxv (wip/3 at 8686eeb24, 72 behind), bd-ib-rczglr (wip/2 at e8b5a1b59, 63 behind), livespec-dev-tooling-ehug6z (wip/4 at 0c63b579f, 60 behind) and bd-ib-v75dlb (needs-human/e87ffa04 at 88e04926f, 55 behind). The coordinator's rule, in force as the v0.325.0 mitigation: a stale seed is re-seeded by DIFF-APPLY onto current master, never by a janitor refresh rebase. THE LIVE INSTANCE: with no sanctioned reseed route, legacy-coordinator-agent (session f8c15059) ruled at about 05:0xZ on 2026-11-13 that the Dispatcher's six queued seeds relaunch FRESH with a reference rider naming their preserved work, so each discards its seed rather than starting from a seed built by hand. This paragraph is the route that lets such a relaunch keep its seed.

WHY NOT A REBASE. A rebase replays each of the seed's commits and stops inside a rebase at the first conflict. Inside a run, the fix stage that continues such a rebase is refused by the commit runner's authored-subject guard (LIVESPEC_COMMIT_NO_AUTHORED_SUBJECT; bd-ib-vpvdn4, proposal the-commit-runner-s-authored, #5110), which is the defect class this route avoids. A diff-apply produces one commit with one authored subject and either applies or names its conflicting paths, with no partial operation left behind. A seed 66 commits ahead is one apply rather than 66 replays.

WHAT THE SPEC SAYS TODAY. No ratified clause names a diff-apply reseed (contracts.md, scenarios.md, constraints.md and spec.md on origin/master searched case-insensitively for "diff-apply", "diff apply", "reseed" and "re-seed": one hit in all four, "pre-seeded" in a pi trust sentence of contracts.md, which is unrelated). The ruled-seed paragraph checks out the ruled commit as it stands. The pending proposal a-stale-seed-is-rebased-before-it-runs (2026-11-11) requires every seeded route to move its seed onto the default branch's tip before the run, by REBASE, published under refs/heads/seed-rebased/; it holds on a rebase conflict and routes a work-free seed fresh. This proposal keeps that proposal's routing decisions and replaces only its mechanism, its ref and its conflict refusal.

RELATIONSHIP TO PENDING PROPOSALS. a-stale-seed-is-rebased-before-it-runs: REFINE. Its routing rules stand; its third and fourth bullets are replaced by change 2 below when both are ratified; if it is rejected, this paragraph still governs every move of a seed onto the tip, and the ruled-seed and preference-order routes stay unchanged. a-seeded-dispatch-whose-seed (the reclaim's preservation ref as a seed's read path): ALIGN; a reseed reads the seed commit from whatever ref that paragraph names, and publishes its own ref. preserve-runs-sh-keeps-every and an-operator-preserve-writes-a govern operator preserve copies and refs: ALIGN, no overlap. Placement after the ruled-seed paragraph composes with a-stale-seed-is-rebased-before-it-runs, which inserts BEFORE that paragraph, and with a-seeded-dispatch-whose-seed, which also inserts after it: the revise orders the two inserted paragraphs with a-seeded-dispatch-whose-seed first, because a reseed reads the seed through the ref that paragraph names.

### Proposed Changes

### 1. `SPECIFICATION/contracts.md` §"Factory-configurable ACP fallback priority": add one paragraph

Insert this paragraph directly AFTER the paragraph whose opening sentence is **A ruled seed names the tree a released item's next dispatch starts from.** (and after the paragraph that a-seeded-dispatch-whose-seed inserts there, when that proposal is ratified first), separated by one blank line. No existing paragraph changes:

```markdown
**A stale seed is re-seeded by diff-applying its work onto the default branch's tip.** A *seed* here is the commit a `seeded` route would start a run from, whether it comes from the preference order of this clause or from a current seed ruling. A seed is *stale* when its merge base with the repository's default branch, read from the forge remote, is not that branch's current tip. Whenever the Dispatcher starts a run from a stale seed, it MUST move the seed onto the default branch's current tip by a *diff-apply reseed*, and MUST NOT move it by a rebase, a cherry-pick sequence, a merge, or a janitor or refresh stage. A diff-apply reseed MUST take these steps, in a scratch clone outside every checkout and every sandbox, with the repository's hooks disabled: it computes the binary diff from the seed's merge base with the default branch to the seed commit; when the seed's tree is identical to the tree of that merge base, the seed carries no work, exactly as "A needs-human tree is recognised by the run it carries" defines it, and the reseed MUST stop, publish nothing, and report the seed's ref and commit with the statement that it carries no work; otherwise it applies the diff, with a three-way apply, to the tree of the default branch's tip; when the apply leaves any path unmerged or rejected, the reseed MUST stop and publish nothing; otherwise it records ONE commit whose only parent is the default branch's tip and whose tree is that tip's tree with the diff applied. That commit's subject MUST be authored, never a generated rebase, merge or fixup subject, and MUST name the work item and the source seed ref, as `reseed <work-item-id> from <seed ref> onto <default branch>`, and its message MUST carry the trailers `Livespec-Reseed-Source: <seed ref> <seed commit>` and `Livespec-Reseed-Onto: <tip commit>`, with full commit ids. The Dispatcher MUST publish the commit at `refs/livespec/reseed/<work-item-id>/<reseed commit>`, and MUST confirm by one remote read that the ref stands at that commit before it reports the reseed done or starts a run from it. The run MUST then start from the reseed commit, and the seed record MUST name that ref as its preservation reference and the reseed commit's full id as its immutable commit, together with the source seed ref and commit and the tip commit. The reseed MUST NOT move, delete or rewrite the source seed's ref, any needs-human ref, any preservation ref, or any checkout. A seed that carries no work MUST NOT be routed `seeded`, and the `recovery-route` record MUST list it as passed over with the reason `no-change`. When the apply conflicts, the route MUST be `held`: the `recovery-held` record MUST name the refusal `seed-reseed-conflict`, the seed's ref and commit, the tip commit and every conflicting path, the Dispatcher MUST add one ledger comment on the item that names the same so the item's owner can resolve it, a current seed ruling MUST stay current, and routing MUST NOT fall through to another preserved tree, to the observed published head, or to `fresh`. Holding for a reseed conflict is a `held` cause in its own right. A default branch, a tip, a diff or an apply that cannot be read or attempted, and a publication whose remote read does not confirm the ref, are the existing unobservable-measurement hold, and MUST NOT be read as a conflict, as a clean apply, or as the absence of work. Reseed refs MUST be deleted on the same terms as the item's `refs/livespec/preserved-publish/<work-item-id>/` refs under §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Preservation refs are deleted when the Dispatcher closes or collects an item's runs". An operator or coordinator that seeds a dispatch by hand MUST seed it from a ref this paragraph's reseed published, or from a seed that is not stale. Every writer of preserved work is covered through the seed it becomes: a needs-human ref, a work-in-progress ref and a preserved-publish ref reach a seed through the preference order of this clause, and an operator `refs/heads/preserve/run-<run-id>` ref, which that order does not rank, reaches one only through a seed ruling that names it. A seed from any of them is reseeded by this paragraph when it is stale, and this paragraph adds no ref to the preference order.
```

### 2. Composition with the pending proposal a-stale-seed-is-rebased-before-it-runs

When that proposal is ratified in the same revise pass as this one, or earlier, the revise MUST make these edits to its paragraph "**A seed is rebased onto the current default branch before its run starts.**", and no others:

- Its heading sentence MUST become: **A seed is moved onto the current default branch before its run starts.**
- Its third bullet, which begins "Otherwise the Dispatcher MUST rebase the seed's work onto the default branch's tip before the run starts.", MUST become: "Otherwise the Dispatcher MUST move the seed onto the default branch's tip by the diff-apply reseed of the paragraph \"A stale seed is re-seeded by diff-applying its work onto the default branch's tip\" before the run starts, and the run, the seed record and the goal brief MUST name the reseed commit and its ref as that paragraph states."
- Its fourth bullet, which begins "When the rebase conflicts, the route MUST be `held`.", MUST become: "When the reseed's apply conflicts, the route MUST be `held` as that paragraph states, with the refusal `seed-reseed-conflict`."
- In its closing paragraph, "a rebase that cannot be read or attempted" MUST become "a reseed that cannot be read or attempted", and "a clean rebase" MUST become "a clean apply".

Its first two bullets, its once-per-pass tip read, and its rule that no seeded run starts behind the tip read in the pass, are unchanged. Its scenario's references to `refs/heads/seed-rebased/`, to a rebase and to `seed-rebase-conflict` MUST be read as `refs/livespec/reseed/<work-item-id>/`, a reseed and `seed-reseed-conflict`, and the revise MUST edit that scenario's text to match. When that proposal is rejected, this change is void and change 1 stands alone.

### 3. `SPECIFICATION/scenarios.md`: add one scenario, numbered at revise

The heading is numberless here. The revise pass MUST assign the next free scenario number and update the heading text in changes 4 and 5 to match.

~~~markdown
## Scenario: a stale seed is re-seeded by diff-apply onto the default branch's tip, and a conflicting or work-free seed publishes nothing

```gherkin
Feature: A seeded relaunch far behind the default branch needs no hand-built seed
  As the operator of a factory whose recovery relaunches start from preserved seeds
  I want a stale seed moved onto the current default branch as one authored commit
  So that no seed is rebased inside a run and no relaunch has to be built by hand

  Scenario: A stale seed is re-seeded and the run starts from the reseed commit
    Given a repository whose default branch on origin is main at commit T
    And item W released for recovery whose seed ref S stands at commit P, whose merge base with main is 60 commits behind T
    And the diff from that merge base to P applies to T's tree without conflict
    When the Dispatcher routes and dispatches W
    Then it records one commit R whose only parent is T and whose tree is T's tree with that diff applied
    And R's subject is "reseed W from S onto main" and its message carries Livespec-Reseed-Source and Livespec-Reseed-Onto trailers naming S, P and T
    And a remote read shows refs/livespec/reseed/W/R at R before the run starts
    And the run starts from R, and the seed record names that ref, R's full commit id, S, P and T
    And S still stands at P

  Scenario: A conflicting apply publishes nothing and holds the item for its owner
    Given item W released for recovery whose stale seed ref S at commit P has a diff that conflicts with main's tip T in two paths
    When the Dispatcher routes W
    Then the route is held, and the recovery-held record names seed-reseed-conflict, S, P, T and both paths
    And the item carries one ledger comment naming the same
    And no ref under refs/livespec/reseed/W/ exists on origin and no run is launched

  Scenario: A seed that carries no work is never re-seeded
    Given item W released for recovery whose seed ref S stands at commit P, whose tree equals the tree of its merge base with main
    When the Dispatcher routes W
    Then no commit is recorded and no ref under refs/livespec/reseed/W/ is published
    And the recovery-route record lists S at P as passed over with the reason no-change

  Scenario: A seed already based on the tip is used unchanged
    Given item W released for recovery whose seed's merge base with main is main's current tip
    When the Dispatcher routes and dispatches W
    Then no reseed commit is recorded and the run starts from the seed commit
```
~~~

### 4. `tests/heading-coverage.json`: add the new heading in the same revise

The revise that ratifies this MUST add one entry, using the heading as numbered at revise:

```json
{"heading": "## Scenario: a stale seed is re-seeded by diff-apply onto the default branch's tip, and a conflicting or work-free seed publishes nothing", "spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "test": "TODO", "work_item": "bd-ib-5xihdt", "reason": "An integration-tier test is owed by bd-ib-5xihdt: the reseed route driven against a local bare origin whose default branch has advanced past the seed's merge base."}
```

### 5. `tests/heading-coverage-debt.json`: regenerate it in the same revise

The register is generated, never authored by hand. The revise MUST regenerate it with `uv run python -m livespec_dev_tooling.heading_coverage_debt` and stage the result. The generated row is expected to read:

```json
{"spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "heading": "## Scenario: a stale seed is re-seeded by diff-apply onto the default branch's tip, and a conflicting or work-free seed publishes nothing", "work_item": "bd-ib-5xihdt", "first_seen": "<revise date>"}
```

No existing heading changes, per AGENTS.md §"Revise co-edit discipline".

### 6. Follow-through outside the spec (not part of this revise)

On ratification, bd-ib-5xihdt's Definition of Done `References:` line SHOULD name the new scenario heading, as numbered at revise, and its spec-change tier is then re-classified. Its bullet "leaves the item blocked for its owner" is met by the `held` route and the owner-facing ledger comment this paragraph requires; the groom that re-references the Definition of Done SHOULD reword that bullet to match.
