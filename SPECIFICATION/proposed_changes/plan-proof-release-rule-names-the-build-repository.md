---
topic: plan-proof-release-rule-names-the-build-repository
author: claude-opus-5-5
created_at: 2026-10-13T10:20:17Z
---

## Proposal: Judge a plan record's release tag against the remote of the repository its build identity names

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The plan Proof of Done release rule currently judges both whether a release applies and whether a named release tag is real against the plan's governed repository only. A plan anchored in one repository whose work ships as another repository's releases can therefore never pass the proof leg with honest records. This change judges the rule against the RELEASE REPOSITORY a record names in its installed build identifier, and reads that repository's release tags from its remote on the forge, never from a local clone. A bare repository name means the same forge owner as the governed repository. When the record names no repository the forge knows, the governed repository is used, as today. It adds a scenario for the accepted and rejected sibling-repository cases.

### Motivation

The livespec plan k3s-on-gmktec-for-vps-usage (epic livespec-sab5gn) is anchored in the livespec repository, but its work shipped as livespec-dev-tooling releases. Its plan Proof of Done records were captured at livespec-dev-tooling v1.95.12 and independently verified at v1.96.1. Each record's build identity says so, for example 'Installed build: livespec-dev-tooling release v1.95.12'. archive_thread refused both records as naming 'a release tag this repository does not carry', because the gate collects tags only from livespec. The gate conforms to the ratified text, so the text must change: re-capturing against a livespec tag would misstate the artifact the steps actually exercised. The maintainer approved this direction on 2026-10-13, and on 2026-10-14 ruled that the tags be read from the remote rather than from any local checkout, because a worktree or a cloud container carries no sibling clones. Out of the spec target, the plan operation prose (`.claude-plugin/prose/plan.md`, its release-rule paragraph) restates the old rule, and the implementation work-item that realizes this change updates it in the same change.

### Proposed Changes

In SPECIFICATION/contracts.md, in the plan Proof of Done record paragraph, replace the sentence beginning "Where a release applies to the plan's work" with:

> The release rule is judged against the RELEASE REPOSITORY of each record. The release repository is named by the first whitespace-delimited word of the record's installed build identifier, written either as `<owner>/<repository>` or as a bare `<repository>` that denotes the same forge owner as the governed repository's own remote. The release repository's release tags MUST be read from its remote on the forge that hosts the governed repository, and MUST NOT be read from any local clone or worktree. When the record carries no installed build identifier, or the forge reports that the repository its first word names does not exist, the release repository is the plan's governed repository. When the forge cannot be reached, or answers with any failure other than that the repository does not exist, the archive gate MUST reject the record, naming the release repository and the failure, and MUST NOT fall back to the governed repository. Where a release applies to the plan's work — the release repository carries at least one release tag — a `captured` record taken against an unreleased tree is not evidence: the steps MUST run against the released artifact installed through its normal installation path, and the archive gate MUST reject a record that states `release: none` for such a repository, or names a release tag the release repository does not carry, naming the missing release identity and the release repository it judged. The gate MUST NOT accept a tag merely because some repository carries it: the tag MUST be carried by the record's release repository.

In the same paragraph, replace the sentence "The installed build identifier is recorded, not verified." that immediately follows the release-rule sentence above (the plan record's occurrence; the identical sentence in the work-item Proof of Done rule elsewhere in contracts.md MUST stay unchanged) with:

> The installed build identifier is recorded, not verified, save for the repository name the release rule reads from it.

The rest of the paragraph is unchanged.

In SPECIFICATION/scenarios.md, under `## Scenario 135 — A plan cannot archive until its own Definition of Done is proved against the released build`, immediately after the scenario `A record captured against an unreleased tree is not evidence`, add:

```gherkin
  Scenario: A record names a sibling repository's release
    Given a plan whose governed repository does not carry the release tag a record names
    And a plan Proof of Done record whose installed build identifier begins with the name of a sibling repository on the same forge owner
    And no clone of the sibling repository exists on the host running the archive gate
    When the archive gate evaluates the proof leg
    Then the record's release tag is judged against the sibling repository's release tags read from its remote
    And a record naming a tag the sibling repository's remote carries is accepted as evidence
    And a record naming a tag the sibling repository's remote does not carry is rejected naming the missing release identity and the sibling repository
  Scenario: An unreachable forge does not fall back to the governed repository
    Given a plan Proof of Done record whose installed build identifier names a sibling repository
    And the forge cannot be reached when the archive gate evaluates the proof leg
    When the archive gate evaluates the proof leg
    Then the record is rejected naming the sibling repository and the failure
```

No `## ` heading is added, removed or renamed, so tests/heading-coverage.json is unchanged.
