---
topic: an-environments-only-fabro-hosts
author: claude-opus-5-5
created_at: 2026-11-13T03:05:00Z
---

## Proposal: A factory server's sandbox environment catalog converges through an environments-only path

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add one bullet to §"Fabro factory host provisioning constraints", **Environments-only catalog convergence.** The committed provisioning of a factory server MUST offer one committed selector, for both the drift read and the apply, that converges ONLY that server's sandbox environment catalog.

- It runs only the catalog writes and the read-only tasks they need. No task that installs a binary, writes a unit or settings file, or touches the vault runs.
- It never restarts the server.
- It leaves runs already in flight running.
- Its drift read reports a pending environment change exactly as the full drift read does.

Each runbook procedure that switches a factory sandbox environment's backend MUST name that selector's commands and their measured wall-clock duration. The section's scope, its no-hostname sentence and its Verification paragraph are amended to cover the new bullet. One scenario covers the switch.

### Motivation

Work item bd-ib-4f24p4 (plan kubernetes-sandbox-backend, epic bd-ib-nmuyjc) was held at the ledger screen on the spec-change tier with this linked topic, because no ratified clause states an environments-only path. legacy-coordinator-agent (session 56ce1bcd) routed it back to this plan as a spec-tier orphan on 2026-11-13. It also asked that the item's 2026-11-05 host-route hold be re-justified or lifted.

**The hold is lifted.** The 2026-11-05 hold queued 4f24p4 at plan priority P6, behind three items, and all three are now CLOSED (read 2026-11-13):

- bd-ib-digmk2 (driver v0.8.2 umask);
- livespec-dev-tooling-izazkx (the reaper stranding a Running pod);
- livespec-dev-tooling-6prge3 (the reaper creating a full sandbox pod).

Its other stated trigger, "the next fabro-hosts change I carry", also occurred on 2026-11-13. The candidate instance's driver re-pin (livespec-dev-tooling#4393) was applied at 00:37Z.

**The problem is still real.**

- livespec-dev-tooling `ansible/factory-sandbox-backend-runbook.md` §"Recovery time" still reads: "Each switch costs one full `fabro-hosts.yml --limit gmktec-xubuntu` apply, about 30 minutes. A drift run before it takes 12 to 20 minutes more. The play has no environments-only path".
- The catalog write lands about two-thirds of the way through the apply, at the task "Replace this environment in the instance's catalog".
- A switch to the Docker fallback during a cluster outage therefore costs about 45 minutes from merge to converged catalog.
- The `fabro_server` role has no tag that selects only its catalog tasks (`ansible/roles/fabro_server/tasks/main.yml` and `environment.yml`, read on origin/master).

The rule belongs to the factory host's provisioning, because a backend switch is the documented recovery from a cluster outage, and recovery time is part of operating the factory. Like the section's other bullets, it names no host. The play and role that implement it are livespec-dev-tooling's, where bd-ib-4f24p4 lands its change.

In-flight survey (pending proposals in this repository, 2026-11-13 ~03:05Z, grepped for "fabro-hosts", "environment catalog" and "runbook"): none touches a factory server's environment catalog convergence. Relation: `independent`.

### Proposed Changes

**1. `constraints.md` §"Fabro factory host provisioning constraints", scope.** Replace "**Scope** — bringing up any additional Fabro factory server the fleet operates" with:

> **Scope** — bringing up, or re-converging, any Fabro factory server the fleet operates

The rest of that sentence is unchanged.

**2. Same section, new bullet.** Append after the bullet that begins "**New-host credential sourcing.**":

> - **Environments-only catalog convergence.** The committed provisioning that installs a factory server MUST offer one committed selector, for example a tag, for both a drift read and an apply on one host. Under that selector they MUST run only:
>   - that host's factory servers' sandbox environment catalog writes; and
>   - the read-only tasks those writes need, such as resolving the server's address, its API token and its health.
>
>   The catalog writes are the only tasks that may report a change. No task of the same role that installs a binary, writes a unit or settings file, or touches the vault may run under that selector, and no task of any other role may run. The selector MUST NOT restart any factory server, and a run in flight on that server before the apply MUST keep running through it. The drift read under that selector MUST report a pending environment change with the same disposition (for example "will be replaced") as the full drift read for the same change. Every runbook procedure that switches a factory sandbox environment from one backend to another MUST give that selector's drift and apply commands as the switch procedure. It MUST also give the measured duration of each command: its wall-clock time from start to exit, measured on a named date against a named host.

**3. Same section, no-hostname sentence.** Replace "Neither bullet MAY name a specific hostname, tailnet, or domain" with "No bullet MAY name a specific hostname, tailnet, or domain". The rest of that sentence is unchanged.

**4. Same section, Verification.** Append to the paragraph that begins "**Verification.**":

> Environments-only catalog convergence is decided by four reads against one factory server:
> - the drift read's output under the selector reports the pending environment change with the same disposition as the full drift read;
> - the apply's output under the selector shows that only catalog-write tasks reported a change, and that no task of another role ran;
> - the server unit's `ActiveEnterTimestamp` is unchanged across the apply;
> - a run that was in flight before the apply still reports a running status after it.
>
> The runbook's recorded durations are the wall-clock times of those two commands.

**5. Scenario (`scenarios.md`).** Add, numbered with the next free number:

## Scenario NN — A sandbox backend switch converges only the environment catalog and leaves the server running

Given a factory server whose committed sandbox environment `factory-python` names the `kubernetes` provider, with one run in flight on that server

And a committed change that switches `factory-python` to the `docker` provider

When the operator runs the drift read under the environments-only selector, limited to that server's host

Then it MUST report `factory-python` as "will be replaced", the same disposition the full drift read reports

And no task of any other role may have run

When the operator runs the apply under the same selector and limit

Then the server's catalog MUST name the `docker` provider for `factory-python`

And only the catalog-write tasks may have reported a change, and no task that installs a binary, writes a unit or settings file, or touches the vault may have run

And the server unit's `ActiveEnterTimestamp` MUST be unchanged, and the run in flight MUST still be running

And the runbook's backend-switch procedure MUST give these two commands and the wall-clock duration of each, measured on a named date

**6. `tests/heading-coverage.json`.** Add one entry in the same revise for the new scenario heading, with `"test": "TODO"`, `"work_item": "bd-ib-4f24p4"`, and a non-empty `reason`. The reason states that the scenario is host-captured and owes a test at the integration tier or above: a real drift run and apply from the control node against a live factory server, which no factory sandbox reaches. bd-ib-4f24p4's host-captured proof is the evidence until that test exists. Regenerate the heading-coverage debt register in the same commit.
