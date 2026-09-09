---
topic: pr-node-default-claude-haiku
author: claude-opus-4-8
created_at: 2026-09-09T08:56:46Z
---

## Proposal: The publish default is the Claude adapter

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Change the built-in fleet default for the `pr` (publish) ACP node class from the Codex publish pin to a model-agnostic Claude adapter pinned to Claude Haiku 4.5, exactly mirroring the existing implementer-class Claude default. The `pr` Codex tier MUST expand ONLY when the dispatch target explicitly configures `dispatcher.codex_models.pr` (a table), so an unconfigured repository runs the workflow's own `pr_adapter` input default — a single source — rather than a baked Codex slug. A repository still routes `pr` to Codex by writing the table, or to any other model via `dispatcher.acp_nodes.pr`.

### Motivation

The baked Codex `pr` default (`gpt-5.4-mini`) fell out of the ChatGPT-account Codex catalog, so every repository that had not explicitly pinned `pr` failed at the publish stage with HTTP 400 'model is not supported when using Codex with a ChatGPT account'. The reachable set is a runtime property of the account catalog, which OpenAI moved, so a Codex slug is the wrong thing to bake as a fleet default. The value was also duplicated across the plugin constant, the cost table, this contract, and six test files. Defaulting `pr` to a model-agnostic Claude adapter (the factory already runs Claude for implement/review) removes the OpenAI-catalog exposure from the default path and collapses the duplication to one source, while leaving Codex and any other model available as an explicit per-repository choice.

### Proposed Changes

In §"Codex ACP node model pins":

1. In the paragraph beginning 'Tiers resolve from the dispatch target's own configuration', change the built-in fleet default clause from '... the Claude default for the implementer class, the Codex publish pin for the `pr` class' to '... the Claude default for the implementer class, and the Claude publish default (Claude Haiku 4.5) for the `pr` class'. In the same paragraph, change 'an absent block, an absent `pr` entry, or a non-table `pr` entry resolves to the Codex publish defaults' to 'an absent block, an absent `pr` entry, or a non-table `pr` entry resolves to the Claude publish default (the workflow's `pr_adapter` input); a `pr` entry that IS a table routes the publish class to the Codex adapter under the existing rules of this section, with an absent `model` or `reasoning_effort` key falling back to that tier's built-in Codex default for exactly what is missing.'

2. Add a new paragraph, immediately after 'The implementer default is the Claude adapter', titled '**The publish default is the Claude adapter.**' It states: when the dispatch target's `dispatcher.codex_models` block carries NO `pr` entry (the block is absent, the `pr` key is absent, or the entry is not a table) AND `dispatcher.acp_nodes.pr` is not set, the Dispatcher MUST render the `pr_adapter` input as the model-un-pinned publish default it inherits from the workflow, which is the Claude ACP adapter pinned to Claude Haiku 4.5. The rendered form, literally, is `ANTHROPIC_MODEL=claude-haiku-4-5 CLAUDE_CODE_EFFORT_LEVEL=high npx -y @agentclientprotocol/claude-agent-acp`. As with the implementer default, the model and effort MUST ride the adapter's own environment as leading `KEY=value` assignments because Fabro rejects `model`/`reasoning_effort` as ACP node attributes; and the Dispatcher SHOULD treat the first dispatch after a change to this default as a verification run whose resolved model is checked against the pinned model. A `dispatcher.codex_models.pr` entry that IS a table MUST route the publish class to the Codex adapter under the existing rules of this section, so a repository stays on (or moves to) Codex by writing the entry and takes the Claude default by removing it — exactly symmetric with the implementer class.

3. In the paragraph defining the publish class ('The **publish** class, rendered into the `pr_adapter` input ...'), adjust the trailing clause so it reads that the publish node executes a fixed `git`/`gh` recipe with no design judgement and therefore takes a cheap model — the Claude Haiku default, or a cheaper explicit override — rather than implying a Codex default.

4. Preserve every 'every Codex ACP node is pinned' guarantee: it continues to bind whenever `pr` IS configured as Codex. The un-pinned-base-string, opt-out, no-environment-override, and rendered-form material for the Codex publish adapter is unchanged and applies to the explicit-Codex `pr` case.

5. Update the built-in-fleet-defaults table and its two rendered-form examples so the publish row is the Claude Haiku adapter and the Codex publish string is presented as the FORMER default / an explicit-Codex-pin example rather than the current default.

6. In `SPECIFICATION/scenarios.md`, co-update the ratified scenarios that assert the old "pr defaults to Codex absent configuration" behavior so the two spec files do not contradict: Scenario 64's "A repository with no configuration inherits the fleet default adapters" (the publish adapter becomes the Claude fleet-default adapter, not a Codex one); Scenario 86's "The publish class is unaffected by the implementer default" (the rendered adapter becomes the Claude publish default pinned to Claude Haiku 4.5); and Scenario 90's "A default dispatch renders both adapters in their ratified forms" plus "The publish adapter declares its agent mode" (reworded so the publish node is pinned to Codex by an EXPLICIT `dispatcher.codex_models.pr` table, since a default dispatch no longer resolves the publish node to Codex — this preserves the Codex-adapter rendering coverage under the explicit-Codex path).

No `## ` heading is added or removed in either file; the contracts.md edits are within the existing §"Codex ACP node model pins" section, and the scenarios.md edits change only gherkin step and inner-scenario lines, not `## Scenario NN` headings, so `tests/heading-coverage.json` is unaffected.
