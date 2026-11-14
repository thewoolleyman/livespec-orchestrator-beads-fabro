---
topic: dod-gate-check-5-names
author: claude-opus-5-5
created_at: 2026-11-14T02:03:51Z
---

## Proposal: dod_gate check 5 names three more surface classes: a long reproduction, a missing harness, and a git write

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

contracts.md's check-5 list of surface classes that no sandbox capability provides gains three entries. The first is a reproduction that runs longer than one proof_capture turn. The second is a harness or fixture that neither the repository nor the item's own deliverables provide. The third is a git commit or push that the proof_capture stage itself would have to perform, including a push to a local bare origin, because that stage is read-only on the repository. Scenario 272's examples gain the same three rows. A scenario also states that a reproduction command the repository provides, which completes within one turn, raises no proof-surface finding. Every taking of the Definition-of-Done judgement (dod_gate, pre-admission, pre-dispatch, and the filing display once the-filing-display-shows-the ratifies) shares the rubric, so each holds or names these items before a factory run is spent.

### Motivation

Work items bd-ib-x7sm72 and bd-ib-xzmca5. Both are linked to this topic by their derived stem, and both are children of plan factory-run-yield, epic bd-ib-ft26pi, carrying assertion 1 (refuse assertions the sandbox cannot prove). Measured causes: bd-ib-2it27f (run 01M7B7ECXJ0C1BFDBTN7SSMNA5) asked for 20 consecutive full fleet-launch harness runs under load, and one unloaded run took 11m51s, so proof_capture timed out at 1800000 ms on both attempts. overseer-uzvcbn.20 (run 01M7BJ9RV3HZZ1YTH6A2K9B3T1) needed a harness nothing provided and timed out on three attempts. bd-ib-hzul2n and bd-ib-yw7yot ended NEEDS-HUMAN at proof_capture because their assertions needed a git push to a local bare origin, while proof-capture.md says 'This stage is READ-ONLY on the repository' and 'Do NOT commit, and do NOT push'. Every one of these runs passed dod_gate and spent a full implement before the refusal. The spec-change-tier judgement graded x7sm72 PARTIAL, because the check-5 list names only four classes. The git-write class is drawn narrowly: a push performed INSIDE a test the repository's suite runs, against a scratch repository the test creates, is not this class, because the suite run is the proof and the capture stage performs no git write. Effect on the track metric (PRs per repository per hour merged to main and green): each such item stops at dod_gate, or earlier at a host taking, instead of spending an implement run and a proof_capture turn. That returns the run slot to work that can merge. Measured as the weekly count of runs ending at proof_capture by timeout or by a read-only refusal of a git write, which becomes readable as livespec.dispatch.failure_class once a-factory-run-s-terminal ratifies. In-flight alignment: default-align. It is compatible with #5205 (a-factory-run-s-terminal) and #5209 (the-filing-display-shows-the) from the same plan; no other open spec pull request touches check 5 (surveyed 2026-11-14).

### Proposed Changes

**1. Three more surface classes (`contracts.md` §"Definition-of-Done and Proof-of-Done stages", the `dod_gate` deliverable-policy paragraph).** Replace the sentence "The surface classes that no sandbox capability provides are: an external cluster or service; a credential or kubeconfig not given to the sandbox; operator-host state; and the released-build effects of a changed prompt or workflow file, including a stage prompt or workflow file under `.claude-plugin/.fabro/` that the item itself changes." with:

> The surface classes that no sandbox capability provides are: an external cluster or service; a credential or kubeconfig not given to the sandbox; operator-host state; the released-build effects of a changed prompt or workflow file, including a stage prompt or workflow file under `.claude-plugin/.fabro/` that the item itself changes; a reproduction that runs longer than one `proof_capture` turn, such as repeated full-suite runs or a soak under host load; a harness or fixture that neither the repository nor the item's own deliverables provide; and a git commit or push that the `proof_capture` stage itself would have to perform, including a push to a local bare origin, because that stage is read-only on the repository. A git write performed inside a test the repository's own suite runs, against a repository that test creates, is not of that last class. A reproduction command the repository provides that completes within one `proof_capture` turn is not a surface of these classes.

The following sentence ("The node MUST name the surface of each `factory_captured` assertion before judging it, ...") is kept unchanged and covers the three new classes.

**2. Scenario 272 (`scenarios.md`).** Append three rows to the `Examples:` table of `Scenario Outline: The gate names the surface class an assertion's proof needs`:

```gherkin
      | a reproduction that runs longer than one proof_capture turn                      |
      | a harness or fixture that neither the repository nor the item provides           |
      | a git commit or push the read-only proof_capture stage would have to perform     |
```

and append this scenario to Scenario 272:

```gherkin
  Scenario: A repository-provided reproduction that fits one turn raises no proof-surface finding
    Given an item whose factory-captured assertion names a reproduction command the repository provides
    And that command completes within one proof_capture turn
    And any git write it performs happens inside a test against a repository the test creates
    When the dod_gate node evaluates the rendered goal
    Then the gate raises no proof-surface finding for that assertion
```

**3. Heading coverage.** No `## ` heading is added or removed, so `tests/heading-coverage.json` is unchanged.
