---
proposal: an-oom-killed-sandbox-is-resource-exhaustion.md
decision: modify
revised_at: 2026-11-09T16:17:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:kubernetes-sandbox-backend
---

## Decision and Rationale

Accepted in substance under delegated decision mode. Coordinator legacy-coordinator-agent ruled the change SPEC-CHANGE (2026-11-09 ~06:10Z) after both implement turns of bd-ib-jnstxo run 01M6ZEHHFJSW found that the CONTROL clause of contracts.md §"Provider-limit permanence and root-cause surfacing" forbids a third permanent class. The measured cause stands: on 2026-11-09 the memory-cgroup OOM killer took the claude agent at 7.2-7.4 GB in a 7629 MiB sandbox in runs 01M6YS4E7TG2 and 01M6YVGGFC9K, and the next checkpoint exec's API 500 was recorded as transient_infra, so retry and re-dispatch repeated a run that could not succeed. The independent read-only sonnet review found no blockers. Its non-blocking notes: the tests/heading-coverage.json row for Scenario 335 is added in the same change (with the spec-first debt-register entry), owned by bd-ib-jnstxo; 'typed resource-exhaustion state' is a new typed state the implementation introduces. Carrier: bd-ib-jnstxo (plan bd-ib-nmuyjc).

## Modifications

(1) NNN resolved to Scenario 335, the next free number. (2) The CONTROL paragraph's 'NO permanent cause of either class above' becomes 'of any class above', since the section now recognises three classes; the proposal left that sentence unchanged, which would have read as excluding the new class from the control. (3) The scenario's Governing clause line uses the file's existing backtick-and-arrow convention.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T16:15:08Z
verdict: NO BLOCKERS
proposal_stem: an-oom-killed-sandbox-is-resource-exhaustion
content_digest: 66f7e02af9920b66da809702a80c0243529fb44f4b98a006602cbb1c2e144423
