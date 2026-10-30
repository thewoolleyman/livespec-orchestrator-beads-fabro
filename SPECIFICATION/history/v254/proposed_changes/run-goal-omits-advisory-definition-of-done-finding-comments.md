---
topic: run-goal-omits-advisory-definition-of-done-finding-comments
author: claude-opus-5-5
created_at: 2026-10-30T20:10:59Z
---

## Proposal: The run goal omits filing-time advisory Definition-of-Done finding comments

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend the goal-omission clause in 'One rubric, one subject' (exercised by Scenario 239) so filing-time advisory Definition-of-Done finding comments, recognized by their first line beginning `definition-of-done finding (advisory):`, are left out of the run goal's operator-rider section while later operator comments still appear, and add a scenario beside Scenario 239.

### Motivation

Source item bd-ib-2dwxbu. Coordinator ruling R324(3), 2026-10-20: filing appends every advisory finding as a ledger comment, the run goal renders every ledger comment as an operator rider, and the dod_gate then fails the item on an advisory heuristic (measured on bd-ib-7a2ftx). Ledger comments cannot be edited or removed. The coordinator regroomed the item on 2026-10-30 under the maintainer's delegation ('You do the regroom, keep them moving.'), found no ratified heading stating the behaviour (the clause and Scenario 239 omit only livespec-dod-judgement records, Scenario 140 governs filing only), and routed this change here as topic run-goal-omits-advisory-definition-of-done-finding-comments. Unblocks re-grooming bd-ib-2dwxbu with the new heading on its References line.

### Proposed Changes

In SPECIFICATION/contracts.md, '## Dispatcher admission, WIP cap, and post-merge acceptance' -> 'One rubric, one subject', the GOAL bullet, replace this text: "every ledger comment except the Definition-of-Done JUDGEMENT RECORDS: each comment whose first line begins with `livespec-dod-judgement`, whichever taking or surface wrote it (verdict, did-not-run and disagreement records alike). Those records are receipts, not brief, so the Dispatcher MUST omit them from the node's rendered goal as well, and recording one MUST NOT change any subject digest." with: "every ledger comment except the Definition-of-Done JUDGEMENT RECORDS: each comment whose first line begins with `livespec-dod-judgement`, whichever taking or surface wrote it (verdict, did-not-run and disagreement records alike), and except the filing-time ADVISORY FINDING COMMENTS: each comment whose first line begins with `definition-of-done finding (advisory):`, the prefix filing writes before each advisory finding. Those records are receipts, not brief, so the Dispatcher MUST omit them from the node's rendered goal as well, and recording a judgement record MUST NOT change any subject digest. A ledger comment added after filing that is neither a judgement record nor an advisory finding comment remains in the rendered goal's operator-rider section."

Nothing else in the bullet changes.

In SPECIFICATION/scenarios.md, add Scenario NN (numbered at revise) after the last scenario, titled '## Scenario NN — The run goal omits a filing-time advisory finding comment and still lists a later operator comment', with this body:

```gherkin
Feature: The rendered goal omits filing-time advisory findings and keeps later operator riders
  Scenario: A filing-time advisory finding comment is left out of the goal and a later rider stays
    Given an item whose ledger carries a comment whose first line begins with `definition-of-done finding (advisory):`
    And an operator comment added after filing
    When the Dispatcher renders the node's goal for the item
    Then the operator-rider section lists the operator comment
    And the operator-rider section does not carry the advisory finding comment
    And the advisory finding comment remains on the item's ledger
```
