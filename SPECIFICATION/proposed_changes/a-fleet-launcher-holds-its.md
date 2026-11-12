---
topic: a-fleet-launcher-holds-its
author: claude-opus-5-5
created_at: 2026-11-12T18:35:24Z
---

## Proposal: a-fleet-launcher-holds-its

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

While its own Dispatcher reports the master-CI preflight's bounded wait, a fleet-launch launcher marks its fleet in-flight marker as waiting. The shared fleet count skips a waiting marker, so a slow or red default branch no longer strands fleet slots. When the wait passes, the launcher re-binds under the factory mutex. Resume launchers get the same rule. The Dispatcher's per-poll wait line becomes a MUST and gains a pass line, and `drive` and `resume --item` pass both lines through unchanged. The launcher therefore keys only on the Dispatcher's own output and never reads default-branch CI itself.

**Scope.** The rule covers both `fleet-launch/` launcher scripts, the impl launcher and the resume launcher. It applies to every tenant whose dispatch runs the master-CI preflight. A tenant that waives the step through a `master-ci` entry under `dispatcher.step_waivers` emits no wait line, so its launches never release a slot under this rule.

### Motivation

Measured on 2026-11-12 on the dispatching host. livespec-dev-tooling-ljmpht took its fleet in-flight marker at 17:49:50Z and invoked drive at 17:50:26Z. Its Dispatcher then printed `master-ci preflight: master run 43271983614 is in_progress; it has not failed. Waiting for its verdict.` on every poll for about 30 minutes. It ended PENDING and exited 3 at 18:20:51Z. A launcher keeps its marker until its run lists or its drive exits, so that slot counted against the shared fleet cap for the whole wait. At 18:19Z the factory board read 14 live runs while every launcher counted fleet=20 against cap 20. Six live unlisted markers made the difference, and five of them were dev-tooling launches parked in that same wait. Four launchable tickets waited behind them.

The section already says that a launcher waiting to re-take a ticket after an early exit holds no marker ("Early-exit re-ticket"). Nothing says what happens to the marker while the Dispatcher is still inside its wait, how to bind again when the wait passes, or that a resume launcher does the same. §"A caller does not gate a dispatch on the default branch's CI" forbids the launcher from reading that CI run itself, so the only admissible signal is the Dispatcher's own preflight output, and that output is only a SHOULD today.

Linked work items:

- bd-ib-4vwaty carries the launcher change. It was filed under coordinator ruling 2026-11-12 (legacy-coordinator-agent session 7c4d3e4c): shape (b) only, resume parity, fleet scope.
- bd-ib-ho6u2n owns the Dispatcher's wait and pass lines and the `drive` and `resume --item` pass-through.

The launcher change is ordered after bd-ib-ho6u2n. Change 2 also covers a Dispatcher build that predates it.

### Proposed Changes

**1. The master-CI wait and pass lines become machine-readable (`contracts.md`, the master-CI preflight's bounded-wait paragraph).** Replace the final sentence of that paragraph, "Each poll that observes a pending run SHOULD emit one progress line naming the run and its status, so an operator watching a dispatch can tell a wait from a hang.", with:

> Each poll that observes a pending run MUST emit one progress line on the Dispatcher's standard error, so that an operator or a caller watching a dispatch can tell a wait from a hang. The line begins with the literal prefix `master-ci preflight: `, names the run and its pending status, and ends with the words `Waiting for its verdict.` When the preflight passes after at least one such line, whether on the waited run or on a concluded green ancestor, it MUST emit one line on standard error that begins with the same prefix, names the run it passed on, and contains the words `passed after waiting`. `drive --action impl:<item>` and `resume --item <item>` MUST pass both line forms through to their own standard error unchanged. These two line forms are the whole of what a caller may read about the wait. A `fleet-launch/` launcher MAY use them only for its own fleet count, as §"Provisional fleet launch scripts" prescribes. Neither line is a verdict that a caller may act on in place of the preflight's own outcome.

**2. The impl launcher's marker lifetime, and the waiting marker (`contracts.md` §"Provisional fleet launch scripts").** After the bullet beginning "**Holds re-read until admission.**", add:

> - **Impl launcher marker lifetime.** Before it releases the factory mutex to start `drive --action impl:<item>`, an impl launcher MUST write a fleet in-flight marker that every launcher's fleet count includes. It MUST keep that marker until the launched run lists on its factory board or the drive exits, and it MUST then remove it. "Marker marked waiting during the master-CI wait" below is the one change to what that marker counts toward while it exists.
> - **Marker marked waiting during the master-CI wait.** While a launcher waits for its launched run to list, it MUST read its drive's standard error at least once a second. That read is separate from the poll, every 15 seconds or as configured, in which it reads its factory board for the listing.
>   - **Waiting.** At the first master-CI wait progress line that drive emits, the launcher MUST append one line `master-ci-wait=1` to its fleet in-flight marker, and MUST NOT delete the marker. Every launcher's shared fleet count MUST skip a marker that carries that line. The in-flight addition of the target repository MUST still count it, because the launch is still past the FIFO and not yet `active`.
>   - **Pass.** At a `passed after waiting` line read while the work item still reads `ready`, the launcher MUST take the factory mutex, remove the `master-ci-wait=1` line from its marker under that mutex, re-count the shared fleet count with its marker included, and release the mutex. The marker then counts as before the wait, until the run lists or the drive exits.
>   - **Over the cap.** If that re-count is over the shared fleet cap, the launcher MUST still let the drive proceed, and MUST log one line naming the work item, its ticket number, the count, the cap and the cause `fleet-cap-exceeded-after-master-ci-wait`. It MUST NOT answer an over-cap re-bind by sending the drive TERM. The overshoot is bounded by the number of launches whose markers carry `master-ci-wait=1` at that moment.
>   - **Admitted first.** If the work item reads `active`, or the launched run lists, before a pass line is read, the launcher MUST remove the `master-ci-wait=1` line under the factory mutex without a cap verdict. Where the run has listed, it then removes the marker itself, because the board counts the run. When a pass line and an `active` reading arrive in the same poll, the `active` reading wins: the launcher follows this bullet, not the over-cap re-count.
>   - **Drive exit.** If the drive exits while the marker carries `master-ci-wait=1`, the launcher removes its marker, and the drive-exit rules of this section govern what follows.
>   - **Older Dispatcher build.** A launcher MUST apply this rule only to a drive whose Dispatcher build emits the pass line, which is the build that carries bd-ib-ho6u2n's change or a later one. It determines that from the installed build's version, against a host value in `fleet-launch/config.sh` naming the first such version. For an older build, which never emits the pass line, the launcher MUST keep its marker counted for the whole wait, exactly as before this rule.
>
>   The launcher reads only its own drive's output for this rule. It MUST NOT read the default branch's CI run itself, as §"A caller does not gate a dispatch on the default branch's CI" forbids. Marking the marker waiting changes only the launcher's own fleet count. It is not a hold, deferral or skip of the dispatch, and the Dispatcher's master-CI preflight remains the sole authority on whether the dispatch proceeds. A launch into a tenant whose `dispatcher.step_waivers` waives `master-ci` emits no wait line, so its marker is never marked waiting.

**3. Resume parity (`contracts.md` §"Provisional fleet launch scripts", the resume launcher's bullets).** Replace the bullet "Before it releases the mutex to start a resume, it MUST write a fleet in-flight marker that every launcher's fleet count includes until the resumed run lists on its factory board, and it MUST remove that marker when the resume ends." with:

> - Before it releases the mutex to start a resume, it MUST write a fleet in-flight marker that every launcher's fleet count includes until the resumed run lists on its factory board, and it MUST remove that marker when the resume ends. While its `resume --item <item>` reports the master-CI wait, a resume launcher MUST mark that marker waiting at the first wait line, and MUST remove the waiting line at the pass line, under the factory mutex, exactly as "Marker marked waiting during the master-CI wait" prescribes for an impl launcher. That includes the older-build exception. A resume launcher MUST NOT stop its resume and MUST NOT re-take a ticket for this rule. It re-marks at the pass line even when the re-count is over the shared fleet cap, logging `fleet-cap-exceeded-after-master-ci-wait`, because a resume re-enters a run whose item was already admitted, as "Holds re-read until admission" already recognizes.

**4. Harness cases (`contracts.md` §"Provisional fleet launch scripts", the `check-fleet-launch` case list).** Append a paragraph:

> The `check-fleet-launch` harness cases MUST also cover "Marker marked waiting during the master-CI wait", using a stub drive and a stub resume that print master-CI preflight lines:
> - a stub drive that prints wait lines and then exits 3: no launcher's fleet count includes the launch during the wait, the in-flight addition still counts it, and the launcher holds no marker while it waits to re-take its ticket;
> - a stub drive that prints wait lines and then the `passed after waiting` line with the fleet count under the cap: the `master-ci-wait=1` line is removed under the mutex and the run proceeds;
> - the same lines with the fleet count at the cap: the drive is not stopped, the run proceeds, and the launcher logs `fleet-cap-exceeded-after-master-ci-wait`;
> - the active-first race, a stub whose item reads `active` in the same poll that its pass line arrives: the `master-ci-wait=1` line is removed with no cap verdict and no `fleet-cap-exceeded-after-master-ci-wait` line;
> - a resume launcher whose stub resume prints wait lines and then the pass line with the fleet count at the cap: no fleet count includes it during the wait, and it re-binds at the pass line without stopping the resume or re-taking a ticket;
> - the Dispatcher pass line: a stub drive standing in for a build that emits the pass line, whose line reaches the launcher's read of the drive's standard error byte-for-byte, and a stub drive standing in for an older build, under which the marker stays counted for the whole wait.

**5. Scenario (`scenarios.md`).** Append the scenario below.

## Scenario: a fleet launcher holds no fleet slot while its Dispatcher waits at the master-CI preflight

Governing clause: `contracts.md` §"Provisional fleet launch scripts".

```gherkin
Feature: A fleet-launch launcher marks its in-flight marker waiting for the master-CI wait
  Background:
    Given fleet-launch/config.sh values overridden to stub factory boards, a stub drive and a stub resume that print master-CI preflight lines, and throwaway queue, lock, in-flight and state directories
    And a shared fleet cap of 2
    And a host value naming the stub Dispatcher build as one that emits the pass line

  Scenario: A launch whose Dispatcher waits on a pending default-branch run is not counted
    Given an impl launcher whose stub drive prints "master-ci preflight: master run 7 is in_progress; it has not failed. Waiting for its verdict." on each poll
    When another launcher reads the shared fleet count during that wait
    Then the count excludes the waiting launch
    And the waiting launcher's marker carries the line master-ci-wait=1
    And the target repository's in-flight addition still counts the launch

  Scenario: A wait that ends PENDING leaves no marker through the re-take delay
    Given an impl launcher whose stub drive prints wait lines and then exits 3
    When the launcher waits to re-take its ticket under "Early-exit re-ticket"
    Then it holds no fleet in-flight marker during that delay

  Scenario: A wait that passes re-binds under the cap
    Given an impl launcher whose stub drive prints wait lines and then "master-ci preflight: master run 7 passed after waiting"
    And the shared fleet count without that launch is 1
    When the launcher reads the pass line while the work item still reads ready
    Then it removes the master-ci-wait=1 line from its marker under the factory mutex
    And the run proceeds and lists

  Scenario: A wait that passes with the cap full proceeds and logs the overshoot
    Given an impl launcher whose stub drive prints wait lines and then the pass line
    And the shared fleet count without that launch is 2
    When the launcher re-counts with its marker included
    Then it does not stop the drive
    And it logs the cause fleet-cap-exceeded-after-master-ci-wait
    And the run proceeds and lists

  Scenario: An admission in the same poll as the pass line wins
    Given an impl launcher whose stub drive prints wait lines
    And the work item reads active in the same poll that the pass line arrives
    When the launcher handles that poll
    Then it removes the master-ci-wait=1 line with no cap verdict
    And it logs no fleet-cap-exceeded-after-master-ci-wait line

  Scenario: A resume launcher releases for the same wait and re-binds at the pass line
    Given a resume launcher whose stub resume prints master-CI wait lines and then the pass line
    And the shared fleet count without that resume is 2
    When another launcher reads the shared fleet count during that wait
    Then the count excludes the waiting resume
    And at the pass line the resume launcher removes the master-ci-wait=1 line without stopping the resume or re-taking a ticket

  Scenario: An older Dispatcher build keeps the marker counted
    Given a host value naming a first pass-line version later than the stub Dispatcher build
    And an impl launcher whose stub drive prints wait lines
    When another launcher reads the shared fleet count during that wait
    Then the count includes the waiting launch
```

**6. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading. The row is carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit. It carries `test: "TODO"`, `work_item: "bd-ib-4vwaty"` and a non-empty `reason` naming the tier the owed test runs at: integration, as `check-fleet-launch` harness cases over stub drives and boards. The same commit adds one matching `tests/heading-coverage-debt.json` entry carrying `spec_root`, `spec_file`, `heading`, `work_item: "bd-ib-4vwaty"` and `first_seen` set to the revise date.
