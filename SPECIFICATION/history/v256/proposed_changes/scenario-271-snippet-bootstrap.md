---
topic: scenario-271-snippet-bootstrap
author: claude-opus-5-5:anthropic-burn-mitigation
created_at: 2026-10-30T23:35:04Z
---

## Proposal: Scenario 271 states that operation-prose snippets bootstrap through the registered-root command

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Add a fourth case to Scenario 271 stating the clause's second requirement: an operation-prose step that imports this plugin's package from a snippet bootstraps through the root the registered-root command prints, never a literal cache-build path.

### Motivation

Spec v254 ratified topic snippets-and-helper-scripts-bind. Its clause under ## Self-contained plugin dispatch ('A session resolves its project's registered build rather than a remembered one') states three requirements, but Scenario 271 carries cases for only two of them: the registered-root command and the session-start warning. The snippet-bootstrap requirement has no scenario, contrary to the authoring rule that load-bearing behaviour is stated as a clause AND a scenario. This had a measured cost. On 2026-10-30T23:32:19Z the dispatch-stage spec-stated judgement held bd-ib-uyg266 at the spec-change tier (verdict partial, hold reason awaiting-rejudgement, spec version 255) with the rationale: 'Scenario 271 states the first and third bullets ... The text shown does not state the second bullet, that operation prose steps bootstrap their package import through that command. The body of Self-contained plugin dispatch is omitted from this prompt, so I can't confirm it states that.' The section is about 115,000 characters, so its body does not reach the judge, and every re-judgement returns the same partial verdict. Stating the requirement in the scenario completes the scenario and lets the judgement read it.

### Proposed Changes

In SPECIFICATION/scenarios.md, in ## Scenario 271 — A session finds its project's registered plugin build and is told when it is stale, append one case to its gherkin block, after the case 'Session start warns about a registered install older than the latest release':

  Scenario: An operation-prose snippet imports the package through the registered root
    Given an operation-prose step that has an agent import this plugin's package from a snippet
    When the agent follows that step for a governed project
    Then the snippet puts on its import path the plugin root the registered-root command prints for that project
    And the step names no literal plugin cache-build path

The scenario heading is unchanged, so tests/heading-coverage.json needs no new entry; its existing Scenario 271 entry stays as it is.
