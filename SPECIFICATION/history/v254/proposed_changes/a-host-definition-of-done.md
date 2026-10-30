---
topic: a-host-definition-of-done
author: claude-opus-5-5:petri-factory-on-gmktec
created_at: 2026-10-29T12:48:26Z
---

## Proposal: A bound-ended Definition-of-Done judgement records each candidate's input size, and every host taking is journaled with it

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend the pre-dispatch and pre-admission did-not-run record to name each bound-ended candidate's total input tokens and the bound that ended it, and require every host taking of the Definition-of-Done judgement to append one dispatch-journal row with its stage, candidates and input sizes, so bound-ended judgements can be sized and counted.

### Motivation

Work-item bd-ib-ebdvbn measures that the 100,000-token host judgement input bound (HOST_JUDGEMENT_INPUT_LIMIT, from bd-ib-jp2qr2, released in v0.251.1) now ends real judgements without recording how large the input was. On 2026-10-28 three livespec-dod-judgement-unavailable records carried cause input-limit-reached, bound-ended candidate claude-acp:claude-sonnet-5-5 and exit 143, and none stated an input size: bd-ib-iy4cd4 (pre-dispatch, where the judgement did not run and the item dispatched without it), overseer-trgq2p and livespec-console-beads-fabro-pjceof (both pre-admission). On 2026-10-29 bd-gj-cbbyic's subject measured about 7,500 characters, roughly 2,000 tokens, so the bound was reached by context the judgement assembles around the subject; without a recorded size nobody can tell which part dominated, or whether a subject was 101,000 or 400,000 tokens. Scenario 239 already requires a DECIDING candidate's record to name its total input tokens, but the did-not-run case, where the size matters most, names none, and no surface counts how often the bound fires. The orchestrator's spec-change-tier gate held ebdvbn on 2026-10-29 (topic a-host-definition-of-done) for exactly this gap. This proposal only adds measurement; whether to raise the bound or shrink the subject is left to the plans that own the token budget once the sizes are recorded.

### Proposed Changes

In SPECIFICATION/contracts.md, under ## Dispatcher admission, WIP cap, and post-merge acceptance, in the paragraph that states 'When the judgement cannot be run (no eligible model, a timeout, or an unparseable verdict), the Dispatcher MUST record on the item that the pre-dispatch judgement did not run and why', append after that sentence:

When the judgement did not run because every candidate reached the host judgement input bound, the did-not-run record MUST name, for each candidate the bound ended, the total input tokens its requests reported (marked complete, partial or unreported, as Scenario 239 marks a deciding candidate's total) and the bound that ended it. The same holds for the pre-admission taking's did-not-run record.

Then add a new paragraph after that one:

**Every host taking is journaled with its input size.** Each host taking of the Definition-of-Done judgement (repository preflight, pre-admission and pre-dispatch) MUST append one dispatch-journal row naming its stage, the candidate that decided it or, when it did not run, each candidate the bound ended, and the total input tokens each named candidate's requests reported, with the same complete, partial or unreported marking. The row lets the share of takings that reach the bound be counted from the journal alone, without reading the item's ledger.

In SPECIFICATION/scenarios.md, under ## Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric, append:

  Scenario: A judgement every candidate's bound ends records each candidate's input size
    Given a governed repository whose resolved dod_gate chain has one candidate
    When the pre-dispatch Definition-of-Done judgement is taken and that candidate's requests together report 140,000 input tokens
    Then the judgement did not run
    And the did-not-run record names that candidate, its total of 140,000 input tokens marked complete, and the 100,000-token bound that ended it

  Scenario: Every host taking appends a journal row with its input size
    Given any host taking of the Definition-of-Done judgement
    When the taking ends, whether a candidate decided it or it did not run
    Then the dispatch journal carries one row for it naming its stage, the deciding or bound-ended candidates, and each one's total input tokens with its marking

This adds scenarios under an existing heading, so no new tests/heading-coverage.json entry is required.
