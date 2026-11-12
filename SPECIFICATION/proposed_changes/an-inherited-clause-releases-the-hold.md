---
topic: an-inherited-clause-releases-the-hold
author: claude-opus-5-5
created_at: 2026-11-12T10:18:15Z
---

## Proposal: A held item whose behaviour an inherited specification file states is released without a local ratification

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Proposal the-spec-change-tier-judgement (#5031) makes the spec-stated judgement read inherited specification files: other repositories' spec files that a repository's constraints.md declares as applying without restatement. It does not change the hold. A held spec-change-tier item still waits for its OWN linked topic's local ratification even when the judgement now returns `stated` against an inherited clause, so a behaviour a library repository ratified as a fleet contract still holds every consumer's slice. This proposal treats an inherited clause as ratified text: an item it states is an implementation follow-up, released at the next intake or drain pass. It also lets `release-spec-tier` attest an inherited heading.

### Motivation

Work item bd-ib-bkkasc (plan bd-ib-ax3rds), decided on legacy-coordinator-agent's (session c8c6cc4b) §10 routing on 2026-11-12, then re-scoped to ALIGN with #5031 (bd-ib-lrjdlo, plan bd-ib-acrr56), which already supplies the reading mechanism. Trigger: livespec-dev-tooling v202 (livespec-dev-tooling#4279) ratified a FLEET contract in dev-tooling's `## Delegated pre-push gate` (Token memoization). Eight slices implement it (livespec-driver-claude-d5hgms, livespec-driver-codex-xzlzvd, livespec-driver-pi-ee555c, bd-gj-kiflbk, livespec-runtime-u6vrc5, livespec-console-beads-fabro-2cix4o, bd-ib-p2qt2j, livespec-kjpjq6), and all eight are held at spec-change because each is judged against its own tree (bd-ib-p2qt2j: "The delegated cluster token itself is defined only in a livespec-dev-tooling spec that is not part of this tree"). With #5031 alone, each consumer's judgement could return `stated`, but under §"Grooming and slice-size calibration" → "An autonomy tier is assigned" the hold still requires the item's linked topic to carry a local revision record with decision accept or modify. These slices' topics are their own derived stems, which nobody will ever propose, so they would stay held. Pressing `release-spec-tier` against a LOCAL heading that does not state the behaviour would be a false attestation, which the coordinator refused. Measured 2026-11-12: none of the eight consumers' constraints.md yet declares livespec-dev-tooling's spec as inherited. Each will need one declaration sentence under #5031's grammar; that is a one-time declaration per repository, after which every later dev-tooling contract is read. In-flight alignment: #5031 `align` (this builds on its inherited-file definition and changes none of it); #5019 `align`.

### Proposed Changes

**1. An inherited clause releases the hold (`contracts.md` §"Grooming and slice-size calibration" → the bullet "**An autonomy tier is assigned**").** After the sentence that holds a spec-change-tier item out of `ready` until its linked topic's revision record carries decision `accept` or `modify` and the judgement returns `stated`, add:

> A clause of an inherited specification file, as §"Dispatcher admission, WIP cap, and post-merge acceptance" → §"Effective acceptance criteria" defines one, is ratified text of the repository that owns that file. So when the judgement, re-run against the ratified specification text including the inherited files, returns `stated` for a held item's asked-for behaviour and names a heading of an inherited specification file as governing, the item MUST be treated as an implementation follow-up to an already ratified change. The next intake or drain pass MUST release it exactly as this bullet releases an item whose linked topic was ratified locally, with no local proposed-change ratification of its linked topic. Its tier record MUST name the inherited file's declared path and the stating heading. A behaviour that only an undeclared repository's specification states MUST NOT release a hold.

**2. `release-spec-tier` attests an inherited heading (same bullet, the `release-spec-tier` sentences).** The `<heading>` argument MUST also accept `<declared-path>:<heading>`, naming the verbatim H2 heading of a declared inherited specification file at the path the repository's `constraints.md` declares. For such an attestation the durable ledger comment and the dispatch-journal entry MUST record that declared path in place of the local spec file, beside the clause digest they already record. A path no declaration names MUST be refused, naming the reason.

**3. Scenario (`scenarios.md`).** Append:

## Scenario 355 — A held item whose behaviour an inherited specification file states is released without a local ratification

```gherkin
Feature: a library-ratified contract releases its consumers' held slices
  Scenario: an inherited clause states the behaviour
    Given a repository whose constraints.md declares another repository's contracts file as applying without restatement
    And a held spec-change-tier item whose asked-for behaviour that inherited file states and the local tree does not
    And no local revision record ratifies the item's linked topic
    When the next intake pass runs
    Then the item is released as an implementation follow-up
    And its tier record names the inherited file's declared path and the stating heading
  Scenario: an undeclared repository's text does not release a hold
    Given a held item whose asked-for behaviour only an undeclared repository's specification states
    When the next intake pass runs
    Then the item stays held
  Scenario: release-spec-tier attests an inherited heading
    Given a held item and a heading of a declared inherited specification file that states its behaviour
    When a human drives release-spec-tier naming that declared path and heading
    Then the hold is released and the attestation records the declared path and the clause digest
```

**4. **Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading, carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json` or edited directly in that commit, with `test: "TODO"`, `work_item: "bd-ib-bkkasc"` and a non-empty `reason` naming the tier the owed test runs at, integration or above; and one matching `tests/heading-coverage-debt.json` entry carrying the key three, `work_item: "bd-ib-bkkasc"` and `first_seen` set to the revise date. If the revise renumbers Scenario 355, the row and entry MUST carry the renumbered heading text.
