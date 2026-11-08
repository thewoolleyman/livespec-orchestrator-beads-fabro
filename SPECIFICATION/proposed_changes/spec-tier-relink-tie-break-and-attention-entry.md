---
topic: spec-tier-relink-tie-break-and-attention-entry
author: claude-opus-5-5
created_at: 2026-11-08T03:01:26Z
---

## Proposal: The relink-candidate tie-break has a scenario, and its attention fact has a family entry

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Close the two advisory gaps the post-revise doctor phase raised against topic a-spec-change-hold-whose. First, add a Scenario 206 scenario for its tie-break: when more than one qualifying revision exists, the refusal and the hygiene:spec-tier-relink fact name the most recently cut one. Second, add a `hygiene:spec-tier-relink:<work-item-id>` family entry to contracts.md §"Orchestrator-owned attention facts", beside the other per-work-item entries, so the fact is listed where every other attention fact family is listed. No H2 heading is added, changed or removed.

### Motivation

legacy-coordinator-agent (R301; revise and drift decisions are delegated to it) dispositioned both findings as CAPTURE on 2026-11-08, as one follow-up proposal, with a work item owing the new scenario's test linked to held work item bd-ib-jnbcny (plan spec-implementation-lockstep, epic bd-ib-ax3rds). The findings came from the independent ratification reviewer and the doctor LLM phase on the a-spec-change-hold-whose revise. (1) That topic's clause says that when more than one qualifying revision exists the refusal and the fact MUST name the most recently cut one, but neither of its two scenarios exercises that sentence. Under the behaviour-needs-a-scenario split, a MUST with no scenario is gradeable only by reading the prose. (2) The clause surfaces `hygiene:spec-tier-relink:<work-item-id>` "per §\"Orchestrator-owned attention facts\"", but that section lists every other operational fact family by name and this one is absent, so a reader of the section cannot find it. The entry adds no new requirement beyond the autonomy-tier bullet: it restates where the fact is defined and states how it clears and how a failed read surfaces, matching its sibling per-work-item entries. This topic depends on a-spec-change-hold-whose having been ratified first, because both edits refer to the relink-candidate paragraph that topic adds; it is revised after it in the coordinator's queue.

### Proposed Changes

In SPECIFICATION/contracts.md, §"Orchestrator-owned attention facts", insert one new paragraph immediately after the paragraph that begins "**Workflow-edit approval (`hygiene:workflow-edit-approval:<work-item-id>`).**" and ends "Scenario 232 in `scenarios.md` exercises this paragraph.", separated from it by one blank line:

> **Spec-tier relink candidate (`hygiene:spec-tier-relink:<work-item-id>`).** For every held spec-change-tier work-item of this repository for which §"Grooming and slice-size calibration" → "An autonomy tier is assigned" names a relink candidate, the snapshot MUST carry one attention item, with the `summary` and `handoff` that bullet defines. The fact surfaces a candidate only: it MUST NOT release the hold, relink the item, or write any ledger record, and it clears when the item is relinked, released or closed, or when no candidate remains. A store read or a spec-history read that fails MUST surface as a visible failure rather than as an absence of these items. Scenario 206 in `scenarios.md` exercises this paragraph.

In SPECIFICATION/scenarios.md, append to the end of the gherkin block under `## Scenario 206 — The spec-change tier is decided by the spec-stated judgement, and a feature waits for ratification`, after the scenario titled "A rejected revision is never named as a relink candidate" and before the block's closing fence, separated by one blank line:

```gherkin
  Scenario: When more than one revision ratified the generalization target under another topic, the most recently cut one is named
    Given a held spec-change-tier item whose linked topic has no revision record
    And two revisions with decision accept or modify, each cut after the item's tier record, each amended the body of that record's generalization-target heading under a topic other than the linked one
    When a dispatch of the item is refused, and when needs-attention is composed
    Then the refusal and the hygiene:spec-tier-relink fact name the topic and specification version of the more recently cut revision
    And neither names the topic of the earlier revision
```

No H2 heading is added, changed or removed, so tests/heading-coverage.json needs no edit.
