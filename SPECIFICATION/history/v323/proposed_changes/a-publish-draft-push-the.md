---
topic: a-publish-draft-push-the
author: claude-opus-5-5
created_at: 2026-11-08T02:48:20Z
---

## Proposal: A publish_draft push refused for an oversize file or by the pre-push hook takes a repair brief to fix

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a publish-repair route beside Refresh repair. When origin refuses a publish_draft push with GitHub's GH001 large-file error, or the repository's pre-push hook refuses it, publish_draft records a repair brief naming the refusal and routes to fix, while the refresh-repair budget of two rounds lasts. Every other push refusal stays fail-closed with its cause named: a protected branch, non-fast-forward, an unreachable origin, and authentication. A refused publish push no longer ends the run with LIVESPEC_REFRESH_REPAIR_ABSENT.

### Motivation

Work item bd-ib-7owmkq, plan publish-draft-green-work-loss (epic bd-ib-acrr56). It was filed on legacy-coordinator-agent's R301 ruling "FILE it" (session a21903eb, 2026-11-08). The same ruling confirmed that the item is spec-change tier and confirmed the narrowing to the two refusals the fix node can repair.

Measured instance, reported by gmktec-factory-placement from a fabro dump:
- Run: ob-td6fup (openbrain), run 01M6WF7GHVJX4NGBK1R4XHY8KW on petri, build 0.303.0.
- Ending: needs-human at 2026-11-08T02:34:32Z, after publish_draft@1 and then refresh_repair@1, recorded as LIVESPEC_REFRESH_REPAIR_ABSENT.
- Actual cause: GitHub refused the push with GH001, because the implement commit carried /workspace/.pnpm-store/v10/files/... at 119 MB and 124 MB.
The run's work had passed janitor. The fix node could drop the files from the run's unpublished commits, but the ratified text sends every publish refusal to fail-closed: "The stages" says "In every case the node still fails closed before proof_capture", and "Refresh repair" says "every other cause keeps its existing fail-closed behaviour". So the run was lost. Scenario 224's pre-push-hook case states the same fail-closed outcome. A pre-push hook refusal on publish is likewise repairable inside a fix turn.

Why the narrowing: fix can neither change branch protection nor reconcile a foreign stale branch, and it cannot repair an unreachable origin or failed credentials. Those keep their ratified routes. Sharing the refresh-repair budget bounds the new route with the existing two-round limit rather than a new counter.

In-flight alignment: this aligns with proposed_changes/janitor-refresh-merge-grades-once.md (bd-ib-yqjaut), which changes how the janitor grades a refresh merge and does not touch publish_draft's refusal routes. Out of scope: the ABSENT cause naming after a briefless refresh failure (bd-ib-abbb3j), and the upstream guard that keeps .pnpm-store off the branch (openbrain's .gitignore and kubernetes-sandbox-backend's store directory).

### Proposed Changes

In `contracts.md` §"Self-contained plugin dispatch" → "The stages", and in that section's "Refresh repair" passages, make four edits.

1. In "The stages" paragraph, the sentence "In every case the node still fails closed before `proof_capture`." MUST be replaced by:

"A GH001 rejection MUST name each path the rejection names together with the size it reports. A pre-push hook refusal and a GH001 rejection MUST instead take the publish-repair route of "Publish repair" below while the refresh-repair budget lasts. Every other refusal, including a protected-branch refusal, a non-fast-forward rejection, an origin that cannot be reached and an authentication failure, still fails closed before `proof_capture`, and so does a pre-push hook refusal or a GH001 rejection once that budget is spent."

Here, a GH001 rejection is origin refusing the push with GitHub's GH001 large-file error.

2. Directly after the "Refresh repair" paragraph (the one ending "... so only proof for the repaired head can reach publication."), a new paragraph MUST be added:

**Publish repair.** When origin refuses a `publish_draft` push with GitHub's GH001 large-file error, or the repository's pre-push hook refuses it, `publish_draft` MUST record a repair brief and MUST route to the existing `fix` agent node, as a refresh-repair round does. The brief MUST name the stage, the head whose push was refused, and the cause. For a GH001 rejection, the cause is each path the rejection names together with the size it reports. For a hook refusal, it is each target the hook names as failed together with the last 80 lines of the hook's own output. The `fix` turn MUST remove each named path from every commit of the run that origin does not already hold, or repair each named target. It MUST NOT rewrite a commit origin already holds, MUST let hooks run normally, and MUST NOT use `--no-verify` or bare force. A publish-repair round is a refresh-repair round for every other rule of this section: it is counted by "Refresh-repair accounting", the run then re-enters `janitor`, then `publish_draft`, then `proof_capture`, and the `publish_draft` visit after it follows a refresh-repair round. A protected-branch refusal, a non-fast-forward rejection, an origin that cannot be reached and an authentication failure MUST NOT take this route. A publish_draft refusal MUST NOT end the run at `needs_human` with `LIVESPEC_REFRESH_REPAIR_ABSENT`. Scenario <N> in `scenarios.md` exercises this paragraph.

3. In "Refresh-repair accounting", the sentence "A run MAY take at most two refresh-repair rounds in total across the janitor's pre-aggregate refresh and `pr_refresh`;" MUST become "A run MAY take at most two refresh-repair rounds in total across the janitor's pre-aggregate refresh, `pr_refresh` and `publish_draft`;". Every other sentence of that paragraph is unchanged, so a third round fails closed to `needs_human` with the named cause `refresh-repair-exhausted`.

4. In the "Refresh repair" paragraph, the sentence "only a conflict, a commit-hook refusal of the refresh's own commit, or a gate rejection takes this route, and every other cause keeps its existing fail-closed behaviour." MUST become "only a conflict, a commit-hook refusal of the refresh's own commit, or a gate rejection takes this route, a `publish_draft` push refusal takes it only as "Publish repair" below states, and every other cause keeps its existing fail-closed behaviour."

In `scenarios.md`, make two edits.

5. In `## Scenario 224 — A refused publish_draft push names the cause that refused it`, the case "A pre-push hook refusal names its failed targets" MUST replace its last step "And the run fails closed before proof capture" with "And the run routes to fix with a repair brief naming lint and format". Add this case:

```gherkin
  Scenario: A GH001 rejection names each oversize path
    Given a publish_draft push origin refuses with GitHub's GH001 large-file error naming path P at 119 MB
    When publish_draft reports the failure
    Then its output names the GH001 rejection, path P and its size
```

6. Add a new scenario, numbered as the next free scenario number at revise time, headed `## Scenario <N> — A publish_draft push refused for an oversize file or by the pre-push hook is repaired through fix`, with the governing-clause line `contracts.md` §"Self-contained plugin dispatch" → "Publish repair" and this body:

```gherkin
Feature: Publish repair for a repairable push refusal
  As the operator of a repository dispatched through the factory
  I want a push refusal the run itself can repair to reach the fix node
  So that a green run is not lost to an oversize file or a hook failure

  Scenario: a GH001 rejection reaches fix with a brief naming the oversize path
    Given a run whose publish_draft push origin refuses with GH001 naming path P at 119 MB
    And the run has taken no refresh-repair round
    When publish_draft fails
    Then the run routes to fix with a repair brief naming publish_draft, the refused head, path P and its size
    And the run does not end at needs_human with LIVESPEC_REFRESH_REPAIR_ABSENT

  Scenario: the fix turn removes the oversize path and the run republishes
    Given a fix turn entered with a publish-repair brief naming path P
    When the fix turn completes
    Then no commit of the run that origin does not hold carries path P
    And no commit origin already held was rewritten
    And the run re-enters janitor, then publish_draft, then proof_capture

  Scenario: a pre-push hook refusal reaches fix with its failed targets
    Given a run whose publish_draft push the repository pre-push hook refuses naming failed target lint
    When publish_draft fails
    Then the run routes to fix with a repair brief naming lint and the last 80 lines of the hook output

  Scenario: a protected-branch refusal stays fail-closed
    Given a run whose publish_draft push origin refuses because the branch is protected
    When publish_draft fails
    Then the run fails closed before proof capture with its output naming the protected-branch refusal
    And the run does not route to fix

  Scenario: a publish repair counts toward the refresh-repair budget
    Given a run that has taken two refresh-repair rounds
    And its publish_draft push origin refuses with GH001
    When publish_draft fails
    Then the run fails closed to needs_human with the named cause refresh-repair-exhausted
```

In the same revise, `tests/heading-coverage.json` MUST gain an entry for the new scenario heading (spec_root `SPECIFICATION`, spec_file `scenarios.md`, test `TODO`), with a reason naming the owning work item bd-ib-7owmkq, per the revise co-edit discipline. The Scenario 224 heading is unchanged, so its entry stands.

Fleet scope, stated for the reviser: `publish_draft` is a node of the plugin's bundled `implement-work-item` workflow, so this amendment governs every repository dispatched through that workflow. Forked workflow copies converge on it by their own re-sync.
