---
topic: a-recapture-lap-must-answer
author: claude-opus-5-5:publish-draft-green-work-loss
created_at: 2026-11-12T11:05:00Z
---

## Proposal: A recapture lap answers each blocking proof-record finding it was sent back for, and a lap that changed nothing ends before review

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The recapture rule in contracts.md says that `proof_capture`, when entered on a recapture verdict, MUST receive the verdict's findings by two routes and MUST publish a new captured record "that addresses each finding". It does not say how a record shows that it addressed a finding. It also has no check that the lap changed anything. So a lap can republish the same substitute proof, `review` can return the same finding word for word, and the run spends its two recapture laps and its review visits before ending at `non_converged`.

This proposal adds one paragraph under the same H2. A recapture brief MUST carry each blocking proof-record finding verbatim, with the assertion it judged. The new record MUST answer each finding in a response section, either by stating the change made to that assertion's reproduction steps or by stating that the finding was not answered and why. Before `review` is entered, the workflow MUST compare each judged assertion's steps with the steps that finding judged. A lap whose steps are byte-identical MUST end at the existing `non_converged` terminal with a cause naming the unanswered finding, and MUST spend no review visit.

One sentence of the existing recapture paragraph is amended to point at the new paragraph. Scenario 354 exercises it.

### Motivation

Measured 2026-11-12 by gmktec-factory-placement (plan livespec-dev-tooling-me5aqz) on legacy-coordinator-agent's ruling (session cb187a57). The window was 72 hours, 2026-11-09 10:30Z to 2026-11-12 10:30Z, read from every fleet repository's dispatch journal (outcome rows carrying LIVESPEC_RECAPTURE_EXHAUSTED) and from the run durations `fabro ps -a` reports on petri. In that window, 5 runs ended LIVESPEC_RECAPTURE_EXHAUSTED on a proof-content finding that recurred unchanged across all three recapture verdicts, about 12.4 run-hours in all:

- bd-ib-qshcwc, run 01M73ZK6Z090: a proof that stops short of the refusal it claims to prove.
- bd-ib-fde4ie, run 01M74D0JAMPM: a throwaway commit made with no hooks installed, in place of a fix-turn commit through the gate.
- bd-ib-lrjdlo, run 01M76Z1PZCRN: a statement built from the Definition of Done in place of the item's asked-for behaviour.
- livespec-dev-tooling-627xuz, run 01M773XDZTVR: a fixture that declares the members the assertion requires it NOT to declare.
- bd-ib-ngyfmi, run 01M77B4XB59M: a generated script missing the helper it invokes.

Each finding was specific, checkable against the recorded steps, and satisfiable in a sandbox, so no Definition-of-Done shape defeats capture and a filing-time screen would not help.

The publish-draft-green-work-loss seat spot-checked the lrjdlo run on PR #5008. Its second and third captured records (07:11Z and 07:16Z) still carry the substitution the 07:09Z and 07:14Z review findings named. The lap therefore re-captured without answering the finding, and review read the newer record each time.

The defect is that nothing obliges a lap to answer the finding it was sent back for, and nothing stops a lap that changed nothing from spending a review visit. Recovery after exhaustion (Scenarios 342 and 343, closed bd-ib-p6ammc) is unchanged; this proposal is about not exhausting.

Fleet scope: the `implement-work-item` workflow ships in this plugin's payload and runs for every tenant the Dispatcher admits, so the rule applies to every repository dispatched through it.

Owning work item: bd-ib-gixqwz, plan publish-draft-green-work-loss (epic bd-ib-acrr56).

Co-edit owed at revise, outside this spec target: `tests/heading-coverage.json` gains one row for the new `## Scenario 354` heading (test TODO, reason naming bd-ib-gixqwz). The revise MUST confirm that Scenario 354 is still free when it cuts, because Scenarios 345 to 353 are claimed by open proposals and Scenario 353 is claimed twice. If 354 is taken, the revise MUST renumber.

### Proposed Changes

1. contracts.md: insert this new paragraph IMMEDIATELY BEFORE the paragraph that begins "**`proof_verify`.** The node MUST run on an adapter distinct from the implementer's", that is, after the paragraph that begins "A blocking review finding whose subject is the latest captured record":

**A recapture lap answers each finding it was sent back for.** This paragraph governs every `proof_capture` visit entered on a recapture verdict from `review`, and every `proof_capture` visit that a fix round reaches while the verdict that started the round carried a proof-record finding. It does not govern a fidelity verdict from `proof_verify`, whose findings concern the record's rendering rather than its steps. It also does not govern a finding that the record is not current for the head under review, or that the newest captured comment does not parse as a record: neither of those is answered by changing an assertion's steps.

- The visit's brief MUST carry each blocking proof-record finding of the verdict verbatim. Each finding MUST name the assertion it judged, by its Definition of Done ordinal, or state that it judged the record as a whole. The brief MUST also name the record that finding judged by its comment URL.
- The new captured record MUST carry one response for each such finding. Each response MUST quote the finding verbatim and name the assertion it judged. It MUST then state either the change made to that assertion's reproduction steps, or that the finding was not answered and why.
- Before `review` is entered, the workflow MUST compare, for each finding that named an assertion, that assertion's reproduction steps in the new record with that assertion's reproduction steps in the record the finding judged. The comparison MUST be byte-for-byte, MUST be computed from the two records alone, and MUST NOT take a language-model judgement.
- When any compared assertion's steps are byte-identical, the run MUST NOT enter `review`. It MUST end at the existing `non_converged` terminal with the cause `LIVESPEC_RECAPTURE_UNANSWERED`, naming each finding whose assertion's steps did not change, the assertion's ordinal and the URL of the record that finding judged. The cause MUST carry the record's "not answered" statement for that finding when the record makes one. That ending consumes no `review` visit and no recapture lap, and the preserved-work and recovery-routing rules that apply to a recapture-exhausted run apply to it unchanged.
- When every compared assertion's steps changed, the run enters `review` exactly as before. `review` MUST read each response beside the steps it describes, and a finding returned word for word against changed steps remains an ordinary blocking finding under the existing two-lap bound.

Scenario 354 in `scenarios.md` exercises this paragraph.

1b. contracts.md: in the paragraph that begins "A blocking review finding whose subject is the latest captured record", change the sentence "It MUST read that record when the preamble carries no finding, and MUST publish a new captured record, current for the publish head, that addresses each finding." to: "It MUST read that record when the preamble carries no finding, and MUST publish a new captured record, current for the publish head, that addresses each finding as the paragraph \"A recapture lap answers each finding it was sent back for\" requires." No other sentence of that paragraph changes.

2. scenarios.md: append this new H2 section after the last ratified scenario:

## Scenario 354 — A recapture lap answers each blocking proof-record finding, and a lap whose judged steps did not change ends before review

```gherkin
Feature: A recapture lap cannot spend a review visit on the proof it was sent back for
  Scenario: The recapture brief carries the finding verbatim with the assertion it judged
    Given a run whose review ended with a recapture verdict carrying one blocking proof-record finding against assertion 2 of record R1
    When the run enters proof_capture with preferred_label recapture
    Then the proof_capture brief carries that finding verbatim
    And the brief names assertion 2 and the comment URL of R1

  Scenario: The new record answers each finding
    Given that recapture entry
    When proof_capture publishes record R2 whose steps for assertion 2 differ from R1's
    Then R2 carries a response that quotes the finding, names assertion 2 and states the change made to its steps
    And the run enters review

  Scenario: A lap whose judged steps are byte-identical ends before review
    Given that recapture entry
    When proof_capture publishes record R2 whose steps for assertion 2 are byte-identical to R1's
    Then the run does not enter review
    And the run ends at non_converged with the cause LIVESPEC_RECAPTURE_UNANSWERED naming the finding, assertion 2 and the comment URL of R1
    And no review visit and no recapture lap is consumed

  Scenario: A finding stated as not answered is carried into the cause
    Given that recapture entry
    When proof_capture publishes record R2 whose response states the finding was not answered because the sandbox lacks the asserted surface, and whose steps for assertion 2 are byte-identical to R1's
    Then the run ends at non_converged with the cause LIVESPEC_RECAPTURE_UNANSWERED
    And the cause carries R2's not-answered statement for that finding

  Scenario: A currency finding is not compared
    Given a run whose review ended with a recapture verdict whose only blocking finding is that record R1 is not current for the published head
    When proof_capture publishes record R2 for the published head with steps byte-identical to R1's
    Then the run enters review
```

No existing H2 heading is renamed or removed. The revise that accepts this proposal MUST add one `tests/heading-coverage.json` row for the new `## Scenario 354` heading in the same change.
