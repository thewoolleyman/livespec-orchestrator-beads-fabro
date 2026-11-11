---
topic: plan-record-posting-renders-artifact
author: claude-opus-5-5
created_at: 2026-11-11T12:51:48Z
---

## Proposal: The plan record posting primitive renders a record's artifact paths line from an optional build artifact_paths array

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State how the one posting primitive that renders plan records carries the artifact paths that v350 made part of a plan Proof of Done record's build identity. The primitive accepts an optional artifact_paths array of repository-relative paths with the build identity it is given. When the array is present and non-empty, the primitive renders it as the record's `artifact paths:` line. When the array is absent, it renders no such line. It refuses a malformed value and posts nothing. Without this, v350 requires a record to carry an `artifact paths:` line that no session may hand-format and that the primitive has no stated way to produce.

### Motivation

At v350 (df7f359b5, livespec-orchestrator-beads-fabro#4938, proposal plan-record-release-applies-per-component), a record in a component-declaring repository MUST name its artifact paths on an `artifact paths:` line in its build identity. The same paragraph says one posting primitive renders every plan record, so that no session hand-formats one. The v350 revise deliberately left the primitive's payload field unstated as implementation detail. The dispatcher's spec-stated judgement then read carrier bd-ib-qpibvm as PARTIAL at drive (2026-11-11T12:31:53Z, spec-change tier, generalization target "## Planning Lane realization"). Its five gate-judgement assertions are stated, and the assertion that the primitive accepts an optional build.artifact_paths array and renders it is not. The coordinator session legacy-coordinator-agent ruled a split: bd-ib-qpibvm keeps the five stated assertions, and this proposal states the sixth for its own carrier. The case is homelab plan secret-writer-stored-key-alias (epic homelab/hl-bvycoc). Its proof record must name the writer's artifact paths through this primitive, so it needs both halves released.

### Proposed Changes

In SPECIFICATION/contracts.md, §"Planning Lane realization" → "### Plan Definition of Done and Proof of Done", in the plan Proof of Done record paragraph, immediately after the sentence ending "and MUST refuse a `verified` post whose computed identity equals that of the `captured` record it replays.", insert:

> The primitive MUST accept, with the build identity it is given, an optional `artifact_paths` array of repository-relative paths. When that array is present and non-empty it MUST render it as the record's `artifact paths:` line, naming every path in the order given, and when it is absent it MUST NOT render that line. It MUST refuse a value that is not an array of non-empty strings, naming the field, and post nothing.

In SPECIFICATION/scenarios.md, append one scenario with an unnumbered heading, as v349 and v350 did:

## Scenario: the plan record posting primitive renders a record's artifact paths line

```gherkin
Feature: the plan record posting primitive renders a record's artifact paths line

  Scenario: a payload naming artifact paths renders the artifact paths line
    Given a captured plan Proof of Done payload stating release none with the default-branch commit
    And its build identity carries the artifact_paths array tools/shared_credentials_provisioning/ and infra/shared-credentials/write-secret.sh
    When the posting primitive renders the record
    Then the record's build identity carries an artifact paths line naming tools/shared_credentials_provisioning/ and infra/shared-credentials/write-secret.sh in that order

  Scenario: a payload naming no artifact paths renders no artifact paths line
    Given a captured plan Proof of Done payload whose build identity carries no artifact_paths array
    When the posting primitive renders the record
    Then the record carries no artifact paths line

  Scenario: a malformed artifact paths value is refused and nothing is posted
    Given a captured plan Proof of Done payload whose build identity carries an artifact_paths value that is not an array of non-empty strings
    When the posting primitive is invoked
    Then it refuses naming artifact_paths
    And no record is posted
```

At revise, tests/heading-coverage.json gains a TODO row and tests/heading-coverage-debt.json a debt row for the new heading. Both are owned by this proposal's implementation carrier, the item titled "Plan record posting renders artifact paths ...", whose derived topic stem equals this proposal's topic. Spec size: one sentence group added, one scenario added.
