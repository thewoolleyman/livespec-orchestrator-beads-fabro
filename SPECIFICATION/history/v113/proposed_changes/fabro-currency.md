---
topic: fabro-currency
author: codex-gpt-5
created_at: 2026-09-30T06:45:22Z
---

## Proposal: Replace the frozen Fabro ceiling with a bounded currency policy

### Target specification files

- SPECIFICATION/constraints.md

### Summary

Replace the temporary `<0.256` compatibility ceiling with an exact-upstream-tag currency policy that keeps the factory within 30 publication-days of the newest published Fabro release, preserves the single `factory-integration` carrier for required patches, and gives every carried patch an auditable upstream-or-drop disposition.

### Motivation

The ratified ceiling was conditional on migrating `workflow.fabro`, but a backlog sweep misread it as a permanent stable-frozen posture and closed the named migration item. Upstream has since replaced the old workflow engine with Petri while the factory remains on 0.254 plus 24 carried commits, including obsolete patches and unshipped security behavior. Plan `fabro-currency` (`bd-ib-6tcjfx`) records the maintainer's intent to stay on Fabro, stay current, and contribute required capabilities upstream where practical.

### Proposed Changes

Amend `constraints.md` under `Fabro runtime constraints` to remove the permanent-looking `<0.256` base-version ceiling and its pointer to closed item `bd-ib-6qu`. The replacement currency rule MUST define an upstream base as an exact tag published by `fabro-sh/fabro`, including an official nightly tag; a moving branch, untagged upstream commit, or locally invented version MUST NOT be the base. The `factory-integration` tip MAY carry required commits on top of that exact base, and the runbook MUST record both the upstream base tag and the integration commit.

The selected upstream base's GitHub publication timestamp MUST be no more than 30 calendar days earlier than the publication timestamp of the newest release returned by `fabro-sh/fabro`'s GitHub Releases surface at the time currency is evaluated. Stable and prerelease/nightly releases participate equally; semantic-version ordering and commit timestamps MUST NOT substitute for release publication time. The factory MUST evaluate that condition at least once every seven calendar days and before any rebuild or re-pin. After the initial transition below, no compatibility hold or warning-only exception MAY admit an out-of-window base.

Ratification MUST include one transition exception for the Petri-era migration owned by plan epic `bd-ib-6tcjfx`: the existing 0.254 carrier MAY remain in service for at most 45 calendar days after ratification while P3-P6 measure, migrate, and cut over. The revise pass MUST materialize that relative bound as one absolute UTC deadline in the ratified constraint and dispatch contract. That transition MUST NOT be renewed or used for unrelated feature work. When it expires, the ordinary 30-publication-day rule applies without an exception.

Retain the single-carrier composition rule, and strengthen it so every commit carried beyond the exact upstream base MUST have one current disposition in the runbook: an open upstream Fabro PR, an upstream Petri issue/PR where the engine now owns the capability, or a written reason the patch is intentionally fork-local or being dropped. Each disposition MUST name an owner and a review-by date no more than 30 days away. A carried patch that is present upstream, obsolete on the selected engine, or past its review-by date MUST be dropped or re-justified before the next re-pin.

The rebuild, rollback-artifact, image lockstep, version-audit, and runbook-lockstep duties MUST remain in force. The deciding evidence MUST include the upstream tag survey, the ancestry from the integration commit to the exact base tag, `fabro --version` for both factory hosts, the container image's baked binary identity, and the carried-fix disposition table. The old stable-frozen/never-modernize interpretation MUST be explicitly disclaimed: the factory is obligated to move forward within this bounded policy, not remain indefinitely on 0.254.

## Proposal: Dispatch preflight enforces Fabro currency before claim

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Turn the currency policy into target-aware dispatch behavior: the dispatcher proves the serving Fabro build and current upstream release evidence before claim, refuses stale or unidentifiable builds, and admits only the one initial migration transition before strict enforcement begins.

### Motivation

Ledger item `bd-ib-j9x` already tracks the missing mechanical gate for the old ceiling. Reframing that work around the ratified currency window closes the same severe failure mode without hard-coding an obsolete version range: a workflow must not be claimed onto a server whose engine is outside the factory's supported currency posture.

### Proposed Changes

Add a target-aware Fabro-currency leg to `contracts.md` under the dispatch-time baseline conformance gate. Before claim or run creation, every direct, hand-picked, drain, and autonomous-loop dispatch path MUST resolve the selected factory target's serving integration commit and the latest `fabro-sh/fabro` GitHub release publication metadata through one shared predicate. From all published upstream release tags whose tagged commits are ancestors of the serving integration commit, the predicate MUST select the tag with the latest publication timestamp as that build's upstream base; no matching tag means the build has no valid base. The predicate MUST compare that base's publication timestamp with the newest release's publication timestamp using the 30-calendar-day rule defined in `constraints.md`. It MUST refuse before mutation when the serving build cannot be identified, the upstream release observation is older than seven calendar days, no exact release-tag ancestor exists, or the base is outside the window after the transition deadline. Inability to refresh an observation that has aged past seven days MUST refuse; a warning-only result MUST NOT admit the dispatch. Carried-fix disposition remains a rebuild/re-pin review constraint and is not reimplemented in this dispatch predicate.

The refusal MUST name the factory target, serving build when known, resolved upstream base and its publication time when one exists, newest observed upstream release and its publication time, observation time, the failed currency condition, and the corrective route. Before the one absolute transition deadline, an otherwise stale 0.254 carrier MUST be reported as an admitted transition rather than silently treated as in-window. The shared predicate MAY cache upstream release metadata for seven calendar days; cached evidence older than that MUST NOT prove currency. The behavior MUST reuse successor work to `bd-ib-j9x` rather than preserve its obsolete hard-coded `<0.256` premise.

Add Gherkin coverage in `scenarios.md` for: an exact tagged base inside the 30-publication-day window admitting; an untagged or ancestry-mismatched build refusing before claim; an out-of-window base refusing with complete evidence; the non-renewable 45-day initial migration transition admitting before its absolute deadline and refusing afterward; stale upstream-release evidence refusing when refresh fails; stable and prerelease/nightly publication timestamps participating identically; and two configured factory targets being evaluated against their own serving versions. The revision MUST update `tests/heading-coverage.json` atomically so the new behavior is linked to its exercising scenario and eventual regression tests.
