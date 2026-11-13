---
topic: recovery-routing-reads-a-rework
author: claude-opus-5-5:factory-run-work-preservation
created_at: 2026-11-12T17:55:12Z
---

## Proposal: A rework return after a merge is recorded on the ledger and lets recovery routing route the rework

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Two gaps meet in one routing decision. First, the ratified text makes a merged pull request ALWAYS a non-fallback refusal (§"Factory-configurable ACP fallback priority"), yet the shipped router (bd-ib-nkoyln, cd98919a0) lifts it when a rework rejection was journaled after the merge. That exemption is right, because otherwise `reconcile-merged` closes out an unfinished rework, but it is unratified. Second, the router reads that rejection ONLY from the dispatching clone's journal. The journal is gitignored and local to one clone, and the ledger carries no timestamped rework return. This proposal ratifies the exemption, and makes both rework returns also write a timestamped `livespec-rework-rejection` ledger comment. Routing then reads a return from either source. Unreadable instants keep the hold. Six new Scenario 185 scenarios exercise it, and two existing ones are qualified to match.

### Motivation

Owning work item bd-ib-xc74il, "Recovery routing reads a rework rejection only from the dispatching clone's journal, so a reader that misses the row holds a reworked item on its pre-rework merge", a child of plan factory-run-work-preservation (epic bd-ib-nckst7). Its spec-change-tier judgement (2026-11-12, verdict partial, topic recovery-routing-reads-a-rework) found the journal half stated and the ledger comment and the merge ordering unstated. legacy-coordinator-agent ranked it LOW, at the end of the orchestrator revise queue, because no live item is misrouted today.

Measured 2026-11-12 on bd-ib-5d5aue (build 58fb211b056e). Its branch carries #4046 (merged 2026-11-01T09:59:52Z) and #4328 (merged 2026-11-03T23:15:32Z). The primary checkout's 522,667-line journal holds its human-valve-reject-rework records at 2026-11-01T11:03:12Z and 2026-11-04T09:48:19Z. Read against the full journal, routing is seeded from needs-human/a045fd5f at 8246ef5b7. A probe that read only the journal's last 200,000 lines missed both records and read held, with "pull request #4328 is already merged ... close the item out with reconcile-merged". An earlier reading of the same shape, on v0.309.2 (2026-11-09), drove a close-out order the coordinator then retracted. The ledger carried only the acceptance -> active status move and the boolean rework:pending label, neither of which can be ordered against the merge.

In-flight survey (2026-11-12 about 17:00Z): no remote spec/* branch or open pull request edits the active-entry bullet or the non-fallback sentence. The two proposals this seat merged today (an-operator-preserve-writes-a and a-run-routed-fresh-can) both append scenarios to Scenario 185; this one appends after every existing scenario, so the three compose in any revise order. Out of scope, dropped by the coordinator as a spec change: letting a seed ruling later than a merge lift the merged refusal.

### Proposed Changes

1. contracts.md, §"Work-item state semantics": in the bullet that begins "- `active` is entered ONLY by a journaled dispatch", IMMEDIATELY AFTER its sentence "Both are named here because a door rule that omits a shipped writer is false, not merely incomplete.", append these sentences to the same bullet, indented as its continuation lines:

"Each rework return MUST ALSO write one ledger comment on the item whose first line is the marker `livespec-rework-rejection` and which names the return's kind — `reject:rework` with its invoker, or `acceptance-auto-rework` with the disposition that took it — and the UTC instant of the return. The comment MUST pass the shared template-opener detector before it is written. The journal record stays required. The ledger comment exists because a journal is local to the clone that wrote it, while a reader in any clone or on any host must be able to order a rework return against the item's other events."

2. contracts.md, §"Factory-configurable ACP fallback priority": in the sentence "Every other refusal is *non-fallback*: the earlier run is live, the item's dispatch-scoped ownership lock is held by a live process, or the pull request is merged (its remedy stays `reconcile-merged --item`).", replace "or the pull request is merged (its remedy stays `reconcile-merged --item`)" with "or the pull request is merged and no rework return of the item is recorded after the merge (its remedy stays `reconcile-merged --item`)". Then, IMMEDIATELY AFTER the sentence "The not-ready refusal cannot apply, because routing grades a `ready` item.", insert:

"A pull request that merged BEFORE a recorded rework return of the item is a fallback-permitting refusal, not a non-fallback one. The merged change was returned to rework, so "no unmerged publication is left" no longer means the item's work is complete, and routing MUST grade the rework through the preference order this clause states. Routing MUST read rework returns from BOTH sources: the item's `livespec-rework-rejection` ledger comments, and the journal's rework-return records for the item, either record: the reject valve's `human-valve-reject-rework` record, or the automatic disposition's record, which has stage `auto-disposition` and disposition `ai-fail-auto-rework`. A return from either source that is later than the merge instant the forge reports suffices. A return instant or merge instant that cannot be read MUST be treated as no return after the merge, so the merged refusal keeps its non-fallback precedence and the item is held."

Also in that paragraph, replace "so a merged pull request is never treated as a missing anchor" with "so a merged pull request with no later recorded rework return is never treated as a missing anchor".

No other sentence of either contracts.md section changes.

3. scenarios.md, §"Scenario 185 — A released item's recovery route is decided before admission and executed per item, and a deferred item keeps its branch": inside that section's gherkin block, append these six scenarios at its END, IMMEDIATELY BEFORE the block's closing fence, after every scenario already in the block, including any that an earlier revise of this cycle appended. Separate them from the preceding scenario by one blank line:

```gherkin
  Scenario: A rework return recorded on the ledger after a merge lets routing route the rework
    Given an item released for recovery whose pull request merged at instant M
    And a livespec-rework-rejection ledger comment on the item records a reject:rework return at an instant later than M
    And the dispatching clone's journal holds no rework-return record for the item
    And the item holds a needs-human ref that carries one of its earlier runs
    When the Dispatcher grades the item's recovery route
    Then the merged pull request is graded as a fallback-permitting refusal
    And the route is seeded from that needs-human ref

  Scenario: A rework return journaled after a merge still lets routing route the rework
    Given an item released for recovery whose pull request merged at instant M
    And the journal holds a human-valve-reject-rework record for the item at an instant later than M
    And the item carries no livespec-rework-rejection ledger comment
    When the Dispatcher grades the item's recovery route
    Then the merged pull request is graded as a fallback-permitting refusal

  Scenario: A merged pull request with no later rework return holds the route
    Given an item released for recovery whose pull request merged at instant M
    And neither a livespec-rework-rejection ledger comment nor a rework-return journal record for the item is later than M
    When the Dispatcher grades the item's recovery route
    Then the route is held and the refusal names reconcile-merged --item

  Scenario: A rework return writes its ledger comment
    Given an item resting in acceptance
    When drive --action reject:<id>:rework succeeds
    Then the item carries one ledger comment whose first line is livespec-rework-rejection, naming reject:rework, the invoker and the UTC instant of the return

  Scenario: The automatic rework disposition writes its ledger comment
    Given an item resting in acceptance whose acceptance pass takes the AI-fail automatic rework disposition
    When the Dispatcher returns the item to rework
    Then the item carries one ledger comment whose first line is livespec-rework-rejection, naming acceptance-auto-rework, the disposition and the UTC instant of the return

  Scenario: An unreadable rework return or merge instant leaves the route held
    Given an item released for recovery whose pull request merged
    And the merge instant, or the instant of every rework return recorded for the item, cannot be read
    When the Dispatcher grades the item's recovery route
    Then the route is held and the refusal names reconcile-merged --item
```

4. scenarios.md, the same Scenario 185 gherkin block: qualify the two existing scenarios that the new rule would otherwise contradict.
- In `Scenario: A merged pull request holds a released item and keeps the reconcile-merged remedy`, replace the step "Given a ready released item whose publish branch carries a merged pull request" with "Given a ready released item whose publish branch carries a merged pull request, and no rework return of the item is recorded after the merge".
- In `Scenario: A non-fallback refusal still holds an item that carries a seed ruling`, replace the step "And the item's pull request is merged, or its earlier run is live" with "And the item's pull request is merged and no rework return of the item is recorded after the merge, or its earlier run is live".

No other scenario changes. No H2 heading is added, removed or renamed, so `tests/heading-coverage.json` needs no co-edit.
