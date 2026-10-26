---
topic: reflector-takes-dod-gate-chain
author: claude-opus-5-5
created_at: 2026-10-26T18:37:14Z
---

## Proposal: The out-of-band reflector takes its judgement from the resolved dod_gate chain

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Add the out-of-band reflector to the host judgements of 'Host judgements take the resolved dod_gate chain': it tries the resolved candidate chain in order with no direct claude -p, no environment variable such as LIVESPEC_REFLECTOR_MODEL selects its model and it has no hard-coded default, and when no candidate returns a verdict it records did-not-run and files no work item and proposes no lesson.

### Motivation

Coordinator gitops-fleet-capacity-monitoring ruling R44 (high priority, part of the Anthropic spend fix) routes this spec-first change so work-item bd-ib-c6va2d, filed by petri on R42 and held for this version, has a governing clause. The v220 paragraph "Host judgements take the resolved `dod_gate` chain" names the Definition-of-Done takings, the governing-heading and classification verdicts and the drift judge, but not the out-of-band reflector. Today the reflector (_reflector_runtime.py, _dispatcher_reflector_oob.py) spawns a headless `claude -p` on the model LIVESPEC_REFLECTOR_MODEL names, with a hard-coded default of claude-opus-4-8, bypassing the Codex-first chain. bd-ib-mfzvdl routes the other host judgements through the chain, so the reflector is the one Anthropic seam left standing.

The reflector has no ratified did-not-run route of its own, so this change states one: record that the judgement did not run and why, and file nothing (no work item, no lesson) from that pass. The reflector's Honeycomb MCP access is named on its own invocation, which the following paragraph ("A host judgement launches outside the interactive agent configuration") already permits.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance", paragraph "Host judgements take the resolved `dod_gate` chain", replace

```
every governing-heading verdict and work-item classification the Dispatcher takes from the spec-stated judgement on the host, and the drift run's spec-stated judgement MUST each take
```

with

```
every governing-heading verdict and work-item classification the Dispatcher takes from the spec-stated judgement on the host, the drift run's spec-stated judgement, and the out-of-band reflector's judgement of shipped work's telemetry MUST each take
```

2. In `SPECIFICATION/contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance", paragraph "Host judgements take the resolved `dod_gate` chain", replace

```
When no candidate returns a verdict, the judgement did not run, and the taking follows its ratified did-not-run route. A host judgement MUST NOT carry a hard-coded model default and MUST NOT take its model from any other source.
```

with

```
When no candidate returns a verdict, the judgement did not run, and the taking follows its ratified did-not-run route. For the out-of-band reflector that route is this: its pass MUST record that its judgement did not run and why, and MUST file no work item and propose no lesson from that pass. A host judgement MUST NOT carry a hard-coded model default and MUST NOT take its model from any other source. In particular, the out-of-band reflector MUST NOT launch an agent process of its own outside the candidate chain, such as a headless `claude -p`, and no environment variable, `LIVESPEC_REFLECTOR_MODEL` included, selects its model. The Honeycomb telemetry access the reflector needs is named on the reflector's own invocation, as the next paragraph permits. Measured 2026-10-26, the reflector was the one host judgement still launching `claude -p` directly, on the Anthropic model `LIVESPEC_REFLECTOR_MODEL` named.
```

3. In `SPECIFICATION/contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance", paragraph "Host judgements take the resolved `dod_gate` chain", replace

```
A repository preflight that runs its own chain of candidate judges is not governed by this paragraph; it keeps the independently graded chain the TAKING paragraph below defines. Scenario 239 in `scenarios.md` exercises this paragraph.
```

with

```
A repository preflight that runs its own chain of candidate judges is not governed by this paragraph; it keeps the independently graded chain the TAKING paragraph below defines. Scenario 239 in `scenarios.md` exercises this paragraph, and Scenario 251 exercises its sentences on the out-of-band reflector.
```

4. In `SPECIFICATION/scenarios.md`, append:

````
## Scenario 251 — The out-of-band reflector takes its judgement from the resolved dod_gate chain

```gherkin
Feature: The out-of-band reflector spends only what the repository's candidate chain names
  As the operator of a factory
  I want the reflector to judge with the same candidate chain as every other host judgement
  So that no host judgement keeps a private model path the repository configuration cannot route

  Scenario: The reflector tries the resolved chain in order
    Given a governed repository whose dod_gate chain resolves to a Codex candidate first and a Claude candidate second
    And LIVESPEC_REFLECTOR_MODEL is set in the host environment
    When the reflector judges a merged item's telemetry and the Codex candidate returns a verdict
    Then the verdict comes from the Codex candidate
    And the Claude candidate is not run
    And no claude -p process is launched outside the chain
    And LIVESPEC_REFLECTOR_MODEL selected nothing

  Scenario: A reflector pass whose candidates all fail files nothing
    Given a governed repository whose every dod_gate candidate times out or returns an unparseable reply
    When the reflector judges a merged item's telemetry
    Then the pass records that its judgement did not run and why
    And the pass files no work item and proposes no lesson
```
````

5. Add a TODO row for the new heading to `tests/heading-coverage.json` and a matching debt row to `tests/heading-coverage-debt.json`, both owned by the implementing work-item bd-ib-c6va2d.
