---
topic: the-pre-claim-refusal-of
author: claude-opus-5-5
created_at: 2026-11-12T18:15:00Z
---

## Proposal: Every per-dispatch override of a new-grammar-enabled node refuses before claim, and the refusal names the override's form

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Two sentences of §"Factory-configurable ACP fallback priority" pull in different directions. The per-dispatch layer's value "MAY be either form — a legacy adapter string … or a JSON object in the structured form — under the same refusal rules before claim". Yet the only refusal rule for a new-grammar-enabled node names the legacy string, and says "A future structured chain override requires separate ratification". So whether a SINGLE structured entry on such a node is refused is unstated. The Dispatcher refuses it, and its refusal text calls it a legacy adapter string. This proposal settles the question in favour of today's behaviour: until a structured chain override is ratified, every per-dispatch override of a new-grammar-enabled node refuses before claim. The refusal names which form the override took.

### Motivation

Work item bd-ib-gg3pyl (plan bd-ib-jxvgq5), routed to this seat for decision by legacy-coordinator-agent (session 959b2f8b, 2026-11-12), LOW band. It is held at spec-change tier for this linked stem: verdict partial, generalization target `## Factory-configurable ACP fallback priority`. The topic is the item's linked stem, so the hold links without a relink.

The decision (this seat, as routed): the item is not wording-only. The refusal of a single structured entry is not clearly conformant, because the per-dispatch sentence permits the structured form and no refusal rule names it. It is not clearly nonconformant either, because a per-dispatch value on a node whose metadata is a candidate chain overrides that chain, and the spec defers structured chain overrides to separate ratification. Since neither reading is stated, this needs a ratified sentence, not a release. The sentence chosen keeps today's measured behaviour, so no tenant's dispatches change. The kubernetes-sandbox-backend seat measured on 2026-11-09 that `_acp_chain_resolution._preconditions_refusal` refuses any per-dispatch override of a new-grammar-enabled node. The item's Definition of Done then fixes only the refusal TEXT, which this sentence now governs.

In-flight alignment: none of this seat's pending proposals touch ACP node routing. Fleet scope: the Dispatcher's per-dispatch layer, so every tenant inherits the change. A repository's plain structured `acp_nodes` entry (one carrying `agent`) makes its node new-grammar-enabled, because `_acp_node_chains._structured_chain` sets the chain's `enabled` for every structured entry, matching the spec's count of the structured form as new grammar. So every per-dispatch override of such a node refuses under this sentence, as it does today.

### Proposed Changes

**1. Settle the structured per-dispatch form (`contracts.md` §"Factory-configurable ACP fallback priority").** After the sentence "A future structured chain override requires separate ratification.", add:

> Until such an override is ratified, a per-dispatch `--acp-node` value of EITHER form for a new-grammar-enabled node MUST refuse before claim. This covers a legacy adapter string and a JSON object in the structured form, including a single structured entry. The refusal MUST name the form the value took. For a legacy adapter string, it states that the string carries no stable candidate or domain identity. For a structured value, it states that a structured per-dispatch chain override is not ratified. It MUST NOT call a structured value a legacy adapter string. The per-dispatch layer's acceptance of the structured form applies to nodes whose workflow-default and per-repository layers carry no new-grammar metadata; the per-dispatch value itself does not make a node new-grammar-enabled.

**2. Scenario (`scenarios.md`).** Append the scenario below, numbered at revise time.

## Scenario <number assigned at revise> — A per-dispatch override of a new-grammar-enabled node refuses before claim, naming the override's form

```gherkin
Feature: a per-dispatch node override refuses by its own form
  Scenario: a structured entry on a new-grammar-enabled node is refused as structured
    Given a node whose committed metadata enables the new grammar
    When a dispatch passes --acp-node naming that node with a structured JSON entry
    Then the dispatch refuses before claim
    And the refusal states that a structured per-dispatch chain override is not ratified
    And the refusal does not call the value a legacy adapter string

  Scenario: a legacy string on a new-grammar-enabled node is refused as legacy
    Given a node whose committed metadata enables the new grammar
    When a dispatch passes --acp-node naming that node with a legacy adapter string
    Then the dispatch refuses before claim, identifying the value as a legacy adapter string
```

**3. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading. The row is carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit, with `test: "TODO"`, `work_item: "bd-ib-gg3pyl"`, and a non-empty `reason` naming integration or above as the owed test's tier. It also adds one matching `tests/heading-coverage-debt.json` entry. The row and entry MUST carry the heading as numbered at revise.
