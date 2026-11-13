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

§"Provisional fleet launch scripts" says a launcher refuses at the shared fleet cap, keeps its ticket and counts in-flight markers. It never says which factory instances the shared fleet count sums. It also lets the seat's interim launcher copies drift from the committed sources with nothing recording how they differ. The committed `fleet-launch/dispatch-dual.sh` sums gmktec, mi-homelab and markers. The copy every running launcher executes, `tmp/petri-canary/dispatch-dual-r681b.sh`, also sums the candidate instance and leaves the arm64 lane out. A launcher restarted from the committed file would therefore put candidate runs outside the fleet cap. This proposal makes three changes:

- **Shared fleet count.** The section defines the shared fleet count. It is the live runs listed on the boards of the gmktec default instance, the candidate instance and the mi-homelab instance, plus the unlisted fleet in-flight markers of launches onto those three. The `homelab-worker-arm64` instance (the *arm64 lane*) is not part of it. A launch onto the arm64 lane is bounded by that lane's own per-factory cap and not by the shared fleet cap.
- **Interim copies match the committed sources.** Until the cutover, each launcher script or helper the seat runs from outside `fleet-launch/` (an *interim copy*) differs from its committed source only in differences that `fleet-launch/README.md` lists, each with its reason. An interim copy with no committed source is listed too. Seat-local values become host values in `fleet-launch/config.sh` or listed differences.
- **Committed helpers.** The impl launcher recomputes the counted-claims count for its WIP gate through `fleet-launch/wip-claimed-count.py`, which writes the shared claim-count cache. The resume launcher starts each resume through `fleet-launch/resume-repo.sh`. No committed launcher runs a script from an uncommitted path.

The `check-fleet-launch` harness gains cases for the candidate-lane sum, the arm64 exclusion and both helpers. Scenario 307 gains six Gherkin scenarios. No H2 heading is added, renamed or removed, so `tests/heading-coverage.json` is unchanged.

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

- `tmp/petri-canary/dispatch-dual-r681b.sh` line 262 computes `fleet=$(( hp_live + gmk_live + vps_live + hl_live + cand_live + markers ))`. `hp_live` and `vps_live` are fixed at 0 for the retired factories. Lines 238-239 and 259-263 leave arm64 markers and runs out of that sum, and check them against `ARM_CAP` (1) instead. An `ONLY_ARM` launcher gates on that cap alone, not on the fleet cap (line 670).
- The committed `fleet-launch/dispatch-dual.sh` line 284 computes `fleet=$(( gmk_live + hl_live + markers ))`. It never reads the candidate board for the fleet count.
- 30 live launcher processes run `tmp/petri-canary/dispatch-dual-r681b.sh`, and none runs the committed file.
- The running copies diverge from their committed sources (counted as changed lines in `diff`): `dispatch-dual-r681b.sh` by 1298 changed lines, `resume-capped.sh` by 379 and `ready-set-check.py` by 97. `wip-claimed-count.py` (112 lines), `resume-repo.sh` (16 lines) and `chain-opd3hq-after-close.sh` (15 lines, a one-off chain script) have no committed counterpart. The running `wip-claimed-count.py` implements the section's capacity-projection read and shared claim-count cache. The running `resume-repo.sh` starts `dispatcher.py resume` under the target's `tenant_wrap`. It sources that function from the interim launcher and reads a factory token over ssh.

With every lane at its configured budget, the per-lane budgets sum to 19 against a fleet cap of 18. A launcher restarted from the committed file would leave the candidate lane outside the cap and break the budget sum. Until this lands, every launcher restart has to use the r681b copy.

Design choices, stated for the grade:
- **The lanes are named by factory instance, not by script variable.** "gmk", "hl" and "cand" in the scripts are the gmktec default instance, the mi-homelab instance and the candidate instance the "gmktec target and candidate cap" bullet already names. The retired hp-xubuntu and vps factories are not in the sum. That is already a README-recorded deliberate difference.
- **The arm64 lane has its own cap, named as a per-factory cap.** That way each-gmktec-fabro-server-s-2 (bd-ib-rtzhfc), if ratified, maps it onto `homelab-worker-arm64`'s own `max_concurrent_runs` through that proposal's sentence "Where this section names a per-factory cap, it means that server's limit". No text in either proposal has to change.
- **The arm64 board's readability does not touch the shared fleet count.** The running copy makes the whole fleet count unknown when the arm64 board cannot be read (line 257), so a one-slot lane can hold every amd64 launch. The lane is outside the sum, so this proposal holds only arm64 launches on an unreadable arm64 count. The README lists this as a deliberate difference until the interim copy matches.
- **Routing onto the arm64 lane stays as the section already has it.** The cutover paragraph already requires the committed launchers to carry the arm64 route and fleet count before the cutover. This proposal states how that lane is counted and capped. Until a committed launcher routes it, the README lists the arm64 route as a deliberate omission. The harness case for the arm64 cap is owed from the change that adds the route.
- **The helpers are named after their interim counterparts.** `fleet-launch/wip-claimed-count.py` and `fleet-launch/resume-repo.sh` are named so that the host-captured diff compares file to file. Every rule this section already places on a `fleet-launch/` script applies to them, the banner and the `FLEET_LAUNCH_` host-value rule included.
- **The WIP helper runs only on a cache miss.** The "Shared WIP claim-count cache" bullet says a launcher MUST read the cache file before it spawns any process to compute the count. So the launcher reads a fresh cached read itself and runs `fleet-launch/wip-claimed-count.py` only to recompute. The helper writes the cache file the launcher reads, so every count the gate compares comes from the helper. The running copy spawns the helper on every poll and lets it read the cache. Under this proposal that becomes a listed difference or goes away when the seat adopts the committed launcher.
- **Parity binds the seat before the cutover.** The existing cutover paragraph lets the interim launcher run until the cutover and forbids uncommitted copies only after it. This proposal keeps that order. It requires, from ratification, that every way an interim copy differs from its committed source be written down with a reason. The cutover then swaps like for like.

In-flight survey, 2026-11-13 about 08:05Z. Scope: the in-tree proposals on origin/master `ac149c49d`, the 37 remote `spec/*` branches (fetched), and the open pull requests. The items that touch §"Provisional fleet launch scripts" or Scenario 307:
- the-fleet-launcher-serializes-each (bd-ib-kzmihk, #5126, merged as a proposal, in-tree): it moves the pre-dispatch checks ahead of the queue head and re-reads the fleet cap and factory capacity under the mutex. It covers the candidate and mi-homelab lanes. It reads "the shared fleet count" and never says what it sums. This proposal supplies that sum without editing #5126's text. Relation: `align`, in either revise order.
- check-fleet-launch-sub-case (bd-ib-fokcuo, #5127, merged as a proposal, in-tree): the harness decides each wait by the launcher's observed state. The harness cases added here are ordinary launcher waits and follow that rule once it is ratified. Relation: `align`.
- the-fleet-launcher-reports-a (bd-ib-joyvut, #5128, merged as a proposal, in-tree): a run counts as never listed only from a board read taken after the drive exits. That decides when a marker stops being unlisted, and this proposal only says which markers the shared fleet count includes. Relation: `align`.
- bd-ib-4xqmqh (pending approval): its proposals the-committed-fleet-launcher-lacks and -2 landed in v337 and added the gate bullets and the cutover paragraph. Its implementation converges the named gates on the committed launcher. This proposal extends the cutover paragraph with the parity list and does not change the gates. Both implementations land in `fleet-launch/dispatch-dual.sh`, so whichever lands second rebases on the first. Neither changes the other's Definition of Done. Relation: `align`.
- each-gmktec-fabro-server-s-2 (bd-ib-rtzhfc, #5101, in-tree): it makes the runtime fleet cap "the sum of the limits of the servers the shared fleet count counts", today petri, candidate and mi-homelab. That is the set this proposal names. Its "committed-cap count" is built on the shared fleet count, so it excludes the arm64 lane too. That matches the running copy's note that arm64 runs on the M4's own pod budget. Relation: `align`.
- a-fleet-launcher-holds-its (bd-ib-4vwaty, #5088, in-tree): it skips `master-ci-wait=1` markers from the shared fleet count. The marker term here is "the fleet in-flight markers that the shared fleet count includes under the other rules of this section", so that skip still applies. Relation: `align`.
- the-launcher-holds-one-wip-number (bd-ib-5k2yq2, in-tree): its preamble says the interim launcher is outside this section until the cutover, "so the seat that runs it changes it by hand". Under this proposal that change lands in the committed launcher, and the seat adopts it or lists the difference. Its proposed contract text is unchanged. Relation: `align`.
- a-committed-single-item-operator (bd-ib-fc6da3, #5120, draft): it replaces the parenthetical "(impl through `dispatch-dual.sh`, resume through `resume-capped.sh`)" in the cutover paragraph. This proposal only appends after that paragraph's last sentence. Its override reads the shared fleet count "as an impl launcher reads it", so the lane sum governs it, and its committed `override-item.sh` falls under the parity rule like any committed launcher. Relation: `align`, in either revise order.
- a-fleet-launcher-honours-a (bd-ib-aibd3u, in-tree), fleet-launchers-log-and-retry (bd-ib-7itf42, #5073) and concurrent-git-fetches-into-one (bd-ib-zyu2ug, #5072): hold exemptions, non-run exit logging and the fetch lock. None touches the fleet count, interim copies or the two helpers. Relation: `align`.
- The remote branches `spec/codex-floor-reset-proximity`, `spec/red-turn-changes-no-product-file`, `spec/revise-v330-goal-template-opener-modify`, `spec/revise-v364-the-incident-authority-cli-has` and `spec/revise-v366-incident-authority-cli-reply-and-fenced-reads` show this section only because they carry `history/` snapshots. Each has its history directory on master (v266, v278, v330, v364, v366), so each has landed.
No in-flight item is superseded or in conflict.

### Proposed Changes

The edits are in `contracts.md` §"Provisional fleet launch scripts" and in the existing Scenario 307 block of `scenarios.md`. No H2 heading in either file is added, renamed or removed, so `tests/heading-coverage.json` is unchanged.

**1. Shared fleet count, arm64 lane and committed helpers (`contracts.md`).** Immediately after the paragraph that begins "Every script under `fleet-launch/` MUST open with a banner", insert the following text:

> The *shared fleet count* that every rule of this section compares against the shared fleet cap is the sum of two things:
> - the live runs listed on the factory boards of three instances: the gmktec default instance, the gmktec candidate instance and the mi-homelab instance;
> - the fleet in-flight markers of launches onto those three instances whose runs none of those boards lists yet, counting only the markers the shared fleet count includes under the other rules of this section.
>
> A launcher MUST count the candidate instance's runs and markers whatever its own gmktec target setting selects, and MUST NOT leave any of the three instances out of the sum. A board read for any of the three that cannot be taken makes the shared fleet count unreadable, and this section already treats an unreadable count as at the cap. No other factory instance is part of the shared fleet count. In particular, the `homelab-worker-arm64` instance (the *arm64 lane*) is not. A launcher MUST NOT add the arm64 lane's listed runs, or the markers of launches onto it, to the shared fleet count. An arm64 board read that cannot be taken MUST NOT make the shared fleet count unreadable.
>
> A launch onto the arm64 lane MUST be bounded by the arm64 lane's own per-factory cap, a host value assigned in `fleet-launch/config.sh` and overridable like any other. The shared fleet cap MUST NOT hold it. The *arm64 count* is the arm64 lane's listed live runs plus the fleet in-flight markers of launches onto it whose runs it does not list yet. A launcher MUST launch onto the arm64 lane only while the arm64 count is below that cap. At the binding re-count under the factory mutex, with its own marker counted, it MUST proceed only while the arm64 count is at or below that cap. An arm64 count that cannot be read MUST hold every launch onto the arm64 lane, and MUST NOT hold any other launch.
>
> A committed `fleet-launch/` launcher MUST NOT run any script kept only on the dispatching host outside a committed source tree or a released plugin build, such as a file under `tmp/`. Two helpers in particular MUST be committed under `fleet-launch/` and run from there:
> - **WIP count helper.** Whenever the "Shared WIP claim-count cache" bullet requires the counted-claims count to be recomputed rather than read from a cached read, the impl launcher MUST recompute it by running `fleet-launch/wip-claimed-count.py`. That helper MUST read the count through the capacity projection that the "Repository WIP gate" bullet names, under the per-repository serialization that the "Shared WIP claim-count cache" bullet requires, and MUST write the claim-count cache file that the launcher reads. The launcher MUST NOT compute the counted-claims count any other way.
> - **Resume start helper.** The resume launcher MUST start each `resume --item <item>` by running `fleet-launch/resume-repo.sh`. That helper MUST run the resume under the target repository's committed `credential_wrapper`, as the "Tenant credential wrapper" bullet requires. The launcher MUST NOT start a resume any other way.
>
> Each helper is a `fleet-launch/` script under every rule of this section, its banner and its host-value rule included.

**2. Interim copies match their committed sources (`contracts.md`).** In the paragraph that begins "Until the deletion the next paragraph requires", append the following after its final sentence, "A gate the seat needs that the committed launchers lack MUST land in them through this repository's change path before the seat relies on it.", inside the same paragraph:

> An *interim copy* is a launcher script, or a script a launcher runs, that the seat executes on the dispatching host from outside `fleet-launch/`. Until the cutover, each interim copy MUST differ from its committed `fleet-launch/` source only in differences that `fleet-launch/README.md` lists. An interim copy with no committed source, such as a one-off chain script, MUST itself be listed. `fleet-launch/README.md` MUST keep one list of these deliberate differences. Each entry MUST name four things: the interim copy, its committed source or `none`, what differs, and why the committed launchers omit or change it. Some values an interim copy holds belong to one seat or host, such as a hold-file name, an absolute host path or a session id. Each such value MUST either be a host value under this section's host-value rule or be listed. A change the seat makes to an interim copy MUST land through this repository's change path before the seat runs it, either in the committed source or as a list entry.

**3. Harness coverage (`contracts.md`).** Immediately before the paragraph that begins "Until the deletion the next paragraph requires", insert:

> The `check-fleet-launch` harness cases MUST also cover the shared fleet count and the committed helpers:
> - Stub boards for the default, candidate and mi-homelab instances, with a shared fleet cap that candidate-lane runs and one unlisted candidate marker bring the shared fleet count up to. An impl launcher targeting the default instance and a resume launcher each launch nothing and keep their tickets. The impl launcher launches once a candidate run ends.
> - A stub arm64 board that lists live runs, plus a fleet in-flight marker of a launch onto the arm64 lane. The shared fleet count includes neither.
> - An arm64 board that cannot be read, which leaves the shared fleet count readable.
> - The repository WIP gate run through `fleet-launch/wip-claimed-count.py` against a stub capacity projection.
> - A resume started through `fleet-launch/resume-repo.sh` under a stub committed `credential_wrapper`.
>
> In the last two cases the harness MUST stub only what the helper calls, never the helper itself. Once a committed launcher routes launches onto the arm64 lane, the harness MUST also cover two cases. A launch onto that lane is held at the lane's per-factory cap while the shared fleet count is below the shared fleet cap. The same launch goes ahead below that per-factory cap while the shared fleet count is at the shared fleet cap. Scenario 307 in `scenarios.md` exercises these cases.

**4. Scenario 307 (`scenarios.md`).** Append the following scenarios to the Gherkin block of "## Scenario 307 — The committed fleet-launch launchers enforce the repository hold, WIP gate, breakage exception, re-ticket, gmktec hold and candidate target". They go after the block's last scenario, whichever scenario is last when this proposal is revised, and before the closing fence. The block's Feature line, Background and existing scenarios are unchanged.

```gherkin
  Scenario: Candidate-lane runs count toward the shared fleet cap
    Given the shared fleet cap is 4
    And the gmktec default instance's board lists 1 live run and the mi-homelab board lists none
    And the candidate instance's board lists 2 live runs
    And one fleet in-flight marker of a launch onto the candidate instance whose run no board lists yet
    And an impl launcher whose gmktec target setting selects the default instance holds the oldest gmktec FIFO ticket, and a resume launcher holds the next
    When the launchers read the shared fleet count
    Then each reads 4
    And each launches nothing and keeps its FIFO ticket
    When one of the candidate instance's live runs ends
    Then the impl launcher binds and launches onto the default instance
    And the resume launcher, whose shared fleet count now includes the impl launcher's marker, launches nothing and keeps its FIFO ticket

  Scenario: The arm64 lane is not part of the shared fleet count
    Given the shared fleet cap is 4
    And the gmktec default instance's board lists 3 live runs and the candidate and mi-homelab boards list none
    And the homelab-worker-arm64 board lists 1 live run
    And one fleet in-flight marker of a launch onto the arm64 lane whose run no board lists yet
    When an impl launcher whose gmktec target setting selects the default instance reads the shared fleet count
    Then it reads 3
    And it binds and launches onto the default instance

  Scenario: An unreadable arm64 board leaves the shared fleet count readable
    Given the shared fleet cap is 4
    And the gmktec default instance's board lists 1 live run and the candidate and mi-homelab boards list none
    And every read of the homelab-worker-arm64 board fails
    When an impl launcher whose gmktec target setting selects the default instance reads the shared fleet count
    Then it reads 1
    And it binds and launches onto the default instance

  Scenario: A launch onto the arm64 lane is bounded by its own cap, not the shared fleet cap
    Given the arm64 lane's per-factory cap is 1
    And a committed launcher whose launch is routed onto the arm64 lane
    When the homelab-worker-arm64 board lists 1 live run and the shared fleet count is below the shared fleet cap
    Then the launcher launches nothing onto the arm64 lane and keeps its FIFO ticket
    When the homelab-worker-arm64 board lists no live run and the shared fleet count equals the shared fleet cap
    Then the launcher binds and launches onto the arm64 lane

  Scenario: The WIP gate recomputes its count through the committed helper
    Given no cached claim count for the target repository
    And a stub capacity projection that reports a counted-claims count equal to the target repository's wip_cap
    When an impl launcher for that repository runs
    Then it recomputes the count by running fleet-launch/wip-claimed-count.py from its checkout
    And the claim-count cache file for that repository records that count
    And the launcher keeps its FIFO ticket, yields the FIFO head and does not run its launch-time preflight

  Scenario: A resume starts through the committed resume helper
    Given a stub target repository whose .livespec.jsonc names a stub credential_wrapper
    And a resume launcher for that repository at the head of the FIFO, with the shared fleet count below the shared fleet cap
    When the launcher starts the resume
    Then it runs fleet-launch/resume-repo.sh from its checkout
    And the stub resume command receives --item with the launcher's work item under the stub credential_wrapper
```

The fourth scenario above runs in the harness only once a committed launcher routes launches onto the arm64 lane, per change 3. Until then, `fleet-launch/README.md` lists the arm64 route as a deliberate difference under change 2.
