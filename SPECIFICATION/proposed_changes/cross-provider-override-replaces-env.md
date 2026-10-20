---
topic: cross-provider-override-replaces-env
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-10-20T23:37:47Z
---

## Proposal: An acp_nodes layer that changes a node's agent replaces the inherited env instead of merging it

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

ACP node resolution merges `env` across layers, with the more specific layer's keys winning. When a more specific layer routes a node to a DIFFERENT agent, for example from `claude-acp` to `codex-acp`, the merge carries the replaced adapter's model and effort keys (such as `ANTHROPIC_MODEL` and `CLAUDE_CODE_EFFORT_LEVEL`) into the new adapter. The rendered adapter then names two different models, and any instrument that reads the model from it reports the wrong one. This proposal keeps the merge for layers that resolve to the same agent. When the more specific layer's resolved agent id differs from the less specific layer's, the less specific layer's `env` is discarded, and only the more specific layer's `env` applies.

### Motivation

Work-item bd-ib-5j4b. Measured 2026-08-26 on run 01M0YVK5KHMH (hp, release 0.82.0): this repository's review node, routed to Codex through `dispatcher.acp_nodes`, rendered an adapter carrying `ANTHROPIC_MODEL=claude-opus-4-8[1m]` beside a Codex configuration naming `gpt-5.6-terra`. The ratified per-field rule in "## ACP node adapter configuration" produces exactly that. The built-in Claude adapter still selects its model through `ANTHROPIC_MODEL` (§"Built-in ACP node defaults"), so the stale key is not inert to readers. Plan spec-implementation-lockstep R1 batch 12 routes the item here.

### Proposed Changes

In SPECIFICATION/contracts.md, section "ACP node adapter configuration", replace the sentence "Resolution is per node and per FIELD: a more specific layer that sets `command` or `args` REPLACES that field; `env` MERGES with the more specific layer's keys winning." with:

> Resolution is per node and per FIELD: a more specific layer that sets `command` or `args` REPLACES that field, and `env` MERGES with the more specific layer's keys winning, EXCEPT that when the more specific layer's resolved agent id differs from the agent id the less specific layers resolve to, the less specific layers' `env` is DISCARDED and only the more specific layer's `env` applies. A model or effort key that selects the replaced agent's model therefore never reaches the agent that replaced it. Scenario 233 in `scenarios.md` exercises this sentence.

In SPECIFICATION/scenarios.md, add at the end of the file (tests/heading-coverage.json MUST gain an entry in the same revise):

## Scenario 233 — A node routed to a different agent does not inherit the replaced agent's env

```gherkin
Feature: A cross-agent override renders one model
  As an operator reading which model a factory node ran
  I want a node routed to a different agent to carry only that agent's env
  So that the rendered adapter names exactly one model

  Scenario: A cross-agent override discards the inherited env
    Given a node whose built-in default is claude-acp with ANTHROPIC_MODEL in its env
    And dispatcher.acp_nodes routes that node to codex-acp with its own env
    When the Dispatcher resolves the node's adapter
    Then the rendered adapter carries no ANTHROPIC_MODEL and names only the Codex model

  Scenario: A same-agent override still merges env
    Given a node whose built-in default is claude-acp with ANTHROPIC_MODEL and CLAUDE_CODE_EFFORT_LEVEL in its env
    And dispatcher.acp_nodes sets only ANTHROPIC_MODEL for that node on claude-acp
    When the Dispatcher resolves the node's adapter
    Then the rendered adapter carries the override's ANTHROPIC_MODEL and the inherited CLAUDE_CODE_EFFORT_LEVEL
```
