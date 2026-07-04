---
topic: retire-root-research-directory
author: claude-fable-5
created_at: 2026-07-04T00:46:49Z
---

## Proposal: Retire the root research/ tree from the Planning Lane realization

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Remove the sentence in the Planning Lane realization's thread-store subsection stating that "The broader `research/` tree stays for standalone analysis that is not an active planning thread." Successor wording: there is NO root `research/` directory — standalone analysis lives in a plan thread (or, once the thread closes, under `plan/archive/`), and a living reference document lives in `docs/`, `.ai/`, or a dedicated top-level topic directory (precedent: `loop-reflection-gate/`).

### Motivation

The retire-research-dirs epic (livespec-gt7crt; residual map at the livespec repo's plan/retire-research-dirs/research/01-residual-map.md) retires the root `research/` directory fleet-wide per the maintainer's 2026-07-04 direction. In this repo, the runtime-written `research/loop-reflection-gate/` content already moved to top-level `loop-reflection-gate/` (PR #282), leaving only the placeholder `research/CLAUDE.md`. The contract sentence endorsing a standing root `research/` tree is the last spec-side anchor keeping the directory alive; it must be replaced so the directory can be removed without contradicting the specification.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Planning Lane realization" → "### The `plan/<topic>/` thread store", replace the sentence:

> The broader `research/` tree stays for
> standalone analysis that is not an active planning thread.

with:

> There is NO root `research/`
> tree: standalone analysis lives in a plan thread (or, once the
> thread closes, under `plan/archive/`), and a living reference
> document lives in `docs/`, `.ai/`, or a dedicated top-level topic
> directory (precedent: `loop-reflection-gate/`).

No heading is added, removed, or renamed; the H2 set is unchanged, so no `tests/heading-coverage.json` co-edit is required.
