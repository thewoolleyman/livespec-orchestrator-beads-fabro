---
topic: a-committed-fleet-launcher-screens
author: claude-opus-5-5:gmktec-factory-placement
created_at: 2026-11-05T05:52:21Z
---

## Proposal: A fleet launcher screens host-only items with the shared factory-safety routing predicate and never re-tickets a permanent refusal

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A committed fleet-launch launcher asks the Dispatcher's own shared factory-safety routing predicate whether its work item is host-only before it takes a factory mutex or runs its launch-time preflight, and exits without a run when it is. A launcher whose drive ends before listing with a permanent pre-dispatch refusal (exit code 5) does not re-take its FIFO ticket; it reports the drop on the item instead. The early-exit re-ticket rule keeps re-taking the ticket for every transient early exit.

### Motivation

Measured on bd-ib-dqxcsh on 2026-11-05 (bd-ib-v52w7a; legacy-coordinator-agent ruling R301). The item declares an edit under .github/workflows/ and carries no factory-safety label. A label-only launch screen passed it. drive then refused it as host-only at 05:35:51Z, and the launcher's early-exit handling re-took its ticket, because 'Early-exit re-ticket' mandates a re-take on every non-zero exit before listing. The launcher relaunched at 05:39:22Z, spending a mutex turn and a preflight on an item no factory may run, until an operator stopped it by pid. The screen and drive classified host-only on different inputs: the label versus the shared predicate's declared-workflow-edit heuristic. A permanent refusal also cannot be cleared by any number of re-takes.

### Proposed Changes

In contracts.md §"Provisional fleet launch scripts":

1. ADD a bullet beside the existing launcher gates:

- **Host-only screen.** Before it takes a factory launch mutex or runs its launch-time Definition-of-Done preflight, a launcher MUST evaluate the shared factory-safety routing predicate for its work item, the same predicate the Dispatcher's admission valve and the plan child audit's `HOST-ONLY` classification consume (a non-null `factory_safety`, or a declared edit under `.github/workflows/` that no `workflow-scope-override:citation-only` label overrides). The launcher MUST obtain that verdict from the Dispatcher, through `dispatcher.py host-only --repo <path> --item <work-item-id> --json`, and MUST NOT re-implement the predicate in shell. The Dispatcher MUST provide that command, and it MUST print one JSON object carrying `work_item_id`, `host_only` (boolean) and, when `host_only` is true, `reason`. When the verdict is host-only, the launcher MUST make a non-run exit whose terminal line names the work item, its ticket number and the cause `host-only`, MUST NOT re-take its ticket, and MUST append the one ledger comment that "Ready item never silently dropped" prescribes, naming the dropped ticket number and the host-only reason. A command that cannot answer MUST NOT be read as `host_only: false`: the launcher MUST then proceed to its next gate, where the Dispatcher's own refusal still applies. This screen is a caller-side gate under the section's first paragraph; it MUST NOT stand in for the Dispatcher's own host-only refusal, which remains authoritative.

2. MODIFY "Early-exit re-ticket" by appending: A drive or resume that exits with code `5` (§"Dispatcher exit codes": a permanent pre-dispatch refusal) is NOT an early exit for this rule. The launcher MUST NOT re-take its ticket for it, and MUST make a non-run exit whose terminal line names the work item, its ticket number and the cause `refused`, and MUST append the one ledger comment that "Ready item never silently dropped" prescribes, naming the dropped ticket number and the refusal line the Dispatcher wrote. Every other non-zero exit before listing remains an early exit and MUST still re-take the ticket at the same ticket number.

3. EXTEND the `check-fleet-launch` harness case list: the harness MUST cover a launcher whose stub `host-only` verdict is true, which exits before any mutex or preflight with a `host-only` terminal line and one ledger comment and re-takes no ticket; a launcher whose stub drive exits 5, which re-takes no ticket and leaves a `refused` terminal line and one ledger comment; and a launcher whose stub drive exits 1 before listing, which still re-takes its ticket at the same ticket number.

In scenarios.md, ADD:

## Scenario 314 — A fleet launcher screens a host-only item with the Dispatcher's predicate and never re-tickets a permanent refusal

Governing clause: `contracts.md` §"Provisional fleet launch scripts".

```gherkin
Feature: A committed fleet-launch launcher spends no launch slot on work no factory may run
  Background:
    Given fleet-launch/config.sh values overridden to stub factory boards, a stub Dispatcher, a stub ledger that records comments, and throwaway queue, lock, in-flight and state directories

  Scenario: A host-only item exits before the mutex and the preflight
    Given an impl launcher for bd-x holding FIFO ticket T
    And the stub Dispatcher's host-only command reports bd-x host_only true with reason "declares an edit under .github/workflows/"
    When the launcher reaches its host-only screen
    Then it takes no factory mutex and runs no launch-time preflight
    And its sequence log ends with one terminal line naming bd-x, T's ticket number and the cause host-only
    And the stub ledger records one comment on bd-x naming T's ticket number and the host-only reason
    And no launcher re-takes a ticket for bd-x

  Scenario: A drive refused with exit code 5 is not re-ticketed
    Given an impl launcher for bd-x whose stub drive exits 5 before any run lists, writing "REFUSED: work-item bd-x is held"
    When the drive exits
    Then the launcher re-takes no ticket for bd-x
    And its sequence log ends with one terminal line naming bd-x, its ticket number and the cause refused
    And the stub ledger records one comment on bd-x naming the dropped ticket number and the REFUSED line

  Scenario: A transient early exit still re-takes the same ticket
    Given an impl launcher for bd-x holding FIFO ticket T whose stub drive exits 1 before any run lists
    When the drive exits
    Then the launcher re-takes a FIFO ticket for bd-x at T's ticket number
```

## Proposal: Every permanent pre-dispatch refusal, the host-only refusal included, exits 5 with one REFUSED line

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The Dispatcher's factory-safety (host-only) refusal of a hand-picked dispatch joins the other permanent pre-dispatch refusals under exit code 5. Every exit-5 refusal writes exactly one stderr line beginning `REFUSED: ` that names the work item and the refusal, so a caller has one signal for 'no retry can clear this'.

### Motivation

Measured on 2026-11-05. bd-ib-rk7mbd's pre-dispatch Definition-of-Done refusal exited 5 with a `REFUSED:` stderr line. bd-ib-dqxcsh's host-only refusal exited 1, with the refusal carried only as a `host-only-refused` status inside the structured stdout. A caller that keys its retry decision on exit 5 therefore read the host-only refusal as transient and retried it. legacy-coordinator-agent ruled under R301 that the exit-code unification belongs in this same proposal: one signal for every permanent refusal is the consolidation.

### Proposed Changes

In contracts.md §"Dispatcher exit codes", REPLACE the `5` entry's opening "`5` — effective-criteria refusal:" with "`5` — permanent pre-dispatch refusal:", and APPEND to its list of causes: ", or the factory-safety routing predicate routed a hand-picked dispatch's work item to the host (a non-null `factory_safety`, or a declared edit under `.github/workflows/` that no `workflow-scope-override:citation-only` label overrides)". ADD after that entry: Every exit-`5` refusal MUST write exactly one line to stderr that begins with `REFUSED: `, names the work-item id, and states the refusal and its remedy. The structured outcome MUST still carry the refusal's own status (for example `host-only-refused`). A refusal that a later retry of the same invocation could clear MUST NOT use exit code `5`. A drain that skips a host-only item without a hand-picked `--item` is not a refusal and MUST NOT change its own exit code on that account.

In scenarios.md, ADD:

## Scenario 315 — A hand-picked dispatch of a host-only item is refused with exit code 5 and one REFUSED line

Governing clause: `contracts.md` §"Dispatcher exit codes".

```gherkin
Feature: Every permanent pre-dispatch refusal gives a caller one signal
  Scenario Outline: A hand-picked dispatch refused before any run exits 5
    Given a ready work item bd-x <shape>
    When an operator runs dispatcher.py loop --item bd-x
    Then no claim is taken and no factory run is created
    And the command exits with code 5
    And stderr carries exactly one line beginning "REFUSED: " that names bd-x

    Examples:
      | shape                                                             |
      | whose factory_safety is needs-host-secrets                        |
      | whose description declares an edit under .github/workflows/      |
      | whose pre-dispatch Definition-of-Done judgement rests it at needs-human |
```
