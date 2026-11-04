---
proposal: five-hour-window-absent.md
decision: modify
revised_at: 2026-11-01T05:23:20Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in substance under the 2026-11-01 stop-the-line ordered by the fleet coordinator (gitops-fleet-capacity-monitoring). Measured: every pool slot's 2xx usage response now carries the seven-day headers (status allowed) and no `anthropic-ratelimit-unified-5h-*` header, so the clause floor-skipped every slot as unobservable and the factory dispatched nothing from about 01:35Z. An authenticated 2xx that reports no five-hour window is the provider stating there is no five-hour limit, not a failure to measure; transport, authentication, timeout, malformed and non-2xx readings stay unobservable. Mirrors livespec-overseer overseer-yizu3e (5.43.0, merge 3798347e). No design record is contradicted: the unobservable rule exists so a FAILED measurement never reads as headroom, and an absent window on a successful response is not a failed measurement. The default floor of 20 is unchanged. The Scenario 288 heading-coverage entry (`test: TODO`) is co-edited in tests/heading-coverage.json in the same change.

## Modifications

The independent ratification reviewer found one blocker in the proposal as filed: the unchanged per-item journal sentence and the host-history entry sentence admitted only a numeric utilization or an explicit unobservable result, which the new rule forbids for an absent window. Modified by (a) adding 'or the named `five-hour-window-absent` result' to the per-item journal sentence, (b) adding the same to the host-history entry sentence, and (c) adding the sentence 'An assessment or host-history entry naming `five-hour-window-absent` carries no valid reading, so it MUST NOT serve as a drain-rate baseline or a carried rate.' before the caam-precedent sentence. Every other edit is as filed.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-01T05:22:39Z
verdict: NO BLOCKERS
proposal_stem: five-hour-window-absent
content_digest: a2649d37fbce1ad63cbe32b8ce053cf1cce8cf5f3884cb5f999b1b383be901ff
