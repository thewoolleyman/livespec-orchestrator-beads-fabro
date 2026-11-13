---
topic: a-routing-schema-node-prints-a-directive-on-every-exit-0-path
author: claude:factory-run-work-preservation plan seat session d3d4ab
created_at: 2026-11-13T00:28:07Z
---

## Proposal: A routing-schema command node prints a routing directive on every exit-0 path, and a commit-time check refuses a committed graph that does not

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add a "Routing-schema command nodes" bullet to constraints.md §"Fabro runtime constraints". It requires every command node of a committed workflow graph that declares `output_schema="routing"` to print a routing directive on stdout on every path on which its script exits 0, its success path included. A directive's `preferred_next_label` must be one an outgoing edge of that node takes. The repository's commit-time check aggregate MUST refuse a committed graph that breaks either rule, naming the graph file and the node, and the check MUST be invocable from another fleet repository's aggregate against that repository's own committed graphs. Add one numberless scenario carrying the behaviour, plus its heading-coverage and debt-register rows.

### Motivation

MAINTAINER DIRECTION, verbatim, relayed by legacy-coordinator-agent from the scope event of about 00:3xZ on 2026-11-13 on epic livespec-dev-tooling-6tgd2z: "Ensure this doesn't happen again." The coordinator ruled that the routing-directive rule must be in the spec before the gate that enforces it (bd-ib-nuswku, P1) is approved.

The incident: 171ca17b2 (PR #4989, bd-ib-woiqjm) gave the implement-work-item graph's `fix_commit_settle` node `output_schema="routing"`, while its settled-success path still ended in a bare `exit 0` with empty stdout. The engine parses a routing-schema node's stdout only when the stage succeeded (petri `crates/attractor/steps/src/command.rs`, the `output_schema == "routing"` branch). It fails a missing directive as `bad_output` ("the script's output is not a routing directive"), and the third such failure ended each run RoutingBlocked. Every run whose fix stage committed cleanly died at that node. Six runs were measured on 2026-11-12: livespec-dev-tooling o4j3kg (01M78J9HFWDT), lmuhvi (01M78NRFTY2V), kjwanx (01M78J2W8W2F), 7sqr36 (01M78SVQF4NJ), wc6sxv (01M78YNSH7G9) and ehug6z (01M78X72TBS2). The schema change was reverted by #5100 (ab4dbe812), which ships in v0.325.0. Nothing at commit time could have refused 171ca17b2: SPECIFICATION/ states no rule about routing directives or `output_schema` (contracts.md, constraints.md and scenarios.md searched for output_schema, preferred_next_label and routing directive; zero hits), and the existing factory-graph gate (`check-fabro-graph-validity`, which runs `fabro validate`) validates graph structure, not what a script prints.

The directive's shape is the engine's, read from petri `crates/attractor/steps/src/directive.rs`: the last JSON object on stdout that carries any of `preferred_next_label`, `outcome`, `failure_reason`, `suggested_next_ids` or `context_updates`.

FLEET SCOPE, measured 2026-11-13 across the clones under /data/projects: in the livespec fleet only livespec-orchestrator-beads-fabro commits routing-schema nodes today, 7 of them, all in `.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`. livespec-console-beads-fabro commits none. The engine repositories fabro and petri commit some, but they are not fleet members. The rule nonetheless covers every graph a fleet repository commits, the console fork included, so the check must be invocable from those repositories' aggregates.

IN-FLIGHT ALIGNMENT: the pending proposal the-factory-graph-gate-validates also edits constraints.md §"Fabro runtime constraints", but only its "CI graph-gate binary" bullet, and adds its own numberless scenario. This proposal adds a separate bullet and a separate scenario, and changes neither of those. Relationship: align. The open spec branches spec/a-fork-test-s-verdict-never, spec/codex-floor-reset-proximity, spec/red-turn-changes-no-product-file, spec/revise-attention-item-answer-policy and spec/revise-v330-goal-template-opener-modify touch the same section on other bullets only. Relationship: align.

### Proposed Changes

### 1. `SPECIFICATION/constraints.md` §"Fabro runtime constraints": add one bullet

Append this bullet to the section's bullet list. No existing bullet changes:

```markdown
- **Routing-schema command nodes.** A command node of a committed workflow
  graph that declares `output_schema="routing"` MUST print a routing
  directive on stdout on every path on which its script exits with status 0,
  its success path included. A routing directive is a JSON object carrying
  at least one routing field the engine recognises: `preferred_next_label`,
  `outcome`, `failure_reason`, `suggested_next_ids` or `context_updates`.
  The engine reads the directive only when the script exits 0, and it fails
  the stage when none is printed. A path that exits non-zero MAY print no
  directive, because the engine routes it by the node's failure edges. When
  a directive's `preferred_next_label` matches no `preferred_label=`
  condition on the node's outgoing edges, the node MUST carry an
  unconditional outgoing edge. The repository's commit-time check aggregate
  MUST refuse a committed graph that breaks either rule, naming the graph
  file and the node, and the label as well when the label rule is broken.
  The check MUST read every workflow graph the repository commits, member
  and forked graphs included. It MUST be invocable as one command from
  another fleet repository's check aggregate against that repository's own
  committed graphs, so a forked graph is held to the same rule.
```

### 2. `SPECIFICATION/scenarios.md`: add one scenario, numbered at revise

The heading is numberless here. The revise pass MUST assign the next free scenario number and update the heading text in changes 3 and 4 to match.

~~~markdown
## Scenario: a routing-schema command node prints a routing directive on every exit-0 path, and the commit-time check refuses a graph whose node does not

```gherkin
Feature: A routing-schema node always tells the engine where to go
  As a maintainer committing a change to a Fabro workflow graph
  I want a routing-schema node that can exit 0 without a routing directive refused at commit time
  So that no run dies RoutingBlocked on a path that succeeded

  Scenario: A success path with no directive is refused
    Given a committed workflow graph with a command node declaring output_schema="routing"
    And the node's script has a path that exits 0 printing nothing on stdout
    When the repository's commit-time check aggregate runs
    Then the aggregate fails naming the graph file and the node

  Scenario: A directive label that no edge takes is refused
    Given a routing-schema command node whose script prints {"preferred_next_label":"retry"} and exits 0
    And no outgoing edge of that node carries the condition preferred_label=retry
    And the node has no unconditional outgoing edge
    When the repository's commit-time check aggregate runs
    Then the aggregate fails naming the graph file, the node and the label retry

  Scenario: A non-zero exit needs no directive
    Given a routing-schema command node whose failure path exits 1 printing nothing on stdout
    And every exit-0 path of the node prints a routing directive that an outgoing edge takes
    When the repository's commit-time check aggregate runs
    Then the aggregate reports no finding for that node

  Scenario: A forked graph in another fleet repository is held to the same rule
    Given a fleet repository that commits a forked workflow graph with a routing-schema command node whose success path prints nothing
    When that repository's check aggregate runs the check against its own committed graphs
    Then that repository's aggregate fails naming its graph file and the node
```
~~~

### 3. `tests/heading-coverage.json`: add the new heading in the same revise

The revise that ratifies this MUST add one entry, using the heading as numbered at revise:

```json
{"heading": "## Scenario: a routing-schema command node prints a routing directive on every exit-0 path, and the commit-time check refuses a graph whose node does not", "spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "test": "TODO", "reason": "A test at the integration tier or above is owed: the commit-time routing-directive check's own suite, delivered by bd-ib-nuswku, which fails on a fixture graph whose routing-schema node exits 0 without a directive."}
```

### 4. `tests/heading-coverage-debt.json`: add the matching row in the same revise

The register has no generator, so the row is authored. `check-heading-coverage-debt-register` admits it under its spec-first admission, because this same change introduces the heading:

```json
{"spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "heading": "## Scenario: a routing-schema command node prints a routing directive on every exit-0 path, and the commit-time check refuses a graph whose node does not", "work_item": "bd-ib-nuswku", "first_seen": "<revise date>"}
```

No existing heading changes, per AGENTS.md §"Revise co-edit discipline".

### 5. Follow-through outside the spec (not part of this revise)

On ratification, bd-ib-nuswku's Definition of Done `References:` line SHOULD name the new scenario heading, as numbered at revise, beside `## Fabro runtime constraints`. Its spec-change tier is then re-classified, and it is approved for dispatch. The in-session forward fix that re-lands the `fix_commit_settle` routing schema with a directive on every exit-0 path MUST satisfy the new bullet when it lands.
