---
topic: dod-judgement-shared-rubric
author: claude-opus-5-5
created_at: 2026-10-22T08:30:11Z
---

## Proposal: Every taking of the Definition-of-Done judgement grades one subject by one rubric

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

The Definition-of-Done judgement is taken up to three times before implementation spend: before admission, before dispatch, and in the `dod_gate` node. The ratified text already says the earlier two are "the same Definition-of-Done judgement the `dod_gate` node applies", but it does not pin the SUBJECT each taking grades or forbid a taking from adding its own grading guidance. The two have drifted apart in practice. This proposal makes the node's prompt file the one rubric artifact. Every taking MUST load it from the build that will execute the dispatch. A taking other than the node MAY append only an ending contract and a capability-source statement, and any grading guidance MUST live in the rubric itself. Every taking MUST grade the same subject: the item's rendered goal exactly as the node receives it (title, description, effective criteria, notes, lessons and every ledger comment), the verbatim body of each referenced heading, the spec tree of the default-branch tip a dispatch would seed from, and the capability set resolved from the committed `dispatcher.sandbox_capabilities` array. Verdict reuse is keyed on a digest of both subject and rubric, so a new comment or a changed rubric invalidates a stored verdict. The References-coverage rule the node actually enforces is written into the contract: a reference line must name, for each assertion, every scenario heading that states behaviour the assertion names and the non-scenario H2 whose clauses govern it. That rule stays a semantic judgement and is not added to the deterministic host-side wall. The node keeps running on every run. When the node refuses a subject and rubric that a pre-dispatch verdict admitted, the Dispatcher records the disagreement so the residual rate is measurable.

### Motivation

Filed under bd-ib-gob6gl (P1, coordinator rulings R588 and R589). Four measured instances on 2026-10-22 show a host-side PASS followed by an in-run refusal on byte-identical Definition-of-Done text, each costing a factory slot. (1) livespec-dev-tooling-u5j5f6: the host preflight passed on both legs; the in-run dod_gate of run 01M5GMPAYBDT refused after 73 s because the References line named only a non-scenario H2 while a scenario governed the fair-share behaviour. (2) livespec-dev-tooling-7kvh2d: the same Codex leg gave PASS and then FAIL ten minutes apart on unchanged text. (3) livespec-dev-tooling-7oec4d: the launch-time preflight passed at 07:52:30Z, and the in-run dod_gate of run 01M5H9TYCAVD refused at 55 s for three missing governing headings. (4) livespec-dev-tooling-4cipbr: the preflight passed at 08:01:58Z, and run 01M5HACC4AZZ refused at 2m27s for a missing contract section (`## Delegated pre-push gate`) whose clause governed two assertions. Reading the three takings shows they do not grade the same thing. The node grades the full rendered goal: title, description, criteria, notes, lessons and every ledger comment. The Dispatcher's host judgement (`_dispatcher_dod_judgement_run.py`) grades the effective criteria plus the referenced heading bodies, with no ledger comments. The stopgap `dev-tooling/dod-preflight.sh` grades title, description and comments. It also appends a check-5 grading instruction of its own that the node never receives, so the host and the node grade check 5 by different text. The References rule the node enforced in instances 1, 3 and 4 (every governing scenario plus the governing contract section) is stricter than the rubric's written check 6 (a non-scenario H2 alone is a finding only when a scenario states the behaviour). A reader of the contract therefore cannot predict which judge is right. R589 decides the direction: same inputs and same rubric; the in-run node stays, because contracts.md requires the semantic half to run in the node on every run; and a deterministic host References check is rejected. The original gob6gl parser defect (a non-bullet line inside the section projected as a factory_captured assertion) needs no spec change, because Scenario 131 already requires the host-side wall to refuse a malformed section; it stays in the implementing item's scope. Instance 2 shows nondeterminism within a single judge, which a shared rubric cannot remove. The disagreement record this proposal adds is what will measure that residual after the shared subject and rubric land.

### Proposed Changes

In `SPECIFICATION/contracts.md`, in the **`dod_gate`.** paragraph, replace the clause

> and every reference line that names only a non-scenario H2 while a scenario heading states the behaviour the assertion names (§"Effective acceptance criteria" → "Behavioural assertions" and "The Definition of Done section"), naming the remedy in each case.

with

> and every reference line that omits, for any assertion, a heading that governs it — each `## Scenario NN — <title>` heading of `scenarios.md` that states behaviour the assertion names, and each non-scenario H2 whose clauses govern that behaviour — naming each omitted heading verbatim and the remedy of adding it to the reference line (§"Effective acceptance criteria" → "Behavioural assertions" and "The Definition of Done section"). This reference-coverage finding is a semantic judgement: it MUST NOT be added to the mechanical half the host-side wall runs, and a reference line the wall accepts MAY still carry it.

In the same paragraph, after the final sentence "neither earlier judgement removes or replaces the node.", append:

> Every taking of this judgement grades the subject and rubric of "One rubric, one subject" in §"Effective acceptance criteria".

In `SPECIFICATION/contracts.md`, §"Effective acceptance criteria", insert a new paragraph immediately BEFORE the paragraph **Judged before admission.**:

> **One rubric, one subject.** The Definition-of-Done judgement is taken by the `dod_gate` node, before admission, before dispatch, and by any host-side preflight a repository runs before launching a dispatch. Every taking MUST grade by ONE rubric: the `dod_gate` node's prompt file, read from the plugin build that will execute the dispatch. A taking MUST NOT add, remove or restate a check. A taking other than the node MAY append only (a) an ending contract stating the verdict form it must return, and (b) a statement that the published capability file is unreachable, so the capability set is resolved from the committed `dispatcher.sandbox_capabilities` array alone. Any other guidance about how to grade a check MUST be written into the rubric itself, so that the node grades by it too. Every taking MUST grade the same SUBJECT: the item's rendered goal exactly as the Dispatcher would render it for the node (title, description, effective criteria, notes, lessons and every ledger comment), followed by the verbatim body of each heading its reference line names, against the governed repository's spec tree at the default-branch tip a dispatch would seed from, with the capability set resolved from the committed `dispatcher.sandbox_capabilities` array. The node additionally reads the published capability file, and its configuration-mismatch report is unchanged. Every recorded verdict MUST carry a digest of that subject and a digest of the rubric bytes it was graded by. The verdict reuse that "Judged again before dispatch" permits MUST require both digests to be unchanged, so an added ledger comment or a changed rubric invalidates a stored verdict. When a run's `dod_gate` node refuses an item whose most recent pre-dispatch verdict admitted the same subject digest under the same rubric digest, the Dispatcher MUST append one `dod-judgement-disagreement` row to the dispatch journal and one ledger comment on the item. Each MUST name the run, both digests, the admitting verdict's timestamp and the node's findings. The item MUST rest exactly as any `dod_gate` refusal rests it. Scenario 239 in `scenarios.md` exercises this paragraph.

In `SPECIFICATION/scenarios.md`, add after the last scenario:

```gherkin
## Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric

Feature: A Definition of Done passed before dispatch is graded in-run by the same rubric on the same subject
  As the operator of a factory
  I want every Definition-of-Done judgement to grade the same text by the same rules
  So that a pre-dispatch pass is not refused in-run on unchanged bytes

  Scenario: A host taking grades by the node's rubric and appends only its ending contract
    Given the plugin build that will execute a dispatch carries the dod_gate node's prompt file
    When the pre-dispatch judgement is taken on the host
    Then the judge's prompt carries that prompt file's bytes unchanged
    And after it only the host ending contract, the capability-source statement and the subject

  Scenario: The subject carries every ledger comment the node would receive
    Given a ready item whose ledger comments include a rider appended after filing
    When the pre-dispatch judgement is taken
    Then the subject it grades carries the rider's text as the node's rendered goal would
    And appending another comment to the item changes the recorded subject digest

  Scenario: A reference line missing a governing contract section is refused before dispatch
    Given a ready item whose reference line names one scenario heading
    And a non-scenario H2 of contracts.md whose clauses govern the item's second assertion is not on its reference line
    When the Dispatcher selects the item for a dispatch
    Then the pre-dispatch judgement refuses it naming that H2 verbatim with the remedy of adding it
    And no factory run is created

  Scenario: A changed rubric invalidates a stored verdict
    Given an item whose pre-dispatch verdict admitted it under one rubric digest
    And the plugin build that will execute the dispatch carries a dod_gate prompt file with different bytes
    When the Dispatcher selects the item for a dispatch
    Then the stored verdict is not reused
    And the judgement is taken again by the new rubric

  Scenario: An in-run refusal of an admitted subject is recorded as a disagreement
    Given an item whose pre-dispatch verdict admitted a subject digest under a rubric digest
    When the run's dod_gate node refuses that same subject under that same rubric
    Then the dispatch journal carries one dod-judgement-disagreement row naming the run, both digests, the admitting verdict's timestamp and the node's findings
    And the item carries one ledger comment with the same facts
    And the item rests at blocked with blocked_reason needs-human exactly as any dod_gate refusal rests it
```

In `tests/heading-coverage.json`, add the entry:

```json
{
  "heading": "## Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric",
  "spec_root": "SPECIFICATION",
  "spec_file": "scenarios.md",
  "test": "TODO",
  "reason": "An integration-tier test is owed for this heading: ratified with proposal dod-judgement-shared-rubric, and the owning work-item bd-ib-gob6gl makes every taking of the Definition-of-Done judgement grade one subject by one rubric, together with the test that binds this entry.",
  "work_item": "bd-ib-gob6gl"
}
```
