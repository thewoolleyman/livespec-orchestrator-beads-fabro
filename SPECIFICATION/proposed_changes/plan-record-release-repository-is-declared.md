---
topic: plan-record-release-repository-is-declared
author: claude-opus-5-5
created_at: 2026-11-01T01:58:49Z
---

## Proposal: A plan record's release repository must be the governed repository or one the plan epic declares

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Since v148 a plan Proof of Done record's release repository is whatever repository its first installed build identifier names, so a record can satisfy the release rule by naming any unrelated repository that happens to carry the tag. This change closes that loophole: the release repository MUST be the plan's governed repository or a repository the plan epic's Definition of Done section declares on one optional `Release repositories:` line, and the archive gate MUST reject a record naming any other repository, naming it. It amends the existing release-repository sentences of the plan Proof of Done record paragraph and adds one scenario to Scenario 135's neighbourhood as Scenario 283.

### Motivation

Item bd-ib-y6mj57 ("Restrict a plan record's release repository to the governed repository or a child work-item's repository"), filed as this R1 bd-ib-j6uvkj residual under plan spec-implementation-lockstep (epic bd-ib-ax3rds), coordinator ruling 2026-11-01T00:21:09Z. OWNING PLAN: the item has no parent edge. It came from the independent review of proposal plan-proof-release-rule-names-the-build-repository (ratified v148), which was raised for livespec plan k3s-on-gmktec-for-vps-usage (epic livespec-sab5gn, livespec tenant); the proof leg in this repository was owned by plan definition-and-proof-of-done (epic bd-ib-7sjdzv), which is now closed and archived. The revise therefore has no live owning plan to route to and SHOULD be reviewed by whoever revises the proof leg; the maintainer approved filing this tightening on 2026-10-13. Judged a FEATURE (a stricter ratified gate, new behaviour), not a bug: the implementation conforms to the v148 text. DEVIATION FROM THE ITEM'S WORDING, for the reviewer to accept or modify: the item asks to allow 'the repository of one of the plan epic's child work-items', but no clause gives a child work-item a machine-readable repository (batch 2 of bd-ib-j6uvkj recorded exactly that gap), and in this fleet each repository has its own ledger tenant, so a plan epic's children are in the governed repository's tenant and that rule would admit only the governed repository, re-breaking the livespec-sab5gn case v148 was ratified to fix. A declared list on the epic is machine-readable and keeps that case passing. If accepted, bd-ib-y6mj57's Definition of Done assertion must be re-worded to the declared-list form and re-pointed at Scenario 283.

### Proposed Changes

In SPECIFICATION/contracts.md, in the plan Proof of Done record paragraph under "### Plan Definition of Done and Proof of Done", replace the sentence

> The gate MUST NOT accept a tag merely because some repository carries it: the tag MUST be carried by the record's release repository.

with:

> The gate MUST NOT accept a tag merely because some repository carries it: the tag MUST be carried by the record's release repository, and that release repository MUST be the plan's governed repository or a repository the plan epic's Definition of Done section names on its one optional `Release repositories:` line (whitespace- or comma-separated entries, each `<owner>/<repository>` or a bare `<repository>` under the governed repository's forge owner). The archive gate MUST reject a record whose release repository is any other repository, naming that repository and the declared set, and MUST NOT judge that record against the governed repository instead. A `Release repositories:` line is not a plan assertion and is not graded by the effective-criteria primitive.

In SPECIFICATION/scenarios.md, append:

## Scenario 283 — A plan record naming an undeclared repository's release is rejected

```gherkin
Feature: A plan record's release repository is bounded by the plan
  Scenario: A declared sibling repository's release is accepted
    Given a plan epic whose Definition of Done section declares a sibling repository on its Release repositories line
    And a plan Proof of Done record whose installed build identifier names that sibling repository and a tag its remote carries
    When the archive gate evaluates the proof leg
    Then the record is accepted as evidence
  Scenario: An undeclared repository's release is rejected
    Given a plan epic that declares no Release repositories line
    And a plan Proof of Done record whose installed build identifier names an unrelated repository whose remote carries the named tag
    When the archive gate evaluates the proof leg
    Then the record is rejected naming that repository and the declared set
    And the record is not judged against the governed repository
```

The existing Scenario 135 step 'A record names a sibling repository's release' then additionally needs its plan to declare that sibling; at revise, amend its Given to add 'And the plan epic declares the sibling repository on its Release repositories line'. Spec size: one sentence extended, one scenario added. At revise, `tests/heading-coverage.json` gains an entry for the Scenario 283 heading.
