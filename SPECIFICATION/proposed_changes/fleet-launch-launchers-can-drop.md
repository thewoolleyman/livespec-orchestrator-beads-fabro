---
topic: fleet-launch-launchers-can-drop
author: claude-opus-5-5
created_at: 2026-11-13T23:59:21Z
---

## Proposal: fleet-launch-launchers-can-drop

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A committed fleet-launch launcher, impl (`dispatch-dual.sh`) or resume (`resume-capped.sh`), that receives SIGINT or SIGHUP before its run lists exits with status 128 plus the signal number (130 for INT, 129 for HUP) and leaves one terminal line whose cause names that signal. This holds wherever the signal lands, including while the launcher is evaluating a command substitution under bash 5.2. HUP joins TERM and INT as a named trappable signal cause. The `check-fleet-launch` harness covers each launcher and each of the two signals landing during a command substitution, and Scenario 312 gains the matching cases.

### Motivation

Work item bd-ib-pyughi (fleet-launch launchers can drop or mis-record SIGHUP and SIGINT on bash 5.2) was refused at the dispatch spec tier (exit 5) as held for this linked proposed-change topic. Its spec-stated judgement graded the asked-for behaviour PARTIAL and named §"Provisional fleet launch scripts" as the heading to generalize. The rationale: the "Terminal line" bullet requires one terminal line naming the exit cause on every trappable non-run exit and names TERM and INT among the causes, but the ratified text does not state the 129/130 exit statuses, does not name HUP as a cause, and does not require that this hold when the signal lands during a command substitution on bash 5.2. The fleet coordinator (legacy-coordinator-agent) ruled at about 23:55Z on 2026-11-13 that the dispatcher seat, which owns the launcher topics, draft this proposal, since no proposal under this topic existed and the hold could never end.

The defect, measured 2026-11-13 by seat ci-runtime-and-cost: on bash 5.2 a string trap action fails to parse when its signal lands while bash is parsing a `$(...)` command substitution (`trap: line 2: unexpected EOF while looking for matching ')'`). bd-ib-ekrfg5 (PR #4939) fixed the TERM half; the INT and HUP string traps in `fleet-launch/dispatch-dual.sh` and `fleet-launch/resume-capped.sh` carry the same parse failure, so a real launcher can drop or mis-record a HUP or INT: it neither records the signal nor exits with 128+N. The delegated pre-push gate 20261113T213038Z-2430589 failed `check-fleet-launch` case 23 this way (`impl did not record HUP as signal HUP (rc=1)`).

This proposal states only the behaviour bd-ib-pyughi's Definition of Done asserts: the 129/130 exit statuses, the signal-named terminal line, both launchers, and delivery during a command substitution on bash 5.2. It does not prescribe how the launchers install their handlers. Linked work item: bd-ib-pyughi.

### Proposed Changes

**1. `SPECIFICATION/contracts.md` §"Provisional fleet launch scripts", the "Terminal line" bullet.** In the sentence "The trappable causes include a TERM or INT signal, a hold or WIP yield wait that ends, ...", replace "a TERM or INT signal" with "a TERM, INT or HUP signal". Then, immediately after the sentence "It MUST also write it before any ledger read or write it makes on that exit, so that an exit cut short after the line still leaves the line.", insert:

> A launcher that makes a non-run exit on an INT or HUP signal MUST exit with status 128 plus that signal's number, 130 for INT and 129 for HUP, and its terminal line's exit cause MUST name that signal. This MUST hold for the impl launcher `dispatch-dual.sh` and the resume launcher `resume-capped.sh` wherever the signal lands, including when the launcher runs under bash 5.2 and the signal arrives while it is evaluating a command substitution.

The rest of the bullet, including the closing sentence on a signal the launcher cannot trap, is unchanged.

**2. `SPECIFICATION/contracts.md` §"Provisional fleet launch scripts", the paragraph that begins "The `check-fleet-launch` harness cases MUST also cover non-run exits."** Immediately before that paragraph's final sentence, "Scenario 312 in `scenarios.md` exercises these cases.", insert:

> An impl launcher and a resume launcher that each receive HUP while evaluating a command substitution MUST exit with status 129 and leave a terminal line whose cause is signal HUP, and each that receives INT while evaluating a command substitution MUST exit with status 130 and leave a terminal line whose cause is signal INT. These cases MUST run under bash 5.2 and MUST land the signal during a `$(...)` command substitution, repeated over enough attempts that a launcher whose signal handling fails to parse when the signal lands there is caught.

**3. `SPECIFICATION/scenarios.md`, "## Scenario 312 — A fleet launcher that exits without a run leaves a terminal line, and its ready item's ticket is re-taken or reported".** Inside that scenario's existing `gherkin` block, after the scenario "A launcher stopped by TERM while yielding leaves a terminal line and reports its dropped ticket" and before "A ready-set refusal that clears within the retry bound keeps the ticket", add this Scenario Outline. The heading is unchanged, so `tests/heading-coverage.json` MUST NOT change for this edit:

```gherkin
  Scenario Outline: A launcher signalled while evaluating a command substitution exits 128+N and names the signal
    Given the <launcher> launcher for bd-x running under bash 5.2
    And the launcher is evaluating a command substitution
    When the launcher receives <signal>
    Then it exits with status <status>
    And its sequence log ends with one terminal line naming bd-x, its ticket number or none, and the <signal> signal

    Examples:
      | launcher         | signal | status |
      | dispatch-dual.sh | HUP    | 129    |
      | dispatch-dual.sh | INT    | 130    |
      | resume-capped.sh | HUP    | 129    |
      | resume-capped.sh | INT    | 130    |
```

No other clause of the section changes. In particular, the "Ready item never silently dropped" bullet, the TERM behaviour, and every gate bullet are untouched.
