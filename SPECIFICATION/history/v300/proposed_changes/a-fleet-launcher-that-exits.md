---
topic: a-fleet-launcher-that-exits
author: claude-opus-5-5
created_at: 2026-11-05T00:54:13Z
---

## Proposal: a-fleet-launcher-that-exits

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A committed fleet-launch launcher that ends without its run listing writes one terminal line to its own output naming the item, its ticket number and the exit cause, before its exit removes the ticket. If the item still reads ready, the launcher either re-takes the ticket at the same ticket number or appends a ledger comment naming the dropped ticket and the cause. A ready-set refusal is retried for a bounded number of polls before the launcher gives up. A queue reader that finds a ticket whose launcher pid is dead reports a stall line instead of skipping or deleting it silently. This generalizes the two narrow logging rules §"Provisional fleet launch scripts" states today: the max-wait give-up line and the early-exit re-ticket stop line.

### Motivation

Linked work item: bd-ib-rk7mbd (absorbs bd-ib-3mhh5r), routed by legacy-coordinator-agent under R301 on 2026-11-05 and owned by plan gmktec-factory-placement. Its spec-change-tier screen (spec v299) found that §"Provisional fleet launch scripts" states only two narrow pieces of exit reporting. A launcher that gives up at FLEET_LAUNCH_MAX_WAIT_S logs the item and queue ticket. A launcher whose drive exits non-zero before its run lists re-takes its ticket, and logs the item and exit code if it stops. The section states no terminal line for any other non-run exit (a TERM or INT signal, a hold or WIP yield wait that ends, a ready-set refusal, a failed preflight). It states no ledger-comment alternative to re-taking a ticket, no bounded ready-set retry, and no stall report for a dead-pid ticket. Measured on 2026-11-04 on the interim launcher that the committed fleet-launch/ scripts replace at the bd-ib-x7bwug cutover: launchers for bd-ib-5d5aue, bd-ib-k4ltmr, bd-ib-welwbc, bd-ib-dqxcsh, bd-ib-rpit5z and livespec-dev-tooling-ifhymw stopped between 19:11Z and 19:15Z while yielding on a red-master repository hold. bd-ib-weawfe and bd-ib-j6rbdx stopped between 18:57Z and 19:07Z. livespec-dev-tooling-243dzr, mauiu5, 22wpdk and bd-ib-s5idxj were lost the same way earlier. Each sequence log simply stops mid-wait, with no terminal line, no run and no ledger record. The EXIT trap deleted each ticket file, so the queue showed nothing, and every loss surfaced only when an owning seat noticed hours later. The committed scripts share the shape. dispatch-dual.sh's and resume-capped.sh's EXIT traps drop the ticket with no terminal line, and both trap TERM and INT straight to exit 143. dispatch-dual.sh's ready-set refusal exits 3 at once. oldest_live_ticket() in dispatch-dual.sh deletes a dead-pid ticket silently, and resume-capped.sh's head scan skips one with `kill -0 ... || continue`.

### Proposed Changes

In SPECIFICATION/contracts.md §"Provisional fleet launch scripts":

1. Append the following to the sentence that ends "...a launcher that gives up waiting at that bound MUST log the work-item id it was launching and the queue ticket it held.":

"That log line is the launcher's terminal line, defined below, with the cause `max-wait`."

2. Replace the bullet **Early-exit re-ticket** with:

"- **Early-exit re-ticket.** A launcher whose `drive --action impl:<item>` or `resume --item <item>` exits non-zero before the launched run lists on its factory board MUST re-take a FIFO ticket for the same work item, at the same ticket number, and pass every gate again, rather than dropping the item from the queue. A launcher MAY bound how many times it re-takes a ticket for one work item. When it stops re-taking, it exits without a run, and the rules for a non-run exit below apply, with a cause that names the drive's exit code."

3. After the list of caller-side gates and before the paragraph that begins "`just check` MUST run a `check-fleet-launch` target", add the following subsection text:

"Every committed `fleet-launch/` launcher, impl or resume, MUST account for every exit it makes before its launched run lists on its factory board (a *non-run exit*). A launcher's *ticket number* is the ordering key in its FIFO ticket's file name, the part that fixes its FIFO order. A launcher's *sequence log* is its own standard output, which the caller that starts it captures to a per-launch log file.

- **Terminal line.** On every non-run exit for a trappable cause, a launcher MUST write exactly one terminal line to its sequence log. The line MUST name the work-item id, the ticket number it held (or `none` when it never took one) and the exit cause. The trappable causes include a TERM or INT signal, a hold or WIP yield wait that ends, a ready-set refusal (including a give-up after the bounded retries below), a failed launch-time preflight, a drive or resume that exits before its run lists, and the `max-wait` give-up. The launcher MUST write the terminal line before its exit removes its FIFO ticket file. It MUST also write it before any ledger read or write it makes on that exit, so that an exit cut short after the line still leaves the line. A launcher that is killed by a signal it cannot trap writes no terminal line; that case is covered by the stall report below.
- **Ready item never silently dropped.** A launcher that makes a non-run exit while its work item still reads `ready` in the ledger MUST do one of two things. It either re-takes its FIFO ticket at the same ticket number, or it appends one ledger comment to the work item naming the dropped ticket number and the exit cause. A launcher exiting on a TERM or INT signal MUST NOT re-take its own ticket, because it is ending. It MUST append the comment unless it can establish that a successor launcher already holds a ticket at the same ticket number for that work item. That comment MUST describe the drop as a dropped or lost ticket. It MUST NOT state or imply that the work item is held by its owner, though it MAY name a repository hold file as the exit cause. A screen that reads ledger comments for owner holds before it issues a ticket would otherwise refuse the item's next ticket. If the comment cannot be appended, the launcher MUST write a second line to its sequence log saying the comment failed and why. The launcher MUST NOT change the work item's status on such an exit.
- **Bounded ready-set retry.** A launcher whose ready-set check refuses its work item MUST NOT exit at once. It MUST re-run that check on each of its next polls, up to `FLEET_LAUNCH_READY_RETRY_POLLS` polls, a host value assigned in `fleet-launch/config.sh` and overridable like any other. While it retries, it MUST keep any FIFO ticket it holds, and MUST NOT hold the factory mutex or a fleet in-flight marker. It MUST yield the FIFO head as a held launcher does. A refusal that clears within those polls MUST let the launcher take its FIFO place back, in the order of the ticket it kept. A launcher that gives up after those polls MUST name the work-item id, the last refusal reason and the number of polls it tried. It MUST do so both in its terminal line and in the ledger comment of the previous bullet, when that comment is owed. The retry asks the Dispatcher's own ready set again; it is not an admission decision, and it does not change any admission condition the Dispatcher owns.
- **Dead-pid ticket is a stall.** Any launcher code that reads a per-factory FIFO directory (a *queue reader*) and finds a ticket file whose launcher pid is no longer alive MUST report that ticket as a stall. It MUST write a stall line to its own output naming the work-item id, the ticket number and the dead pid. It MUST do so the first time it finds that ticket, and MUST NOT skip the ticket silently. A queue reader MAY remove the dead ticket after it has reported it, and MUST NOT remove it before."

4. After the paragraph that begins "The `check-fleet-launch` harness cases MUST also cover the shared WIP claim-count cache", add:

"The `check-fleet-launch` harness cases MUST also cover non-run exits. An impl launcher and a resume launcher that each receive TERM while yielding on a repository hold MUST write a terminal line naming the item, the ticket number and the signal before their ticket file is removed. A launcher whose item still reads `ready` at a non-run exit either re-takes its ticket at the same ticket number or appends a ledger comment naming the dropped ticket number and the cause, and that comment does not state that the item is held by its owner. A ready-set refusal that clears within `FLEET_LAUNCH_READY_RETRY_POLLS` polls keeps the launcher's ticket and launches. A refusal that persists past those polls ends with a terminal line and a ledger comment, each naming the last refusal reason and the number of polls tried. A queue reader that meets a ticket whose launcher pid is dead writes a stall line naming the item, the ticket number and the dead pid before it removes or skips that ticket."

In SPECIFICATION/scenarios.md, add a scenario titled "Scenario NN — A fleet launcher that exits without a run leaves a terminal line, and its ready item's ticket is re-taken or reported", where NN is the next free scenario number at revise time. It MUST begin with "Governing clause: `contracts.md` §\"Provisional fleet launch scripts\"." and carry a gherkin block covering four cases:

- Given a launcher for bd-x holding ticket T while yielding on a repository hold file, When it receives TERM, Then its sequence log ends with one terminal line naming bd-x, T and the signal, written before T's file is removed. And because bd-x still reads ready, either a successor holds T or bd-x carries a ledger comment naming T and the cause.
- Given a ready-set check that refuses bd-x for fewer than `FLEET_LAUNCH_READY_RETRY_POLLS` polls and then admits it, When the launcher polls, Then it keeps its ticket and launches bd-x.
- Given a ready-set check that refuses bd-x on every poll, When the launcher exhausts `FLEET_LAUNCH_READY_RETRY_POLLS` polls, Then its terminal line and a ledger comment on bd-x each name the last refusal reason and the number of polls tried.
- Given a ticket file in a FIFO directory whose launcher pid is dead, When another launcher reads that FIFO, Then it writes a stall line naming the item, the ticket number and the dead pid before it removes or skips the ticket.

The co-edit of tests/heading-coverage.json belongs in the same revise pass, together with its debt-register row. It adds one entry for the new scenario heading. That entry's `test` MAY be the literal "TODO", with a `reason` naming the integration tier and work item bd-ib-rk7mbd as the owner of the owed test.
