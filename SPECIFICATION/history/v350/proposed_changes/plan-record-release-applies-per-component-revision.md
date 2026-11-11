---
proposal: plan-record-release-applies-per-component.md
decision: modify
revised_at: 2026-11-11T11:24:24Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accept with modifications. Filed spec-first by plan secret-writer-stored-key-alias (epic homelab/hl-bvycoc) on the legacy-coordinator-agent ruling of 2026-11-11, with that plan as the case. homelab releases shared-credentials-v0.2.0, a zipapp built from tools/shared_credentials/ only, and state-backend-v0.1.0, while the plan's artifact (the canonical secret writer under tools/shared_credentials_provisioning/) is in no release and runs from main. Under the v148 rule a release applies whenever the release repository carries any release tag, so that plan has no truthful record to post. The change scopes the rule to the declared release component that ships the artifact. Declaring no components, naming no artifact paths, or carrying a tag that no component owns all keep the repository-wide rule, so omitting the declaration never loosens it. A malformed declaration rejects every record of the repository. The anchor sentence is unchanged on master since v148 (2f3029407), and v345-v349 did not touch it. The pending proposal plan-record-release-repository-is-declared bounds which repository a record may name, which composes with this change, and it amends no sentence this one replaces. Implementation carrier: livespec-orchestrator-beads-fabro bd-ib-qpibvm, which owns the spec-first TODO coverage row and the debt row.

## Modifications

(1) The new scenario takes an unnumbered '## Scenario:' heading, as v349 did, instead of the next number, because pending proposals already claim 345-347; its sub-scenario titles are lowercased to match. (2) A fifth sub-scenario, 'a malformed release component declaration rejects every record of the repository', covers the paragraph's MUST that a malformed dispatcher.release_components array is refused with a configuration finding and every record rejected, so every new MUST has a scenario. (3) The posting primitive's optional build.artifact_paths payload field stays implementation detail for bd-ib-qpibvm and is not stated in the spec; the ratified surface is the artifact paths: line in the record's build identity. (4) tests/heading-coverage.json gains a TODO row and tests/heading-coverage-debt.json a debt row (first_seen 2026-11-11), both owned by bd-ib-qpibvm. The contracts.md paragraph text is as filed.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T11:24:18Z
verdict: NO BLOCKERS
proposal_stem: plan-record-release-applies-per-component
content_digest: 4a856ac053f7ff13a409bda340c30e6e158f7a4a75e0b4919f7d8786abb1ee1c
