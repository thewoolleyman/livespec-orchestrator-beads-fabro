---
topic: sandbox-setup-runs-as-explicit-command-nodes
author: claude-sonnet-5-5
created_at: 2026-11-10T13:10:00Z
---

## Proposal: Sandbox setup runs as numbered command nodes after `start`, a failed setup node ends the run, and no committed workflow carries a run-config prepare table

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

The sandbox setup chain, which the plugin carried as `[[run.prepare.steps]]` in each committed `workflow.toml` and appended to in the Dispatcher's overlay, becomes a chain of explicit command nodes named `run_prepare_1` to `run_prepare_<N>`, wired after `start` and before the first stage. The committed workflows declare their own steps as nodes. The Dispatcher appends the steps it materializes to the chain in the per-dispatch graph, in the order the overlay always appended them. Every setup node routes a failure to a terminal `setup_failed` node, because a command node that exits non-zero otherwise follows its unconditional edge and the run succeeds. No committed workflow declares a prepare table. In `scenarios.md` the scenario that admits a token "in a prepare-step position" is split, because the bundled workflows no longer place a token there and only a target-local run configuration can, and three scenarios are added to Scenario 32 for the new shape.

### Motivation

Upstream `fabro-sh/fabro` `b452f498f`, first released in `v0.396.0-nightly.0`, makes the run-config parser refuse `run.prepare`, and `lithoscomputer/petri` `a04dae73` does the same. Its migration guide says setup commands belong in each workflow as explicit command nodes after `start`, or in a shared script those nodes invoke. The currency admission in `## Fabro runtime constraints` refuses every dispatch once the serving base is more than 30 calendar days older than the newest release, and the first upstream release on or after 2026-11-21 does that to the serving base `v0.393.0-nightly.1`. The workflows have to run on the engine that refuses the table before that date, so they have to stop declaring it first.

The node names are not free. The carrier's re-prepare-on-reacquire fix (`fabro-petri/src/prepare.rs`, carried from `bd-ib-ljw2xg`) recognises a run's setup only by the `run_prepare_` prefix and keeps that prefix on the v0.408 carrier as Fabro's own constant, so a sandbox re-acquired after a host error re-runs the setup only when the nodes carry those names.

The failure route is a measured requirement. On candidate run `01M6VWWEK8QP` at `bbe6938`, a command node that exited 1 followed its unconditional edge and the run ended succeeded, so a migrated setup node without an explicit failure route turns a failed step into a run that carries on without its setup. The engine rejects a node whose every outgoing edge is conditional (`all_conditional_edges`), so the unconditional edge stays and the failure edge is conditional beside it.

Linked work item: bd-ib-dpsiwz (plan `fabro-currency`, step 6 of the maintainer's 2026-11-02 rollout ruling). In-flight survey: no open spec pull request touches these headings.

### Proposed Changes

No H2 heading is added, renamed or removed, so `tests/heading-coverage.json` is unchanged.

1. In `constraints.md` §"Fabro runtime constraints", after the bullet that begins "- **One non-renewable Petri transition.**", insert this bullet:

"- **Sandbox setup is graph nodes.** A workflow the factory dispatches MUST declare no run-config prepare table (`run.prepare`), because Fabro releases from `v0.396.0-nightly.0` refuse it. Its sandbox setup MUST be explicit command nodes named `run_prepare_1` to `run_prepare_<N>`, numbered from 1 in the order the steps run, entered from `start` and ahead of the workflow's first stage; the fork's re-prepare-on-reacquire recognises a run's setup only by that name prefix. The Dispatcher MUST add every step it materializes for a dispatch to that chain as further `run_prepare_<N>` nodes of the dispatch's own graph, after the workflow's committed nodes and in the order it materialized them, and MUST carry none of them in the run configuration it submits. Every setup node MUST also route a failed outcome to a terminal node that ends the run and names the failed step, beside its unconditional edge to the next node, because a command node that exits non-zero otherwise follows that unconditional edge and the run goes on without its setup. A dispatch whose graph cannot take the chain MUST be refused before any run exists."

2. In `scenarios.md` §"Scenario 100 — The repository integration contract resolves once and projects identically to every seam", replace the scenario "A token in a prepare-step position is admitted with the overlay recorded as its resolver" (its heading line and its three steps) with:

```gherkin
  Scenario: A token in a setup node's script is admitted as a position the engine renders
    Given the implement-work-item workflow places an inputs token in the script of a run_prepare_N command node
    When the CI seam-equivalence check runs
    Then the check admits the position as one the engine renders

  Scenario: A token in a target-local run configuration's prepare step is admitted with the overlay recorded as its resolver
    Given a dispatch target's own run configuration places an inputs token in a run.prepare step position the Dispatcher's overlay substitutes host-side
    When the CI seam-equivalence check runs over that target's payload
    Then the check admits the position and records the overlay as its resolver
```

The scenario "An overlay-resolved position whose host-side substitution was removed fails the check" stays as it is: the overlay still substitutes the prepare steps a target-local run configuration declares, and those are the only prepare steps it substitutes.

3. In `scenarios.md` §"Scenario 32 — Adopter-target dispatch compatibility", inside its gherkin block, append after the scenario "Pull-primary resolves the target's default branch":

```gherkin
Scenario: The committed workflows declare their setup as numbered command nodes and no prepare table
  Given the committed implement-work-item and groom-work-item workflows
  When their run configurations and graphs are read
  Then neither run configuration declares a run-config prepare table
  And each graph declares command nodes run_prepare_1 to run_prepare_N entered from start and ahead of its first stage

Scenario: A dispatch carries the Dispatcher's materialized setup as further nodes in order
  Given a dispatch whose overlay materializes setup steps beyond the committed nodes
  When the Dispatcher writes the dispatch's run configuration and graph
  Then the run configuration declares no prepare table
  And the graph declares the materialized steps as run_prepare_N nodes continuing the committed numbering in the order the overlay materialized them
  And a dispatch whose graph has no edge to hang the chain on is refused before any run exists

Scenario: A failed setup node ends the run before the first stage and names the step
  Given a run of a workflow whose setup is run_prepare_N command nodes
  When one setup node exits non-zero
  Then the run routes to the terminal setup node rather than to the next node
  And the run ends without entering the first stage
  And the run's recorded failure cause names the failed run_prepare_N step
```
