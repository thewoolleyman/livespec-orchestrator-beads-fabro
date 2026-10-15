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

The v134 refresh-repair route sends a repaired run back through janitor and publish_draft, but two ratified clauses (v116) still say publish_draft only pushes a plain fast-forward, rewrites no other ref, and leaves the lease-guarded force push to pr_refresh alone. A fix turn that rebases onto the advanced default branch makes the run's own previously published head a non-ancestor of the repaired head by construction, so publish_draft refuses it as a divergent prior run and every conflicted pr_refresh still ends at needs_human, one stage later. This proposal makes the spec self-consistent: on re-entry after a refresh-repair round, publish_draft MUST republish the repaired head over the run's own published head, established from its publication record or its validated resume provenance, under an explicit lease on that head. It MUST keep refusing any other divergent tip. It narrows both v116 clauses to that single exception and adds two Scenario 176 sub-scenarios. The exhausted-budget arm of Refresh-repair accounting is untouched.

### Motivation

Measured on hp run 01M504QX5PJF0VM35DMZT99S2D, the bd-ib-un7ch2 resume on released build v0.201.0 (3a2a826a8ac4), the first run after bd-ib-nyovwv gave pr_refresh a single failure edge. The refresh-repair route worked: pr_refresh conflicted in workflow.fabro, refresh_repair routed to fix, fix rebased onto 3a2a826a and resolved the conflict, all 93 check targets passed, and janitor was green. publish_draft then failed after 9 s with "LIVESPEC_PUBLISH_DRAFT_PUSH_FAILED: origin/feat/bd-ib-un7ch2 carries a divergent prior run, so refusing before refresh". The tip it refused, 34966016, was the head this same item had published (PR 3047), which the resume started from. It wrote no refresh-repair brief, so the run ended at needs_human. Implementation is tracked by bd-ib-c435hh (plan publish-draft-green-work-loss, epic bd-ib-acrr56). Its Definition of Done was blocked by the stability freeze driver's Fable review because its first assertion contradicts the two v116 clauses quoted below; the driver ruled spec-first. The alternative of having the fix turn perform the leased push itself was considered and is not taken: it would move publication out of the scripted publication stage.

### Proposed Changes

### contracts.md, §"Definition-of-Done and Proof-of-Done stages", paragraph **Refresh repair.**

After the sentence ending "so only proof for the repaired head can reach publication.", append:

> On that re-entry `publish_draft` MUST establish the run's previously published head from its publication record (`livespec-publish-head`) or its validated resume provenance (`LIVESPEC_RESUME_PUBLISHED_HEAD`), never from a local tracking ref. When origin's publish branch tip is an ancestor of the repaired head, `publish_draft` MUST push a plain fast-forward as before. When the tip equals the run's previously published head and is not an ancestor of the repaired head, `publish_draft` MUST republish the repaired head over that tip with a push leased on that head. Hooks MUST run normally during that push, and it MUST NOT use `--no-verify`, bare force, or a rewrite of any other ref. A non-fast-forward of the run's own published head is the expected result of a repair that rebased, not evidence of a stale or foreign branch. When the tip is neither an ancestor of the repaired head nor the run's previously published head, or when that head cannot be established, `publish_draft` MUST keep failing closed with its existing divergent-prior-run cause and MUST NOT push. This republication applies only on re-entry after a refresh-repair round; a `publish_draft` visit that follows no refresh-repair round MUST NOT rewrite the publish branch.

### contracts.md, §"Stale publish-branch reclaim before a re-dispatch"

```diff
-  request and every record on it remain readable. `publish_draft` is
-  unchanged: it still pushes a plain fast-forward and rewrites no other
-  ref; the reclaim is a HOST-side act because the host is the one party
-  that can answer whether the run that pushed the branch is still alive,
-  and the stages clause grants the lease-guarded force push to the `pr_refresh`
-  node alone.
+  request and every record on it remain readable. `publish_draft` is
+  unchanged here: it pushes a plain fast-forward and MUST rewrite no ref
+  except, on re-entry after a refresh-repair round, the run's own publish
+  branch over the head established from its publication record
+  (`livespec-publish-head`) or its validated resume provenance
+  (`LIVESPEC_RESUME_PUBLISHED_HEAD`), under an explicit lease on that head
+  ("Refresh repair" above). The reclaim is a HOST-side act because the host
+  is the one party that can answer whether the run that pushed the branch is
+  still alive, and every other lease-guarded rewrite of a publish branch
+  belongs to the `pr_refresh` node.
```

### contracts.md, §"Resume from a published pull request (`resume --item`)", paragraph **Unchanged.**

```diff
-**Unchanged.** `publish_draft` still pushes a plain fast-forward and
-rewrites no other ref; the `pr_refresh` node's lease-guarded force push stays the
-only rewrite of a publish branch; `reconcile-merged` still refuses an
+**Unchanged.** `publish_draft` still pushes a plain fast-forward and MUST
+rewrite no ref except, on re-entry after a refresh-repair round, the run's own
+publish branch over the head established from its publication record
+(`livespec-publish-head`) or its validated resume provenance
+(`LIVESPEC_RESUME_PUBLISHED_HEAD`), under an explicit lease on that head; apart
+from that one republication, the `pr_refresh` node's lease-guarded force push
+stays the only rewrite of a publish branch; `reconcile-merged` still refuses an
```

The exhausted-budget arm of §"Refresh-repair accounting" (`refresh-repair-exhausted`) MUST remain unchanged.

### scenarios.md, `## Scenario 176`

Inside the existing gherkin block, after the scenario "A resumed run restores its resume provenance head", insert:

```gherkin
  Scenario: A repaired pr_refresh republishes over the run's own published head
    Given a run whose published head on origin is P, established from its publication record or its validated resume provenance
    And its pr_refresh rebase conflicted and the fix turn integrated the default branch into a repaired head R that does not contain P
    When the run re-enters publish_draft after janitor passes on R
    Then publish_draft pushes R over P with a push leased on P
    And the run enters proof_capture for R rather than needs_human

  Scenario: publish_draft still refuses a foreign divergent tip after a repair
    Given a run that re-enters publish_draft after a refresh-repair round with repaired head R and previously published head P
    And origin's publish branch tip is T, which is neither an ancestor of R nor equal to P
    When publish_draft publishes
    Then publish_draft fails closed with its divergent-prior-run cause and pushes nothing
```

No `## ` heading is added, removed or renamed, so `tests/heading-coverage.json` MUST NOT change.
