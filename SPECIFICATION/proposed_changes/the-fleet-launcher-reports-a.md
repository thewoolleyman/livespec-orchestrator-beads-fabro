---
topic: the-fleet-launcher-reports-a
author: claude-opus-5-5
created_at: 2026-11-13T05:08:21Z
---

## Proposal: A fleet launcher decides that a run never listed only from a board read taken after it saw its drive exit

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Provisional fleet launch scripts" requires exactly one terminal line when a launched drive or resume exits before its run lists on its factory board. It never says how a launcher decides that a run did not list. The committed impl launcher `fleet-launch/dispatch-dual.sh` reads the board first and checks whether the drive is alive second. A drive that submits its run and exits between those two reads is therefore misreported: the launcher sees no row and a dead drive, then writes a terminal line with the cause "drive exited before its run listed", although the run is on the board. This proposal makes three changes:

- **Listing decided after the drive exits.** A launcher MUST NOT decide that a run never listed from a board read taken before it observed the launched process exit. When it finds that process exited with no listing seen, it MUST take one further board read, the *final listing read*. That read's listing must be produced after the exit was observed: either a direct factory read, or a shared snapshot whose refresh started after the observation. If the final listing read lists the run, the launcher records the run as listed. It prints its `LISTED` line and makes no non-run exit: no terminal line, no "drive exited before its run listed" cause, no dropped-ticket comment and no early-exit re-ticket. Only a final listing read that lists no run produces that cause, with exactly one terminal line. A final listing read that cannot be taken is never read as an empty board. The launcher retries it on each listing poll for up to `FLEET_LAUNCH_LISTING_WAIT_S` seconds, and only then makes the same non-run exit, with a terminal line stating that the read could not be taken. Every other rule of the section that turns on whether a run listed before its drive exited is decided by this bullet.
- **Harness coverage.** The `check-fleet-launch` non-run-exit harness paragraph gains four cases. (1) A stub drive submits and exits at once while every stub board read is slowed past that exit, and the launcher records the run as listed. (2) A stub drive exits without submitting, and the launcher writes exactly one terminal line with that cause. (3) A final listing read cannot be taken, and the launcher writes one terminal line stating so. (4) The case-312 ready-set refusal that clears within the retry bound still launches and lists, with no terminal line, however long each board read takes.
- **Scenario 312.** Four new Gherkin scenarios are added to the existing Scenario 312 block in `scenarios.md`. No H2 heading is added, renamed or removed, so `tests/heading-coverage.json` is unchanged.

### Motivation

Work item bd-ib-joyvut, "The fleet launcher reports a listed run as never listed when its drive exits between the board read and the liveness check (check-fleet-launch case 312 ready-refusal-clears)". The Dispatcher refused its launch at 2026-11-13T04:52:22Z, as legacy-dispatcher-agent recorded on the item. The reason: spec-change tier, held for its linked proposed-change topic `the-fleet-launcher-reports-a`, with hold reason `unratified-topic`. The `livespec-spec-change-tier` comment recorded at dispatch (spec version 365) reports the asked-for behaviour as `partial` and names ## Provisional fleet launch scripts as the generalization target. Its rationale: "The text states that a launcher writes exactly one terminal line when a drive exits before its run lists ... It does not state how a drive that submits its run and exits between the launcher's board read and its liveness check is classified. Reading the board one final time after finding the drive exited, the LISTED record, and the absence of a terminal line in that race are not stated, nor is the case-312 timing robustness." This proposal states each of those four things.

The item's Definition of Done asserts:

1. When an impl drive submits its run and exits before the launcher's next listing poll observes it, the fleet launcher (`fleet-launch/dispatch-dual.sh`) records the run as listed and prints its `LISTED` line. It writes no `terminal:` line and no "drive exited before its run listed" cause.
2. When an impl drive exits without its run ever appearing on the factory board, the fleet launcher still writes exactly one `terminal:` line naming "drive exited before its run listed", as Scenario 312 and the non-run exit rule require.
3. The `check-fleet-launch` case-312 sub-case `ready-refusal-clears` passes however long a board listing takes, including when every stub `fabro ps` call is slowed past the drive's own exit.

Observed failure, 2026-11-11. The delegated pre-push gate Job `gate-livespec-orchestrator-beads-fabro-q7ltq` ran branch `spec/a-failed-fix-or-review`, a branch that adds only one proposed-change file on top of the green master `3825b0d35`. It failed case 312 `ready-refusal-clears`. The rc and both ready-set polls were correct. The case log read "drive exited before listing", "drive rc=0", "terminal: item=bd-ib-ready ticket=100 cause=drive exited before its run listed (drive rc=0)", so the terminal-line clause failed on a launch whose run had reached the stub board.

Mechanism, read from origin/master `73682f96c`. In `fleet-launch/dispatch-dual.sh` the listing loop runs `run_row=$(board_rows "$FABRO" "$tserver" | ...)` (line 609). Only after that does it run `if ! kill -0 "$drive_pid" ...; then echo "... drive exited before listing"; break; fi` (line 611). Line 624 then sets `exit_cause="drive exited before its run listed (drive rc=$rc)"` whenever `run_listed` is not 1. A drive that submits and exits after line 609 has read the board, but before line 611 runs, is classified as never listed. The harness's ungated stub drive writes its listing marker and exits at once, and under gate-pod load the stub `fabro ps` subprocess is slow, which widens the window. The real launcher has the same latent window: a fast real drive can exit between those two reads. `board_rows` also reads a shared snapshot that is up to `FLEET_LAUNCH_BOARD_TTL_S` old, so even a re-read could return a listing taken before the submission. That is why the final listing read must be one the factory produced after the exit was observed. A longer stub linger would only hide the window. The fix belongs in the launcher, and the section must state the rule so that the fix and the harness case can be graded against it.

Design choices, stated for the grade:
- **The rule binds every committed launcher, not only `dispatch-dual.sh`.** It is phrased over "the process a launcher started to launch its work item", so it also covers `resume-capped.sh` and any launcher a later proposal adds, such as the single-item operator override of #5120. `resume-capped.sh` already takes its listing decision from reads made after the resume client exits: its `wait_for_listing` keeps reading the board for `FLEET_LAUNCH_LISTING_WAIT_S` after that exit, and a snapshot refreshed after the exit falls inside that wait. The listing decision therefore needs a code change only in `dispatch-dual.sh`. A side observation, not changed here: once its resume has started, `resume-capped.sh` writes no terminal line for a resume that never lists. The existing "Terminal line" bullet already requires one, so this is a pre-existing gap, outside this item.
- **Freshness is defined by when the listing was produced, not by when the read was issued.** A shared snapshot older than the observed exit is exactly the window this item closes, so it cannot serve as the final listing read. A direct read, or a snapshot refresh that started after the observation, can. The launcher may take either.
- **An unreadable final read is bounded by an existing host value.** The section already treats an unreadable board as never zero. The final read inherits that rule, and its retry is bounded by `FLEET_LAUNCH_LISTING_WAIT_S`, which `fleet-launch/config.sh` already assigns (default 600 s) for the resume launcher's post-exit listing wait. No new host value is introduced.
- **The fleet in-flight marker is not extended.** While the board is unreadable the shared fleet count is already treated as at the cap, so keeping the marker through the retry would add no protection. The proposal leaves marker removal to the rules that already govern it, including #5088's, if ratified.
- **The drive's exit code does not override the board.** A run the final listing read lists is listed whatever code the drive exited with. So a drive that submits and then exits non-zero is not re-ticketed under "Early-exit re-ticket", which already applies only "before the launched run lists". The exit-`5` and `goal-minijinja-preflight` rules are unaffected, because a refused or pre-flight-failed drive submits no run.
- **Terminal rows are out of scope.** The committed board reader lists only non-terminal runs. A run that submits, lists and reaches a terminal state before the final listing read is not addressed here and is not part of the item's Definition of Done.
- **The listing decision is independent of read duration.** The rule says outright that a board read returning after the drive exited is evaluated like any other. That is the property Definition of Done assertion 3 tests.

In-flight survey, 2026-11-13 ~05:05Z. Scope: the in-tree proposals on origin/master under `SPECIFICATION/proposed_changes/`, the 27 remote `spec/*` branches, and the open pull requests. These touch §"Provisional fleet launch scripts" or Scenario 312:
- a-committed-single-item-operator (bd-ib-fc6da3, #5120, draft): adds `fleet-launch/override-item.sh`, whose non-run exits follow this section's rules. The new bullet binds every committed launcher, so the override's listing decision follows it once both are ratified. Relation: `align`, in either revise order.
- fleet-launchers-log-and-retry (bd-ib-7itf42, #5073): rules for a failed status read, the dropped-ticket comment only while `ready`, and a TERM bound on non-run exits. It applies to the non-run exit this proposal decides and is not changed by it. Relation: `align`.
- a-fleet-launcher-holds-its (bd-ib-4vwaty, #5088, in-tree): impl and resume markers marked `master-ci-wait=1` during the Dispatcher's master-CI wait, and removed when "the run lists or the drive exits". This proposal does not move marker removal, so the two compose. Relation: `align`.
- each-gmktec-fabro-server-s-2 (bd-ib-rtzhfc, #5101, in-tree), each-gmktec-fabro-server-s (in-tree), the-launcher-holds-one-wip-number (bd-ib-5k2yq2, in-tree), a-fleet-launcher-honours-a (bd-ib-aibd3u, in-tree) and concurrent-git-fetches-into-one (bd-ib-zyu2ug, #5072): these change caps, the WIP gate, hold exemptions and fetch locking. None of them decides whether a run listed. Relation: `align`.
- `spec/revise-v366-incident-authority-cli-reply-and-fenced-reads` (bd-ib-txbv7i), a pending revise: it edits `contracts.md` and adds scenarios to `scenarios.md` for the incident authority CLI. It touches neither §"Provisional fleet launch scripts" nor Scenario 312. Relation: `align`. The other remote revise branches (`spec/revise-v330-...`, `spec/codex-floor-reset-proximity`, `spec/red-turn-changes-no-product-file`, `spec/revise-attention-item-answer-policy`) carry revisions at or below the current v365, so they are not pending design work. Relation: none.
- The fleet-flaky-tests plan's two concurrent drafts, `spec/the-fleet-launcher-serializes-each` and `spec/check-fleet-launch-sub-case`, were being written at survey time and were not yet on the remote. Their text could not be surveyed. This proposal adds no H2 heading and changes only Scenario 312's Gherkin block and one paragraph and one bullet of the section, so a textual collision is unlikely; the reviser should check them at revise time.
No in-flight item is superseded or in conflict.

### Proposed Changes

All edits are in `contracts.md` §"Provisional fleet launch scripts" and in the existing Scenario 312 block of `scenarios.md`. No H2 heading in either file is added, renamed or removed, so `tests/heading-coverage.json` is unchanged.

**1. Listing decided after the drive exits (`contracts.md`).** In the bullet list that follows the paragraph beginning "Every committed `fleet-launch/` launcher, impl or resume, MUST account for every exit it makes before its launched run lists on its factory board (a *non-run exit*).", insert this bullet immediately before the bullet beginning "**Terminal line.**":

> - **Listing decided after the drive exits.** A launcher decides whether the run it launched *listed* on its factory board from its own reads of that board. It MUST NOT decide that a run never listed from any board read it took before it observed that the process it started to launch its work item had exited. That process is its `drive --action impl:<item>`, its `resume --item <item>`, or any other launch command this section names. When a launcher finds that process exited, and no board read it has taken lists a non-terminal run for its work item, it MUST take one further read of its target factory's board, the *final listing read*. The listing of the final listing read MUST have been produced by the factory after the launcher observed the exit. That listing is either a direct read of the factory or a shared board snapshot whose refresh started after that observation. A shared snapshot produced before the observation MUST NOT serve as the final listing read.
>   - **Listed.** If the final listing read lists a non-terminal run for its work item, the launcher MUST treat the run as listed, exactly as if an earlier poll had listed it. It MUST log its listing line naming the run (the `LISTED` line of `fleet-launch/dispatch-dual.sh`) and record that run wherever it records a listed run. It MUST reset the work item's consecutive early-exit count under "Early-exit re-ticket". That launch is not a non-run exit, whatever code the process exited with. The launcher therefore MUST NOT write a terminal line for it, MUST NOT name an exit-before-listing cause (for an impl launcher, "drive exited before its run listed") anywhere, MUST NOT append the comment "Ready item never silently dropped" prescribes, and MUST NOT re-take its ticket under "Early-exit re-ticket".
>   - **Never listed.** Only a final listing read that lists no non-terminal run for its work item establishes that the process exited before its run listed. The launcher MUST then make the non-run exit the rules of this section require for that exit. Its sequence log MUST carry exactly one terminal line. That line MUST name the work item, its ticket number, the process's exit code, and a cause stating that the launched process exited before its run listed. For an impl launcher that cause is "drive exited before its run listed".
>   - **Unreadable final read.** A final listing read that cannot be taken, because its command fails or times out or its output is not a board listing, MUST NOT be read as an empty board. The launcher MUST retry the final listing read on each of its listing polls, for up to `FLEET_LAUNCH_LISTING_WAIT_S` seconds after it observed the exit. That is a host value assigned in `fleet-launch/config.sh` and overridable like any other. A retry that lists the run MUST be treated as **Listed** above. If no final listing read can be taken within that bound, the launcher MUST make the non-run exit of **Never listed** above, and its one terminal line MUST also state that the final listing read could not be taken.
>
>   The decision MUST NOT depend on how long a board read takes: a board read that returns after the process has exited MUST be evaluated like any other read. Every rule of this section that turns on whether a launched run listed before its drive or resume exited, "Holds re-read until admission", "Early-exit re-ticket", "Terminal line" and "Ready item never silently dropped" included, MUST take that answer from this bullet.

**2. Harness coverage (`contracts.md`).** In the paragraph that begins "The `check-fleet-launch` harness cases MUST also cover non-run exits.", replace its final sentence "Scenario 312 in `scenarios.md` exercises these cases." with:

> The harness cases MUST also cover the listing decision after a drive exits:
> - A stub drive submits its run and exits at once while every stub board read is slowed past that exit. The launcher records the run as listed with its listing line, and writes no terminal line and no "drive exited before its run listed" cause.
> - A stub drive exits without submitting a run. The launcher writes exactly one terminal line naming that cause.
> - A stub board cannot be read after the drive exits. The launcher retries the final listing read until `FLEET_LAUNCH_LISTING_WAIT_S` and then writes exactly one terminal line stating that the final listing read could not be taken.
> - In the ready-set refusal case that clears within `FLEET_LAUNCH_READY_RETRY_POLLS` polls, the launcher launches, records its run as listed and writes no terminal line, whatever each stub board read's duration, including when every stub board read is slowed past the stub drive's own exit.
>
> Those cases MUST NOT rely on the stub drive outliving a board read to pass. Scenario 312 in `scenarios.md` exercises these cases.

**3. Scenario 312 (`scenarios.md`).** In the Gherkin block of "## Scenario 312 — A fleet launcher that exits without a run leaves a terminal line, and its ready item's ticket is re-taken or reported", append the following scenarios after the scenario "A dead-pid ticket is reported as a stall", before the closing fence. The block's Feature line, Background and existing scenarios are unchanged, and so is the heading.

```gherkin
  Scenario: A drive that lists its run and exits before the launcher's next board read is recorded as listed
    Given a stub drive for bd-x that submits a run the stub factory board lists as non-terminal, then exits at once with code 0
    And a stub factory board whose every read reports the board as it stood when the read began, and returns only after the stub drive has exited
    When the impl launcher for bd-x launches it
    Then after it observes the stub drive exited, it takes a final listing read whose listing began after that observation
    And its sequence log carries one LISTED line naming bd-x's run
    And its sequence log carries no terminal line and does not name the cause "drive exited before its run listed"
    And it does not re-take its FIFO ticket
    And the stub ledger records no dropped-ticket comment on bd-x

  Scenario: A drive that exits without its run ever listing leaves exactly one terminal line
    Given a stub drive for bd-x that exits with code 0 without submitting a run
    When the impl launcher for bd-x launches it
    Then after it observes the stub drive exited, it takes a final listing read that lists no run for bd-x
    And its sequence log carries exactly one terminal line naming bd-x, its ticket number and the cause "drive exited before its run listed"

  Scenario: A final listing read that cannot be taken is not read as an empty board
    Given a stub drive for bd-x that exits with code 0 without submitting a run
    And a stub factory board whose every read fails once the stub drive has exited
    And FLEET_LAUNCH_LISTING_WAIT_S set to a short bound
    When the impl launcher for bd-x observes the stub drive exited
    Then it retries the final listing read on each listing poll until that bound
    And its sequence log then carries exactly one terminal line naming bd-x, its ticket number, the cause "drive exited before its run listed" and that the final listing read could not be taken

  Scenario: A ready-set refusal that clears launches and lists however slowly the board is read
    Given FLEET_LAUNCH_READY_RETRY_POLLS set to 3
    And a stub ready-set check that refuses bd-x on its first 2 polls and admits it on the 3rd
    And a stub drive for bd-x that submits its run and exits at once
    And a stub factory board whose every read returns only after the stub drive has exited
    When the impl launcher for bd-x polls
    Then it launches bd-x once the check admits it
    And its sequence log carries one LISTED line naming bd-x's run and no terminal line
    And the stub ledger records no dropped-ticket comment on bd-x
```
