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

A fleet-launch launcher releases its fleet in-flight marker while its own Dispatcher reports the master-CI preflight's bounded wait. When that wait passes, it re-binds under the fleet cap before the run is admitted, so a slow or red default branch no longer strands fleet slots. Resume launchers get the same rule. The Dispatcher's per-poll wait line becomes a MUST, and it gains a pass line, so the launcher keys only on the Dispatcher's own output and never reads default-branch CI itself.

### Motivation

Measured on 2026-11-12 on the dispatching host. livespec-dev-tooling-ljmpht took its fleet in-flight marker at 17:49:50Z and invoked drive at 17:50:26Z. Its Dispatcher then printed `master-ci preflight: master run 43271983614 is in_progress; it has not failed. Waiting for its verdict.` on every poll for about 30 minutes, ended PENDING and exited 3 at 18:20:51Z. Under §"Provisional fleet launch scripts" a launcher keeps its marker until its run lists or its drive exits, so that slot counted against the shared fleet cap for the whole wait. At 18:19Z the factory board read 14 live runs while every launcher counted fleet=20 against cap 20. Six live unlisted markers made the difference, five of them dev-tooling launches parked in that same wait. Four launchable tickets waited behind them. The section already says a launcher waiting to re-take a ticket after an early exit holds no marker ("Early-exit re-ticket"). Nothing says to release the marker while the Dispatcher is still inside its wait, how to bind again when the wait passes, or that a resume launcher does the same. §"A caller does not gate a dispatch on the default branch's CI" forbids the launcher from reading that CI run itself, so the only admissible signal is the Dispatcher's own preflight output. That output is only a SHOULD today. Linked work item: bd-ib-4vwaty (coordinator ruling 2026-11-12, legacy-coordinator-agent session 7c4d3e4c: shape (b) only, resume parity, fleet scope).

### Proposed Changes

**1. The master-CI wait and pass lines become machine-readable (`contracts.md`, the master-CI preflight's bounded-wait paragraph).** Replace the final sentence of that paragraph, "Each poll that observes a pending run SHOULD emit one progress line naming the run and its status, so an operator watching a dispatch can tell a wait from a hang.", with:

> Each poll that observes a pending run MUST emit one progress line on the Dispatcher's standard error, so that an operator or a caller watching a dispatch can tell a wait from a hang. The line begins with the literal prefix `master-ci preflight: `, names the run and its pending status, and ends with the words `Waiting for its verdict.` When the preflight passes after at least one such line, whether on the waited run or on a concluded green ancestor, it MUST emit one line on standard error that begins with the same prefix, names the run it passed on, and contains the words `passed after waiting`. These two line forms are the whole of what a caller may read about the wait; neither line is a verdict a caller may act on in place of the preflight's own outcome.

**2. A launcher releases its marker for the wait (`contracts.md` §"Provisional fleet launch scripts").** After the bullet beginning "**Holds re-read until admission.**", add:

> - **Marker released during the master-CI wait.** While a launcher waits for its launched run to list, it MUST read its drive's standard error on every poll. From the first master-CI wait progress line that drive emits, the launcher MUST NOT hold a fleet in-flight marker for that launch. It removes its marker at that line, so no launcher's fleet count includes the launch while its Dispatcher waits. The wait ends at the first of these: the preflight's `passed after waiting` line, the drive's exit, the work item reading `active` in the ledger, or the launched run listing on its factory board.
>   - At a `passed after waiting` line read while the work item still reads `ready`, the launcher MUST take the factory mutex, write its fleet in-flight marker again, and re-count with that marker included.
>   - If that count is at or under the shared fleet cap, the launcher MUST release the mutex and keep the marker until its run lists or its drive exits, exactly as before the wait.
>   - If that count is over the cap, the launcher MUST stop the drive by sending it TERM before the drive submits a run. It then keeps its FIFO ticket at the same ticket number, releases the mutex and the marker, and yields as a held launcher does. It logs one line naming the work item, its ticket number and the cause `fleet-cap-after-master-ci-wait`. Such a stop does not trigger "Early-exit re-ticket" and is not a non-run exit. The post-stop status re-read of "Holds re-read until admission" applies to it unchanged.
>   - If the wait ends because the work item reads `active` and the run has not yet listed, the launcher MUST write its marker again without stopping the drive.
>   - If it ends because the run listed, the launcher writes no marker, because the board counts the run.
>   - If it ends because the drive exited, the launcher holds no marker, and "Early-exit re-ticket" governs what follows.
>
>   The launcher reads only its own drive's output for this rule. It MUST NOT read the default branch's CI run itself, as §"A caller does not gate a dispatch on the default branch's CI" forbids. Releasing the marker is a change to the launcher's own fleet count. It is not a hold, deferral or skip of the dispatch, and the Dispatcher's master-CI preflight remains the sole authority on whether the dispatch proceeds.

**3. Resume parity (`contracts.md` §"Provisional fleet launch scripts", the resume launcher's bullets).** Replace the bullet "Before it releases the mutex to start a resume, it MUST write a fleet in-flight marker that every launcher's fleet count includes until the resumed run lists on its factory board, and it MUST remove that marker when the resume ends." with:

> - Before it releases the mutex to start a resume, it MUST write a fleet in-flight marker that every launcher's fleet count includes until the resumed run lists on its factory board, and it MUST remove that marker when the resume ends. While its `resume --item <item>` reports the master-CI wait, a resume launcher MUST apply "Marker released during the master-CI wait" exactly as an impl launcher does. It reads the resume's standard error, releases the marker from the first wait line, and re-binds under the cap at the pass line. Where that rule stops a drive, a resume launcher stops its resume, keeps its ticket and yields.

**4. Harness cases (`contracts.md` §"Provisional fleet launch scripts", the `check-fleet-launch` case list).** Append a paragraph:

> The `check-fleet-launch` harness cases MUST also cover "Marker released during the master-CI wait", using a stub drive that prints master-CI wait progress lines:
> - a stub that prints wait lines and then exits 3, during which no launcher's fleet count includes the launch and the launcher holds no marker while it waits to re-take its ticket;
> - a stub that prints wait lines and then the `passed after waiting` line with the fleet count under the cap, after which the marker is written again and the run proceeds;
> - a stub that prints the same lines with the fleet count at the cap, after which the drive is stopped by TERM before it submits a run, and the ticket keeps its number and yields;
> - a resume launcher whose stub resume prints wait lines, during which no fleet count includes it.

**5. Scenario (`scenarios.md`).** Append the scenario below, numbered with the next free number at revise time (350 to 364 are claimed by pending proposals and peer drafts). The same revise pass adds its `tests/heading-coverage.json` entry; `test` MAY be the literal "TODO" with a non-empty `reason`.

## Scenario NN — A fleet launcher holds no fleet slot while its Dispatcher waits at the master-CI preflight

Governing clause: `contracts.md` §"Provisional fleet launch scripts".

```gherkin
Feature: A fleet-launch launcher releases its in-flight marker for the master-CI wait
  Background:
    Given fleet-launch/config.sh values overridden to stub factory boards, a stub drive and a stub resume that print master-CI preflight lines, and throwaway queue, lock, in-flight and state directories
    And a shared fleet cap of 2

  Scenario: A launch whose Dispatcher waits on a pending default-branch run is not counted
    Given an impl launcher whose stub drive prints "master-ci preflight: master run 7 is in_progress; it has not failed. Waiting for its verdict." on each poll
    When another launcher reads the shared fleet count during that wait
    Then the count excludes the waiting launch
    And the waiting launcher holds no fleet in-flight marker

  Scenario: A wait that ends PENDING leaves no marker through the re-take delay
    Given an impl launcher whose stub drive prints wait lines and then exits 3
    When the launcher waits to re-take its ticket under "Early-exit re-ticket"
    Then it holds no fleet in-flight marker during that delay

  Scenario: A wait that passes re-binds under the cap
    Given an impl launcher whose stub drive prints wait lines and then "master-ci preflight: master run 7 passed after waiting"
    And the shared fleet count without that launch is 1
    When the launcher reads the pass line while the work item still reads ready
    Then it writes its fleet in-flight marker again under the factory mutex
    And the run proceeds and lists

  Scenario: A wait that passes with the cap full stops the drive before admission
    Given an impl launcher whose stub drive prints wait lines and then the pass line
    And the shared fleet count without that launch is 2
    When the launcher re-counts with its marker included
    Then it stops the drive with TERM before the drive submits a run
    And it keeps its FIFO ticket at the same ticket number and yields
    And it logs the cause fleet-cap-after-master-ci-wait

  Scenario: A resume launcher releases its marker for the same wait
    Given a resume launcher whose stub resume prints master-CI wait lines
    When another launcher reads the shared fleet count during that wait
    Then the count excludes the waiting resume
```
