---
topic: dod-gate-check-5-names
author: claude-opus-5-5
created_at: 2026-10-30T20:10:58Z
---

## Proposal: dod_gate names the proof-surface classes that no sandbox capability provides

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Generalize the dod_gate paragraph of '## Self-contained plugin dispatch' so it lists the proof-surface classes no sandbox capability provides and requires the node to name each factory_captured assertion's surface, and add a scenario beside Scenario 139.

### Motivation

Source item bd-ib-3yiapm (dod_gate check 5 grades a factory_captured assertion's wording instead of naming its proof surface). Two measured cases: bd-ib-qnokup and livespec-dev-tooling-cmgqnz, where a gate passed assertions whose proof needed a real Job on the k3s gates cluster and implement ran 74 minutes before proof_capture refused. The coordinator regroomed the item on 2026-10-30 under the maintainer's delegation ('You do the regroom, keep them moving.'), cut one slice per assertion, and judged the credential/operator-host slice PARTIAL against the ratified text because the dod_gate paragraph does not say a credential, kubeconfig or operator-host state is such a surface; it routed the generalization here as topic dod-gate-check-5-names. Unblocks slice bd-ib-vhx5vl (credential/operator-host surface), which depends on bd-ib-hxkikj (external cluster/service surface).

### Proposed Changes

In SPECIFICATION/contracts.md, '## Self-contained plugin dispatch', the `dod_gate` paragraph, after the sentence ending "declare it `human_attested` only when no agent session can exercise it." and before "Its refusal of a `host_captured` or `human_attested` assertion that a sandbox capability could exercise MUST name the capability it relies on", insert this text in full: "The surface classes that no sandbox capability provides are: an external cluster or service; a credential or kubeconfig not given to the sandbox; operator-host state; and the released-build effects of a changed prompt or workflow file, including a stage prompt or workflow file under `.claude-plugin/.fabro/` that the item itself changes. The node MUST name the surface of each `factory_captured` assertion before judging it, and MUST report an assertion whose proof needs a surface of one of these classes as a Definition-of-Done finding that names that surface; for the released-build class the finding names the released-build requirement."

Nothing else in the paragraph changes.

In SPECIFICATION/scenarios.md, add Scenario NN (numbered at revise) after the last scenario, titled '## Scenario NN — A factory-captured assertion whose proof surface no sandbox capability provides is named in the gate's finding', with this body:

```gherkin
Feature: A factory-captured assertion whose proof surface no sandbox capability provides is a gate finding that names the surface
  Scenario Outline: The gate names the surface class an assertion's proof needs
    Given an item whose factory-captured assertion's proof needs <surface>
    When the dod_gate node evaluates the rendered goal
    Then the run ends through the structured needs-human ending
    And the finding names the assertion and names <surface> as its proof surface

    Examples:
      | surface                                                                          |
      | an external cluster or service                                                   |
      | a credential or kubeconfig not given to the sandbox                              |
      | operator-host state                                                              |
      | the released-build effects of a prompt or workflow file the item itself changes  |

  Scenario: A prompt or workflow file under .claude-plugin/.fabro/ that the item changes names the released-build requirement
    Given an item that changes a stage prompt file under .claude-plugin/.fabro/
    And a factory-captured assertion naming behaviour of that stage prompt
    When the dod_gate node evaluates the rendered goal
    Then the run ends through the structured needs-human ending
    And the finding names the released-build requirement
```
