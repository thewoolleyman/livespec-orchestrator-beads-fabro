---
proposal: provisional-fleet-launch-scripts.md
decision: modify
revised_at: 2026-10-24T21:48:37Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratifies the provisional fleet-launch/ directory committed by plan provisional-fleet-launch (epic bd-ib-klkbxp, PR #3595) as a caller-side launch loop, under the coordinator gitops-fleet-capacity-monitoring's standing mandate for that plan. Child bd-ib-nz4av6's check-fleet-launch obligation had no governing heading. MODIFIED after two independent read-only reviews found real gaps: three scenarios were added (banners, host values, retirement), and the override variables were named with the FLEET_LAUNCH_ prefix. A fourth review over the final payload shape (spec-relative paths; tests/heading-coverage.json co-edited outside the payload, per the v206 precedent) returned NO BLOCKERS. Final reviewer: codex exec read-only, model gpt-6-astra, session 01a16fe2-1249-7081-b860-da39a06514be.

## Modifications

Scenario 242 gains three Gherkin scenarios: every provisional script carries its banner (read with comment markers removed); host values are declared once and overridable through FLEET_LAUNCH_ environment variables; the directory is retired once nothing launches through it. The contracts clause names the FLEET_LAUNCH_ override prefix.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-24T21:48:01Z
verdict: NO BLOCKERS
proposal_stem: provisional-fleet-launch-scripts
content_digest: f8c4deff9d0a1aa37da3ca0c65e0282fe3acdd8c981fba6031ca0b21546e7cdb
