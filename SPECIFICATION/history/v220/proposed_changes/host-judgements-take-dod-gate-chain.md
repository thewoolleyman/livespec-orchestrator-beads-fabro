---
topic: host-judgements-take-dod-gate-chain
author: claude-opus-5-5
created_at: 2026-10-25T20:06:10Z
---

## Proposal: Host-side model judgements fall back along the resolved dod_gate chain

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The host takings of the Definition-of-Done judgement (pre-admission and pre-dispatch), the host's governing-heading and classification verdicts, and the drift run's spec-stated judgement take their model from the resolved `dod_gate` candidate chain and try its candidates in order as fallbacks. A host judgement carries no hard-coded model. The repository preflight's independently graded chain is unchanged.

### Motivation

Plan split-drift-check-from-cleanup-timer (epic bd-ib-oi2nyu), DoD assertion 5, under the maintainer's 2026-10-25 ruling that the drift check must not waste tokens. The Dispatcher supplies the spec-stated judgement's model runner, but no ratified clause says which model, so the implementation hard-codes `claude-opus-4-8` in `_drift_run_judge.py` and `_dispatcher_dod_judgement_run.py`. Every dispatch and every intake auto-admission therefore pays one Opus full-tree call on the protected Anthropic account, while the repository's own committed routing for the `dod_gate` node is Codex-first. Implementing child bd-ib-mfzvdl was refused at launch because no ratified clause governs this behaviour.

### Proposed Changes

In SPECIFICATION/contracts.md, under `## Dispatcher admission, WIP cap, and post-merge acceptance`, insert this paragraph immediately after the paragraph that begins "**The spec-stated judgement is one shared component.**", separated by blank lines:

"**Host judgements take the resolved `dod_gate` chain.** The pre-admission and pre-dispatch takings of the Definition-of-Done judgement, every governing-heading verdict and work-item classification the Dispatcher takes from the spec-stated judgement on the host, and the drift run's spec-stated judgement MUST each take their model judgement from the `dod_gate` node's candidate chain as a dispatch of the governed repository resolves it under §"ACP node adapter configuration" (repository layer over workflow layer, with no per-dispatch override). They try the candidates in chain order as FALLBACKS: the first candidate that returns a verdict decides the judgement, and the remaining candidates are not run. A candidate the host cannot launch, because its resolved adapter carries no agent identity the host can run or its agent is not available, or one that returns no verdict (a timeout or an unparseable reply), passes the judgement to the next candidate. When no candidate returns a verdict, the judgement did not run, and the taking follows its ratified did-not-run route. A host judgement MUST NOT carry a hard-coded model default and MUST NOT take its model from any other source. A repository preflight that runs its own chain of candidate judges is not governed by this paragraph; it keeps the independently graded chain the TAKING paragraph below defines. Scenario 239 in `scenarios.md` exercises this paragraph."

In SPECIFICATION/scenarios.md, under `## Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric`, append to the gherkin block:

```gherkin
  Scenario: A host judgement falls back along the resolved dod_gate chain
    Given a governed repository whose resolved dod_gate chain is a codex-acp primary followed by a claude-acp fallback
    When the pre-dispatch Definition-of-Done judgement is taken and the primary returns a verdict
    Then the verdict comes from the codex-acp primary and the claude-acp fallback is not run
    When the primary instead times out
    Then the claude-acp fallback is run and its verdict decides the judgement
    When every candidate fails to return a verdict
    Then the pre-dispatch taking follows its did-not-run route
```

No `## ` heading is added, changed or removed.
