---
topic: factory-overflow-selection
author: claude-opus-5-5:petri-factory-on-gmktec
created_at: 2026-10-19T01:33:47Z
---

## Proposal: An unpinned dispatch goes to the least-utilized declared factory that has a free scheduler slot

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add an opt-in, committed `dispatcher.overflow_factories` list. For a dispatch that names no factory and carries no usable recorded factory, the Dispatcher considers `dispatcher.default_factory` and then the overflow list. Among the candidates whose own Fabro server reports a free scheduler slot, it places the dispatch on the one using the smallest fraction of its own `max_concurrent_runs`, with ties going to the earlier candidate. When no candidate reports a free slot, it places the dispatch on the default factory exactly as today. Selection chooses only WHERE a dispatch goes. It never refuses, defers, holds or counts one, so the Fabro scheduler stays the only concurrency authority. Amend the clauses that forbid it today, and add Scenario 203.

### Motivation

Maintainer direction, 2026-10-19 (verbatim): "Yes add GMK to the factory map. There's no reason that that shouldn't have been done already. The whole plan was to get it usable and start using it." The coordinator relayed the decided goal: ordinary dispatches from every orchestrator seat should land on the second factory (`petri`, the Petri-era instance on the factory host the maintainer named the Petri factory's home on 2026-10-18) whenever it has a free slot, and the Dispatcher should choose it when the default factory is at its cap or busier.

Today every unpinned dispatch goes to `dispatcher.default_factory` (`hp`), which is often saturated: measured 2026-10-19 00:41Z at 6 live runs and 0.9% idle under a fleet capacity hold. Meanwhile `petri`, converged to two concurrent runs in an 18G slice, sat idle. A caller may already pick a factory per dispatch through `--factory` or `LIVESPEC_FABRO_FACTORY`, but that leaves every seat to re-implement the same choice.

The rule compares utilization rather than taking the first free slot because the two servers' own ceilings differ widely. Measured 2026-10-19 03:01Z through `fabro settings --server`: hp reports `max_concurrent_runs: 10` and `petri` reports 2. A first-free-slot rule would therefore send almost nothing to `petri`, because hp has a free slot until it runs ten. Comparing each server's own fraction in use sends work to `petri` whenever hp is busier, which is the stated goal.

The ratified text forbids the Dispatcher from making this choice. §"Host concurrency belongs to the Fabro scheduler" says the Orchestrator MUST NOT derive available capacity from `server.scheduler.max_concurrent_runs` on any surface. §"Factory addresses resolved from a host registry" says the registry does not change the factory selection order. The point of the prohibition is that the Orchestrator never REFUSES or GATES on host capacity, since queueing at the scheduler is the sanctioned behaviour. Choosing which scheduler queues a run is a different act. It can read each server's own account of itself without enforcing, duplicating or reporting any ceiling as the Orchestrator's own.

### Proposed Changes

1. contracts.md, §"Host concurrency belongs to the Fabro scheduler": after the paragraph beginning "The Orchestrator MUST NOT report the Fabro scheduler's `server.scheduler.max_concurrent_runs` as its own bound", add this paragraph: "The ONE exception is factory overflow selection (§\"Factory overflow selection\"). It MAY read a candidate factory server's own `max_concurrent_runs` and that server's own non-terminal run count, solely to choose which declared factory receives an unpinned dispatch. That read MUST NOT refuse, defer, hold or count a dispatch. It MUST NOT be reported as an Orchestrator bound, and it MUST NOT feed any admission, gating or capacity-reporting surface. The tenant-scope clause below does not govern it. Every other prohibition in this section stays binding."

2. contracts.md, §"Factory addresses resolved from a host registry": replace the selection-order sentence and the recorded-factory sentence. The selection order becomes: an explicit `--factory` first, then `LIVESPEC_FABRO_FACTORY` when it is set and non-empty, then the item's recorded factory, then factory overflow selection (§"Factory overflow selection") when `dispatcher.overflow_factories` is non-empty, and otherwise `dispatcher.default_factory`. A recorded factory name that `dispatcher.factories` no longer declares is ignored when no explicit selection is made, and the dispatch proceeds as an unpinned one.

3. contracts.md: add a new section, §"Factory overflow selection", immediately after §"Factory addresses resolved from a host registry". It states:

   - `dispatcher.overflow_factories` is an OPTIONAL committed array of factory names. Each entry MUST name an entry of `dispatcher.factories`, MUST NOT repeat, and MUST NOT name `dispatcher.default_factory`. An entry that violates this MUST be refused before any item is claimed, with a configuration finding naming the offending value. The key is committed-only and is NOT declared API-configurable. When it is absent or empty, selection is exactly the order of §"Factory addresses resolved from a host registry", and nothing in the new section applies.
   - Overflow selection applies ONLY to a dispatch, including a resume, that has no explicit `--factory`, no non-empty `LIVESPEC_FABRO_FACTORY`, and no recorded factory that `dispatcher.factories` still declares.
   - For such a dispatch the candidates are `dispatcher.default_factory` followed by each entry of `dispatcher.overflow_factories`, in that order. For each candidate the Dispatcher MUST read, from that candidate's own Fabro server at selection time, its non-terminal run count and its own `max_concurrent_runs`. A candidate has a FREE slot when its count is below its `max_concurrent_runs`. A candidate whose read fails, times out, is unparseable, or reports a `max_concurrent_runs` below 1 MUST count as having no free slot.
   - The Dispatcher MUST place the dispatch on the candidate with a free slot whose count divided by its `max_concurrent_runs` is smallest; ties go to the earlier candidate. When no candidate has a free slot, the dispatch MUST be placed on `dispatcher.default_factory`.
   - Selection MUST NOT refuse, defer, hold, delay or count a dispatch. Every dispatch proceeds to submission on the chosen factory, where that factory's scheduler queues it as §"Host concurrency belongs to the Fabro scheduler" sanctions.
   - The chosen factory MUST be recorded as the item's dispatch-factory record exactly as an explicit choice is, so that a later resume, reconcile or acceptance pass of the same dispatch follows it.
   - A registry-backed candidate MUST be resolved through the host registry before its server is read. A candidate the registry cannot resolve counts as having no free slot for selection. This does not relax the registry refusal for a dispatch that names that factory explicitly.
   - The Dispatcher MUST journal each overflow selection as one record. The record carries every candidate considered, in order, with the non-terminal run count and `max_concurrent_runs` its server reported or the reason its read failed. It also carries the chosen factory and the reason for the choice, which is `least-utilized-free-slot` or `no-candidate-free-default`. A dispatch to which overflow selection did not apply journals no such record.

4. scenarios.md: add Scenario 203, "An unpinned dispatch goes to the least-utilized declared factory that has a free scheduler slot", with four cases: the less-utilized overflow factory is chosen; the less-utilized default factory is kept; no candidate has a free slot and the dispatch falls back to the default without being refused or deferred; and a pinned dispatch reads no capacity and journals no selection.
