---
topic: each-gmktec-fabro-server-s-2
author: claude-opus-5-5
created_at: 2026-11-12T22:28:33Z
---

## Proposal: Each gmktec Fabro server's launch limit is its own max_concurrent_runs, and the shared fleet cap is bounded by the committed fleet cap

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Provisional fleet launch scripts" today lets the fleet launchers keep caps of their own, each restating a number a Fabro server already enforces: a shared fleet cap read from an uncommitted runtime file (`FLEET_LAUNCH_FLEET_CAP_FILE`), per-factory caps assigned in `fleet-launch/config.sh` (`FLEET_LAUNCH_GMK_CAP`, `FLEET_LAUNCH_HL_CAP`), and a candidate cap read from a host location. This is the launch-scripts half of bd-ib-rtzhfc; the WIP-cap half is the sibling `each-gmktec-fabro-server-s.md`. It makes three changes:

- **Per-server limit.** For every gmktec Fabro server a launcher launches onto or counts (petri, candidate and mi-homelab today), the launcher takes that server's concurrent-run limit from the one value the server enforces: its `max_concurrent_runs`, read from the `<factory>.max_concurrent_runs` file livespec-dev-tooling renders in the run-cap directory from the same inventory value the `fabro_server` role renders into that server's `settings.toml`. `fleet-launch/config.sh` carries no cap value for any of them. Changing a server's limit is one committed change to that one value, and the launchers admit runs to that server up to the new limit with nothing else edited.
- **Shared fleet cap derived, not stored.** The fleet-cap file is retired. The *runtime fleet cap* is the sum of the per-server limits of the servers the shared fleet count covers.
- **Committed fleet cap bound.** The runtime fleet cap is bounded by the committed fleet cap that livespec-dev-tooling renders as `fleet-launch-cap` (`fabro_fleet_launch_cap`, livespec-dev-tooling#4385). A launch whose marker the shared fleet count skips, such as one held in the Dispatcher's master-CI wait, still counts against the committed fleet cap. A committed fleet cap that cannot be read holds every launch.

**Dependency.** The committed fleet cap and its rendered `fleet-launch-cap` file are defined ONLY by livespec-dev-tooling's proposal the-factory-runs-resourcequota-restates. livespec-dev-tooling#4385 merged that proposal at 2026-11-12T23:32Z as a PROPOSAL only: `fabro_fleet_launch_cap` is not yet in livespec-dev-tooling's ratified specification, nor in its ansible inventory, and no dispatching host renders `fleet-launch-cap` today. This proposal MUST NOT be ratified until the-factory-runs-resourcequota-restates is RATIFIED in livespec-dev-tooling. The fail-closed launcher this proposal specifies MUST NOT ship to a dispatching host before `fleet-launch-cap` is rendered on that host, because until then it would hold every launch.

**How the two are reconciled.** The staged "Committed fleet cap bound" text bound the fleet-cap file, and the per-server change deletes that file. Here the bound binds what remains: the sum of the per-server limits the launcher reads. It clamps the shared fleet cap to the committed value. It never lowers any one server's limit. An unreadable committed value holds every launch, as an unreadable server limit holds launches onto its server. The two numbers count different things. A server's `max_concurrent_runs` is the one number for that server's queue. The committed fleet cap is the one number for runs across the servers that share one factory namespace quota, and that quota is derived from it. So "nothing else edited" holds for each server's own limit. A change meant to let the FLEET run more runs at once than the committed fleet cap is a raise of the shared quota, and it raises the committed fleet cap first, as livespec-dev-tooling#4385 rules. Today petri's limit alone (20) already equals the runtime fleet-cap file's 20, so the committed value stays the fleet's working ceiling, as that file was.

### Motivation

Work item bd-ib-rtzhfc, Definition of Done bullets 1 and 2. Bullet 3 is the sibling `each-gmktec-fabro-server-s.md`, the WIP-cap half, merged as #5081. The item was refused at launch as spec-change tier on linked topic each-gmktec-fabro-server-s. legacy-coordinator-agent routed its two halves as two proposals under that one topic, so this one files as `each-gmktec-fabro-server-s-2`.

Maintainer direction, 2026-11-04, verbatim on epic livespec-dev-tooling-6tgd2z and quoted in the item's Context: "why we have three different levers for the same fucking queue, do we really need that? Are they redundant and still necessary? ... IF any of this is the case, fix it." In short: one queue, one number. The item's Context lists the knobs that bound the same petri run count. The server's `max_concurrent_runs` is the only enforcing one; the uncommitted fleet-cap file and `FLEET_LAUNCH_GMK_CAP` duplicate it. As recorded on 2026-11-07: petri fleet-cap 18 / gmk-cap 20 / `max_concurrent_runs` 20; candidate candidate-cap 1 / server 16; mi-homelab server 2.

What a second copy costs, measured. Run 01M78KW65M3F of bd-ib-t5aju3 failed at 2026-11-12T19:31Z at sandbox acquire with `exceeded quota: factory-runs, requested limits.cpu=6, used 114100m, limited 120`. The petri `factory-runs` ResourceQuota's `limits.cpu` 120 equals exactly 20 sandboxes at `limits.cpu` 6, the launchers' runtime fleet cap of 20, with no room for any other limits-bearing pod. The live quota is now `limits.cpu` 126, applied and read back at 21:56Z. The runtime fleet cap had no committed home, so nothing tied it to the quota. livespec-dev-tooling's proposal the-factory-runs-resourcequota-restates (filed by livespec-dev-tooling#4385, merged 2026-11-12T23:32Z as a proposal, not yet ratified) gives it one: `fabro_fleet_launch_cap` in `ansible/inventory/group_vars/dev_hosts.yml`, rendered on every `dev_hosts` host as the file `fleet-launch-cap` in the run-cap directory. It is NOT any server's `max_concurrent_runs`. That proposal states the dev-tooling half of the coordinator's rule ("Whoever raises such a runtime cap MUST raise `fabro_fleet_launch_cap` first") and names this proposal's "Committed fleet cap bound." as the launcher-side half.

The per-server values already have a committed, rendered home. livespec-dev-tooling §"Run caps rendered beside the registry" renders `<factory>.max_concurrent_runs` in `/home/ubuntu/.local/state/livespec/fleet-limits` from the same inventory entry the `fabro_server` role writes into `settings.toml` (livespec-dev-tooling-o5xpdy, the build-order prerequisite the item names). Read on the dispatching host on 2026-11-12: petri 20, candidate 16, mi-homelab 2, homelab-worker-arm64 1.

§"Host concurrency belongs to the Fabro scheduler" forbids the Orchestrator to enforce or report `max_concurrent_runs` as its own bound. The launcher's read here is caller-side under this section's first paragraph and feeds no Dispatcher surface, and the new bullet says so.

Design choices, stated for the grade:
- **Fail closed on every unreadable value.** An unreadable server limit holds launches onto that server, like the existing rule for an unreadable run count. An unreadable committed fleet cap holds every launch. Leaving the runtime sum in force would not be safe: the per-server limits sum to 38 (petri 20, candidate 16, mi-homelab 2), about twice what the `factory-runs` quota holds (`limits.cpu` 126, about 21 sandboxes at 6). It would also break #4385's "A runtime launch cap that a launcher reads from any other file MUST NOT exceed this value". This replaces the fail-open sentence of the staged text.
- **Skipped markers still hold a committed slot.** A rule that skips a marker from the shared fleet count lowers only that count. The committed-cap count still includes the marker. A launch held in the Dispatcher's master-CI wait, which a-fleet-launcher-holds-its (#5088) skips, therefore keeps its committed slot, and a re-bind at the pass line can never take the fleet past the committed fleet cap. This needs no quota read. Clamping `FLEET_LAUNCH_MASTER_CI_WAIT_MAX` to the quota's slack would.
- **Read on every gate pass**, so a changed value governs the next pass with no launcher restart and no other edit.
- **Unlisted markers count toward a server**, so binds queued between board reads cannot overshoot its limit.
- **Resume launches are bounded too**, because a resumed run takes a slot on its server.
- **Existing terms kept.** "Shared fleet cap" and "per-factory cap" stay in the bullets that use them, among them two that pending proposals rewrite. They now take the values this proposal defines, so no in-flight text has to change.

Fleet scope: every Fabro server the `fabro_factory_registry` places on gmktec-xubuntu that a committed launcher launches onto or counts. That is petri, candidate and mi-homelab today, and homelab-worker-arm64 once a committed launcher routes to it. livespec-orchestrator-git-jsonl has no `fleet-launch/` launchers. The committed launcher build in impl PR #4822 (bd-ib-3ufx6l) carries the candidate target and `FLEET_LAUNCH_GMK_CAP`, and rtzhfc's launcher change lands on what that PR leaves.

In-flight survey, 2026-11-12 ~22:25Z: in-tree proposals on origin/master, the 25 remote `spec/*` branches, and open PRs touching `SPECIFICATION/` or `fleet-launch/`.
- each-gmktec-fabro-server-s (bd-ib-rtzhfc, in-tree, the WIP-cap half): edits §"Per-repo WIP cap" and Scenario 58 only. Relation: `align`.
- the-launcher-holds-one-wip-number (bd-ib-5k2yq2, in-tree): rewrites **Breakage exception.** and adds **Capacity-deferred return.**. Its "MUST NOT raise the shared fleet cap or any per-factory cap" keeps its meaning, because both terms survive here with the values defined below. No sentence overlaps. Relation: `align`.
- a-fleet-launcher-holds-its (bd-ib-4vwaty, PR #5088): its waiting markers are skipped from the shared fleet count, up to `FLEET_LAUNCH_MASTER_CI_WAIT_MAX` of them, and that ceiling defaults to the shared fleet cap. Its "Over the cap" rule lets a drive proceed past the shared fleet cap at the pass line. Left alone, that overshoot could reach many runs past the committed fleet cap. This proposal bounds it without editing #5088's text: every marker the shared fleet count skips still counts in the committed-cap count. A launch therefore never starts while waiting launches fill the committed fleet cap, and the overshoot past the shared fleet cap can never pass the committed fleet cap. `FLEET_LAUNCH_MASTER_CI_WAIT_MAX` bounds skipped markers, not runs, so it is not a cap value of the kind this proposal removes from `fleet-launch/config.sh`. The two compose in either revise order. Relation: `align`.
- a-fleet-launcher-honours-a (bd-ib-aibd3u, in-tree): hold-file exemptions only. Relation: `align`.
- fleet-launchers-log-and-retry (bd-ib-7itf42, PR #5073) and concurrent-git-fetches-into-one (bd-ib-zyu2ug, PR #5072): non-run exits and the fetch lock in this section, with no cap text. Relation: `align`.
- Cross-repo, livespec-dev-tooling's the-factory-runs-resourcequota-restates (proposal merged by livespec-dev-tooling#4385 at 2026-11-12T23:32Z, not yet ratified): it defines and renders `fleet-launch-cap`, and this proposal only reads it. Relation: `align`, and this proposal depends on it. It MUST NOT be ratified until that topic is ratified (see the Dependency paragraph and change 9).
No in-flight item is superseded or in conflict.

### Proposed Changes

All edits are in `contracts.md` §"Provisional fleet launch scripts" and in `scenarios.md` Scenarios 242 and 307. No H2 heading is added, renamed or removed.

**1. Caller-side framing (`contracts.md`, the section's first paragraph).** Replace "Its shared fleet cap, per-factory FIFO tickets and mutex, hold file, board and in-flight readers are caller-side gates;" with:

> Its shared fleet cap, per-server limit gate, per-factory FIFO tickets and mutex, hold file, board and in-flight readers are caller-side gates;

**2. The candidate cap is retired (`contracts.md`, the bullet beginning "**gmktec target and candidate cap.**").** Replace the whole bullet with:

> - **gmktec target.** The *gmktec target setting* selects which gmktec factory instance a gmktec launch goes to: the default instance, or the candidate instance. The launcher MUST read the setting on every gate pass from the location a host value in `fleet-launch/config.sh` names, and MUST select the default instance when the setting is absent or names anything other than the candidate. A launcher whose setting selects the candidate instance MUST launch onto it only as the "Per-server limit" bullet allows, against the candidate's own limit.

**3. Per-server limit and the committed fleet cap bound (`contracts.md`).** Immediately after the **gmktec target.** bullet, add:

> - **Per-server limit.** The *gmktec Fabro servers* are the Fabro servers that the `fabro_factory_registry` places on gmktec-xubuntu and that a `fleet-launch/` launcher launches onto or counts in its shared fleet count; today they are `petri`, `candidate` and `mi-homelab`. A server's *limit* is the one value that server enforces, its `max_concurrent_runs`. The launcher reads it from the file `<factory>.max_concurrent_runs` that livespec-dev-tooling renders in the run-cap directory from the same committed inventory value the `fabro_server` role renders into that server's `settings.toml` (livespec-dev-tooling §"Run caps rendered beside the registry"). The run-cap directory's path is a host value in `fleet-launch/config.sh`, defaulting to `/home/ubuntu/.local/state/livespec/fleet-limits`, and is overridable like any other. A launcher MUST read each server's limit from that file on every gate pass, so that a changed value governs the next pass without any launcher being restarted. It MUST NOT take a gmktec Fabro server's concurrent-run limit from any other file or variable. `fleet-launch/config.sh` MUST NOT assign a concurrent-run limit or cap value for any of them: no per-factory cap (`FLEET_LAUNCH_GMK_CAP`, `FLEET_LAUNCH_HL_CAP`), no shared fleet-cap file (`FLEET_LAUNCH_FLEET_CAP_FILE`) and no candidate cap.
>
>   A server's *count* is its live run count, read from its factory board, plus the fleet in-flight markers of launches onto that server whose runs have not yet listed. An impl launcher or a resume launcher MUST NOT launch onto a server while that server's count is at or above its limit. At the binding re-count under the factory mutex, with its own marker counted, it MUST proceed only while that count is at or below the limit. Each of the following MUST hold every launch onto that server: a limit file that is absent or unreadable, a limit file that is not a non-negative decimal integer, and a count that cannot be read. The launcher MUST then log the cause and name the server. Where this section names a per-factory cap, it means that server's limit.
>
>   Changing a server's limit is a change to that one committed value. The launchers then admit runs to that server up to the new limit with no other file or variable edited, bounded only by the shared fleet cap and the committed fleet cap bound. This read is caller-side under this section's first paragraph. It is not an Orchestrator bound in the sense of §"Host concurrency belongs to the Fabro scheduler", and it MUST NOT feed any Dispatcher admission, gating or capacity-reporting surface.
>
>   The *runtime fleet cap* is the sum of the limits of the servers the shared fleet count counts, where a limit that cannot be read contributes 0. The *shared fleet cap* that every rule of this section compares the shared fleet count against is the runtime fleet cap as the "Committed fleet cap bound" bullet bounds it.
> - **Committed fleet cap bound.** A launcher MUST read the committed fleet cap that livespec-dev-tooling renders as `fleet-launch-cap` in the run-cap directory at every read of the per-server limits. While the runtime fleet cap exceeds the committed fleet cap, the launcher MUST treat the shared fleet cap as the committed value, MUST log one line naming both values on each gate pass that applies the bound, and MUST NOT launch a run the committed value would hold.
>
>   The *committed-cap count* is the shared fleet count plus every live fleet in-flight marker that the shared fleet count skips under any rule of this section, such as a marker marked waiting during the Dispatcher's master-CI wait. An impl launcher or a resume launcher MUST NOT launch while the committed-cap count is at or above the committed fleet cap. At the binding re-count under the factory mutex, with its own marker counted, it MUST proceed only while the committed-cap count is at or below the committed fleet cap. A launch whose marker the shared fleet count skips therefore still holds a committed slot. No re-count or re-bind of a launch already started, under this or any other rule of this section, MAY take the committed-cap count past the committed fleet cap.
>
>   The bound MUST NOT raise the shared fleet cap above the runtime fleet cap, and MUST NOT change any one server's limit. A committed fleet cap that is absent, unreadable or not a positive decimal integer MUST hold every launch, of either kind and onto every server, exactly as an unreadable per-server limit holds launches onto its server. The launcher MUST then log one line naming the path it could not read. A change meant to let the fleet run more runs at once than the committed fleet cap MUST raise the committed fleet cap first, in the same change or before it. Raising a server's `max_concurrent_runs` does not by itself lift the fleet past the committed fleet cap.

**4. Harness cases (`contracts.md`, the `check-fleet-launch` case lists).** In the paragraph beginning "The `check-fleet-launch` harness cases MUST also cover each of the gates above:", replace "and a gmktec launch sent to the instance the gmktec target setting names, launching onto the candidate only while its live run count is below the candidate cap." with:

> and a gmktec launch sent to the instance the gmktec target setting names, launching onto the candidate only while its count is below the limit its stub `candidate.max_concurrent_runs` file holds.

Immediately after the paragraph beginning "The `check-fleet-launch` harness cases MUST also cover the shared WIP claim-count cache:", add:

> The `check-fleet-launch` harness cases MUST also cover the per-server limit and the committed fleet cap bound, against a throwaway run-cap directory:
>
> - a launch onto a stub server held while that server's count equals the limit its `<factory>.max_concurrent_runs` file holds;
> - the same launcher launching on its next gate pass once only that file's value is raised, and held again at the new limit;
> - a launch held, with a log line naming the server, when that server's limit file is absent or does not hold an integer;
> - a launch held while the shared fleet count equals a committed `fleet-launch-cap` that is below the runtime fleet cap, with one log line naming both values;
> - every launch, impl and resume, held when `fleet-launch-cap` is absent or does not hold a positive integer, with one log line naming the unreadable path;
> - a launch held while the shared fleet count is below the committed fleet cap, but the committed-cap count equals it because of a stub marker carrying `master-ci-wait=1` that the shared fleet count skips;
> - a `fleet-launch/config.sh` that assigns no per-factory, candidate or shared fleet cap value.
>
> Scenario 307 in `scenarios.md` exercises these cases.

**5. Scenario 242 (`scenarios.md` §"Scenario 242 — The provisional fleet launch check fails the build on a broken launcher").** In the scenario "host values are declared once and overridable", replace "the fleet-cap file," with "the run-cap directory,", so the step reads:

```gherkin
    Given a host value a fleet-launch script reads, such as a factory server URL, the run-cap directory, a queue, lock or in-flight directory, or the fabro binary path
```

**6. Scenario 307 (`scenarios.md` §"Scenario 307 — The committed fleet-launch launchers enforce the repository hold, WIP gate, breakage exception, re-ticket, gmktec hold and candidate target").** Inside its existing gherkin block, replace the scenario "The gmktec target setting selects the candidate only below its cap" (its heading line and its eight steps) with the following six scenarios:

```gherkin
  Scenario: The gmktec target setting selects the candidate only below its own limit
    Given the gmktec target setting names the candidate instance
    And the run-cap directory's candidate.max_concurrent_runs file holds 2
    When the candidate instance's board lists 2 live runs
    Then the launcher holds the launch
    When the candidate instance's board lists 1 live run
    Then the launcher launches onto the candidate instance
    When the gmktec target setting is absent
    Then the launcher launches onto the default instance

  Scenario: A server's own limit is the only value a raise edits
    Given fleet-launch/config.sh assigns no per-factory, candidate or shared fleet cap value
    And the run-cap directory's petri.max_concurrent_runs file holds 3
    And fleet-launch-cap holds a value above the runtime fleet cap
    When petri's board lists 3 live runs
    Then a launcher holds its launch onto petri
    When petri.max_concurrent_runs is changed to 4 and no other file or variable is edited
    Then on its next gate pass the launcher launches onto petri
    When petri's board lists 4 live runs
    Then the next launcher holds its launch onto petri

  Scenario: A server whose limit cannot be read takes no launch
    Given the gmktec target setting names the candidate instance
    And the run-cap directory holds no candidate.max_concurrent_runs file
    When a launcher reaches the per-server limit gate
    Then it holds the launch
    And it logs that the candidate's limit could not be read

  Scenario: The committed fleet cap bounds the shared fleet cap
    Given the servers the shared fleet count counts have limits summing to 5
    And fleet-launch-cap holds 4
    And the shared fleet count is 4 while the target server's count is below its limit
    When a launcher reaches the shared fleet cap gate
    Then it holds the launch
    And it logs one line naming the runtime fleet cap 5 and the committed fleet cap 4

  Scenario: An unreadable committed fleet cap holds every launch
    Given the servers the shared fleet count counts have limits summing to 5
    And the run-cap directory holds no fleet-launch-cap file
    And the shared fleet count is 0 while the target server's count is below its limit
    When an impl launcher and a resume launcher reach the shared fleet cap gate
    Then both hold their launches
    And each logs one line naming the fleet-launch-cap path it could not read

  Scenario: A launch skipped from the shared fleet count still holds a committed slot
    Given the servers the shared fleet count counts have limits summing to 5
    And fleet-launch-cap holds 3
    And the target server's count is below its limit
    And two live runs listed on the boards and one live fleet in-flight marker carrying master-ci-wait=1
    And the shared fleet count skips that marker and reads 2
    When a launcher reaches the shared fleet cap gate
    Then the committed-cap count reads 3
    And it holds the launch
```

**7. Unchanged.** The resume launcher's bullet ("below the shared fleet cap"), Scenario 302, and the **Breakage exception.** and **gmktec factory hold.** bullets MUST keep their text. Their "shared fleet cap" and "per-factory cap" now read the values change 3 defines. No rule of this section MAY read a fleet cap or a per-factory cap from `fleet-launch/config.sh`.

**8. Revise co-edit.** None is owed. No H2 heading changes, and Scenario 242's and Scenario 307's existing `tests/heading-coverage.json` rows cover the edited scenarios unchanged.

**9. Dependency on livespec-dev-tooling's the-factory-runs-resourcequota-restates.** This proposal MUST NOT be ratified, by `revise` or any other path, until the topic the-factory-runs-resourcequota-restates is RATIFIED in livespec-dev-tooling, that is, until its proposal file has left `SPECIFICATION/proposed_changes/` and the topic is under `SPECIFICATION/history/`. livespec-dev-tooling#4385 merging the proposal (2026-11-12T23:32Z) does not satisfy this. That topic is the only definition of `fabro_fleet_launch_cap` and its rendered `fleet-launch-cap` file. If it is rejected, or ratifies with a different file name or meaning, this proposal MUST be revised to match before it is ratified. The fail-closed launcher MUST NOT ship to a dispatching host before `fleet-launch-cap` is rendered on that host, since an absent file holds every launch.
