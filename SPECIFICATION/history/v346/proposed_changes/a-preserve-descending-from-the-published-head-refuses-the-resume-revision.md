---
proposal: a-preserve-descending-from-the-published-head-refuses-the-resume.md
decision: modify
revised_at: 2026-11-11T07:49:55Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratify. Three measured instances (livespec-dev-tooling-fjpqqq, livespec-dev-tooling-hmztez, bd-ib-ofvsr3) show recovery routing resuming onto an older published head and silently dropping committed work a same-or-later-run preserve holds beyond it, because the ratified text gives an admissible resume precedence over any seed. The refusal is confined to the case where refusing loses nothing: the preserve's tip descends from the head (so seeding keeps every byte the resume would) and its tree differs (an identical tree is already not a competitor under v344); it is bounded by the existing run age rule and defers to publishing-run-unobservable when a run cannot be established. It is fallback-permitting, so non-fallback refusals keep precedence. Decided by the factory-run-work-preservation plan seat under delegated decision mode, per legacy-coordinator-agent's ruling assigning v346 to this seat.

## Modifications

One placement and wording change, no new normative content. The proposal's sentence 'When that last refusal is the only one that applies, routing MUST seed from the ref it names.' is placed at the END of the fallback-permitting definition paragraph (after '...is never treated as a missing anchor.') rather than directly after the extended list, and reads 'When the refusal for a preserved ref that descends from the head with a different tree is the only refusal that applies, routing MUST seed from the ref it names.' Inserting it mid-paragraph made the following 'Every other refusal is non-fallback' ambiguous, and 'that last refusal' no longer resolves once the sentence moves. All other text is applied verbatim.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T07:49:17Z
verdict: NO BLOCKERS
proposal_stem: a-preserve-descending-from-the-published-head-refuses-the-resume
content_digest: b55d83d1d691853b3bb413a07fae1e4fcceb88d248c9e0127fce87662c818afe
