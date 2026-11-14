---
topic: needs-attention-surfaces-an-item
author: claude-opus-5-5
created_at: 2026-11-14T04:33:44Z
---

## Proposal: needs-attention surfaces a spec-change hold whose linked topic nobody filed, naming the owning plan as the filer

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The spec-change tier hold names a linked proposal topic, but no clause makes anyone file that proposal or surfaces a hold whose topic was never filed. The only tier-hold hygiene fact, `hygiene:spec-tier-relink`, fires for a ratified relink candidate. This adds `hygiene:spec-tier-unfiled:<work-item-id>`: once a hold's newest tier record is older than a configured bound (default four hours) and its topic names no proposal on the default branch, no revision record, and no open pull request, `needs-attention` surfaces it and names the owning plan epic as the filer. It fails safe on an unreadable pull-request source.

### Motivation

Work item bd-ib-o3kuwr (plan bd-ib-ax3rds, spec-implementation-lockstep), routed by legacy-coordinator-agent (session 719514f8) on 2026-11-14 from throughput-plans-coordinator's finding, and APPROVED. The tier judgement records tier spec-change, verdict unstated, generalization target ## Grooming and slice-size calibration and linked topic needs-attention-surfaces-an-item, at spec 373. Measured in the livespec-dev-tooling tenant, where every item named here sat held on a topic nobody had filed: livespec-dev-tooling-e34ks3 since 2026-11-08 on a-timed-wait-loop-in; livespec-dev-tooling-qeou2e on a-k3s-ci-job-s; livespec-dev-tooling-biq757 since 2026-11-14T01:27Z on test-sandbox-role-retire-s. The hold is correct, but it stays invisible until someone reads the item, because the judge links a topic and moves on and no actor owns filing. Design choices, stated for the grade: (1) Generalize the existing tier-hold hygiene clause instead of adding a new section: the new fact sits beside spec-tier-relink under the same `hygiene` kind and §"Orchestrator-owned attention facts". (2) The owner is the plan epic on the item's parent edges, the plan that holds the item; `none` keeps an orphan visible rather than hidden. (3) Filed means any of three sources, matching how a topic is actually deposited: a pending file on the default branch, any revision record, or an open pull request adding the file. (4) One fact per item: an unfiled topic that also has a relink candidate surfaces only as spec-tier-relink, which already names the way through. (5) Fail-safe: an unreadable pull-request source surfaces the item and says so; it never reads as filed. (6) The bound follows the `_hours` key convention (`dispatcher.ready_aging_threshold_hours`). In-flight alignment, all `align`: a-held-item-s-linked (the record-deposit seam), a-drain-pass-relinks-a (automatic relink to a deposit) and a-spec-change-tier-hold (#5080, a unique derived topic) each change how a topic is recorded or relinked; this proposal only reads whether the recorded topic is filed. Fleet scope: every tenant whose needs-attention runs this plugin.

### Proposed Changes

**1. `SPECIFICATION/contracts.md` §"Grooming and slice-size calibration", the "An autonomy tier is assigned" bullet.** Directly after the sentence "The hold is still released only as this bullet states, and the relink is still the `relink-spec-tier` route's.", insert:

> When an item is held because its linked topic has no revision record with decision `accept` or `modify`, and that topic ALSO names no proposed-change file under `<spec-root>/proposed_changes/` on the governed repository's default branch, no revision record of any decision under `<spec-root>/history/vNNN/proposed_changes/`, and no proposed-change file added by an open pull request against that repository, the topic is UNFILED. Once the item's newest spec-change tier record is older than `dispatcher.spec_tier_unfiled_after_hours` (default `4`), `needs-attention` MUST surface the item under the existing `hygiene` kind as `hygiene:spec-tier-unfiled:<work-item-id>`, per §"Orchestrator-owned attention facts". Its `summary` MUST name the linked topic, how long the hold has stood, and the item's OWNER: the plan epic reached through the item's parent edges, or `none` when no plan epic is among them. Its `handoff` MUST name that owner as the party that files the proposal for the linked topic. An unfiled topic that also has a ratified relink candidate MUST surface once, as the `hygiene:spec-tier-relink` fact above, which already names a way through. When the open-pull-request read cannot be taken, the fact MUST still be surfaced for an item whose topic names no default-branch proposed-change file and no revision record, and its `summary` MUST say that the pull-request read was unavailable. An unreadable source MUST NOT be read as a filed topic. Surfacing the fact MUST NOT release the hold, relink the item, or write any ledger record.

**2. `SPECIFICATION/scenarios.md`, `## Scenario 206 — The spec-change tier is decided by the spec-stated judgement, and a feature waits for ratification`.** Inside that scenario's Gherkin block, after the scenario `A rejected revision is never named as a relink candidate` (and after any scenario another accepted proposal appends there in the same revise), before the block's closing fence, add:

```gherkin
  Scenario: a hold on a topic nobody filed is surfaced to its owning plan
    Given a feature item held at the spec-change tier, a child of a plan epic, whose linked topic names no proposed-change file on the default branch, no revision record and no proposed-change file added by an open pull request
    And its newest spec-change tier record is older than dispatcher.spec_tier_unfiled_after_hours
    When needs-attention runs
    Then it lists one hygiene:spec-tier-unfiled:<work-item-id> fact for the item
    And the fact's summary names the linked topic, how long the hold has stood and the plan epic as owner
    And the fact's handoff names that plan epic as the party that files the proposal
    And the item is still held and no ledger record was written

  Scenario: a filed, young or ownerless unfiled hold
    Given held items whose linked topics are respectively filed on the default branch, filed only by an open pull request, unfiled but held for less than the bound, and unfiled with no plan epic among the item's parents
    When needs-attention runs
    Then neither filed item gets a hygiene:spec-tier-unfiled fact
    And the young item gets no hygiene:spec-tier-unfiled fact
    And the ownerless item's fact names its owner as none

  Scenario: an unreadable pull-request source never reads as filed
    Given a held item whose linked topic names no proposed-change file on the default branch and no revision record, held longer than the bound
    And the open-pull-request read fails
    When needs-attention runs
    Then it lists the hygiene:spec-tier-unfiled fact for the item
    And the fact's summary says that the pull-request read was unavailable
```

No heading is added, removed or renamed, so `tests/heading-coverage.json` needs no edit.
