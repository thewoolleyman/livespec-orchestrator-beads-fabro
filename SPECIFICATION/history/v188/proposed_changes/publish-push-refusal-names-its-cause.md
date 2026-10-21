---
topic: publish-push-refusal-names-its-cause
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T17:42:50Z
---

## Proposal: A refused publish_draft push names which of its three causes refused it

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A failed post-merge janitor and a failed engine checkpoint commit each name the hook's failed targets ("Failed post-merge janitor target attribution", "Failed engine checkpoint commit attribution"). A refused `publish_draft` push has no such rule, so its output attributes every refusal to a stale publish branch, including a pre-push hook failure. The needs-human cause then sends triage to the wrong remedy. This proposal extends the same attribution to the publication push. A refusal names which cause refused it: a pre-push hook, naming its failed targets by the same structured-summary rule; a non-fast-forward rejection, directing the operator to reconcile the stale publish branch; or an unreachable origin. The run still fails closed before proof capture.

### Motivation

Work-item bd-ib-35kfra. Commit 8342c3c5 (2026-10-14) partly superseded its framing by routing a refreshed head the repository gate rejects to repair, as the 2026-10-16 rider records. But the push refusal's output still does not distinguish the three causes, and freeze-driver ruling R68 held the item because assertions 1 to 3 are ungoverned. Plan spec-implementation-lockstep R1 batch 6 routes it here as a third surface of the existing failed-targets attribution rather than a new attribution rule.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Definition-of-Done and Proof-of-Done stages", paragraph "**Scripted publication and proof-head integrity.**", insert immediately BEFORE the sentence beginning "All touched nodes MUST retain an unconditional outgoing edge" the following sentences:

> When the `publish_draft` push is refused, its output after the push-failed marker MUST name which cause refused it. A pre-push hook refusal MUST name the hook's failed targets, by the structured-summary rule of §"Failed post-merge janitor target attribution". A non-fast-forward rejection MUST direct the operator to reconcile the stale publish branch. An origin that cannot be reached MUST be named as such. In every case the node still fails the run closed before proof capture. Scenario 224 in `scenarios.md` exercises these sentences.

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 224 — A refused publish_draft push names the cause that refused it

```gherkin
Feature: A publication refusal sends triage to the right remedy
  As an operator triaging a run that could not publish
  I want the refusal to say what refused the push
  So that a hook failure is never mistaken for a stale publish branch

  Scenario: A pre-push hook refusal names its failed targets
    Given a publish_draft push the repository pre-push hook refuses with a Failed targets summary naming lint and format
    When publish_draft reports the failure
    Then its output names the pre-push hook as the cause and names lint and format
    And the run fails closed before proof capture

  Scenario: A non-fast-forward rejection points at the stale branch
    Given a publish_draft push origin rejects as non-fast-forward
    When publish_draft reports the failure
    Then its output names the non-fast-forward rejection and directs reconciling the stale publish branch

  Scenario: An unreachable origin is named
    Given a publish_draft push that cannot reach origin
    When publish_draft reports the failure
    Then its output names the unreachable origin as the cause
```

