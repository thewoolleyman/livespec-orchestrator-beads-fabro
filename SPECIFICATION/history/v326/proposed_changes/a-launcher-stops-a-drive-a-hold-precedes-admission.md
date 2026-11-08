---
topic: a-launcher-stops-a-drive-a-hold-precedes-admission
author: claude-opus-5-5
created_at: 2026-11-07T20:35:08Z
---

## Proposal: An impl launcher stops its drive when a hold appears before admission

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A committed fleet-launch impl launcher keeps re-reading every hold that applies to its launch while its drive runs, until the work item is admitted. If a hold appears while the item still reads ready, the launcher stops the drive before it submits a run, keeps its FIFO ticket and logs the hold. Once the item reads active, a later hold never stops the drive. The boundary is admission rather than the Fabro submission, because a drive stopped after admission and before its run exists strands a claim that reconciliation never releases.

### Motivation

On 2026-11-04 bd-ib-ke5wkf's launcher logged LAUNCH at 09:46:45Z. hold-gmktec was set at 09:54:01Z for the :32276 engine restart, and the run still listed on petri :32276 at 10:08:50Z (run 01M6K0FV7RM5), which refused fabro-currency's main restart at about 10:09Z. The drive spent about 22 minutes in the master-CI preflight's bounded wait between LAUNCH and submission. The "Holds re-read at the launch point" bullet re-reads holds only under the launch mutex immediately before drive starts, so it could not see a hold set during that wait, and no clause of the section states a check after drive starts. The pending proposal a-fleet-launcher-that-exits covers a launcher that exits without its run listing, not a stop during a drive. Linked work item: bd-ib-j6rbdx.

The boundary is admission, not the Fabro submission named in bd-ib-j6rbdx's Definition of Done. The dispatch preamble, including the master-CI preflight wait, runs before admission writes ready -> active (dispatch_preamble in _dispatcher_run_checks.py refuses "provably before admission"), so a drive stopped during that wait has written no claim. A drive stopped after admission and before its run exists leaves the item active under a pending stamp, which §"Stranded claim release" → "Stale assignee clearance" holds as attribution-pending and never releases (remedy: the operator move valve). Using admission as the boundary covers the measured incident without creating that strand. The design constraint of the section is kept: the Dispatcher reads no caller-side hold; stopping the drive is the launcher's act. bd-ib-j6rbdx's Definition of Done is re-worded to this boundary when it is relinked to this proposal.

In-flight survey: 8 remote spec/* branches and 1 open spec-touching pull request (#4603), none touching §"Provisional fleet launch scripts"; aligned. The pending proposal a-fleet-launcher-honours-a (per-item hold exemptions) is compatible: a hold this rule re-reads is a hold that applies to the launch, so an exemption that proposal ratifies applies here unchanged.

### Proposed Changes

In SPECIFICATION/contracts.md §"Provisional fleet launch scripts", in the list of caller-side gates the committed launchers MUST enforce, add this bullet immediately after the "Holds re-read at the launch point" bullet:

"- **Holds re-read until admission.** After an impl launcher invokes `drive --action impl:<item>`, and while that drive runs, the launcher MUST re-read every hold that applies to its launch, by the same rules as the launch-point re-read, on every poll it makes while it waits for the launched run to list on its factory board, until the first of these: the work item reads `active` in the ledger, the launched run lists on its factory board, or the drive exits. If an applicable hold is set while the work item still reads `ready`, the launcher MUST stop the drive by sending it TERM before the drive submits a run. It MUST then keep its FIFO ticket at the same ticket number, release any fleet in-flight marker it holds, yield as a held launcher does, and log one line naming the work item, its ticket number and the hold it read, with that hold's `kinds`, `reason` and `until` text when present. Stopping a drive under this rule is neither an early exit nor a non-run exit, because the launcher itself does not exit. Once the work item reads `active`, or the run lists, the launcher MUST NOT stop the drive for any hold, whenever that hold appears; the Dispatcher's own dispositions govern the dispatch from admission onward. After it stops a drive, the launcher MUST re-read the work item's status. If the item then reads `active`, because the drive admitted it before the signal took effect, the launcher MUST make a non-run exit with the cause `stopped-after-admission`, MUST NOT re-take its ticket, and MUST append one ledger comment to the item naming its ticket number and the operator `move` valve as the remedy for its claim, which carries a pending stamp. A status that cannot be read after the stop MUST be treated as `active`. This gate relies on the Dispatcher running every pre-dispatch step of §"Dispatch preflight and post-merge step discipline", including the master-CI preflight's bounded wait, before the admission write that moves the item to `active`; the Dispatcher MUST keep that order. The Dispatcher MUST NOT read any hold for this purpose: stopping the drive is the launcher's caller-side act. A resume launcher is not subject to this bullet, because a resume re-enters a run whose item was already admitted."

In the same section, after the paragraph that begins "The `check-fleet-launch` harness cases MUST also cover hold scope by launch kind", add this paragraph:

"The `check-fleet-launch` harness cases MUST also cover holds re-read until admission: a hold file created while a stub drive waits before admission, with the item still reading `ready`, under which the launcher stops the drive, no run is submitted, the launcher keeps its ticket at the same ticket number and logs the hold it read; a hold file created after the stub item reads `active`, under which the drive is not stopped and its run lists; no hold file, under which the drive proceeds from launch to listing exactly as before; and a stub item that reads `active` after the stop, under which the launcher makes a `stopped-after-admission` non-run exit, re-takes no ticket and appends one ledger comment naming the `move` valve. Scenario 325 in `scenarios.md` exercises these cases."

In SPECIFICATION/scenarios.md, add after Scenario 324:

A scenario headed `## Scenario 325 — A hold set while a launched drive waits before admission stops the drive`, with the body below:

Governing clause: `contracts.md` §"Provisional fleet launch scripts".

```gherkin
Feature: An impl launcher honours a hold until its item is admitted
  Background:
    Given fleet-launch/config.sh values overridden to stub factory boards and throwaway queue, lock, in-flight and state directories
    And an impl launcher for bd-x in repository R that has invoked a stub drive

  Scenario: A hold set before admission stops the drive
    Given the stub drive is waiting in its master-CI preflight and bd-x still reads ready
    When the gmktec factory hold file is created with the text "engine restart"
    Then the launcher stops the drive before any run is submitted
    And it keeps its FIFO ticket at the same ticket number
    And it logs a line naming bd-x, its ticket number and the hold text "engine restart"

  Scenario: A hold set after admission does not stop the drive
    Given the stub drive has admitted bd-x, which reads active
    When the gmktec factory hold file is created
    Then the launcher does not stop the drive and the run lists on its factory board

  Scenario: No hold leaves the drive unchanged
    Given no hold file exists
    When the stub drive runs to submission
    Then the run lists on its factory board exactly as it did before this rule

  Scenario: A drive that admitted its item before the stop took effect
    Given the stub drive admits bd-x at the moment the launcher stops it
    When the launcher re-reads bd-x and it reads active
    Then the launcher makes a non-run exit with the cause stopped-after-admission
    And it re-takes no ticket
    And it appends one ledger comment to bd-x naming its ticket number and the operator move valve
```

The revise pass that accepts this proposal MUST co-edit tests/heading-coverage.json with one entry for the new Scenario 325 heading; its `test` MAY be the literal "TODO" with a non-empty `reason`. If Scenario 325 is taken by an earlier revise, the revise pass MUST use the next free scenario number and update the harness paragraph's reference to match.
