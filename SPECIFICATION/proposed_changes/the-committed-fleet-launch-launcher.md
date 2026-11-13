---
topic: the-committed-fleet-launch-launcher
author: claude-opus-5-5
created_at: 2026-11-13T08:13:09Z
---

## Proposal: The shared fleet count includes the candidate lane and leaves out the arm64 lane, and interim launcher copies match the committed sources

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Provisional fleet launch scripts" says a launcher refuses at the shared fleet cap, keeps its ticket and counts in-flight markers. It never says which factory instances the shared fleet count sums. It also lets the seat's interim launcher copies drift from the committed sources with nothing recording how they differ. The committed `fleet-launch/dispatch-dual.sh` sums gmktec, mi-homelab and markers. The copy every running launcher executes, `tmp/petri-canary/dispatch-dual-r681b.sh`, also sums the candidate instance and leaves the arm64 lane out. A launcher restarted from the committed file would therefore put candidate runs outside the fleet cap. This proposal makes these changes:

- **Shared fleet count.** The section defines the shared fleet count. It is the live runs listed on the boards of the gmktec default instance, the candidate instance and the mi-homelab instance, plus every unlisted fleet in-flight marker that does not name the `homelab-worker-arm64` instance (the *arm64 lane*). A marker that names no instance, or an unexpected one, counts. Every launcher writes the instance it actually launches onto into its marker. A board of any of the three that cannot be read, the candidate board included, holds every launch the shared fleet cap bounds.
- **arm64 lane.** The arm64 lane is not part of the shared fleet count. A launch onto it is bounded only by the `max_concurrent_runs` that the `homelab-worker-arm64` Fabro server enforces, read under the "Per-server limit" bullet that each-gmktec-fabro-server-s-2 (PR #5101) adds. No `fleet-launch/` file holds a separate arm64 cap. An arm64 limit or count that cannot be read holds every arm64 launch and nothing else. No committed launcher routes onto the arm64 lane yet. The landed text says so, and names the launcher cutover recorded under bd-ib-4xqmqh as the owner of that route.
- **Interim copies match the committed sources.** Until the cutover, each launcher script or helper the seat runs from outside `fleet-launch/` (an *interim copy*) differs from its committed source only in differences that `fleet-launch/README.md` lists, each with its reason. An interim copy with no committed source is listed too. Seat-local values become host values in `fleet-launch/config.sh` or listed differences.
- **Committed helpers.** The impl launcher recomputes the counted-claims count for its WIP gate through `fleet-launch/wip-claimed-count.py`, which writes the shared claim-count cache. A helper failure makes the count unreadable, and the launcher never reuses a cached read older than the cache's time-to-live in its place. The resume launcher starts each resume through `fleet-launch/resume-repo.sh`. No committed launcher runs a script from an uncommitted path.
- **Retired-factory case dropped.** The shared fleet count now names its three instances, so no launcher reads a retired factory's board. The `check-fleet-launch` case "counting a retired factory's board as zero rather than as unknown" is removed, and Scenario 242 drops it.

The `check-fleet-launch` harness gains cases for the candidate-lane sum, an unreadable candidate board, the marker rule, the arm64 exclusion and both helpers, each asserting launch outcomes rather than an internal count. Scenario 242 drops the retired-factory steps. Scenario 307 gains eleven Gherkin scenarios, two of them owed with the arm64 route. No H2 heading is added, renamed or removed, so `tests/heading-coverage.json` is unchanged.

### Motivation

Work item bd-ib-yax6gv, "The committed fleet-launch/ launcher scripts have diverged from the copies the running launchers execute, so a launcher started from the committed files counts the fleet without the candidate lane". Its filing-time spec-change-tier comment (spec v366) names this section as the generalization target and `the-committed-fleet-launch-launcher` as the linked topic. The rationale: the section does not say which lanes the shared fleet count sums, and does not require parity between running copies and committed sources, helpers for the WIP count and resume start, or a README list of deliberate omissions.

The item's Definition of Done references Scenario 307 and asserts:

1. A launcher started from the committed `fleet-launch/dispatch-dual.sh` counts the shared fleet as the listed runs of the gmktec, hl and candidate lanes plus the unlisted launch markers, and leaves the arm64 lane out of that sum.
2. Such a launcher, whose fleet count reaches the fleet cap only because of candidate-lane runs, launches nothing and keeps its queue ticket.
3. The committed `dispatch-dual.sh` reads the claimed-WIP count it gates a launch on through a helper committed under `fleet-launch/`.
4. The committed `resume-capped.sh` starts each resume through a helper committed under `fleet-launch/`.
5. `fleet-launch/README.md` lists every behaviour the running launcher copies carry that the committed launchers deliberately omit, each with its reason.
6. (Host-captured.) On the dispatching host, a diff of each running launcher script under `tmp/petri-canary/` against its committed source at the merge commit shows no difference other than the ones the README lists with a reason.

Measured by legacy-dispatcher-agent at about 08:0xZ on 2026-11-13. The structural finding came from kubernetes-sandbox-backend in livespec-dev-tooling#4476, relayed by legacy-coordinator-agent. Re-read for this proposal on the dispatching host against origin/master `ac149c49d`:

- `tmp/petri-canary/dispatch-dual-r681b.sh` line 262 computes `fleet=$(( hp_live + gmk_live + vps_live + hl_live + cand_live + markers ))`. `hp_live` and `vps_live` are fixed at 0 for the retired factories. Lines 238-239 and 259-263 leave arm64 markers and runs out of that sum, and check them against `ARM_CAP` (1) instead. An `ONLY_ARM` launcher gates on that cap alone, not on the fleet cap (line 670). Line 239 skips a marker from the fleet sum only when it carries `factory=homelab-worker-arm64`, so every other marker counts.
- The committed `fleet-launch/dispatch-dual.sh` line 284 computes `fleet=$(( gmk_live + hl_live + markers ))`. It never reads the candidate board for the fleet count. Its marker records `factory=$1`, the factory its bind is for (line 296).
- 30 live launcher processes run `tmp/petri-canary/dispatch-dual-r681b.sh`, and none runs the committed file.
- The running copies diverge from their committed sources (counted as changed lines in `diff`): `dispatch-dual-r681b.sh` by 1298 changed lines, `resume-capped.sh` by 379 and `ready-set-check.py` by 97. `wip-claimed-count.py` (112 lines), `resume-repo.sh` (16 lines) and `chain-opd3hq-after-close.sh` (15 lines, a one-off chain script) have no committed counterpart. The running `wip-claimed-count.py` implements the section's capacity-projection read and shared claim-count cache. The running `resume-repo.sh` starts `dispatcher.py resume` under the target's `tenant_wrap`. It sources that function from the interim launcher and reads a factory token over ssh.
- The committed harness `fleet-launch/test/run-tests.sh` carries case 5, "counts a retired factory's board as zero, not as unknown" (line 858). `fleet-launch/config.sh` line 25 says the retired factories "are never read".

With every lane at its configured budget, the per-lane budgets sum to 19 against a fleet cap of 18. A launcher restarted from the committed file would leave the candidate lane outside the cap and break the budget sum. Until this lands, every launcher restart has to use the r681b copy.

Design choices, stated for the grade:
- **The lanes are named by factory instance, not by script variable.** "gmk", "hl" and "cand" in the scripts are the gmktec default instance, the mi-homelab instance and the candidate instance the "gmktec target and candidate cap" bullet already names. The retired hp-xubuntu and vps factories are not in the sum. That is already a README-recorded deliberate difference.
- **Markers count by exclusion, not by inclusion.** The running copy skips a marker only when it names the arm64 lane, and counts every other one. This proposal states that rule: a marker counts unless it names `homelab-worker-arm64`. A marker that names no instance, or one this section does not name, still counts. Over-counting holds a launch for one poll, while under-counting lets the fleet pass its cap. The rule needs every launcher to write its real target into its marker, so a candidate launch's marker names the candidate instance and an arm64 launch's marker names the arm64 lane. #5101's per-server count reads the same field.
- **An unreadable candidate board holds every launch the shared fleet cap bounds.** The candidate instance is one of the three boards the shared fleet count sums, so a failed candidate read makes the count unreadable, whatever the launcher's own target. The landed text says so in words, so that a default-target or mi-homelab launcher cannot treat the candidate board as someone else's lane.
- **The arm64 lane has no cap copy of its own.** The running copy hard-codes `ARM_CAP=1`. This proposal adds no such value. A launch onto the arm64 lane is bounded by the `max_concurrent_runs` the `homelab-worker-arm64` Fabro server enforces, read under #5101's "Per-server limit" bullet. That bullet counts the gmktec Fabro servers a launcher "launches onto or counts", and #5101's fleet scope names `homelab-worker-arm64` once a committed launcher routes to it. Its runtime fleet cap sums only the servers the shared fleet count counts, so it leaves the arm64 limit out too. Because this text cites that bullet, this proposal MUST be revised in the same revise pass as each-gmktec-fabro-server-s-2 or after it.
- **The arm64 lane fails closed, and only the arm64 lane.** The running copy makes the whole fleet count unknown when the arm64 board cannot be read (line 257), so a one-slot lane can hold every amd64 launch. The lane is outside the sum, so this proposal holds only arm64 launches when the arm64 limit or count cannot be read. The README lists the running copy's wider hold as a deliberate difference until the interim copy matches.
- **The arm64 route is deferred, with a named owner.** The cutover paragraph already requires the committed launchers to carry the arm64 route and fleet count before the cutover. The launcher cutover recorded under bd-ib-4xqmqh therefore owns the route. The landed text says that, says no committed launcher launches onto the arm64 lane until then, and makes the README list the missing route with that owner. The arm64 exclusion from the shared fleet count binds from ratification, because interim launchers already write arm64 markers into the shared in-flight directory.
- **Observables are launch outcomes.** The scenarios and harness cases assert what a launcher does, launching or holding with its ticket kept, and the files it leaves. They never assert a count the launcher holds internally. Each scenario's numbers are chosen so that the wrong sum flips the outcome. In Scenario "Candidate-lane runs count toward the shared fleet cap", a count without the candidate lane reads 1 against a cap of 4 and would launch. This proposal adds no log contract.
- **The helpers are named after their interim counterparts.** `fleet-launch/wip-claimed-count.py` and `fleet-launch/resume-repo.sh` are named so that the host-captured diff compares file to file. Every rule this section already places on a `fleet-launch/` script applies to them, the banner and the `FLEET_LAUNCH_` host-value rule included.
- **The WIP helper runs only on a cache miss, and its failure is an unreadable count.** The "Shared WIP claim-count cache" bullet says a launcher MUST read the cache file before it spawns any process to compute the count. So the launcher reads a fresh cached read itself and runs `fleet-launch/wip-claimed-count.py` only to recompute. The helper writes the cache file the launcher reads, so every count the gate compares comes from the helper. When the helper fails, the count is unreadable under that bullet's existing rule. The launcher MUST NOT fall back on a cached read older than the time-to-live, because a stale count is exactly the read that the time-to-live exists to refuse. The running copy spawns the helper on every poll and lets it read the cache. Under this proposal that becomes a listed difference or goes away when the seat adopts the committed launcher.
- **The retired-factory case is dropped.** The shared fleet count names exactly three instances, and `fleet-launch/config.sh` never reads a retired factory. The case "counting a retired factory's board as zero rather than as unknown" therefore tests a reader no rule requires. The implementation removes harness case 5 with it. Scenario 242's failing-check example moves to the candidate-lane defect this item measured.
- **Parity binds the seat before the cutover.** The existing cutover paragraph lets the interim launcher run until the cutover and forbids uncommitted copies only after it. This proposal keeps that order. It requires, from ratification, that every way an interim copy differs from its committed source be written down with a reason. The cutover then swaps like for like.

In-flight survey, 2026-11-13 about 08:05Z, re-checked for this revision against origin/master `61a5326a3`. Scope: the in-tree proposals, the 37 remote `spec/*` branches (fetched), and the open pull requests. The items that touch §"Provisional fleet launch scripts", Scenario 242 or Scenario 307:
- the-fleet-launcher-serializes-each (bd-ib-kzmihk, #5126, merged as a proposal, in-tree): it moves the pre-dispatch checks ahead of the queue head and re-reads the fleet cap and factory capacity under the mutex. It covers the candidate and mi-homelab lanes. It reads "the shared fleet count" and never says what it sums. This proposal supplies that sum without editing #5126's text. Relation: `align`, in either revise order.
- check-fleet-launch-sub-case (bd-ib-fokcuo, #5127, merged as a proposal, in-tree): the harness decides each wait by the launcher's observed state. The harness cases added here are ordinary launcher waits and follow that rule once it is ratified. Relation: `align`.
- the-fleet-launcher-reports-a (bd-ib-joyvut, #5128, merged as a proposal, in-tree): a run counts as never listed only from a board read taken after the drive exits. That decides when a marker stops being unlisted, and this proposal only says which markers the shared fleet count includes. Relation: `align`.
- bd-ib-4xqmqh (pending approval): its proposals the-committed-fleet-launcher-lacks and -2 landed in v337 and added the gate bullets and the cutover paragraph. Its implementation converges the named gates on the committed launcher, and its cutover owns the arm64 route this proposal defers to it. This proposal extends the cutover paragraph with the parity list and does not change the gates. Both implementations land in `fleet-launch/dispatch-dual.sh`, so whichever lands second rebases on the first. Neither changes the other's Definition of Done. Relation: `align`.
- each-gmktec-fabro-server-s-2 (bd-ib-rtzhfc, #5101, merged as a proposal, in-tree): it reads every gmktec Fabro server's limit from its rendered `max_concurrent_runs`, retires every cap value in `fleet-launch/config.sh`, and makes the runtime fleet cap "the sum of the limits of the servers the shared fleet count counts", today petri, candidate and mi-homelab. That is the set this proposal names. This proposal binds the arm64 lane to the same per-server limit instead of adding a cap of its own, so no cap copy survives either proposal. #5101's per-server count also reads the marker's instance, which this proposal requires to be the real target. #5101 edits Scenario 242's "host values are declared once and overridable" scenario, and this proposal edits the other two scenarios of that block, so no step overlaps. Relation: `align`. Revise order: same pass as #5101 or after it, because this text cites its "Per-server limit" bullet.
- a-fleet-launcher-holds-its (bd-ib-4vwaty, #5088, in-tree): it skips `master-ci-wait=1` markers from the shared fleet count. The marker term here counts "only the markers the shared fleet count includes under the other rules of this section", so that skip still applies. Relation: `align`.
- the-launcher-holds-one-wip-number (bd-ib-5k2yq2, in-tree): its preamble says the interim launcher is outside this section until the cutover, "so the seat that runs it changes it by hand". Under this proposal that change lands in the committed launcher, and the seat adopts it or lists the difference. Its proposed contract text is unchanged. Relation: `align`.
- a-committed-single-item-operator (bd-ib-fc6da3, #5120, draft): it replaces the parenthetical "(impl through `dispatch-dual.sh`, resume through `resume-capped.sh`)" in the cutover paragraph. This proposal only appends after that paragraph's last sentence. Its override reads the shared fleet count "as an impl launcher reads it", so the lane sum governs it, and its committed `override-item.sh` falls under the parity rule like any committed launcher. Relation: `align`, in either revise order.
- a-fleet-launcher-honours-a (bd-ib-aibd3u, in-tree), fleet-launchers-log-and-retry (bd-ib-7itf42, #5073) and concurrent-git-fetches-into-one (bd-ib-zyu2ug, #5072): hold exemptions, non-run exit logging and the fetch lock. None touches the fleet count, the markers' instance, interim copies, the two helpers or the retired-factory case. Relation: `align`.
- The remote branches `spec/codex-floor-reset-proximity`, `spec/red-turn-changes-no-product-file`, `spec/revise-v330-goal-template-opener-modify`, `spec/revise-v364-the-incident-authority-cli-has` and `spec/revise-v366-incident-authority-cli-reply-and-fenced-reads` show this section only because they carry `history/` snapshots. Each has its history directory on master (v266, v278, v330, v364, v366), so each has landed.
No in-flight item is superseded or in conflict.

### Proposed Changes

The edits are in `contracts.md` §"Provisional fleet launch scripts", in the Scenario 242 block of `scenarios.md` and in the existing Scenario 307 block of `scenarios.md`. No H2 heading in either file is added, renamed or removed, so `tests/heading-coverage.json` is unchanged.

**1. Shared fleet count, markers, arm64 lane and committed helpers (`contracts.md`).** Immediately after the paragraph that begins "Every script under `fleet-launch/` MUST open with a banner", insert the following text:

> The *shared fleet count* that every rule of this section compares against the shared fleet cap is the sum of two things:
> - the live runs listed on the factory boards of three instances: the gmktec default instance, the gmktec candidate instance and the mi-homelab instance;
> - every fleet in-flight marker whose run none of those three boards lists yet, except a marker that names the `homelab-worker-arm64` instance, counting only the markers the shared fleet count includes under the other rules of this section.
>
> A marker that names any other instance, an instance this section does not name, or no instance MUST be counted. Every launcher MUST write into its fleet in-flight marker the factory instance its launch is sent to on that gate pass, such as the candidate instance for a launch its gmktec target setting sends there. It MUST NOT write a FIFO class, a placeholder or any other instance in its place.
>
> A launcher MUST count the candidate instance's runs and markers whatever its own gmktec target setting selects, and MUST NOT leave any of the three instances out of the sum. A board read for any of the three that cannot be taken makes the shared fleet count unreadable, and this section already treats an unreadable count as at the cap. In particular, a candidate board that cannot be read MUST hold every launch the shared fleet cap bounds: every impl launch and every resume, onto the default, candidate or mi-homelab instance, whatever the launcher's gmktec target setting selects. No other factory instance is part of the shared fleet count. In particular, the `homelab-worker-arm64` instance (the *arm64 lane*) is not. A launcher MUST NOT add the arm64 lane's listed runs, or the markers that name it, to the shared fleet count. An arm64 board read that cannot be taken MUST NOT make the shared fleet count unreadable.
>
> A launch onto the arm64 lane MUST NOT be held by the shared fleet cap. Its concurrent-run bound in this section is the limit the `homelab-worker-arm64` Fabro server itself enforces, its `max_concurrent_runs`, applied under the "Per-server limit" bullet exactly as that bullet applies every gmktec Fabro server's limit, with that server's count made of its listed live runs and the markers that name it. `fleet-launch/config.sh` MUST NOT assign an arm64 cap, and no `fleet-launch/` script MAY hold any other copy of that number. The arm64 lane fails closed: a limit file that the "Per-server limit" bullet holds on, or an arm64 board read that cannot be taken, MUST hold every launch onto the arm64 lane, and MUST NOT hold any other launch.
>
> The route of a committed launcher onto the arm64 lane is deferred. That route, with the arm64 rules above and their harness cases, is owed by the launcher cutover recorded under bd-ib-4xqmqh, which the paragraph beginning "Until the deletion the next paragraph requires" requires to carry it. Until a committed launcher carries that route, no committed launcher MAY launch onto the arm64 lane, and `fleet-launch/README.md` MUST list the missing route as a deliberate difference that names bd-ib-4xqmqh. The exclusion of the arm64 lane from the shared fleet count applies from ratification, before that route lands.
>
> A committed `fleet-launch/` launcher MUST NOT run any script kept only on the dispatching host outside a committed source tree or a released plugin build, such as a file under `tmp/`. Two helpers in particular MUST be committed under `fleet-launch/` and run from there:
> - **WIP count helper.** Whenever the "Shared WIP claim-count cache" bullet requires the counted-claims count to be recomputed rather than read from a cached read, the impl launcher MUST recompute it by running `fleet-launch/wip-claimed-count.py`. That helper MUST read the count through the capacity projection that the "Repository WIP gate" bullet names, under the per-repository serialization that the "Shared WIP claim-count cache" bullet requires, and MUST write the claim-count cache file that the launcher reads. The launcher MUST NOT compute the counted-claims count any other way. A helper that exits non-zero, or that exits without writing a cache file taken by that recomputation, is a failed recomputation: the counted-claims count is unreadable, and the "Shared WIP claim-count cache" bullet's rule for a failed recomputation applies. The launcher MUST NOT use a cached read older than the time-to-live in its place, and MUST NOT rewrite the cache file for that failed read.
> - **Resume start helper.** The resume launcher MUST start each `resume --item <item>` by running `fleet-launch/resume-repo.sh`. That helper MUST run the resume under the target repository's committed `credential_wrapper`, as the "Tenant credential wrapper" bullet requires. The launcher MUST NOT start a resume any other way.
>
> Each helper is a `fleet-launch/` script under every rule of this section, its banner and its host-value rule included.

**2. Interim copies match their committed sources (`contracts.md`).** In the paragraph that begins "Until the deletion the next paragraph requires", append the following after its final sentence, "A gate the seat needs that the committed launchers lack MUST land in them through this repository's change path before the seat relies on it.", inside the same paragraph:

> An *interim copy* is a launcher script, or a script a launcher runs, that the seat executes on the dispatching host from outside `fleet-launch/`. Until the cutover, each interim copy MUST differ from its committed `fleet-launch/` source only in differences that `fleet-launch/README.md` lists. An interim copy with no committed source, such as a one-off chain script, MUST itself be listed. `fleet-launch/README.md` MUST keep one list of these deliberate differences. Each entry MUST name four things: the interim copy, its committed source or `none`, what differs, and why the committed launchers omit or change it. Some values an interim copy holds belong to one seat or host, such as a hold-file name, an absolute host path or a session id. Each such value MUST either be a host value under this section's host-value rule or be listed. A change the seat makes to an interim copy MUST land through this repository's change path before the seat runs it, either in the committed source or as a list entry.

**3. Harness coverage (`contracts.md`).** Immediately before the paragraph that begins "Until the deletion the next paragraph requires", insert:

> The `check-fleet-launch` harness cases MUST also cover the shared fleet count, the fleet in-flight markers and the committed helpers. Each case MUST assert what the launchers do, launching or holding with their tickets kept, and the files they leave. A case MUST NOT assert a count a launcher holds only internally.
> - Stub boards for the default, candidate and mi-homelab instances, with a shared fleet cap that candidate-lane runs and one unlisted candidate marker bring the shared fleet count up to. An impl launcher targeting the default instance and a resume launcher each launch nothing and keep their tickets. Once a candidate run ends, the impl launcher launches, and the resume launcher, with the impl launcher's marker counted, still launches nothing.
> - A candidate board that cannot be read, with the other two boards readable and well below the shared fleet cap. An impl launcher targeting the default instance, a resume launcher and an impl launcher for the mi-homelab instance each launch nothing and keep their tickets.
> - A stub arm64 board that lists live runs, and an unlisted marker that names `homelab-worker-arm64`, with a shared fleet cap that only counting them would reach. An impl launcher targeting the default instance launches.
> - An arm64 board that cannot be read. An impl launcher targeting the default instance, below the shared fleet cap, launches.
> - One unlisted marker that names no instance and one that names an instance this section does not name, with a shared fleet cap that only counting both would reach. An impl launcher targeting the default instance launches nothing and keeps its ticket.
> - An impl launcher whose gmktec target setting selects the candidate instance, which leaves a fleet in-flight marker that names the candidate instance.
> - The repository WIP gate run through `fleet-launch/wip-claimed-count.py` against a stub capacity projection. The helper writes the claim-count cache file, and the launcher yields on the count it records.
> - The same helper failing while a claim-count cache file older than the time-to-live records a count at `wip_cap`. The launcher does not hold on the repository WIP gate, and the cache file is left unchanged.
> - A resume started through `fleet-launch/resume-repo.sh` under a stub committed `credential_wrapper`.
>
> In the three helper cases the harness MUST stub only what the helper calls, never the helper itself. The arm64 route cases are owed with the route, by the launcher cutover recorded under bd-ib-4xqmqh. Once a committed launcher routes launches onto the arm64 lane, the harness MUST also cover three cases. A launch onto that lane is held at the `homelab-worker-arm64` limit while the shared fleet count is below the shared fleet cap. The same launch goes ahead below that limit while the shared fleet count is at the shared fleet cap. The same launch is held while that server's limit file is absent or its board cannot be read, while an impl launcher targeting the default instance still launches. Scenario 307 in `scenarios.md` exercises these cases.

**4. Retired-factory case dropped (`contracts.md`).** In the paragraph that begins "`just check` MUST run a `check-fleet-launch` target", delete "counting a retired factory's board as zero rather than as unknown; " from its list of cases. The rest of the list is unchanged.

**5. Scenario 242 (`scenarios.md` §"Scenario 242 — The provisional fleet launch check fails the build on a broken launcher").** Two edits, leaving the block's other scenarios unchanged:

- In the scenario "the harness exercises every launch gate against stubs", replace "launches two queued tickets in FIFO order, holds a launch while the hold file exists, and counts a retired factory's board as zero" with "launches two queued tickets in FIFO order, and holds a launch while the hold file exists".
- In the scenario "a defect in a launcher turns the check red", replace "Given a change that makes the launcher count a retired factory's board as unknown" with "Given a change that makes the launcher leave the candidate instance's live runs out of the shared fleet count".

**6. Scenario 307 (`scenarios.md`).** Append the following scenarios to the Gherkin block of "## Scenario 307 — The committed fleet-launch launchers enforce the repository hold, WIP gate, breakage exception, re-ticket, gmktec hold and candidate target". They go after the block's last scenario, whichever scenario is last when this proposal is revised, and before the closing fence. The block's Feature line, Background and existing scenarios are unchanged.

```gherkin
  Scenario: Candidate-lane runs count toward the shared fleet cap
    Given the shared fleet cap is 4
    And the gmktec default instance's board lists 1 live run and the mi-homelab board lists none
    And the candidate instance's board lists 2 live runs
    And one fleet in-flight marker that names the candidate instance, whose run no board lists yet
    And an impl launcher whose gmktec target setting selects the default instance holds the oldest gmktec FIFO ticket, and a resume launcher holds the next
    When the launchers take their gate passes
    Then neither launches, and each keeps its FIFO ticket
    When one of the candidate instance's live runs ends
    Then the impl launcher binds and launches onto the default instance
    And the resume launcher launches nothing and keeps its FIFO ticket

  Scenario: An unreadable candidate board holds every launch the shared fleet cap bounds
    Given the shared fleet cap is 4
    And the gmktec default instance's board lists 1 live run and the mi-homelab board lists none
    And every read of the candidate instance's board fails
    And an impl launcher whose gmktec target setting selects the default instance holds the oldest gmktec FIFO ticket, and a resume launcher holds the next
    And an impl launcher for the mi-homelab instance holds the oldest mi-homelab FIFO ticket
    When the launchers take their gate passes
    Then none of them launches, and each keeps its FIFO ticket
    When a read of the candidate instance's board succeeds and lists no live run
    Then the impl launcher at the head of the gmktec FIFO binds and launches onto the default instance

  Scenario: Every unlisted fleet in-flight marker counts unless it names the arm64 lane
    Given the shared fleet cap is 4
    And the gmktec default instance's board lists 2 live runs and the candidate and mi-homelab boards list none
    And one unlisted fleet in-flight marker that names no factory instance
    And one unlisted fleet in-flight marker that names a factory instance this section does not name
    And one unlisted fleet in-flight marker that names homelab-worker-arm64
    When an impl launcher whose gmktec target setting selects the default instance takes its gate pass
    Then it launches nothing and keeps its FIFO ticket
    When the marker that names no factory instance is removed
    Then the impl launcher binds and launches onto the default instance
    And its fleet in-flight marker names the gmktec default instance

  Scenario: A launcher names the instance it launches onto in its marker
    Given the candidate instance's count is below its limit and the shared fleet count is below the shared fleet cap
    And an impl launcher whose gmktec target setting selects the candidate instance
    When the launcher binds
    Then its fleet in-flight marker names the candidate instance
    And the marker does not name the gmktec default instance

  Scenario: The arm64 lane is not part of the shared fleet count
    Given the shared fleet cap is 4
    And the gmktec default instance's board lists 3 live runs and the candidate and mi-homelab boards list none
    And the homelab-worker-arm64 board lists 1 live run
    And one fleet in-flight marker that names homelab-worker-arm64, whose run no board lists yet
    When an impl launcher whose gmktec target setting selects the default instance takes its gate pass
    Then it binds and launches onto the default instance

  Scenario: An unreadable arm64 board leaves the shared fleet count readable
    Given the shared fleet cap is 4
    And the gmktec default instance's board lists 1 live run and the candidate and mi-homelab boards list none
    And every read of the homelab-worker-arm64 board fails
    When an impl launcher whose gmktec target setting selects the default instance takes its gate pass
    Then it binds and launches onto the default instance

  Scenario: A launch onto the arm64 lane is bounded by homelab-worker-arm64's own limit, not the shared fleet cap
    Given the shared fleet cap is 4
    And the homelab-worker-arm64.max_concurrent_runs file holds 1
    And a committed launcher whose launch is routed onto the arm64 lane
    When the homelab-worker-arm64 board lists 1 live run, the gmktec default instance's board lists 1 live run, the candidate and mi-homelab boards list none, and no fleet in-flight marker is unlisted
    Then the launcher launches nothing onto the arm64 lane and keeps its FIFO ticket
    When the homelab-worker-arm64 board lists no live run and the gmktec default instance's board lists 4 live runs
    Then the launcher binds and launches onto the arm64 lane
    And its fleet in-flight marker names homelab-worker-arm64

  Scenario: The arm64 lane fails closed and holds nothing else
    Given the shared fleet cap is 4
    And the gmktec default instance's board lists 1 live run and the candidate and mi-homelab boards list none
    And a committed launcher whose launch is routed onto the arm64 lane, and an impl launcher whose gmktec target setting selects the default instance
    When the homelab-worker-arm64.max_concurrent_runs file is absent
    Then the arm64 launcher launches nothing and keeps its FIFO ticket
    And the impl launcher binds and launches onto the default instance
    When the homelab-worker-arm64.max_concurrent_runs file holds 1 and every read of the homelab-worker-arm64 board fails
    Then the arm64 launcher launches nothing and keeps its FIFO ticket

  Scenario: The WIP gate recomputes its count through the committed helper
    Given the target repository's wip_cap is 2
    And no cached claim count for that repository
    And a stub capacity projection that reports a counted-claims count of 2
    When an impl launcher for that repository reaches its repository WIP gate
    Then the stub capacity projection is read once, by fleet-launch/wip-claimed-count.py run from the launcher's checkout
    And the claim-count cache file for that repository records a count of 2
    And the launcher keeps its FIFO ticket, yields the FIFO head and does not run its launch-time preflight

  Scenario: A failed WIP helper leaves the count unreadable and reuses no stale cached read
    Given the target repository's wip_cap is 2
    And a claim-count cache file for that repository that records a count of 2 and is older than the cache's time-to-live
    And a stub capacity projection whose every read fails, so fleet-launch/wip-claimed-count.py exits non-zero
    When an impl launcher for that repository reaches its repository WIP gate
    Then the launcher does not hold on the repository WIP gate and goes on to its launch-time preflight
    And the claim-count cache file is unchanged

  Scenario: A resume starts through the committed resume helper
    Given a stub target repository whose .livespec.jsonc names a stub credential_wrapper
    And a resume launcher for that repository at the head of the FIFO, with the shared fleet count below the shared fleet cap
    When the launcher starts the resume
    Then it runs fleet-launch/resume-repo.sh from its checkout
    And the stub resume command receives --item with the launcher's work item under the stub credential_wrapper
```

The scenarios "A launch onto the arm64 lane is bounded by homelab-worker-arm64's own limit, not the shared fleet cap" and "The arm64 lane fails closed and holds nothing else" run in the harness only once a committed launcher routes launches onto the arm64 lane. The launcher cutover recorded under bd-ib-4xqmqh owes that route and those cases, per change 1 and change 3. Until then, `fleet-launch/README.md` lists the arm64 route as a deliberate difference under change 2.
