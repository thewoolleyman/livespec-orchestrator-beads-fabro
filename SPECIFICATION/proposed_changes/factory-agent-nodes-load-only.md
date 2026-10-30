---
topic: factory-agent-nodes-load-only
author: claude-opus-5-5:factory-context-per-turn-reduction
created_at: 2026-10-30T19:50:38Z
---

## Proposal: Factory ACP nodes load only the instruction files, skills, plugins and MCP tools each node declares

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add an optional per-node `loads` field to the ACP node adapter value in §"ACP node adapter configuration", naming the instruction files, skills, plugins and MCP servers that node's agent session loads. When some layer sets it, the Dispatcher launches the node so its session loads exactly that set. When no layer sets it, the node loads what its agent loads today. The bundled implement-work-item workflow declares a set on every ACP node: implement, fix and review_fix keep the governed repository's instruction file, and every other node loads none. Three scenarios cover the declared-only load, the layer replacement and the refusal of an undeliverable item.

### Motivation

Plan factory-context-per-turn-reduction (epic bd-ib-raqyki) measured on Claude Sonnet 5.5 that every factory ACP node loads the governed repository's CLAUDE.md -> AGENTS.md, about 54,650 tokens per request, on every turn of every node, whether or not the node writes code under the repository's rules (research notes 002, 003 and 005). Nothing in the configuration says what a node loads, so it cannot be reduced per node. The plan's Definition of Done requires a node's sandbox to load only what that node declares. Work item bd-ib-crtnzx carries the implementation; its filing judgement classed it spec-change tier because this section says nothing about such a declaration. The default-loading fallback keeps every other workflow and every adopter's vendored workflow unchanged until it opts in, and the same three-layer resolution lets a repository widen a node's set without a code change if a node's accepted-first-pass rate falls (plan assertion 4).

### Proposed Changes

In `SPECIFICATION/contracts.md` §"ACP node adapter configuration", insert the following paragraph immediately before the paragraph that begins `**Verification.**`:

> **Per-node context declaration.** A node's value, in either form, MAY carry one optional field, `loads`: a table of four arrays of strings — `instruction_files` (paths relative to the governed repository root, for example `AGENTS.md`), `skills`, `plugins` and `mcp_servers` (names as the node's agent identifies them). `loads` resolves through the same three layers as every other field, and a more specific layer that sets it REPLACES it whole; its arrays never merge across layers. When some layer sets `loads` for a node, the Dispatcher MUST launch that node's agent so that its session loads EXACTLY the declared set: every declared item, and no instruction file, skill, plugin or MCP tool — from the governed repository or from the sandbox user's agent configuration — that the declaration omits. A declared instruction file MUST reach the session whichever file name the node's agent reads it under, so declaring `AGENTS.md` covers a `CLAUDE.md` symlink to it. A node whose `loads` arrays are all empty loads none of the four kinds. When no layer sets `loads` for a node, that node loads what its agent loads by default. Harness settings the Dispatcher itself writes into the sandbox are not context under this rule and MUST still apply. A declared item the Dispatcher cannot deliver to that node's agent MUST refuse the dispatch before claim, naming the node and the item. The Dispatcher MUST journal each node's resolved `loads`, and the layer that supplied it, on the dispatch record beside the adapter record above. The bundled `implement-work-item` workflow's defaults MUST set `loads` on every one of its ACP nodes: `implement`, `fix` and `review_fix` declare the governed repository's instruction file, and every other ACP node declares all four arrays empty. Scenario 259 in `scenarios.md` exercises this rule.

In `SPECIFICATION/scenarios.md`, append one new scenario after the current last scenario. Its number MUST be the next unused scenario number at the time of the revise that accepts this proposal (259 as of this proposal; renumber the contracts.md cross-reference to match), and its heading MUST read `## Scenario 259 — A factory ACP node loads only the instruction files, skills, plugins and MCP tools its declaration names`:

```gherkin
Feature: Per-node context declaration

  Scenario: A factory ACP node loads only the instruction files, skills, plugins and MCP tools its declaration names
    Given the implement-work-item workflow's defaults set loads on the implement node to instruction_files ["AGENTS.md"] and on the review node to four empty arrays
    And the governed repository carries an AGENTS.md instruction file, a CLAUDE.md symlink to it, and a project MCP server configuration
    When an implementation run is dispatched
    Then the first request of the implement node session carries the text of AGENTS.md
    And the first request of the review node session carries no text of AGENTS.md
    And neither session lists a tool of the project MCP server
    And the dispatch record journals each node's resolved loads declaration and the layer that supplied it

  Scenario: A repository layer that sets loads replaces the workflow default whole
    Given the implement-work-item workflow's defaults set loads on the review node to four empty arrays
    And the dispatch target's dispatcher.acp_nodes sets loads on the review node to instruction_files ["AGENTS.md"]
    When an implementation run is dispatched
    Then the first request of the review node session carries the text of AGENTS.md
    And the dispatch record journals the review node's loads as supplied by the repository layer

  Scenario: A declared item the node's agent cannot be given refuses the dispatch before claim
    Given the dispatch target's dispatcher.acp_nodes sets loads on the review node to plugins ["no-such-plugin"]
    When a dispatch of an implementation item is requested
    Then the dispatch is refused before the item is claimed
    And the refusal names the review node and no-such-plugin
```

In `tests/heading-coverage.json`, add an entry for the new scenario heading with `test` set to `"TODO"` and the reason `"implemented by work item bd-ib-crtnzx (plan factory-context-per-turn-reduction)"`.
