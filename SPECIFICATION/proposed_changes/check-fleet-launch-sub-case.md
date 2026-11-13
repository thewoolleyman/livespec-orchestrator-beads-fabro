---
topic: check-fleet-launch-sub-case
author: claude-opus-5-5
created_at: 2026-11-13T05:02:54Z
---

## Proposal: The check-fleet-launch harness decides each launcher wait by the launcher's observed state, names why a wait gave up, and proves a slow start by advancing its clock only after the wait arms

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Provisional fleet launch scripts" requires a hermetic `check-fleet-launch` harness and lists the cases it must cover, including holds re-read until admission (Scenario 330). It says nothing about how the harness waits on a launcher it started. That gap let a harness case pass without proving what it claims: sub-case 20f proves that a slow launcher start passes the case-20 wait by putting the waits' clock 15 seconds past launcher start, but the wait can compute its deadline after that clock advance, absorb it, and pass without ever observing more than 10 seconds elapsed. This proposal adds three rules to the harness paragraphs of the section:

- **Launcher waits are decided by observed state.** A harness wait for a launcher to reach a state passes when the state holds and fails on its first poll after it observes the launcher has exited, without waiting for its hang guard. Its only time bound is a hang guard no shorter than the `FLEET_LAUNCH_MAX_WAIT_S` value the awaited launcher runs with. It is never bounded by a shorter fixed wall-clock interval measured from launcher start, unless that bound cannot race the launcher's start-up.
- **A wait that gives up says why.** The case's failure message names the reason (the launcher exited first, or the hang guard elapsed) and the last launcher log line, and a test drives that failure path and asserts both appear.
- **A slow-start proof advances its clock only after the wait arms.** A case that advances the waits' clock to prove a slow start does so only after the wait has computed its deadline. A run in which the wait computed its deadline with the advance already in effect fails, naming the absorbed advance, instead of passing. The harness cases for holds re-read until admission include one such case: a drive held at a start gate, the clock advanced 15 seconds past launcher start, then released.

A new scenario in `scenarios.md` exercises the three rules. The launchers themselves do not change.

### Motivation

Work item bd-ib-fokcuo ("check-fleet-launch sub-case 20f can absorb its 15 s clock skew into the wait deadline and pass without proving a slow start"). Its Definition of Done asserts:

1. In sub-case 20f, the 15-second clock skew is written only after the case-20 wait has computed its deadline, so in every run the wait observes more than 10 seconds elapsed since launcher start before the stub drive is released.
2. When 20f's wait computes its deadline after the skew is already in effect, the sub-case fails with a message naming the absorbed skew, instead of passing without proving a slow start.
3. When a case-20 wait gives up because the launcher exited first or its hang guard elapsed, the failure message carries `WAIT_FAILURE_DETAIL` naming the reason and the last launcher log line, and a test drives that failure path and asserts both appear.
4. Every remaining fixed wall-clock bound in `fleet-launch/test/run-tests.sh` measured from launcher start either waits on observed launcher state with a hang guard no shorter than `FLEET_LAUNCH_MAX_WAIT_S`, or is recorded as safe with the reason it cannot race launcher start-up.

The Dispatcher refused the item at 2026-11-13T04:47:33Z as spec-change tier, held for this topic. The spec-stated judgement found the asked-for behaviour unstated and named §"Provisional fleet launch scripts" as the heading to generalize. Its rationale: the ratified text requires the harness to cover holds re-read until admission and to fail `just check` when a launcher breaks a case, but says nothing about the harness's wait deadlines, the clock skew in sub-case 20f, the `WAIT_FAILURE_DETAIL` failure message, or a sweep of fixed wall-clock bounds measured from launcher start. This proposal states each of those, so the judgement can find them.

The race, on origin/master 3271c2f85. `wait_on_launcher` computes `deadline=$(( $(harness_now) + HARNESS_PREFLIGHT_HANG_GUARD_S ))`, and `harness_now` adds the seconds in `HARNESS_CLOCK_SKEW_FILE`. Sub-case 20f starts the waiter in a background subshell and then writes `15` to the skew file in the parent. Nothing orders the two, so the subshell can compute its deadline after the write. The 15 seconds then sit in both the deadline and every later clock read, so the wait never measures the slow start the case names. The item was split out of legacy-coordinator-agent's FAIL-ON-PROOF grade of bd-ib-fs2i2l (#4929). That grade found three proof gaps: this race, no test of the `WAIT_FAILURE_DETAIL` failure path, and no recorded sweep of the other fixed bounds measured from launcher start.

Design choices, stated for the grade:
- **The rule is general, not a 20f patch.** Sub-case 20f is one instance. The clause binds every launcher wait and every clock-advancing slow-start case, so the next case cannot reintroduce the race. The 15-second and 10-second figures appear only where the clause names the one slow-start case Scenario 330's harness cases must include.
- **The ordering is stated, not the mechanism.** The clause requires the clock advance to follow the deadline computation, and a run that absorbed it to fail. Either fix direction the coordinator named satisfies it: the wait touches a marker once its deadline is computed and the case advances the clock only once the marker exists, or the advance is applied from inside the waiter.
- **The hang guard is at least `FLEET_LAUNCH_MAX_WAIT_S`.** A launcher may legitimately wait that long for a slot, so a shorter guard could fail a healthy launcher. The harness default guard (`HARNESS_PREFLIGHT_HANG_GUARD_S`, 300 s) already exceeds the 120 s every case-20 sub-case sets.
- **A fixed bound that cannot race start-up may stay.** Definition of Done assertion 4 allows a fixed bound recorded as safe. The clause gives the objective test for "safe": the bound begins only after the same launcher has already reached an observed state past its start-up. Which waits pass that test is the implementing change's sweep to record on the item.
- **Negative waits are out of scope.** A wait whose bound elapsing PASSES the case (for example, `if wait_for_line ... "queued behind an older gmktec ticket" 30; then fail`) cannot fail a slow launcher, so the clause does not govern it.
- **No new host value.** The hang guard is a harness setting, not a launcher host value, so the `FLEET_LAUNCH_` host-value rule is unchanged.

In-flight survey, 2026-11-13 ~05:05Z. Scope: the in-tree proposals on origin/master under `SPECIFICATION/proposed_changes/`, the remote `spec/*` branches, and the 21 open pull requests touching `SPECIFICATION/`. These touch §"Provisional fleet launch scripts":
- a-fleet-launcher-holds-its (bd-ib-4vwaty, in-tree), a-fleet-launcher-honours-a (bd-ib-aibd3u, in-tree), each-gmktec-fabro-server-s-2 (bd-ib-rtzhfc, in-tree) and the-launcher-holds-one-wip-number (bd-ib-5k2yq2, in-tree): each adds harness cases for its own launcher gate. None states how the harness waits, so each new case is a launcher wait under this clause once both are ratified. Relation: `align`.
- a-committed-single-item-operator (bd-ib-fc6da3, PR #5120): adds a harness paragraph at the same anchor this proposal uses, immediately after the holds-re-read-until-admission paragraph. The two paragraphs do not interact, and change 1 below fixes the placement for either revise order. Its override cases are launcher waits under this clause. Relation: `align`.
- each-gmktec-fabro-server-s (bd-ib-rtzhfc, in-tree, the WIP-cap half): changes what a launcher's WIP gate counts, with no harness wait text. Relation: `align`.
- fleet-launchers-log-and-retry (bd-ib-7itf42, PR #5073) and concurrent-git-fetches-into-one (bd-ib-zyu2ug, PR #5072): launcher behaviour only, no harness wait text. Relation: `align`.
- the-fleet-launcher-serializes-each: another session is drafting it concurrently. Its branch was not on origin at survey time, so its text was not surveyed. Under this repository's `in_flight_alignment: default-align`, the relation is `align`.
No other open pull request touches this section. No in-flight item is superseded or in conflict.

### Proposed Changes

All edits are in `contracts.md` §"Provisional fleet launch scripts" and one new scenario appended to `scenarios.md`. No `contracts.md` H2 heading is added, renamed or removed, and Scenario 330's text is not edited.

**1. Harness waits on a launcher (`contracts.md`).** Immediately after the paragraph beginning "The `check-fleet-launch` harness cases MUST also cover holds re-read until admission:", add the three paragraphs below. If a proposal ratified earlier has already added a paragraph right after that one (#5120's single-item operator override cases, for example), add these after it. The order of the two has no effect.

> The `check-fleet-launch` harness MUST decide every launcher wait it makes by the launcher's observed state. A *launcher wait* is a harness wait for a launcher the case started to reach an awaited state, where the case fails if that state never comes. The state can be a line in the launcher's log, a stub drive invocation, a stub item status, or a file the launcher or its stubs write. A launcher wait MUST pass as soon as the awaited state holds. It MUST fail on its first poll after it observes the launcher has exited, without waiting for its hang guard, when the state does not hold. Its only time bound MUST be a *hang guard*, which stops a launcher that has hung. The hang guard MUST be no shorter than the `FLEET_LAUNCH_MAX_WAIT_S` value the awaited launcher runs with. A case can set that value for one launcher run alone, and a launcher run for which the case sets no value runs with the 86400-second default. A launcher wait MUST NOT fail a launcher for being slow to start. It MUST NOT be bounded by any fixed wall-clock interval measured from the launcher's start that is shorter than its hang guard. A harness wait MAY keep a shorter fixed bound only when that bound cannot race the launcher's start-up: the bound begins only after the same launcher has already reached an observed state past its start-up, so no part of the start-up counts against it. This paragraph does not govern a wait whose bound elapsing passes the case, such as a check that a line does not appear.
>
> When a launcher wait gives up, the case's failure message MUST name why: either the launcher exited first, or the hang guard elapsed. It MUST also carry the last line of the launcher's log, or state that the log had no output. The harness MUST include a test that drives a launcher wait to give up and asserts that the failure message carries both the reason and the last launcher log line.
>
> A harness case MAY prove that a slow launcher start passes a launcher wait by advancing the clock its launcher waits read, instead of sleeping, past a fixed start-up bound while it holds a stub at a gate. Such a case MUST advance that clock only after the launcher wait has computed its hang-guard deadline. Then, in every run, the wait observes more than the start-up bound elapsed since the launcher's start before the case releases the stub. If the wait computed its deadline while the advance was already in effect, the case MUST fail with a message naming the absorbed advance in seconds. It MUST NOT pass, because that run proved no slow start. The harness MUST include a test that forces the wait to compute its deadline with the advance already in effect and asserts the case fails naming the advance. The `check-fleet-launch` harness cases for holds re-read until admission MUST include one such slow-start case. In it, the stub drive is held at a start gate, the clock is advanced 15 seconds past the launcher's start (beyond the 10-second start-up bound the waits once used), and only then is the drive released. The launcher wait for the drive's start passes, and the run lists. The scenario "The `check-fleet-launch` harness decides each launcher wait by the launcher's observed state" in `scenarios.md` exercises these cases.

**2. Scenario (`scenarios.md`).** Append the scenario below. It carries no number; the revise pass assigns one.

## Scenario: The `check-fleet-launch` harness decides each launcher wait by the launcher's observed state

Governing clause: `contracts.md` §"Provisional fleet launch scripts".

```gherkin
Feature: The check-fleet-launch harness waits on a launcher's observed state
  Background:
    Given fleet-launch/config.sh values overridden to stub factory boards and throwaway queue, lock, in-flight and state directories
    And a launcher wait whose hang guard is no shorter than the FLEET_LAUNCH_MAX_WAIT_S value the awaited launcher runs with

  Scenario: A slow drive start passes the launcher wait
    Given an impl launcher for bd-s whose stub drive is held at a start gate
    And a launcher wait for the stub drive's start that has computed its hang-guard deadline
    When the case advances the waits' clock 15 seconds past the launcher's start
    And then releases the stub drive
    Then the launcher wait observes more than 10 seconds elapsed since the launcher's start before the drive starts
    And the launcher wait passes
    And bd-s's run lists on its factory board

  Scenario: A clock advance absorbed into the wait's deadline fails the case
    Given the launcher wait for the stub drive's start computed its hang-guard deadline after the 15-second advance was already in effect
    When the slow-start case checks its result
    Then the case fails with a message naming the absorbed 15-second advance
    And the case does not pass

  Scenario: A launcher that exits first fails the wait at once and says why
    Given a launcher wait for a state the launcher never reaches
    When the launcher exits after logging the line "drive rc=1"
    Then the wait gives up before its hang guard elapses
    And the failure message names that the launcher exited first
    And the failure message carries the last launcher log line "drive rc=1"

  Scenario: A hung launcher fails the wait at its hang guard and says why
    Given a launcher wait for a state the launcher never reaches
    And the launcher stays alive with an empty log
    When the hang guard elapses
    Then the failure message names that the hang guard elapsed
    And the failure message states that the launcher log had no output
```

**3. Unchanged.** The launchers' behaviour and every launcher rule of the section are unchanged, including the `FLEET_LAUNCH_MAX_WAIT_S` default and its `max-wait` terminal line. The existing harness case lists and Scenario 330's text and gherkin block are also unchanged. This proposal adds no host value.

**4. Revise co-edit.** The revise pass that accepts this proposal MUST add one `tests/heading-coverage.json` row for the new scenario heading, in the same revise commit. The row is carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit. It carries `test: "TODO"`, `work_item: "bd-ib-fokcuo"`, and a non-empty `reason` naming the tier the owed test runs at: integration, as `check-fleet-launch` harness cases over a stub drive held at a start gate and a stub launcher that exits or hangs. The same commit MUST add the matching `tests/heading-coverage-debt.json` entry by running `just generate-heading-coverage-debt-register` and staging its output. That entry MUST NOT be written by hand. No `contracts.md` H2 heading changes, so no other row is owed.
