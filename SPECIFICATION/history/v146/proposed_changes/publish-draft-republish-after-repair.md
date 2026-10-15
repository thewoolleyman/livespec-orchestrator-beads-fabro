---
topic: publish-draft-republish-after-repair
author: claude-opus-5-5
created_at: 2026-10-15T17:02:50Z
---

## Proposal: publish_draft republishes over the run's own published head after a refresh repair

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md


### Summary

The v134 refresh-repair route sends a repaired run back through janitor and publish_draft, but two ratified clauses (v116) still say publish_draft only pushes a plain fast-forward, rewrites no other ref, and leaves every lease-guarded rewrite of a publish branch to pr_refresh. A fix turn that rebases onto the advanced default branch makes the run's own previously published head a non-ancestor of the repaired head by construction, so publish_draft refuses it as a divergent prior run and every conflicted pr_refresh still ends at needs_human, one stage later. This proposal makes the spec self-consistent. On the publish_draft visit that follows a refresh-repair round, publish_draft MUST republish the repaired head over the run's own previously published head under an explicit lease against that head, and MUST keep refusing any other divergent tip. The run's previously published head is established from its own publication record when it has one, otherwise from its validated resume provenance. The proposal narrows both v116 clauses to that single exception and narrows the fix turn's rewrite allowance so pr_refresh and this republication remain the only rewrites of a publish branch. It amends Scenario 144's last sub-scenario and adds two Scenario 176 sub-scenarios. The exhausted-budget arm of Refresh-repair accounting is untouched.

### Motivation

Measured on hp run 01M504QX5PJF0VM35DMZT99S2D, the bd-ib-un7ch2 resume on released build v0.201.0 (3a2a826a8ac4), the first run after bd-ib-nyovwv gave pr_refresh a single failure edge. The refresh-repair route worked: pr_refresh conflicted in workflow.fabro, refresh_repair routed to fix, fix rebased onto 3a2a826a and resolved the conflict, all 93 check targets passed, and janitor was green. publish_draft then failed after 9 s with "LIVESPEC_PUBLISH_DRAFT_PUSH_FAILED: origin/feat/bd-ib-un7ch2 carries a divergent prior run, so refusing before refresh". The tip it refused, 34966016, was the head this same item had published (PR 3047), which the resume started from. It wrote no refresh-repair brief, so the run ended at needs_human. Implementation is tracked by bd-ib-c435hh (plan publish-draft-green-work-loss, epic bd-ib-acrr56). Its Definition of Done was blocked by the stability freeze driver's Fable review because its first assertion contradicts the two v116 clauses quoted below; the driver ruled spec-first. The alternative of having the fix turn perform the leased push itself was considered and is not taken: it would move publication out of the scripted publication stage, so this proposal also removes the fix turn's own rewrite allowance. In the implementation the run's publication record is the run-scoped `livespec-publish-head` state and its validated resume provenance reaches the sandbox as `LIVESPEC_RESUME_PUBLISHED_HEAD`, exactly the two sources `pr_refresh` already reads in that order; the normative text below names neither, because the specification names no publication-state file.

### Proposed Changes

#### contracts.md, §"Definition-of-Done and Proof-of-Done stages", paragraph **Refresh repair.**

Replace the fix turn's rewrite allowance so the fix turn rewrites no ref:

```diff
-turn MUST NOT use `--no-verify`, bare force, or a rewrite of any ref other than
-the run's own publish branch under an explicit lease. After a refresh-repair
-round the run re-enters `janitor`, then `publish_draft`, then `proof_capture`,
+turn MUST NOT use `--no-verify`, bare force, or a rewrite of any ref. After a
+refresh-repair round the run re-enters `janitor`, then `publish_draft`, then `proof_capture`,
```

Then, after the sentence ending "so only proof for the repaired head can reach publication.", append:

> The `publish_draft` visit that follows a refresh-repair round is the visit immediately after the `janitor` visit that follows a `fix` visit entered with a refresh-repair brief; a `publish_draft` visit reached through a review-fix round, or any other path, follows no refresh-repair round. On the visit that follows a refresh-repair round, `publish_draft` MUST establish the run's previously published head as the head the run's last completed `publish_draft` pushed, read from the run's own record as §"The cancel record" reads it, when the run has recorded one, and otherwise as the head named by the run's validated resume provenance; it MUST NOT establish it from a local tracking ref. When origin has no tip for the publish branch, or its tip is an ancestor of the repaired head, `publish_draft` MUST push a plain fast-forward as before. When the tip is not an ancestor of the repaired head and equals the run's previously published head, `publish_draft` MUST republish the repaired head with an explicit lease against the recorded remote head of this run's own publish branch. Hooks MUST run normally during that push, and it MUST NOT use `--no-verify`, bare force, or a rewrite of any other ref. A non-fast-forward of the run's own published head is the expected result of a repair that rebased, not evidence of a stale or foreign branch. When the tip is not an ancestor of the repaired head and either differs from the run's previously published head or that head cannot be established, `publish_draft` MUST keep failing closed with its existing divergent-prior-run cause and MUST NOT push. A `publish_draft` visit that follows no refresh-repair round MUST NOT rewrite the publish branch.

#### contracts.md, §"Stale publish-branch reclaim before a re-dispatch"

```diff
-  request and every record on it remain readable. `publish_draft` is
-  unchanged: it still pushes a plain fast-forward and rewrites no other
-  ref; the reclaim is a HOST-side act because the host is the one party
-  that can answer whether the run that pushed the branch is still alive,
-  and the stages clause grants the lease-guarded force push to the `pr_refresh`
-  node alone.
+  request and every record on it remain readable. `publish_draft` is
+  unchanged here: it pushes a plain fast-forward and MUST rewrite no ref
+  except, on the visit that follows a refresh-repair round, the run's own
+  publish branch over the run's previously published head, established from
+  its publication record when the run has recorded one and otherwise from its
+  validated resume provenance, with an explicit lease against the recorded
+  remote head of this run's own publish branch ("Refresh repair" above). The
+  reclaim is a HOST-side act because the host is the one party that can answer
+  whether the run that pushed the branch is still alive, and every other
+  lease-guarded rewrite of a publish branch belongs to the `pr_refresh` node.
```

#### contracts.md, §"Resume from a published pull request (`resume --item`)", paragraph **Unchanged.**

```diff
-**Unchanged.** `publish_draft` still pushes a plain fast-forward and
-rewrites no other ref; the `pr_refresh` node's lease-guarded force push stays the
-only rewrite of a publish branch; `reconcile-merged` still refuses an
+**Unchanged.** `publish_draft` still pushes a plain fast-forward and MUST
+rewrite no ref except, on the visit that follows a refresh-repair round, the
+run's own publish branch over the run's previously published head, established
+from its publication record when the run has recorded one and otherwise from
+its validated resume provenance, with an explicit lease against the recorded
+remote head of this run's own publish branch; apart from that one
+republication, the `pr_refresh` node's lease-guarded force push stays the only
+rewrite of a publish branch; `reconcile-merged` still refuses an
```

The exhausted-budget arm of §"Refresh-repair accounting" (`refresh-repair-exhausted`) MUST remain unchanged.

#### scenarios.md, `## Scenario 144`

In the sub-scenario "The reclaim is a host-side act and publish_draft is unchanged", the Given line MUST change so the sub-scenario covers only visits that follow no refresh-repair round:

```diff
-    Given a dispatched run whose publish_draft stage runs
+    Given a dispatched run whose publish_draft stage runs with no refresh-repair round before it
```

#### scenarios.md, `## Scenario 176`

Inside the existing gherkin block, after the scenario "A resumed run restores its resume provenance head", insert:

```gherkin
  Scenario: A repaired pr_refresh republishes over the run's own published head
    Given a run whose previously published head on origin is P, established from its publication record when it has one and otherwise from its validated resume provenance
    And its pr_refresh rebase conflicted and the fix turn integrated the default branch into a repaired head R that does not contain P
    When the run re-enters publish_draft after janitor passes on R
    Then publish_draft pushes R with an explicit lease against the recorded remote head of this run's own publish branch, P
    And the run enters proof_capture for R rather than needs_human

  Scenario: publish_draft still refuses a foreign divergent tip after a repair
    Given a run that re-enters publish_draft after a refresh-repair round with repaired head R and previously published head P
    And origin's publish branch tip is T, which is neither an ancestor of R nor equal to P
    When publish_draft publishes
    Then publish_draft fails closed with its divergent-prior-run cause and pushes nothing
```

No `## ` heading is added, removed or renamed, so `tests/heading-coverage.json` MUST NOT change.
