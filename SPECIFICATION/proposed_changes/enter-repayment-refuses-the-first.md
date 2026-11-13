---
topic: enter-repayment-refuses-the-first
author: claude-opus-5-5
created_at: 2026-11-13T20:06:53Z
---

## Proposal: enter-repayment admits the first green descendant master run when every red job on the landed commit's own run is pre-existing and attributed to another recorded incident

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The incident authority's enter-repayment admits only a complete green master run whose head is a landed commit. When the landed commit's own run was red only on a defect another recorded incident owns and fixes, no such run can ever exist, so repayment is unreachable without a re-run or a fabricated binding. This proposal admits the first complete green descendant run under four mechanically checked conditions, keeps the successor on the landed commit, and records the per-job attribution on the chain.

### Motivation

Work item bd-ib-ah5t7i (orchestrator tenant), filed 2026-11-13 on legacy-coordinator-agent's direction, priority 3. Measured on livespec-dev-tooling-xdt4ue: landed commit b2bc5a66's own master run 43480337708 failed only on export-telemetry. That job had already failed on the run of its first parent afd694cd (43476456232), introduced by 71220a770 and owned by incident livespec-dev-tooling-ii557b, whose fix is 3324c2392. The first green descendant run, 43494686574 on 3324c2392, was refused with incident-repayment-master-ci-outstanding (rc 78). The code is _incident_repayment_plan._master_ci_complete, which requires master_ci.head in attempt.landed_commits. plan_repayment takes the successor's base, head and input_parent from master_ci.head but staged_tree from the landed commit, so a descendant run must not move those fields. The coordinator ruled that attribution must rest on the attributing incident's authority history, never on a caller's assertion. ii557b's history retains no failed master run today (its entry records only prose), so the pre-existence leg also accepts the first-parent run, an authenticated forge read that proves the expedited merge did not introduce the job. Rejected alternatives: re-running the landed commit's run (it fails the same way until the other fix lands); admitting any green descendant (it would let a repayment inherit an unexplained red).

### Proposed Changes

**1. Repayment entry on an attributed descendant run (`contracts.md` §"Expedited incident lifecycle").**

In the paragraph that begins "After the expedited merge's complete normal master CI succeeds, the incident MUST remain unfinished and enter one same-item normal factory repayment.", insert the following immediately after its second sentence ("Its eligibility MUST derive from the recorded successful attempt and outstanding repayment, even though an earlier PR already merged."):

> The complete normal master CI success that admits repayment entry is a complete successful normal master run whose head is one of the attempt's landed commits. The incident authority writer's `enter-repayment` action MUST also admit the first complete successful normal master run whose head descends from a landed commit L of the attempt, when and only when every one of the following holds:
>
> - L's own complete normal master run concluded failure.
> - Every job that failed on L's own run is pre-existing. It also failed, under the same job name, either on the complete normal master run of L's first parent, or on a failed normal master run retained in the authority history of the incident it is attributed to.
> - Each such job is attributed to another recorded incident of the same repository, other than this item. That incident's authority history holds a landed commit that is an ancestor of the admitted run's head and is not an ancestor of L.
> - No complete successful normal master run exists whose head descends from L and is a proper ancestor of the admitted run's head.
>
> The writer MUST establish each condition by an authenticated forge read or from the incident authority history. The operator names the attributing incident, but a caller's assertion alone MUST NOT satisfy any condition. When any condition fails or cannot be read, `enter-repayment` MUST refuse with `incident-repayment-master-ci-outstanding`, naming the first condition that failed, and MUST write nothing.
>
> A repayment successor admitted on a descendant run MUST keep L as its base, its head and its carrier's input parent, with L's landed tree as the staged tree. It MUST NOT pair the descendant's commit with L's tree. Its recorded master-CI evidence MUST name the admitted run and its head, L, L's own failed run, and the run on which each failed job was shown to be pre-existing. For each job that failed on L's own run, it MUST also name the attributing incident and that incident's landed fix commit.

**2. Scenario (`scenarios.md`).**

Add the following heading at the end of `scenarios.md`, followed by its gherkin block:

## Scenario 371 — An incident whose landed commit's master run was red only on another incident's defect enters repayment on the first green descendant run

```gherkin
Feature: repayment entry on an attributed descendant master run
  Scenario: A descendant run is admitted when every red job is pre-existing and attributed
    Given an incident attempt in master-observation whose landed commit L's own complete master run concluded failure only on job J
    And J also failed on the complete master run of L's first parent
    And another recorded incident of the same repository has a landed fix commit F that descends from L
    And the first complete successful master run whose head descends from L has head F
    When the operator drives enter-repayment naming that run and attributing J to the other incident
    Then the item enters repayment-admission
    And the successor's base, head and carrier input parent are L, with L's landed tree staged
    And its recorded master-CI evidence names the admitted run, L's failed run, the first-parent run, J, the other incident and F
  Scenario: A descendant run is refused when a red job has no attribution
    Given the same attempt, but J did not fail on L's first parent's run and no attributing incident retains a failed run naming J
    When the operator drives enter-repayment naming the green descendant run
    Then it refuses with incident-repayment-master-ci-outstanding naming the unattributed job
    And the item's phase, generation and authority history are unchanged
```

