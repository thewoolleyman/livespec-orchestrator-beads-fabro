---
topic: the-launcher-holds-one-wip-number
author: claude-opus-5-5
created_at: 2026-11-09T23:34:20Z
---

## Proposal: The fleet launcher holds one repository WIP number: a breakage exception orders, it does not raise the cap, and a capacity-deferred drive returns to the WIP gate

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The repository's `wip_cap`, applied by the `loop` that `drive --action impl:<item>` runs, becomes the only per-repository WIP number a fleet launcher acts on. **Breakage exception.** stops treating the cap as `wip_cap` + 1 for a listed item and instead orders a listed ticket ahead of unlisted ones on its per-factory FIFO. A new **Capacity-deferred return.** bullet covers a drive that reports `capacity-deferred` (exit 1) and launched no run. The launcher re-takes its ticket number with no early-exit delay or count, restores a consumed freeze-allowlist release, and holds at the WIP gate until a fresh projection read shows a free slot. It re-runs its model-backed preflight only when its pass is older than `FLEET_LAUNCH_PREFLIGHT_REUSE_S`.

### Motivation

Measured on 2026-11-09 by legacy-coordinator-agent (session 5779d475). From 23:03 to 23:07Z a launcher-side exemption launched livespec-dev-tooling-zwlrpf into a Dispatcher that deferred it (`capacity deferred: active_count=10 wip_cap=10 free_slots=0`). Nothing ran, and the launcher's 300 s and 600 s early-exit re-tickets re-ran the model-backed preflight. At 23:14:23Z the launcher's shared 60-second count read 9/10 for a moment, and it launched zwlrpf again into a 10/10 deferral. The ratified text causes both. **Breakage exception.** has the launcher stop yielding at `wip_cap` + 1 for a listed item, while the `loop` that `drive --action impl:<item>` runs applies `wip_cap` to that drive, so every excepted launch at count = `wip_cap` is deferred by design. `loop` reports `capacity-deferred` as an exit-0 status, but `drive` copies the status to its top level and exits 1 for anything other than green or handed-off (`_drive_cli.py` `exit_code_for_status`). **Early-exit re-ticket.** therefore treats a deferral as an ordinary early exit, with delays, a counted exit and a fresh preflight, although no run was attempted. A cached count read before the deferral can also pass the gate again at once. It is the shape coordinator-duties §10 names: one queue gets one number. Keeping the breakage exception as FIFO priority preserves its intent, a stop-the-line fix at the queue head, without a second number. Linked work item: bd-ib-5k2yq2, which depends on bd-ib-3ufx6l, the committed launcher build. In-flight survey: no open spec PR and no fleet-launch `spec/*` branch, and the pending a-fleet-launcher-honours-a and cost-gate-covers-every-launched-run proposals do not touch these bullets (align). A pre-filing LLM doctor walk against the Dispatcher and both launchers corrected an earlier draft's exit-code claim and added the fresh-read, failed-read and freeze-allowlist rules, and the cache-bullet exception that the fresh read needs.

### Proposed Changes

All edits are in `contracts.md` §"Provisional fleet launch scripts" and in `scenarios.md` §"Scenario 307 — The committed fleet-launch launchers enforce the repository hold, WIP gate, breakage exception, re-ticket, gmktec hold and candidate target". No H2 heading is added, renamed or removed. The edits govern the committed `fleet-launch/` launchers. The interim launcher is outside this section until the cutover, so the seat that runs it changes it by hand.

1. In the paragraph that begins "A `fleet-launch/` impl launcher that holds a per-factory FIFO ticket MUST run its launch-time Definition-of-Done preflight while it is queued", replace "tickets still bind in FIFO order, and a launcher MUST NOT add any ordering rule beside the FIFO ticket." with:

"tickets still bind in FIFO order as the breakage exception's priority below adjusts it, and a launcher MUST NOT add any other ordering rule."

2. In the bullet that begins "- It MUST take a ticket on the target factory's FIFO", replace "MUST start only when its ticket is the live head of that FIFO, so impl launchers and resume launchers queued on one factory bind in one ticket order." with:

"MUST start only when its ticket is the live head of that FIFO in the order this section computes, the ticket order as the breakage exception's priority adjusts it, so impl launchers and resume launchers queued on one factory bind in one order."

3. Replace the whole **Breakage exception.** bullet with:

"- **Breakage exception.** The repository includes a committed breakage-exception list, the file `fleet-launch/breakage-exception`, holding one work-item id per line; its path is a host value assigned in `fleet-launch/config.sh` and overridable like any other. A ticket whose work item that list names, for an impl launcher or a resume launcher, MUST order ahead of every ticket on the same per-factory FIFO whose work item the list does not name, and listed tickets order among themselves by ticket number. Every launcher MUST re-read the list each time it computes its FIFO place, so that every reader of one FIFO applies the same order, and a list that is absent or unreadable MUST be read as naming no work item. The exception changes ORDER only. The repository WIP gate MUST hold a listed work item exactly as it holds an unlisted one, comparing against that repository's unchanged `wip_cap`, and the exception MUST NOT raise the shared fleet cap or any per-factory cap. A launch past `wip_cap` would only be deferred, because the `loop` that `drive --action impl:<item>` runs applies `wip_cap` to every drive the launcher starts."

4. In the **Shared WIP claim-count cache.** bullet, replace "The in-flight addition refines the comparison of the repository WIP gate and the breakage exception: where those bullets compare the counted-claims count against the cap, the launcher MUST compare" with:

"The in-flight addition refines the comparison of the repository WIP gate: where that bullet compares the counted-claims count against the cap, the launcher MUST compare"

4b. In the same **Shared WIP claim-count cache.** bullet, replace "A cached read younger than the cache time-to-live, a host value assigned in `fleet-launch/config.sh` and overridable like any other, MUST be reused rather than recomputed." with:

"A cached read younger than the cache time-to-live, a host value assigned in `fleet-launch/config.sh` and overridable like any other, MUST be reused rather than recomputed, except for the fresh read the **Capacity-deferred return.** bullet requires, which MUST be recomputed whatever the cached read's age."

5. In the **Early-exit re-ticket.** bullet, replace "Every other non-zero exit before listing, other than one whose drive reports a failed `goal-minijinja-preflight` stage, remains an early exit" with:

"Every other non-zero exit before listing, other than one whose drive reports a failed `goal-minijinja-preflight` stage or a dispatch outcome with status `capacity-deferred`, remains an early exit"

6. Insert this bullet immediately AFTER the **Early-exit re-ticket.** bullet:

"- **Capacity-deferred return.** A `drive --action impl:<item>` that reports, in its JSON output, a dispatch outcome with status `capacity-deferred` for the launcher's work item has launched no run, whatever its exit code; `drive` exits 1 for it today. It is NOT an early exit. The launcher MUST NOT apply the early-exit re-ticket delays to it and MUST NOT count it among that work item's consecutive early exits. The launcher MUST re-take a FIFO ticket for the same work item at the same ticket number, MUST remove its fleet in-flight marker, and MUST log the return. When the launch it made for that drive removed its work item's freeze-allowlist line, it MUST restore that line under the freeze-allowlist lock, because the release launched no run. It MUST then hold at the repository WIP gate as a launcher whose count is at or above `wip_cap` holds there. Before it can pass that gate again, it MUST take a fresh counted-claims read through the capacity projection, under the per-repository serialization, and write it to the claim-count cache. It MUST NOT pass on a cached read taken before the deferral, because that read is the one that showed the slot the Dispatcher refused. When that fresh read fails, or the per-repository serialization cannot be obtained, the launcher MUST stay held at the gate and MUST retry the fresh read on its next poll. This is the one exception to the repository WIP gate's rule that a launcher does not hold on an unreadable count, because the Dispatcher has just reported the cap full. Once the gate no longer holds it, it MUST take its FIFO place back in the order of the ticket it re-took. On that return it MUST run its launch-time preflight again only when it holds no passing preflight younger than `FLEET_LAUNCH_PREFLIGHT_REUSE_S`, as a launcher reaching the FIFO head does. The return does not restart `FLEET_LAUNCH_MAX_WAIT_S`, which keeps counting from the launcher's start. The launcher MUST write one line to its sequence log naming the work item, its ticket number and the cause `capacity-deferred`. That line is not a terminal line, because the return is not a non-run exit."

7. In the `check-fleet-launch` harness coverage list, replace "an item on the breakage-exception list not held at a counted-claims count equal to `wip_cap`, and an unlisted item at the same count held;" with:

"a listed breakage-exception ticket ordering ahead of an older unlisted ticket on the same FIFO, an absent breakage-exception list ordering no ticket ahead, and a listed item held at a counted-claims count equal to `wip_cap` exactly as an unlisted item is held; a drive reporting `capacity-deferred` that re-takes its ticket number with no early-exit delay and no added early-exit count, restores a consumed freeze-allowlist line, does not pass the WIP gate on a cached count read before the deferral, stays held when the fresh read after a deferral fails, and runs no second preflight while its passing preflight is inside the reuse window;"

8. In `scenarios.md` §"Scenario 307 — ...", inside its existing gherkin block, replace the scenario "Only a listed item passes the WIP gate one above the cap" (its heading line and its five steps) with:

```gherkin
  Scenario: A listed item is ordered first and is held at the cap like any other
    Given impl launchers for work items bd-y and bd-x of one repository, holding the two oldest tickets of one per-factory FIFO in that order
    And the committed breakage-exception list names bd-x and not bd-y
    And the repository's counted-claims count is below its configured wip_cap
    When the launchers compute their FIFO places
    Then the bd-x launcher's ticket is the live head ahead of the bd-y launcher's ticket
    When the repository's counted-claims count equals its configured wip_cap
    Then the WIP gate holds the bd-x launcher
    And the WIP gate holds the bd-y launcher
```

and append inside the same gherkin block, after the scenario "A drive that exits before its run lists re-takes a FIFO ticket":

```gherkin
  Scenario: A capacity-deferred drive returns the launcher to the WIP gate without an early-exit retry
    Given an impl launcher that passed its launch-time preflight and launched from FIFO ticket 7
    And FLEET_LAUNCH_PREFLIGHT_REUSE_S is longer than the test runs
    And the claim-count cache holds a read, taken before the drive, of one below wip_cap
    And the capacity projection reports a counted-claims count equal to wip_cap
    When its drive reports a dispatch outcome with status capacity-deferred and exits non-zero
    Then the launcher re-takes FIFO ticket 7
    And it removes its fleet in-flight marker
    And it applies no early-exit re-ticket delay and records no early exit for the work item
    And it holds at the repository WIP gate
    When the capacity projection read fails
    Then it stays held at the repository WIP gate
    When the capacity projection reports a counted-claims count below wip_cap
    Then it takes its FIFO place back in the order of ticket 7
    And it does not run its launch-time preflight again
```
