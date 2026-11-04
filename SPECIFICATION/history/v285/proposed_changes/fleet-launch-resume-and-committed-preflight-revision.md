---
proposal: fleet-launch-resume-and-committed-preflight.md
decision: modify
revised_at: 2026-11-03T11:55:36Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:gmktec-factory-placement
---

## Decision and Rationale

Decided in delegated mode by claude:gmktec-factory-placement on legacy-coordinator-agent's rulings (2026-11-03 ~11:15Z and ~11:25Z). Both proposals extend §"Provisional fleet launch scripts" with behaviour the x7bwug cutover needs: a resume launcher that honours the fleet cap and the FIFO (bd-ib-uhcn36), and a committed launch-time preflight that needs no launcher-local copy (bd-ib-pys5lt). Each is a testable clause with its own scenario (302, 303).

## Modifications

The independent review found one blocker. The existing rule that a launcher holding a FIFO ticket MUST run the launch-time preflight contradicted the new resume launcher, which takes a ticket but runs no preflight. The modification has three parts. First, it scopes that rule to an impl launcher. Second, the resume sentence becomes a MUST NOT, and it also requires the resume launcher to release the mutex before `resume --item <item>` starts, as an impl launcher releases it before `drive --action impl:<item>`. Third, the section opener now names `resume --item <item>` beside `drive --action impl:<item>`. The re-review of the final bytes found NO BLOCKERS.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T11:54:44Z
verdict: NO BLOCKERS
proposal_stem: fleet-launch-resume-and-committed-preflight
content_digest: f30bfc388612e92134d80bbbaee8526cd83306f5663bc9ac47b7b87f679a7d1f
