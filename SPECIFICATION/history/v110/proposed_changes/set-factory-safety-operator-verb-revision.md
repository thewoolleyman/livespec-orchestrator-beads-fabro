---
proposal: set-factory-safety-operator-verb.md
decision: modify
revised_at: 2026-09-10T16:21:53Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Ratified per maintainer ruling. Accepts the set-factory-safety:<id>:<reason> operator verb that sets the intrinsic factory_safety field with a mandatory non-empty reason, replacing the unrecorded raw `bd label add` opt-out path. Modified over the proposal-as-written in two maintainer-directed ways: (1) added the paired Gherkin scenarios the proposal omitted, per the behavior=>scenario authoring discipline every adjacent operator verb follows; (2) made the verb STATUS-INDEPENDENT rather than ready-lane-only, because factory_safety is an intrinsic runnability axis orthogonal to lifecycle status and an item's host-only nature is recordable at any point (maintainer ruling, 2026-09-10). The new clause is an H4 under an existing H3, so tests/heading-coverage.json is unaffected.

## Modifications

contracts.md: added a 'Status-independent verbs' note under '#### Per-lane valid operator verb sets' stating set-factory-safety is valid in ANY lane (including the annotated `done` row), and a new '#### set-factory-safety:<id>:<needs-host-secrets|mutates-host-machinery|needs-privileged-host>' clause after the driver-dispatch clause defining the verb (reason constrained to the three canonical factory_safety enum values matching the field's closed enum and the sibling set-admission/set-acceptance verb grammar; sets factory_safety; journaled; does not change status; MUST NOT alter admission_policy; valid in any lane). scenarios.md: added three scenarios in the factory_safety refusal feature — records the reason on a backlog item, not gated by lifecycle state (acceptance item), and an out-of-enum-reason refusal guard. Also wired the verb into the drive action-id grammar at all three enumeration sites and bumped the counted invariant (twelve -> thirteen human valve/policy actions), so the new first-class verb has a specified execution surface. Three ratification-review blockers (free-text reason vs closed enum; done-row contradiction; verb absent from the drive grammar) were fixed before this evidence was taken.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-10T16:16:39Z
verdict: NO BLOCKERS
proposal_stem: set-factory-safety-operator-verb
content_digest: b932ae969fff1f9e013f6c67af526713b6b1a5562af60378cb2e5fe801ebf212
