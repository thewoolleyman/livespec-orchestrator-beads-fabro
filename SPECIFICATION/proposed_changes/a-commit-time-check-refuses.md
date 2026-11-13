---
topic: a-commit-time-check-refuses
author: claude:factory-run-work-preservation plan seat session d3d4ab
created_at: 2026-11-13T01:10:21Z
---

## Proposal: A routing-schema command node ends every exit-0 path with a literal routing directive, in a shape a commit-time check can decide, and the check refuses a committed graph that breaks it

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add a "Routing-schema command nodes" bullet to constraints.md §"Fabro runtime constraints". A command node declaring `output_schema="routing"` MUST end every exit-0 path with a routing directive, which is the last routing-field JSON object in the node's captured output (stdout and stderr combined). Its script MUST have a decidable shape: every `exit 0`, and the end of the script, comes immediately after a command printing a literal directive in the same command list, and the only other exits are a literal non-zero `exit <N>` and `|| exit $?`. A directive label that no edge condition takes requires an unconditional edge. A commit-time check MUST refuse a committed graph that breaks a rule, naming file, node and (for the label rule) label. It MUST refuse as unverifiable, naming file, node and construct, a non-literal exit status, `exec`, `trap`, a shell function, `exit` in a subshell, or a non-literal label. The check takes a repository root, reads every `*.fabro` committed under `.claude-plugin/.fabro/workflows` and `.fabro/workflows`, needs no fabro client and no network, and is invocable from another fleet repository's aggregate. Add one numberless scenario plus its heading-coverage and debt-register rows.

### Motivation

MAINTAINER DIRECTION, verbatim, relayed by legacy-coordinator-agent from the scope event of about 00:3xZ on 2026-11-13 on epic livespec-dev-tooling-6tgd2z: "Ensure this doesn't happen again." The coordinator ruled that the routing-directive rule must be in the spec before the gate that enforces it (bd-ib-nuswku, P1) is approved.

The incident: 171ca17b2 (PR #4989, bd-ib-woiqjm) gave the implement-work-item graph's `fix_commit_settle` node `output_schema="routing"`, while its settled-success path still ended in a bare `exit 0` with empty stdout. The engine parses a routing-schema node's stdout only when the stage succeeded (petri `crates/attractor/steps/src/command.rs`, the `output_schema == "routing"` branch). It fails a missing directive as `bad_output` ("the script's output is not a routing directive"), and the third such failure ended each run RoutingBlocked. Every run whose fix stage committed cleanly died at that node. Six runs were measured on 2026-11-12: livespec-dev-tooling o4j3kg (01M78J9HFWDT), lmuhvi (01M78NRFTY2V), kjwanx (01M78J2W8W2F), 7sqr36 (01M78SVQF4NJ), wc6sxv (01M78YNSH7G9) and ehug6z (01M78X72TBS2). The schema change was reverted by #5100 (ab4dbe812), which ships in v0.325.0. Nothing at commit time could have refused 171ca17b2: SPECIFICATION/ states no rule about routing directives or `output_schema` (contracts.md, constraints.md and scenarios.md searched for output_schema, preferred_next_label and routing directive; zero hits), and the existing factory-graph gate (`check-fabro-graph-validity`, which runs `fabro validate`) validates graph structure, not what a script prints.

The directive's shape is the engine's, read from petri `crates/attractor/steps/src/directive.rs`: the last JSON object in the node's output that carries any of `preferred_next_label`, `outcome`, `failure_reason`, `suggested_next_ids` or `context_updates`. The engine runs every command script as `exec 2>&1` followed by the script (`command.rs`), so that output is stdout and stderr combined, which is why the bullet speaks of the node's captured output rather than stdout.

SCOPE NARROWING, stated so it is not silent: the maintainer's direction speaks of every node that declares an output_schema. This rule covers only command nodes that declare `output_schema="routing"`. The engine acts on a command node's output_schema only when it is "routing" (`command.rs`). The one other output_schema in the committed graphs is the `implement` ACP node's JSON Schema (`definition_of_done_complete`), which is checked against the agent's structured output at run time and has no script exit path for a commit-time check to read.

DECIDABILITY: "every exit-0 path" of an arbitrary shell script is not decidable, so the bullet fixes a shape a check can decide syntactically, and refuses as unverifiable anything outside it. The coordinator's grader measured all 7 routing-schema nodes on master (implement_completion, fix_open_red_route, publish_merged_reconcile_route, janitor_refresh_route, pr_refresh_merged_reconcile_route, pr_route, review_fix_open_red_route) and found each already in that shape: a literal `printf '%s\n' '{"preferred_next_label":"<label>"}'` right before every `exit 0` and at the script's end, with only `|| exit $?` otherwise. Arming the check therefore cannot turn master red, while 171ca17b2's `fix_commit_settle` fails it at two exits: the final bare `exit 0`, which is the incident path, and the runner-absent `exit 0`. One master script carries the word `exit` inside a quoted message, so the check must tokenize the script with shell quoting rather than match text.

FLEET SCOPE, measured 2026-11-13 across the clones under /data/projects: in the livespec fleet only livespec-orchestrator-beads-fabro commits routing-schema nodes today, 7 of them, all in `.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`. livespec-console-beads-fabro commits none. The engine repositories fabro and petri commit some, but they are not fleet members. The rule nonetheless covers every graph a fleet repository commits under `.claude-plugin/.fabro/workflows` or `.fabro/workflows`, so the check must be invocable from those repositories' aggregates against their own roots. It must need no fabro client and no network, so the client-version floor proposed in the-factory-graph-gate-validates (0.396.0) cannot fail it first on a host whose client is older.

IN-FLIGHT ALIGNMENT: the pending proposal the-factory-graph-gate-validates also edits constraints.md §"Fabro runtime constraints", but only its "CI graph-gate binary" bullet, and adds its own numberless scenario. This proposal adds a separate bullet and a separate scenario, and changes neither of those. Relationship: align. The open spec branches spec/a-fork-test-s-verdict-never, spec/codex-floor-reset-proximity, spec/red-turn-changes-no-product-file, spec/revise-attention-item-answer-policy and spec/revise-v330-goal-template-opener-modify touch the same section on other bullets only. Relationship: align.

TOPIC: this proposal is filed under `a-commit-time-check-refuses`, the linked-proposal topic that bd-ib-nuswku's spec-change tier record names (recorded 00:23Z, spec v361). A re-classify keeps the recorded topic, so ratification under any other slug would leave the item held.

### Proposed Changes

### 1. `SPECIFICATION/constraints.md` §"Fabro runtime constraints": add one bullet

Append this bullet to the section's bullet list. No existing bullet changes:

```markdown
- **Routing-schema command nodes.** A command node of a committed workflow
  graph that declares `output_schema="routing"` MUST end every path on which
  its script exits with status 0 with a routing directive. The engine runs
  the script with its standard error joined to its standard output, reads a
  directive only when the script exits 0, and fails the stage when there is
  none. The directive is therefore the last JSON object in that combined
  captured output that carries a routing field the engine recognises:
  `preferred_next_label`, `outcome`, `failure_reason`, `suggested_next_ids`
  or `context_updates`. Nothing the script prints after the directive may
  carry such a field. A path that exits non-zero MAY print no directive. So
  that this is decidable at commit time, the script of such a node MUST have
  this shape: every `exit 0`, and the end of the script, comes immediately
  after a command in the same command list that prints a literal directive,
  such as `printf '%s\n' '{"preferred_next_label":"<label>"}'`; the only
  other exits are a literal non-zero `exit <N>` and the `|| exit $?` idiom.
  When a directive's `preferred_next_label` matches no `preferred_label=`
  condition on the node's outgoing edges, the node MUST carry an
  unconditional outgoing edge. The repository's commit-time check aggregate
  MUST refuse a committed graph that breaks any of these rules, naming the
  graph file and the node, and also the label when the label rule is
  broken. It MUST refuse as unverifiable, naming the graph file, the node
  and the construct, a routing-schema script that uses a non-literal exit
  status other than `|| exit $?`, `exec`, `trap`, a shell function, `exit`
  inside a subshell, or a non-literal directive label. The check MUST take
  a repository root and read every `*.fabro` workflow graph committed under
  `.claude-plugin/.fabro/workflows` and `.fabro/workflows` there. It MUST
  need neither a fabro client nor network access, and it MUST be invocable
  as one command from another fleet repository's check aggregate against
  that repository's own root.
```

### 2. `SPECIFICATION/scenarios.md`: add one scenario, numbered at revise

The heading is numberless here. The revise pass MUST assign the next free scenario number and update the heading text in changes 3 and 4 to match.

~~~markdown
## Scenario: a commit-time check refuses a committed graph whose routing-schema command node can exit 0 without a literal routing directive

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
    Given a routing-schema command node whose script prints the literal directive {"preferred_next_label":"retry"} and then exits 0
    And no outgoing edge of that node carries the condition preferred_label=retry
    And the node has no unconditional outgoing edge
    When the repository's commit-time check aggregate runs
    Then the aggregate fails naming the graph file, the node and the label retry

  Scenario: A non-zero exit needs no directive
    Given a routing-schema command node whose failure path exits 1 printing nothing on stdout
    And every exit 0 and the end of the node's script come immediately after a literal directive that an outgoing edge takes
    When the repository's commit-time check aggregate runs
    Then the aggregate reports no finding for that node

  Scenario: A routing-schema script the check cannot decide is refused as unverifiable
    Given a committed workflow graph with a routing-schema command node whose script ends with exit "$status"
    When the repository's commit-time check aggregate runs
    Then the aggregate fails naming the graph file, the node and the construct exit "$status" as unverifiable

  Scenario: Another fleet repository's committed graph is held to the same rule without a fabro client
    Given another fleet repository that commits under .fabro/workflows a graph with a routing-schema command node whose success path prints nothing
    And no fabro client is installed on the host
    When that repository's check aggregate runs the check against its own repository root
    Then that repository's aggregate fails naming its graph file and the node
```
~~~

### 3. `tests/heading-coverage.json`: add the new heading in the same revise

The revise that ratifies this MUST add one entry, using the heading as numbered at revise:

```json
{"heading": "## Scenario: a commit-time check refuses a committed graph whose routing-schema command node can exit 0 without a literal routing directive", "spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "test": "TODO", "work_item": "bd-ib-nuswku", "reason": "A test at the integration tier or above is owed: the commit-time routing-directive check's own suite, delivered by bd-ib-nuswku, which fails on a fixture graph whose routing-schema node exits 0 without a directive."}
```

### 4. `tests/heading-coverage-debt.json`: add the matching row in the same revise

The register has no generator, so the row is authored. `check-heading-coverage-debt-register` admits it under its spec-first admission, because this same change introduces the heading:

```json
{"spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "heading": "## Scenario: a commit-time check refuses a committed graph whose routing-schema command node can exit 0 without a literal routing directive", "work_item": "bd-ib-nuswku", "first_seen": "<revise date>"}
```

No existing heading changes, per AGENTS.md §"Revise co-edit discipline".

### 5. Follow-through outside the spec (not part of this revise)

On ratification, bd-ib-nuswku's Definition of Done `References:` line SHOULD name the new scenario heading, as numbered at revise, beside `## Fabro runtime constraints`. Its spec-change tier is then re-classified, and it is approved for dispatch. The in-session forward fix that re-lands the `fix_commit_settle` routing schema with a directive on every exit-0 path MUST satisfy the new bullet when it lands.
