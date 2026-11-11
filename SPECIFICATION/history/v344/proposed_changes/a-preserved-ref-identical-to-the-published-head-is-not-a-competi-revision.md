---
proposal: a-preserved-ref-identical-to-the-published-head-is-not-a-competi.md
decision: accept
revised_at: 2026-11-11T04:22:28Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as written. The publishing-run-unobservable hold exists so routing does not choose between two DIFFERENT trees without knowing which run is newer. When a needs-human or failed-checkpoint preservation ref's tip tree is identical to the observed published head's tree, resuming the head keeps every byte the ref preserves, so there is nothing to choose. The clause already exempts the preserved-publish ref on the same ground. Measured harm: seven items held on 2026-11-10 and archived by hand; identity re-measured on bd-ib-ofvsr3 on 2026-11-11. Plain tree identity matches the existing CARRIES NO WORK convention, and an unreadable comparison stays the unobservable-measurement hold. Decided under the delegated revise_decision_mode by the factory-run-work-preservation plan seat; the independent read-only sonnet reviewer returned NO BLOCKERS on these exact bytes. Its non-blocking note: the per-pass identification is defined over needs-human refs, so an implementer must read the failed-checkpoint ref's and the head's trees in that same pass. Unblocks bd-ib-6szexa.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T04:21:31Z
verdict: NO BLOCKERS
proposal_stem: a-preserved-ref-identical-to-the-published-head-is-not-a-competi
content_digest: f7df11c096755c619ea00443617f1545fc5415d32c5611027b36ff5fb2711a23
