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

- It runs no task of any other role or service.
- It never restarts the server.
- It leaves runs already in flight running.
- Its drift read reports a pending environment change exactly as the full drift read does.

Each runbook procedure that switches a factory sandbox environment's backend MUST name that selector's commands and their measured duration. One scenario covers the switch.

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

**1. `constraints.md` §"Fabro factory host provisioning constraints".** Append after the bullet that begins "**New-host credential sourcing.**":

> - **Environments-only catalog convergence.** The committed provisioning that installs a factory server MUST offer one committed selector (for example a tag) that, applied to one host, converges ONLY that host's factory servers' sandbox environment catalogs, together with the facts those catalog writes need. A drift read and an apply under that selector MUST run no task of any other role or service. They MUST NOT restart any factory server, and a run in flight on that server before the apply MUST keep running through it. The drift read under that selector MUST report a pending environment change with the same disposition, for example "will be replaced", that the full drift read reports for the same change. Every runbook procedure that switches a factory sandbox environment from one backend to another MUST give that selector's drift and apply commands as the switch procedure, together with their measured duration.

**2. Scenario (`scenarios.md`).** Add, numbered with the next free number:

## Scenario NN — A sandbox backend switch converges only the environment catalog and leaves the server running

Given a factory server whose committed sandbox environment `factory-python` names the `kubernetes` provider, with one run in flight on that server

And a committed change that switches `factory-python` to the `docker` provider

When the operator runs the drift read under the environments-only selector, limited to that server's host

Then it MUST report `factory-python` as "will be replaced", the same disposition the full drift read reports, and MUST report no task of any other role

When the operator runs the apply under the same selector and limit

Then the server's catalog MUST name the `docker` provider for `factory-python`

And no task of any other role MUST have run, the server's unit MUST NOT have restarted, and the run in flight MUST still be running

And the runbook's backend-switch procedure MUST give these two commands and their measured duration

**3. `tests/heading-coverage.json`.** Add one entry in the same revise for the new scenario heading, with `"test": "TODO"`, `"work_item": "bd-ib-4f24p4"`, and a non-empty `reason`. The reason states that the scenario is host-captured: it needs a real drift run and apply from the control node against a live factory server, which no factory sandbox reaches, so bd-ib-4f24p4's host-captured proof is its evidence.
