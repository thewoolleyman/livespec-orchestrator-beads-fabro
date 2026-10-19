---
topic: factory-overflow-selection
author: claude-opus-5-5:petri-factory-on-gmktec
created_at: 2026-10-19T01:33:47Z
---

## Proposal: An unpinned dispatch overflows to the first declared factory whose own scheduler has a free slot

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add an opt-in, committed `dispatcher.overflow_factories` list. For a dispatch that names no factory and carries no usable recorded factory, the Dispatcher walks `dispatcher.default_factory` and then the overflow list in order. It places the dispatch on the first factory whose own Fabro server reports a free scheduler slot, and otherwise on the default factory exactly as today. Selection chooses only WHERE a dispatch goes. It never refuses, defers, holds or counts one, so the Fabro scheduler stays the only concurrency authority. Amend the two clauses that forbid it today, and add Scenario 201.

### Motivation

Maintainer direction, 2026-10-19 (verbatim): "Yes add GMK to the factory map. There's no reason that that shouldn't have been done already. The whole plan was to get it usable and start using it." The coordinator relayed the decided goal: ordinary dispatches from every orchestrator seat should land on the second factory (`petri`, the Petri-era instance on the factory host the maintainer named the Petri factory's home on 2026-10-18) whenever it has a free slot, and the dispatcher should choose it when the default factory is at its cap or busier. Today every unpinned dispatch goes to `dispatcher.default_factory` (`hp`), which is often saturated: measured 2026-10-19 00:41Z at 6 live runs and 0.9% idle under a fleet capacity hold. Meanwhile `petri`, converged to two concurrent runs in an 18G slice, sat idle. A caller may already pick a factory per dispatch through `--factory` or `LIVESPEC_FABRO_FACTORY`, but that leaves every seat to re-implement the same choice. The ratified text forbids the Dispatcher from making it: §"Host concurrency belongs to the Fabro scheduler" says the Orchestrator MUST NOT derive available capacity from `server.scheduler.max_concurrent_runs` on any surface, and §"Factory addresses resolved from a host registry" says it does not change the factory selection order. The point of that prohibition is that the Orchestrator never REFUSES or GATES on host capacity, since queueing at the scheduler is the sanctioned behaviour. Choosing which scheduler queues a run is a different act. It can read each server's own account of itself without enforcing, duplicating or reporting any ceiling as the Orchestrator's own.

### Proposed Changes

1. contracts.md, §"Host concurrency belongs to the Fabro scheduler": in the paragraph beginning "The Orchestrator MUST NOT report the Fabro scheduler's `server.scheduler.max_concurrent_runs` as its own bound", append: "The ONE exception is factory overflow selection (§\"Factory overflow selection\"). It MAY read a candidate factory's own `max_concurrent_runs` and its own non-terminal run count, solely to choose which declared factory receives an unpinned dispatch. That read MUST NOT refuse, defer, hold or count a dispatch, MUST NOT be reported as an Orchestrator bound, and MUST NOT feed any admission, gating or capacity-reporting surface. Every other prohibition in this section stays binding."

2. contracts.md, §"Factory addresses resolved from a host registry": replace "It does not change the factory selection order: an explicit `--factory` is taken first, then `LIVESPEC_FABRO_FACTORY` when it is set and non-empty; then the item's recorded factory; then `dispatcher.default_factory`." with "It does not change the factory selection order: an explicit `--factory` is taken first, then `LIVESPEC_FABRO_FACTORY` when it is set and non-empty; then the item's recorded factory; then factory overflow selection (§\"Factory overflow selection\") when `dispatcher.overflow_factories` is declared, and otherwise `dispatcher.default_factory`."

3. contracts.md: add a new section immediately after §"Factory addresses resolved from a host registry":

### Factory overflow selection

`dispatcher.overflow_factories` is an OPTIONAL committed array of factory names. Each entry MUST name an entry of `dispatcher.factories`, MUST NOT repeat, and MUST NOT name `dispatcher.default_factory`. An entry that violates this MUST be refused before any item is claimed, with a configuration finding naming the offending value. The key is committed-only: it is NOT declared API-configurable. When it is absent or empty, selection is exactly the order of §"Factory addresses resolved from a host registry" and nothing in this section applies.

Overflow selection applies ONLY to a dispatch, including a resume, that has no explicit `--factory`, no non-empty `LIVESPEC_FABRO_FACTORY`, and no recorded factory that `dispatcher.factories` still declares. For such a dispatch the Dispatcher MUST consider, in order, `dispatcher.default_factory` and then each entry of `dispatcher.overflow_factories`. It MUST place the dispatch on the FIRST candidate whose own Fabro server reports a FREE scheduler slot, meaning a non-terminal run count below that same server's own reported `max_concurrent_runs`. Both values MUST be read from that candidate's server at selection time. When no candidate reports a free slot, or a candidate's read fails, times out or is unparseable, that candidate MUST count as having no free slot, and when no candidate qualifies the dispatch MUST be placed on `dispatcher.default_factory`. Selection MUST NOT refuse, defer, hold, delay or count a dispatch: every dispatch proceeds to submission on the chosen factory, where that factory's scheduler queues it as §"Host concurrency belongs to the Fabro scheduler" sanctions.

The chosen factory MUST be recorded as the item's dispatch-factory record exactly as an explicit choice is, so that a later resume, reconcile or acceptance pass of the same dispatch follows it. A registry-backed candidate MUST be resolved through the host registry before its server is read. A candidate the registry cannot resolve counts as having no free slot for selection; this does not relax the registry refusal for a dispatch that names that factory explicitly.

The Dispatcher MUST journal each overflow selection as one record carrying every candidate considered, in order, with the non-terminal run count and `max_concurrent_runs` its server reported or the reason its read failed, plus the chosen factory and the reason for the choice (`free-slot` or `no-candidate-free-default`). A dispatch to which overflow selection did not apply journals no such record.

4. scenarios.md: add

## Scenario 201 — An unpinned dispatch overflows to the first declared factory whose own scheduler has a free slot

Given `dispatcher.default_factory` names factory A and `dispatcher.overflow_factories` is ["B"]
And factory A's server reports 6 non-terminal runs and a `max_concurrent_runs` of 6
And factory B's server reports 1 non-terminal run and a `max_concurrent_runs` of 2
And the item carries no recorded factory and no explicit factory is selected
When the Dispatcher dispatches the item
Then the run is submitted to factory B
And the item's dispatch-factory record names factory B
And one overflow-selection journal record lists A with 6 of 6, B with 1 of 2, chosen B, reason free-slot

Given the same configuration but factory B's server also reports no free slot, or its read fails
When the Dispatcher dispatches the item
Then the run is submitted to factory A and queues in A's scheduler
And the journal record names chosen A, reason no-candidate-free-default
And the dispatch is neither refused nor deferred

Given the item's recorded factory is A, or `LIVESPEC_FABRO_FACTORY` names A
When the Dispatcher dispatches the item
Then the run is submitted to factory A without reading either server's capacity
And no overflow-selection journal record is written
