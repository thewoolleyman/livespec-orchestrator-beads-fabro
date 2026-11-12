---
topic: an-operator-preserve-writes-a
author: claude-opus-5-5:factory-run-work-preservation
created_at: 2026-11-12T13:19:47Z
---

## Proposal: A writer that finds a run's needs-human ref behind the tree it preserves moves that ref forward rather than writing a second one

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The ratified text states only how recovery routing READS needs-human refs: §"Factory-configurable ACP fallback priority" → "A needs-human tree is recognised by the run it carries, not only by its ref name" treats every ref whose tip carries the run's trailer as the run's terminal tree and takes the descendant, else the newest. No clause says how a writer NAMES the ref when the run's needs-human ref already exists. An operator preserve therefore writes a SHA-suffixed sibling whenever the existing ref stands at any other commit, even an ancestor of the tree it preserves, so one dispatch's tree is split across two refs and any reader that names the dispatch-id ref sees the older one. This proposal adds one write-side paragraph after the recognition paragraph. A writer that finds the existing ref at an ancestor MUST move it forward with a push that is not forced and MUST NOT write a second ref. A suffixed ref is permitted only on genuine divergence or a rejected forward push, and an operator preserve tool MUST then write it. No preservation write may force-move or delete an existing needs-human ref, and an operator tool reports a write verified only after a remote listing shows it. Three scenarios in Scenario 185 exercise it.

### Motivation

Owning work item bd-ib-4jxlnn, "An operator preserve writes a second needs-human/<dispatch id>-<sha12> ref when the existing dispatch-id ref is an ancestor of the new tree, instead of moving it forward", under plan factory-run-work-preservation (epic bd-ib-nckst7, plan assertion 2). Its spec-change-tier judgement holds it at tier spec-change, verdict unstated, linked topic an-operator-preserve-writes-a, spec v360: the ratified text covers only the reader side. legacy-coordinator-agent asked this seat (2026-11-12) to decide and file the root fix for one canonical preserve ref per dispatch id, with fleet scope across every preserve writer and reader.

Measured 2026-11-12 (implement-test-performance, re-measured by this seat with git ls-remote and git merge-base): livespec-dev-tooling-vobfwi's dispatch 5faca392f7b649cba9871e9dd4f3b15d has refs/heads/needs-human/5faca392f7b649cba9871e9dd4f3b15d at 45462e564 (10:52Z) and refs/heads/needs-human/5faca392f7b649cba9871e9dd4f3b15d-7e2fdab549ef at 7e2fdab54 (12:09Z). 45462e564 is an ancestor of 7e2fdab54 (4 commits, 7 files, +233/-35), and both tips carry Fabro-Run: 01M77NNDRVN7541CHG5WT34J15. A coordinator window table and a dispatch-id check named only the unsuffixed ref, so a re-dispatch seeded from them would have dropped the newer work. The cause is dev-tooling/preserve/preserve_runs.sh's PRESERVE_WRITE_NEEDS_HUMAN block, which suffixes on any other commit without reading ancestry.

Fleet survey of writers (this repository at bcdef38e5): the workflow's needs_human terminal pushes HEAD to refs/heads/needs-human/<dispatch id> without force, so it already conforms. It moves an ancestor forward, and on divergence its push is rejected and it reports LIVESPEC_NEEDS_HUMAN_PUSH_FAILED, which is the 'report that the tree was not preserved' arm. preserve_dispatch.sh delegates to preserve_runs.sh. represerve.sh, the work-in-progress captures and the preserved-publish refs write no needs-human ref. No writer force-pushes a needs-human ref today. The reader half is unchanged and is carried by bd-ib-7gssim, bd-ib-qshcwc and bd-ib-i6wxdw.

Alternative considered and rejected: one canonical ref per dispatch that every write overwrites, with history kept as tags. A forced overwrite on divergence would move the ref off a tree the run's own ending wrote (the hazard measured on bd-ib-azhnw5 and livespec-dev-tooling-t5ct2q, 2026-11-07, which is why the block is create-only today), and the tags would be a second namespace every reader must list. Fast-forward-only keeps the old tip in history, and divergence keeps both refs, which the ratified recognition rule already selects between.

In-flight survey (2026-11-12 about 13:20Z): ten remote spec/* branches and four open spec-touching pull requests (#5050 the-engine-s-per-stage, #5048 incident-read-history-returns-only, #5035 a-commit-settle-node-whose, #5005 a-needs-human-rest-overwrites). None edits the recognition paragraph or names a needs-human ref writer's naming; #5005 concerns the admission label of a needs-human rest. Two pending in-tree proposals mention needs-human refs, and this proposal aligns with both: a-stale-seed-is-rebased-before-it-runs, which rebases a seed and leaves ref naming untouched, and a-commit-settle-abort-preserves-the-in-progress-resolution, which edits the publication-confinement sentence about which refs a run's preservation may push, not how an existing one is moved.

### Proposed Changes

1. contracts.md, §"Factory-configurable ACP fallback priority": IMMEDIATELY AFTER the paragraph that begins "**A needs-human tree is recognised by the run it carries, not only by its ref name.**" and ends "The field MUST be an empty list when there is none, and MUST NOT be omitted.", and BEFORE the paragraph that begins "A confirmed absence of preserved work permits a plain dispatch from the default branch", insert this paragraph, separated from each by one blank line:

"**A writer that finds a run's needs-human ref behind the tree it preserves moves that ref forward rather than writing a second one.** This paragraph governs every writer that preserves a run's tree to a needs-human ref named under one of the run's identifiers, `refs/heads/needs-human/<id>` where `<id>` is the run's dispatch id or run id: the workflow's `needs_human` terminal, an operator preserve tool such as `dev-tooling/preserve/preserve_runs.sh`, and any other. When that ref already exists on the item's repository at a commit other than the commit being preserved, the writer MUST read whether the existing commit is an ancestor of the preserved commit before it writes, and an ancestry it cannot read MUST be treated as not an ancestor. When the existing commit is an ancestor, the writer MUST move that ref to the preserved commit with a push that is not forced, and MUST NOT write any other needs-human ref for that commit. When the existing commit is not an ancestor, or when the push that would move the ref is rejected because the ref has meanwhile moved to a commit that is not an ancestor of the preserved commit, the writer MUST leave the ref where it stands, and MUST either write the preserved commit to `refs/heads/needs-human/<id>-<p>`, where `<p>` is the first twelve hexadecimal digits of the preserved commit, or report that the tree was not preserved on a needs-human ref. An operator preserve tool MUST take the first of those two, because no later step of the run preserves the tree in its place. A preservation write MUST NOT move an existing needs-human ref with a forced push and MUST NOT delete one. An operator preserve tool MUST report a needs-human write as verified only after a remote ref listing shows the ref it names at the preserved commit, and its report MUST name that ref and, when it moved an existing ref, the commit the ref moved from. A suffixed ref this paragraph permits carries the run under the paragraph above whenever its tip commit holds the run's trailer, so recovery routing chooses between it and the unsuffixed ref by descent exactly as that paragraph states."

No other paragraph of the section changes. In particular, the recognition paragraph's selection rule — the descendant, else the newest by committer time, else byte order — stays exactly as it is; this paragraph adds only the write side.

2. scenarios.md, §"Scenario 185 — A released item's recovery route is decided before admission and executed per item, and a deferred item keeps its branch": inside that section's gherkin block, insert these three scenarios IMMEDIATELY AFTER `Scenario: An unreadable ancestry between refs carrying one run holds the route, even when one is named under a run identifier` (whose last step is "And the route is not seeded from needs-human/U") and BEFORE `Scenario: A recovery route with nothing passed over records an empty list`, each separated from its neighbours by one blank line:

```gherkin
  Scenario: An operator preserve moves a dispatch-id needs-human ref forward onto a tree that descends from it
    Given an earlier run of the item, dispatched as D, carried by refs/heads/needs-human/D at commit S1
    And an operator preserve of that run preserves commit S2, which descends from S1
    When the preserve writes the run's needs-human ref
    Then a remote ref listing of origin shows refs/heads/needs-human/D at S2
    And it shows no ref refs/heads/needs-human/D-<first twelve hexadecimal digits of S2>
    And the preserve's report names refs/heads/needs-human/D and S1 as the commit it moved from, and reports the write verified

  Scenario: An operator preserve keeps a diverged dispatch-id needs-human ref and writes a suffixed one
    Given an earlier run of the item, dispatched as D, carried by refs/heads/needs-human/D at commit S1
    And an operator preserve of that run preserves commit S2, which does not descend from S1
    When the preserve writes the run's needs-human ref
    Then a remote ref listing of origin shows refs/heads/needs-human/D still at S1
    And it shows refs/heads/needs-human/D-<first twelve hexadecimal digits of S2> at S2

  Scenario: A forward move rejected after a concurrent write falls back to the suffixed ref
    Given refs/heads/needs-human/D at commit S1, and an operator preserve of commit S2, which descends from S1
    And before the preserve's push lands, another writer moves refs/heads/needs-human/D to commit S3, which is not an ancestor of S2
    When the preserve's push, which is not forced, is rejected
    Then a remote ref listing of origin shows refs/heads/needs-human/D still at S3
    And it shows refs/heads/needs-human/D-<first twelve hexadecimal digits of S2> at S2
```

No H2 heading is added, removed or renamed, so `tests/heading-coverage.json` needs no co-edit.
