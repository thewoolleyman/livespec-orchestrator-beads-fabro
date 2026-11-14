---
topic: a-spec-change-tier-classification
author: claude-opus-5-5
created_at: 2026-11-14T03:04:23Z
---

## Proposal: A spec-change-tier classification that does not run records the judgement's own failure cause and each candidate it tried

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When the spec-stated judgement of a spec-change-tier classification returns no verdict, the did-not-run record names the judgement's own failure cause from a closed set: no eligible model, a provider fault, a timeout, the input bound, or an unparseable verdict. It also names each candidate the judgement tried, with its agent, model and exit code. Today the spec-stated step always records spec-stated-verdict-unreadable, so every failure reads as one cause. One record is kept per distinct cause.

### Motivation

Work item bd-ib-ot5se4 (child of plan factory-run-yield, epic bd-ib-ft26pi, placed there by legacy-coordinator-agent 2026-11-14). On 2026-11-14 at 02:41:50Z the dispatch-time classification of the priority-1 item bd-ib-cwuxfi did not run. Its ledger record says only spec-stated-verdict-unreadable, while the same dispatch's stderr shows the judge answered outcome=unparseable-verdict. In _spec_change_tier_gate.classify_spec_change_tier, the item-class step already maps the model's own cause, but the spec-stated step always passes CAUSE_VERDICT_UNREADABLE, so a provider fault, a timeout, the input bound and an unparseable reply are indistinguishable and the recurring one cannot be found. The autonomy-tier bullet of §"Grooming and slice-size calibration" requires intake to 'record that on the item' and names the causes in a parenthesis ('no eligible model, a timeout, or an unparseable verdict'). It states neither that the record carries which cause, nor the candidates, so the spec-change-tier judgement graded the item PARTIAL against Scenario 206. Effect on the track metric: the did-not-run classification is what let a stale verdict refuse bd-ib-cwuxfi (see the sibling topic when-the-dispatch-time-spec). Counting did-not-run records by cause is how the dominant cause gets fixed. Measure it as the share of livespec-spec-change-tier-unavailable records whose cause is the generic spec-stated-verdict-unreadable, with a target of zero. In-flight alignment: ALIGN with #5068 (a-spec-change-tier-record, bd-ib-bowuak), which makes a tier record name its build and rule. This proposal names the cause and candidates on the did-not-run record and is compatible. Default-align with the rest.

### Proposed Changes

**1. The did-not-run cause (`contracts.md` §"Grooming and slice-size calibration", autonomy-tier bullet).** Immediately after the sentence "When the classification cannot run (no eligible model, a timeout, or an unparseable verdict), intake MUST record that on the item and route it as it would without the classification; ...", insert:

> That did-not-run record MUST name the cause the failing step itself observed, as exactly one value of the closed set `no-eligible-model`, `provider-fault`, `timeout`, `input-bound` and `unparseable-verdict`, for the item-class step and the spec-stated step alike. It MUST name each candidate the failing step tried, with its agent, its model and its exit code. A step that cannot name its cause MUST record `unclassified`, never a cause it did not observe. The record is written once per distinct cause standing on the item, so two classifications that fail for different reasons append two records with different causes, and a repeat of a standing cause appends none. The same rule applies on every path that classifies: filing, groom, intake, drain and dispatch.

**2. Scenario 206 (`scenarios.md`).** Append to Scenario 206:

```gherkin
  Scenario: A classification that does not run records the judgement's own cause and candidates
    Given the spec-stated judgement of a classification returns an unparseable verdict from its only candidate
    When the classification records that it did not run
    Then the did-not-run record's cause is unparseable-verdict
    And the record names that candidate's agent, model and exit code

  Scenario: Different failure causes are recorded apart
    Given one classification of an item that failed on a provider fault
    When a later classification of the item fails on a timeout
    Then the item carries two did-not-run records whose causes are provider-fault and timeout
```

**3. Heading coverage.** No `## ` heading is added or removed, so `tests/heading-coverage.json` is unchanged.
