---
topic: clock-fired-work-supply
author: claude-opus-5-5-plan-bd-ib-opbzv3
created_at: 2026-10-19T01:52:07Z
---

## Proposal: A clock-fired work supply starts an unattended drain pass per tenant on an interval, so factory work supply does not depend on an interactive session

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds a clock-fired work-supply bullet to §"Dispatcher loop invocation surface". The repository ships a host-installable work-supply service and timer. Each firing starts one unattended drain pass, `loop` with no `--item`, for one named tenant repository at an operator-chosen interval, so ready work reaches the factory without any interactive session starting a drain. The pass is an ordinary unattended drain: the ranked queue, `wip_cap`, every admission condition and the fail-closed unattended cost gate govern it unchanged. The service resolves the plugin build it executes from the tenant's registered plugin install at each firing, and a pass still running never prevents the next firing from starting.

### Motivation

Measured 2026-10-13 and recorded in plan gitops-fleet-capacity-monitoring (livespec-dev-tooling, epic livespec-dev-tooling-dfixhe). hp's fleet Fabro server received no new ImplementWorkItem run between about 18:27Z and 22:56Z. For about 4.5 hours there were zero runs in flight, the Claude credential probe reported usable, and dispatch-ready work existed. No dispatcher or drain process was running, and dispatch resumed only when some session started an engine again. The same shape recurred on 2026-10-16, when nine hp slots sat idle for about five hours. Plan factory-idle-with-ready-work (epic bd-ib-opbzv3) owns the fix, and its implementing work-item is bd-ib-hlfw5p. The plan's charter (plan/factory-idle-with-ready-work/research/001-charter-and-ownership-decision.md) decided on 2026-10-14 that the work supply belongs in this repository. The drain is this repository's surface, the root reconcile-runs.timer is the in-repository precedent for a clock-fired Dispatcher subcommand, and the overseer has no dispatch mandate. No ratified clause states this behaviour today: §"Dispatcher loop invocation surface" says the unattended drain is the factory's steady-state path and that the console's factory-drain launcher invokes it, but nothing obliges anything to invoke it when no human or session does. Two design points are carried from the item. First, the reconcile-runs installer substitutes the plugin path at install time, which pins every later firing to the build that existed then. That is the stale-build trap AGENTS.md records, so this clause resolves the build at each firing instead. Second, `loop` blocks until its wave's post-verdict stages finish, which can take hours, so a timer that waits for the previous pass would leave freed capacity idle for the whole of a long pass. The plan charter's first sketch said the timer must not overlap with itself; the item's design notes reversed that after measuring that `loop` blocks for hours, and this clause follows the item. Overlapping passes raise exposure to the known concurrency defects bd-ib-2vda and bd-ib-m1av, which the clause neither fixes nor forecloses; the installer's interval minimum keeps passes far apart relative to bd-ib-m1av's measured stamp window.

### Proposed Changes

1. In SPECIFICATION/contracts.md, section "Dispatcher loop invocation surface", immediately after the bullet that ends "unattended drain is the factory's steady-state path; it is what the
console's factory-drain launcher invokes.", insert the following new bullet:

- **Clock-fired work supply.** The repository MUST ship a host-installable work-supply service and timer whose every firing starts ONE unattended drain pass for one named tenant repository: `loop --repo <tenant> --budget <count>` with NO `--item`. A firing is not a host-session launch: it reports no protected launch and arms no session wait. The pass's own Dispatcher engine owns every dispatch it admits through terminal disposition, and a pass that dies leaves its claims to §"Stranded claim release". Each pass is one bounded process; the work supply is not a daemon (constraints.md §"Process boundaries"). Each pass is therefore an ordinary unattended drain, governed by the ranked queue, `wip_cap`, every admission condition and the fail-closed unattended cost gate below exactly as any other unattended drain, and the work supply MUST NOT add, relax or bypass any of them. The installer MUST install one timer instance per named tenant repository, MUST take each instance's firing interval from the operator, and MUST refuse an instance whose credential environment wrapper is not an executable file on the host, naming the instance and the wrapper path. At each firing the service MUST resolve the plugin build it executes from the plugin install registered for that tenant repository by its governing runtime at that moment, so the next firing after a release executes the released build without reinstalling anything. When no registered install exists for the tenant, the firing MUST refuse, naming the tenant, and MUST NOT fall back to a build pinned at install time or to a guessed path. A pass whose dispatched runs are still in progress MUST NOT prevent the next firing from starting a new pass, so capacity that frees during a long pass is offered to ready work within one interval; each new pass is governed by `wip_cap` as any unattended drain is. Concurrent passes are concurrent Dispatcher engines against one tenant: this clause adds no exclusion between them, licenses no host-scoped admission lock, and does not bar a ledger-level exclusive admission under §"Per-repo WIP cap". The installer MUST state the default interval and MUST refuse an interval shorter than a documented minimum, naming the instance, the interval given and the minimum. With the work supply installed for a tenant and no interactive session running a drain, the pass started by the first firing after an item becomes admission-eligible MUST consider that item: it MUST either admit it or journal it with the exclusion reason the admission conditions every unattended drain honours (including `wip_cap` and the pass's `--budget`) assign it. A tenant whose first-ranked admission-eligible item has a free counted-claim slot and budget MUST see it dispatched by that pass.

2. In SPECIFICATION/scenarios.md, append a new heading after the highest-numbered scenario on master at filing time (Scenario 200), numbered 201 unless that number is reserved by then, in which case it takes the next free number:

## Scenario 201 — A clock-fired work supply drains a tenant on its interval without an interactive session, resolves the plugin build at each firing, and does not wait on a long pass

```gherkin
Feature: Factory work supply does not depend on an interactive session
  As a maintainer whose factory sat idle for hours with ready work because no session ran a drain
  I want a timer to start an unattended drain pass for each tenant on an interval
  So that ready work reaches the factory whether or not any session is running

Scenario: A firing starts one unattended drain pass for its tenant
  Given the work-supply timer is installed for tenant repository "T" with an operator-chosen interval
  And no interactive session is running a drain
  And "T"'s first-ranked admission-eligible ready item has a free counted-claim slot under wip_cap
  When the timer fires with a budget of at least one
  Then the service runs loop --repo T with that budget and no --item argument
  And that first-ranked item is dispatched under the same ranked queue, wip_cap and unattended cost gate as any unattended drain
  And when instead wip_cap or the budget leaves no room, the item is journaled with the exclusion reason the admission conditions assign it, and is not dispatched

Scenario: The installer refuses an instance whose wrapper is not executable
  Given an operator installing a work-supply instance for tenant "T" whose named credential wrapper is not an executable file on the host
  When the installer runs
  Then it refuses that instance, naming the instance and the wrapper path

Scenario: The installer refuses an interval below the documented minimum
  Given an operator installing a work-supply instance for tenant "T" with a firing interval shorter than the installer's documented minimum
  When the installer runs
  Then it refuses that instance, naming the instance, the interval given and the minimum

Scenario: Each firing executes the tenant's registered plugin build
  Given the work-supply timer is installed for tenant "T"
  And the registered plugin install for "T" moves to a newly released build
  When the timer next fires
  Then the pass executes the newly registered build without the unit being reinstalled
  And when instead no registered install exists for "T" the firing refuses, naming "T", and executes no build

Scenario: A long pass does not stop the next firing
  Given a work-supply pass for tenant "T" whose dispatched run is still in progress
  When the next interval elapses
  Then the timer starts a new pass
  And the new pass is governed by wip_cap as any unattended drain
```

3. tests/heading-coverage.json MUST gain an entry for the new Scenario 201 heading with `"test": "TODO"`, `"work_item": "bd-ib-hlfw5p"`, and a non-empty reason stating that the work-supply service, timer and installer are not yet implemented.
