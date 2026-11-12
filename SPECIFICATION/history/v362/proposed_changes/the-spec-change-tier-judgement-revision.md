---
proposal: the-spec-change-tier-judgement.md
decision: modify
revised_at: 2026-11-12T23:02:07Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:publish-draft-green-work-loss
---

## Decision and Rationale

The proposal closes a gap the v348 judgement itself named when it held bd-ib-lrjdlo at spec-change tier on 2026-11-12: the paragraph "The spec-stated judgement is one shared component" requires the clause selection to be deterministic but says nothing about which clauses it must reach, so a selection that withholds the stating paragraph, or never reads a specification file the repository inherits, conformed to it. Measured 2026-11-11: 7 of 22 held items were already stated by the ratified specification, through two mechanisms only the selection can fix (the condensed tree withheld the stating clause; an inherited file was never read). The new paragraph under the same H2 states what the specification text and the selection cover: inherited specification files declared by a closed list of exactly two constraints forms (form one admits plugin, library or application, per the #5066 amendment), resolved relative to the sibling-clones directory and never the working directory; an absent declared file omitted and named in the clause provenance rather than raised on; the most relevant paragraphs placed in full wherever they sit, with budget reserved for them; and the prompt kept under the judgement's ceiling. One sentence of the existing paragraph points at the new one. Placement is correct: this orchestrator's Dispatcher realization belongs in its own contracts.md. No existing H2 heading is renamed or removed. The coordinator (legacy-coordinator-agent) released this single-proposal pass on 2026-11-13 and ruled the topic independent of node-record-names-model-and-tools.

## Modifications

The new scenario is numbered 359 instead of 353, in both the scenarios.md H2 heading and the contracts.md sentence "Scenario 359 in `scenarios.md` exercises this paragraph.". Scenario 353 is reserved by the pending proposal bd-guard-refuses-a-raw, and 357, 358, 360, 361 and 362 are reserved by open proposal pull requests; 359 is the lowest number neither ratified nor reserved when this revise was cut. No other text changes.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T23:00:57Z
verdict: NO BLOCKERS
proposal_stem: the-spec-change-tier-judgement
content_digest: 38df601d91a221966b6eb5c30efc88e49a041630f1891b52ae98421b8be40f9d
