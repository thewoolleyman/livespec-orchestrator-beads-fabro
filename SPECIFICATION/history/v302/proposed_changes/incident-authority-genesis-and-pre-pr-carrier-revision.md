---
proposal: incident-authority-genesis-and-pre-pr-carrier.md
decision: modify
revised_at: 2026-11-05T07:02:02Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:expedited-incident-response-flag
---

## Decision and Rationale

Accepted in delegated mode by seat expedited-incident-response-flag (plan expedited-incident-response-flag, epic livespec-dev-tooling-bqnzcm) under maintainer-local-only-expedited-exception-20261103T2142. legacy-coordinator-agent accepted this exact digest under R301 on 2026-11-05. bd-ib-dzbwaq's remaining incident-entry assertions and its dependents bd-ib-y7ryj3, bd-ib-riguvj, bd-ib-mnny4v and bd-ib-k5teti were blocked on an unratified first-authority and pre-PR carrier contract. The ratified lifecycle required an existing authority root and a carrier PR, so an initial hook or first push could never be authorized. The amendment adds atomic conditional first-root publication with a named capability refusal, operation-id retry and conflict, a discriminated branch-reserved/head-published/pr-bound carrier with a compare-and-swap first push, and a factory-transfer fence. It extends the existing lifecycle without contradicting it, and it keeps the ordinary claim-token protocol (Stranded claim release, v254, Scenario 263) unchanged. An independent read-only sonnet reviewer found NO BLOCKERS on the exact bytes. Its two non-blocking notes (an older 'each attempt MUST bind ... carrier PR' sentence, and no dedicated scenario for the factory-transfer refusal) are routed to a follow-up proposal under bd-ib-dzbwaq.

## Modifications

Wording only. The proposal's three normative subsections are appended verbatim at the end of ## Expedited incident lifecycle. Its framing sentences ('This amendment does not replace ...') are reworded into spec voice ('These incident-specific first-authority and pre-PR carrier requirements do not replace ...') with the same meaning and the same ids. The gherkin block is added verbatim under the proposal's scenario heading, immediately after the existing incident scenarios. No rule was added or dropped.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T07:00:33Z
verdict: NO BLOCKERS
proposal_stem: incident-authority-genesis-and-pre-pr-carrier
content_digest: ba4218cdd24bc3ae66a0651ab258437a16b113dd0fffe2f257f5554656d35723
