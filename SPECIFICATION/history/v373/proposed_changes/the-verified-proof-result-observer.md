---
topic: the-verified-proof-result-observer
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-11-13T19:06:32Z
---

## Proposal: A verified_proof read applies the archive proof leg's currency rule

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State that a `verified_proof` read on a plan epic is satisfied only by a `verified` plan Proof of Done record that postdates both the latest `captured` record and the last carrier-map event. Today that ordering is stated only for the archive proof leg (contracts.md §"Archive on completion"). §"Shared authoritative result reader" requires a verified-proof read to "validate the existing typed Proof of Done semantics, scope, build and verdict" but names no ordering. So the plan-progress observer can read a stale record as satisfied while the archive gate refuses that same record. The rule is added to the result reader BY REFERENCE to the archive leg's wording, so the ordering is stated once. Scenario 146 gains a case that pins it.

### Motivation

Work item bd-ib-yf3svb (plan bd-ib-ax3rds), routed by legacy-coordinator-agent. The tier judgement read the ask as spec-change/partial with generalization `## Planning Lane realization`. The ordering exists in the ratified spec only as a gate on archive, so releasing the item by clause would stretch an archive-only sentence onto the progress observer.

Measured: on homelab epic hl-bvycoc, the plan's typed pointer was advanced to `review` on a `verified` record from 2026-11-12T20:23:46Z (ledger comment 01a1d16e-4538-7914-a5ad-8c1d2f2cfe42). A later carrier-map scope event and a later `captured` record had made that record stale; the archive proof leg would have refused it. Because the observer read the stale record as satisfied, `resume_directive` treated the proof pointer as fulfilled and persisted a derived next step, silently skipping a required replay.

Fleet scope: every plan in every repository whose `next_action` waits on a `verified_proof` required result, since every one of them reads that result through the shared reader.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Shared authoritative result reader", immediately after the sentence "A verified-proof read MUST validate the existing typed Proof of Done semantics, scope, build and verdict rather than match text.", insert:

> For a `verified_proof` on a plan epic, those semantics include the currency rule that the proof leg of §"Archive on completion" states for archive: the deciding record is the latest plan Proof of Done record on the epic whose verdict is `verified` or `not_reproduced`, that record's verdict MUST be `verified`, and it MUST postdate both the latest `captured` record and the last carrier-map event. A `verified` record that does not postdate both MUST read `unsatisfied`, never `satisfied`, and the observation's detail MUST name the later `captured` record or carrier-map event that displaced it. A ruling or deferral that is not a carrier-map event MUST NOT displace a record, exactly as it voids neither proof under the archive leg. The reader and the archive proof leg MUST apply this one ordering rule, so that a record the archive gate refuses as stale can never satisfy a plan's proof wait. Because `resume_directive` reconciles a pointer through this reader, a proof pointer whose only `verified` record is stale MUST remain the plan's pointer, and no derived `review` or `archive` pointer MAY be persisted from it.

In `SPECIFICATION/scenarios.md`, under the existing heading `## Scenario 146 — Authoritative result readers distinguish fulfillment from observation failure`, append to its gherkin block (no new H2 heading, so `tests/heading-coverage.json` needs no edit):

```gherkin
  Scenario: a verified plan record that a later capture or carrier-map event displaced does not satisfy a verified_proof wait
    Given a plan epic whose next_action awaits a verified_proof result for its plan assertions at a named build
    And a verified plan Proof of Done record covering those assertions at that build
    When a captured plan record is posted after that verified record
    Then the shared reader reports the verified_proof result unsatisfied
    And the observation's detail names the later captured record
    When instead a carrier-map scope event is recorded after that verified record
    Then the shared reader reports the verified_proof result unsatisfied
    And the observation's detail names that carrier-map event
    When instead only a ruling that is not a carrier-map event follows the verified record
    Then the shared reader reports the verified_proof result satisfied
    And resume_directive on an epic whose only verified record is displaced keeps the proof pointer and persists no derived review or archive pointer
```
