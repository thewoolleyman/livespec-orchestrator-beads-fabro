---
topic: plan-record-release-applies-per-component
author: claude-opus-5-5
created_at: 2026-11-11T06:03:51Z
---

## Proposal: A plan record's release rule applies per declared release component, not per repository

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Let a governed repository declare its release components: a name, a release-tag prefix and the repository paths each component ships. Where it does, a plan Proof of Done record names the repository paths of each artifact its steps ran from the default-branch tree. A release applies to that artifact only when one of those paths lies in a declared component that carries a release tag, so `release: none` is true, and accepted, for an artifact no released component ships. A repository that declares no components keeps today's per-repository rule unchanged, and a release tag that matches no declared component keeps that rule for the whole repository, so nothing becomes more permissive by omission.

### Motivation

Measured 2026-11-11 on plan secret-writer-stored-key-alias (epic homelab/hl-bvycoc, homelab tenant). homelab carries two stable releases, state-backend-v0.1.0 and shared-credentials-v0.2.0. The second is a zipapp built by tools/shared_credentials/build-artifact.sh from tools/shared_credentials/*.py only: the seal and launch host tool. The plan's artifact is a different one, the canonical secret writer (tools/shared_credentials_provisioning/ through infra/shared-credentials/write-secret.sh). No build script packages it, no release contains it, and the plan's Definition of Done requires it to run from main (`git merge-base --is-ancestor add991a shared-credentials-v0.2.0` is false). Under the plan Proof of Done record paragraph, a release applies whenever the release repository carries any release tag, so every record this plan could publish is rejected: one stating `release: none` is rejected as 'states release none, and a release applies to its release repository'; one naming shared-credentials-v0.2.0 would assert that the writer ran from an artifact that does not contain it; one naming another repository's build to escape the rule routes around the gate. The plan has every child closed and its outcome observed (both tenants' claude-cred-status read usable / HTTP 200 on 2026-11-11), yet it cannot archive truthfully. The same holds for every future plan in any repository that releases some components and runs others from the default branch, and no homelab plan has archived since those releases appeared on 2026-11-02. The rule's own purpose, that a record proves the build adopters actually install, is served by scoping it to the component that ships the artifact: a component that releases still requires its released artifact, and an artifact that no component releases has no release to name. The coordinator session (legacy-coordinator-agent) ruled branch (a) on 2026-11-11 after a measurement that the writer lies outside every released component: file this change spec-first, with that plan as the case, and hold its proof until ratification. Relation to pending proposal plan-record-release-repository-is-declared: that one bounds WHICH repository a record may name; this one decides, within the named repository, WHETHER a release applies. The two compose, and neither amends the sentence the other replaces.

### Proposed Changes

In SPECIFICATION/contracts.md, in the plan Proof of Done record paragraph under "### Plan Definition of Done and Proof of Done", replace the sentence beginning "Where a release applies to the plan's work — the release repository carries at least one release tag —" through "naming the missing release identity and the release repository it judged." with:

> Where a release applies to the plan's work, a `captured` record taken against an unreleased tree is not evidence: the steps MUST run against the released artifact installed through its normal installation path, and the archive gate MUST reject a record that states `release: none` where a release applies, or names, as its first release tag, a tag the release repository does not carry, naming the missing release identity and the release repository it judged. Whether a release applies is decided per repository unless the release repository is the governed repository and that repository declares release components. A repository declares them in its committed `.livespec.jsonc` as a committed-only `dispatcher.release_components` array, each entry carrying a `name`, a `tag_prefix` and a non-empty `paths` array of repository-relative path prefixes. A malformed array MUST be refused with a configuration finding naming the offending key, and the archive gate MUST then reject every record of that repository rather than fall back to either rule. Without that declaration a release applies when the release repository carries at least one release tag. With it, each release tag belongs to the declared component whose `tag_prefix` it begins with, and a record MUST name, beside the default-branch commit, the repository paths of each artifact its steps ran from that tree, on an `artifact paths:` line in its build identity. A release then applies to the plan's work exactly when one of those paths lies under a `paths` entry of a component that owns at least one release tag, and only that component's tags satisfy the rule for that artifact. A record stating `release: none` whose artifact paths lie under no such component is evidence on this leg. A record stating `release: none` that names no artifact paths is judged as if the repository declared no components. A release tag owned by no declared component makes a release apply to the whole repository, exactly as if it declared none. Artifact paths are recorded, not verified, beyond their placement in the declared components; the replaying party of a `verified` record is the one who checks that the steps ran what the record names.

In SPECIFICATION/scenarios.md, append one scenario at the next scenario number free at revise time (pending proposals already claim numbers up to 346):

## Scenario <next> — A plan record's release rule applies to the release component that ships its artifact

```gherkin
Feature: A release applies to the component that ships the artifact a plan record exercised
  Background:
    Given a governed repository that is the plan's release repository
    And its committed configuration declares release component shared-credentials with tag prefix shared-credentials-v and path tools/shared_credentials/
    And its forge carries the release tag shared-credentials-v0.2.0
  Scenario: An artifact no released component ships states release none
    Given a captured plan Proof of Done record stating release none with the default-branch commit
    And its artifact paths line names tools/shared_credentials_provisioning/ only
    When the archive gate evaluates the proof leg
    Then the record is not rejected for its release identity
  Scenario: An artifact a released component ships needs that component's release
    Given a captured plan Proof of Done record stating release none with the default-branch commit
    And its artifact paths line names tools/shared_credentials/seal.py
    When the archive gate evaluates the proof leg
    Then the record is rejected naming the missing release identity and the component shared-credentials
  Scenario: A release tag no declared component owns keeps the repository-wide rule
    Given the forge also carries the release tag state-backend-v0.1.0 and no declared component's tag prefix matches it
    And a captured plan Proof of Done record stating release none whose artifact paths line names tools/shared_credentials_provisioning/ only
    When the archive gate evaluates the proof leg
    Then the record is rejected naming the missing release identity and the release repository
  Scenario: A record naming no artifact paths keeps the repository-wide rule
    Given a captured plan Proof of Done record stating release none with no artifact paths line
    When the archive gate evaluates the proof leg
    Then the record is rejected naming the missing release identity and the release repository
```

The existing Scenario 135 step 'A record captured against an unreleased tree is not evidence' stays true as written, because its repository declares no release components. At revise, `tests/heading-coverage.json` gains an entry for the new scenario heading, and the posting primitive's payload gains an optional `artifact_paths` array on `build`, rendered as the `artifact paths:` line. Spec size: one sentence replaced by one paragraph, one scenario added.
