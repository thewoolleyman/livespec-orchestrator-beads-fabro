---
topic: impl-dispatch-launches-its-dispatcher
author: claude-opus-5-5
created_at: 2026-11-13T19:29:32Z
---

## Proposal: An impl dispatch launches its loop inside the host's dispatch memory slice when the host provides one

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a host-memory-slice clause to §"Dispatcher loop invocation surface". When the launching user's service manager provides the dispatch memory slice and a published per-loop memory bound, the `drive` `impl:` launch MUST run its Dispatcher `loop` in a transient scope inside that slice, bounded by that value and with out-of-memory policy `continue`. On any host without those pieces, it MUST launch exactly as before. The drive record names which launch was used. Two scenarios are added, one for each path.

### Motivation

On 2026-11-13 the dev VPS (94 GiB RAM, no swap) ran out of memory and was rebooted at 15:53Z. Per-run dispatcher loops were one of the uncapped Python consumers: 13 loops measured 0.23-1.69G steady and up to 2.53G peak (VmHWM). livespec-dev-tooling#4543 (role `dev_host_memory_bounds`, coordinator grade PASS) installs a user-manager `factory-dispatch.slice` sized from the fleet cap, and publishes a per-loop scope bound at `/etc/livespec/factory-dispatch-loop-memory-max`. A slice bounds only what is launched into it, and the `impl:` launch path is this repository's code. Work item bd-ib-szbxu7 carries the implementation; its dispatch was refused at the spec tier (unratified-topic) because the launch surface is governed here. Out-of-memory policy `continue` is required because systemd 257 defaults to `DefaultOOMPolicy=stop`, under which one OOM-killed child stops the whole scope and kills the loop. A killed loop leaves its factory run running but strands the merge wait, the ledger close and any long-run preserve request.

### Proposed Changes

In `contracts.md` §"Dispatcher loop invocation surface", append this bullet:

- **Host dispatch memory slice.** When `drive` launches the Dispatcher `loop` for an `impl:<work-item-id>` action, it MUST run that loop, together with every process the launch starts, inside a transient service-manager scope placed in the slice `factory-dispatch.slice`, provided ALL of the following hold for the launching user on the host: the user's service manager loads that slice; the manager delegates the memory controller; a scope launcher (`systemd-run`) is present; and the file `/etc/livespec/factory-dispatch-loop-memory-max` exists and holds a memory size. The scope's memory maximum MUST equal that file's value, and the scope's out-of-memory policy MUST be `continue`, so that the kernel killing one child does not stop the loop. When any of those conditions does not hold, the launch MUST proceed with the same argv and environment it uses without this clause, and MUST NOT fail because the slice is absent. Every `impl:` launch MUST record on its drive record which of the two launches it used and, for the scoped launch, the scope unit's name. The slice and the published bound are host provisioning that this repository does not install; this clause governs only how the launch uses them.

In `scenarios.md`, add:

## Scenario 371 — An impl dispatch on a host with the dispatch memory slice launches its loop inside it

Given the launching user's service manager loads `factory-dispatch.slice` and delegates the memory controller

And `/etc/livespec/factory-dispatch-loop-memory-max` holds `3500M`

When `drive` executes `impl:<work-item-id>` and launches the Dispatcher `loop`

Then the loop process's control group lies in a transient scope under `factory-dispatch.slice`

And that scope reports a memory maximum of `3500M` and an out-of-memory policy of `continue`

And the drive record names the scoped launch and the scope unit.

## Scenario 372 — An impl dispatch on a host without the dispatch memory slice launches its loop as before

Given a host whose launching user's service manager does not load `factory-dispatch.slice`, or that has no `/etc/livespec/factory-dispatch-loop-memory-max`

When `drive` executes `impl:<work-item-id>` and launches the Dispatcher `loop`

Then the loop starts with the same argv and environment as a launch made without the host-memory-slice clause

And the drive record names the unscoped launch.
