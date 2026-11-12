---
topic: fleet-launchers-log-and-retry
author: claude-opus-5-5
created_at: 2026-11-12T17:40:00Z
---

## Proposal: A fleet launcher re-reads an unreadable status before skipping its dropped-ticket comment, logs the skip, comments only on a ready item, and ends promptly on TERM

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Provisional fleet launch scripts" already requires one terminal line on every trappable non-run exit, and one dropped-ticket comment when the item still reads `ready`. It does not say what a launcher does when that status read FAILS. It does not forbid the comment while the item reads anything other than `ready`. And it does not bound how long a TERM takes to end a launcher that is mid-sleep. This proposal adds those four rules and cites the existing two rather than restating them.

### Motivation

Work item bd-ib-7itf42, a child of plan bd-ib-ynnykl (legacy-dispatcher-agent), routed to this seat for its deposit by legacy-coordinator-agent (session 959b2f8b) on 2026-11-12. Its launch was refused as a genuine spec-change partial under `## Provisional fleet launch scripts`; the refusal rationale and the measured instances are on the item. The topic is the item's linked stem, so the hold links without a relink.

The terminal-line rule (the "Terminal line." bullet) and the dropped-ticket rule (the "Ready item never silently dropped." bullet) are already stated, and Scenario 312 exercises them. What they leave open:
- A single failed status read today decides the comment silently. One transient ledger error then reads like "not ready", and the item's ticket is lost without a trace.
- Nothing forbids a comment on an item that has left `ready`, which would mislead the owner-hold screen.
- A TERM during the poll sleep waits out the sleep, so a seat that stops its launchers waits up to a full poll interval for each.

Design choices, stated for the grade:
- **Exactly one retry.** A second read separates a transient error from a real outage without delaying the exit.
- **The skip is logged, not guessed.** When both reads fail, the launcher neither comments nor stays silent. It writes one line saying the comment was skipped and why, which is the existing stall report's evidence.
- **A bound, not a mechanism.** "Well under the poll interval" is stated as a bound, so an implementation may interrupt the sleep however it likes.

Fleet scope: every committed `fleet-launch/` launcher, impl and resume. livespec-orchestrator-git-jsonl has no `fleet-launch/` launchers. In-flight alignment, all `align`: this seat's concurrent-git-fetches-into-one proposal adds a fetch lock to the same section without touching the non-run exit rules. #5058, #5060, #5067 and #5068 do not touch launchers.

### Proposed Changes

**1. The unreadable-status, non-ready and TERM rules (`contracts.md` §"Provisional fleet launch scripts").** After the bullet beginning "**Ready item never silently dropped.**", add:

> - **Status read on a non-run exit.** This bullet governs only the exits on which the dropped-ticket comment depends on the "Ready item never silently dropped" rule. An exit on which another bullet of this section requires that comment unconditionally, such as the host-only and goal-template exits, appends it as that bullet states, whatever the status reads. Whether a launcher owes the one ledger comment that "Ready item never silently dropped" prescribes is decided on the work item's ledger status. When a launcher's read of that status fails on a non-run exit, it MUST read the status once more before deciding. When both reads fail, it MUST NOT append the dropped-ticket comment, and MUST write one line to its sequence log saying the dropped-ticket comment was skipped because the item's status could not be read, naming the work item and its ticket number. That line follows the terminal line of the "Terminal line" bullet and does not replace it. When a read returns any status other than `ready`, the dropped-ticket rule adds no comment. A comment another bullet of this section requires on that exit, such as the move-valve comment of a stopped-after-admission exit, is unaffected.
> - **TERM during the poll sleep.** A TERM or INT signal that reaches a launcher while it sleeps between polls MUST end the sleep. The launcher then makes its signal exit, terminal line first, within a bound well under its poll interval, rather than after the sleep would have ended.

> The `check-fleet-launch` harness cases MUST also cover these two bullets, beside the existing launch-error and exactly-one-terminal-line cases of the non-run exit rules: a status read that fails once and then reads `ready`, which appends one dropped-ticket comment; two failed reads, which append none and write the skip line; a non-`ready` status, which adds no dropped-ticket comment; and a TERM during the poll sleep, which exits well within the poll interval.

**2. Scenario (`scenarios.md`).** Append the scenario below, numbered at revise time.

## Scenario <number assigned at revise> — A fleet launcher retries an unreadable status, logs a skipped dropped-ticket comment, comments only on a ready item, and ends promptly on TERM

```gherkin
Feature: a launcher's non-run exit is accounted for even when the ledger misreads
  Scenario: a failed first status read is retried
    Given a launcher making a non-run exit whose first read of its item's status fails
    When the second read returns ready
    Then the launcher appends exactly one dropped-ticket comment, as the ready-item rule requires

  Scenario: two failed status reads skip the comment and say so
    Given a launcher making a non-run exit whose two reads of its item's status both fail
    When the launcher exits
    Then its sequence log holds its terminal line
    And one further line saying the dropped-ticket comment was skipped because the item's status could not be read
    And the item gains no dropped-ticket comment

  Scenario: a non-ready item gets no dropped-ticket comment
    Given a launcher making a non-run exit while its item reads a status other than ready
    When the launcher exits
    Then its sequence log holds its terminal line
    And the item gains no dropped-ticket comment

  Scenario: a failed first read followed by a non-ready read adds no dropped-ticket comment
    Given a launcher making a non-run exit whose first read of its item's status fails
    When the second read returns a status other than ready
    Then the item gains no dropped-ticket comment

  Scenario: TERM during the poll sleep ends the launcher promptly
    Given a launcher with FLEET_LAUNCH_POLL_S set to 60, sleeping between polls, whose item reads ready
    When a TERM signal reaches it
    Then it exits within 5 seconds of the signal
    And its terminal line names the signal
    And the item gains one dropped-ticket comment naming the signal
```

**3. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading. The row is carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit, with `test: "TODO"`, `work_item: "bd-ib-7itf42"`, and a non-empty `reason` naming integration or above as the owed test's tier. It also adds one matching `tests/heading-coverage-debt.json` entry. The row, the entry and any scenario reference MUST carry the heading as numbered at revise.
