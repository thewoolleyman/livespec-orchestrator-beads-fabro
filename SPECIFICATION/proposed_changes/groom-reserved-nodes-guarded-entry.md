---
topic: groom-reserved-nodes-guarded-entry
author: claude-opus-5-5
created_at: 2026-11-11T08:11:07Z
---

## Proposal: A groom-kind variant's unreached nodes carry one never-firing guarded entry edge, and its terminal reaches exit only as a failed ending

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The registered-variant clause says a groom-kind variant MUST declare an unreachable command `pr_refresh` and MAY leave `dod_gate`, `publish_draft`, `proof_capture` and `proof_verify` unreached by its edges. The Petri-era engine cannot accept those words read literally. Its validator walks every declared edge without reading conditions, and it refuses any node, or an exit, that start cannot reach (`attractor.unreachable_node`, `attractor.exit_unreachable`). This proposal ratifies the shape that shipped in bd-ib-ttrjvj (#4912, fb63f7ac8). Each declared-but-unreached node carries exactly one entry edge from the start node, guarded by a context key no node in the graph sets. "Unreachable" and "unreached" mean never entered by a run, not edge-free. The groom terminal `needs_human` reaches `exit` only behind `on_failure="exit"`, so a groom run still ends failed. One scenario states the behaviour.

### Motivation

bd-ib-ttrjvj: on master at v0.316.0, `fabro validate` refused the committed groom-work-item graph under both Petri-era clients (0.393.0-nightly.1 bbe6938 and 0.408.0-nightly.0 85071c8). It reported attractor.unreachable_node for exit, dod_gate, proof_capture, proof_verify and pr_refresh, and attractor.exit_unreachable. The attractor frontend's reachability check (crates/attractor/frontend/src/lower/structure.rs) follows every declared edge, ignores conditions, and offers no suppression. So no edge-free declaration can pass it. The fix in #4912 kept the declarations and added one guarded entry edge per node. Four tests that pinned "no edge names the node" now pin that guard instead. legacy-coordinator-agent ruled (ec00b770, 2026-11-11) that this reads the spec's words, not just conforms to them, and is therefore a ratification question. This proposal is that ratification, filed on the ruling. Plan fabro-currency (epic bd-ib-6tcjfx).

### Proposed Changes

1. In SPECIFICATION/contracts.md §"Self-contained plugin dispatch", the registered-variant clause's sentence beginning "A groom-kind variant MUST declare an unreachable command `pr_refresh`" MUST be followed by:

"Here "unreachable" and "unreached" mean that no run enters the node. They do not mean the node has no edge. The Petri-era engine's validator follows every declared edge without reading its condition and refuses a node, or an exit node, that the start node cannot reach. So each such node that a groom-kind variant declares MUST carry exactly one entry edge from the start node, guarded by a condition on a context key that no node of that graph sets. The node MUST NOT carry any other entry edge. That key MUST NOT appear anywhere in the variant's graph except in those guard conditions. Because the start node's unconditional edge is the only one whose route can hold, every run takes it. A groom-kind variant's `needs_human` terminal MUST reach the exit node through exactly one edge and MUST declare `on_failure="exit"`. Because `needs_human` always fails, a run that reaches it ends there failed, never green, and the needs-human sentinel remains the channel that carries the draft or the filing plan."

The ratified MAY that lets a groom-kind variant leave `dod_gate`, `publish_draft`, `proof_capture` and `proof_verify` unreached is unchanged. A variant that does not declare one of those nodes owes it no edge.

2. In SPECIFICATION/scenarios.md, one new scenario MUST be added. It is reserved as Scenario 347, and the revise pass MAY renumber it:

```gherkin
## Scenario 347 — A groom workflow variant's unreached nodes pass the Petri-era validator and are never entered

Feature: A groom variant declares its unreached nodes behind a guard no run sets
  Scenario: The committed groom graph validates and its reserved nodes are never entered
    Given the committed groom-kind workflow variant declares pr_refresh, dod_gate, proof_capture and proof_verify
    When it is validated with a Petri-era Fabro client
    Then the validator reports no unreachable node and no unreachable exit
    And each of those nodes carries exactly one entry edge, from the start node, guarded by a context key no node of the graph sets
    And a run of the variant takes the start node's unconditional edge and never enters any of those nodes
  Scenario: A groom run still ends failed at its terminal
    Given a groom run reaches its needs_human terminal
    When needs_human exits non-zero after writing its sentinel
    Then the run ends at the exit node with a failed status, not a green one
    And the Dispatcher reads the draft or filing plan from the needs-human sentinel as before
```

3. The revise pass MUST add a `tests/heading-coverage.json` entry for the new Scenario heading in the same change. `tests/livespec_orchestrator_beads_fabro/commands/test_groom_graph_reachability.py` and the guarded-edge assertions in `tests/integration/test_workflow_dod_gate_scenario131.py`, `tests/integration/test_workflow_proof_capture_scenario132.py`, `tests/integration/test_workflow_proof_verify_scenario132.py` and `tests/integration/test_scripted_publication_stages.py` already exercise it, and the entry SHOULD name the first of these.
