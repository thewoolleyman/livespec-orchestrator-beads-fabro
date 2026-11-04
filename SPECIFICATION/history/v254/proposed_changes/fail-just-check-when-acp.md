---
topic: fail-just-check-when-acp
author: claude-opus-5-5:factory-configurable-model-fallback-priority
created_at: 2026-10-29T13:48:46Z
---

## Proposal: A commit-time check refuses an unresolvable ACP candidate chain in the committed configuration

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a commit-time configuration check to §"ACP node adapter configuration". The repository's `just check` aggregate runs a `check-acp-preflight-config` target. That target evaluates the committed `.livespec.jsonc` through the same resolution the Dispatcher applies before claim, and it fails, printing the refusal text, when that resolution returns a configuration refusal. Availability waits and live holds never fail it. It makes no external call, so its verdict is deterministic and needs no network. A new scenario states the behaviour, and work-item bd-ib-aqrdhl implements it.

### Motivation

On 2026-10-25 the Codex-first routing rollout copied this repository's `dispatcher.acp_nodes` block into 13 fleet repositories. The block names `claude-sonnet-5-5` as the Claude fallback for four nodes, but that model was declared only in this repository's `dispatcher.model_catalog`. Every one of the 13 then refused every dispatch before claim with `dispatcher.acp_nodes.<node>.fallbacks[0].model names 'claude-sonnet-5-5', which the model catalog does not declare for provider 'anthropic'`, from 18:29:54Z until per-repository catalog fixes landed between 18:54Z and 19:23Z. Every pre-commit hook, pre-push hook and PR CI run on all 13 changes passed, because none of them evaluates candidate-chain resolution. Scenario 129's refusal ('Mixed, unknown or unresolvable entries refuse before claim') surfaces only when a real dispatch is admitted. The same evaluation, `resolve_acp_preflight` with no journal, no probe, no headroom policy and no factory reader, read REFUSED on all 13 before the fix and VIABLE on all 14 checkouts after it, so it is a sound commit-time instrument. Work-item bd-ib-aqrdhl was filed to deliver the check. On 2026-10-29 at 13:41Z the dispatch spec-change-tier gate held it as unratified, generalization target §"ACP node adapter configuration", because no ratified clause states a commit-time check. This proposal supplies that clause.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"ACP node adapter configuration", insert the following paragraph immediately before the paragraph that begins `**Verification.**`:

> **Commit-time resolution check.** The repository's `just check` aggregate MUST run a target named `check-acp-preflight-config`. That target MUST evaluate the repository's committed `.livespec.jsonc` through the same ACP node resolution the Dispatcher applies before claim: the three resolution layers, the structured and manual candidate forms, and §"Agent and model catalogs". It MUST NOT use a second, independently written validator. The target MUST exit non-zero and print the refusal text, including the offending node and field, whenever that resolution returns a configuration refusal. Configuration refusals are the refusals this section and §"Agent and model catalogs" define for an entry that mixes forms, names an agent absent from the agent catalog, names a model the model catalog does not declare for that agent, or otherwise cannot be rendered. The target MUST NOT fail on an availability condition: an unexpired availability hold, an outstanding availability confirmation or a session-headroom wait is not a configuration defect. To keep its verdict deterministic, the target MUST read no dispatch journal, MUST NOT probe a credential, MUST NOT apply a session-headroom policy and MUST NOT query a factory. It MUST therefore reach the same verdict on a host with no network access. Because the target is part of `just check`, it runs wherever `just check` runs, locally, in pre-push and in CI, so a committed configuration whose candidate chain cannot resolve is refused before it can reach a dispatch.

In `SPECIFICATION/scenarios.md`, append one new scenario after the current last scenario. Its number MUST be the next unused scenario number at the time of the revise that accepts this proposal, and its heading text after the number MUST be `— A committed configuration whose candidate chain cannot resolve fails just check`:

```gherkin
Feature: A candidate chain that cannot resolve is refused at commit time, not at the first dispatch
  As a factory operator
  I want just check to evaluate the committed ACP node configuration the way the Dispatcher will
  So that a configuration every dispatch would refuse never passes the commit gates

  Scenario: An undeclared fallback model fails the check
    Given a committed .livespec.jsonc whose acp_nodes names claude-sonnet-5-5 as a node's first fallback model
    And its model_catalog declares no anthropic/claude-sonnet-5-5 entry
    When check-acp-preflight-config runs
    Then it exits non-zero
    And its output names that node's fallbacks[0].model field and claude-sonnet-5-5

  Scenario: A resolvable configuration passes with no network
    Given a committed .livespec.jsonc whose every node's candidate chain resolves through the catalogs
    And the host has no network access and no provider credential
    When check-acp-preflight-config runs
    Then it exits zero

  Scenario: An availability hold is not a configuration failure
    Given a resolvable committed configuration
    And a dispatch journal recording an unexpired availability hold on a node's primary candidate
    When check-acp-preflight-config runs
    Then it exits zero, because it reads no journal and judges configuration only
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading. It MAY carry `test: "TODO"` with a reason naming work-item bd-ib-aqrdhl as the implementing item.
