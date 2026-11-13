---
topic: a-fleet-launcher-screens-an
author: claude-opus-5-5:spec-implementation-lockstep
created_at: 2026-11-13T20:10:12Z
---

## Proposal: A fleet launcher screens its item against the spec-change tier hold before it takes a launch ticket

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Provisional fleet launch scripts" gives a launcher one caller-side screen for an item no factory may run: the host-only screen. That screen gets its verdict from the Dispatcher and runs before the mutex and the preflight. The section states no equivalent screen for the spec-change tier hold. So a tier-held item takes a FIFO ticket, waits its turn in the queue, takes a mutex turn and passes the launch-time preflight. Only then does `drive` refuse it with exit 5. This proposal adds a **Spec-change tier screen** bullet modelled on the host-only screen, with one difference: it runs BEFORE the launcher takes its FIFO ticket, so a held item never holds a queue place. The verdict comes from the Dispatcher's `tier-screen` command (the second proposal in this file) and is never re-derived in shell. The screen is a caller-side gate, and the Dispatcher's own refusal stays authoritative. It applies to every committed launcher whose launch passes the pre-dispatch wall's spec-change-tier row, and to every target repository, under that repository's credential wrapper.

### Motivation

Work item bd-ib-kix22a (plan bd-ib-ax3rds), routed by legacy-coordinator-agent on 2026-11-13. The plan owns tier judgement and re-roll. drive refused the item itself with exit 5 at 20:03:35Z. Its tier record names verdict `unstated`, generalization target `## Provisional fleet launch scripts` and linked topic `a-fleet-launcher-screens-an`. A clause release does not fit: the section states no pre-ticket tier screen, and adding one is new launcher behaviour.

Measured cost on 2026-11-13: nine launches each took a ticket, a queue wait, a mutex turn and a full pre-launch pass, and were then refused at the spec-change tier. The items were bd-ib-szbxu7, bd-ib-2it27f, bd-ib-vzfxlg, bd-ib-qnucbe (twice), bd-ib-kzkqf4, bd-ib-5qa6eb, bd-ib-tyeslt and bd-ib-kix22a. Earlier the same day, bd-ib-qshcwc, bd-ib-3h7dsf and bd-ib-yw7yot were refused the same way (hold reason `unratified-topic`). Each refused pass held a fleet slot's mutex turn while the fleet was at cap. Neither the committed `fleet-launch/dispatch-dual.sh` nor `fleet-launch/ready-set-check.py` contains any tier check.

Fleet scope: every committed launcher, on every factory it targets, and every tenant it launches into.

### Proposed Changes

**1. `SPECIFICATION/contracts.md` §"Provisional fleet launch scripts".** Insert this bullet immediately BEFORE the **Host-only screen** bullet:

> - **Spec-change tier screen.** A launcher whose launch passes the spec-change-tier row of the Dispatcher's pre-dispatch wall (an impl launcher's `drive --action impl:<item>`, and any other committed launcher whose Dispatcher path that row guards) MUST screen its work item against the spec-change tier hold BEFORE it takes its FIFO ticket, and so before any factory mutex, launch-time Definition-of-Done preflight or `drive`. It MUST screen again before every re-take of a ticket under **Early-exit re-ticket**. The launcher MUST obtain the verdict from the Dispatcher, through `dispatcher.py tier-screen --repo <path> --item <work-item-id> --json` (§"Dispatcher tier-screen invocation surface"). It MUST NOT re-implement the hold in shell, and MUST NOT read tier records, proposal topics or the spec history itself. When the verdict reads `held: true`, the launcher MUST make a non-run exit, and MUST NOT take or re-take a ticket for that work item. The exit's terminal line MUST name the work item, the ticket number it held (`none` when it never took one) and the cause `spec-change-tier`, followed by the verdict's hold `reason` and its `linked_proposal_topic`. The launcher MUST append the one ledger comment that **Ready item never silently dropped** prescribes, naming the dropped ticket number (or `none`), the cause `spec-change-tier`, the hold reason and the linked topic. A screen that cannot answer (a non-zero exit, or output that is not one JSON object carrying a boolean `held`) MUST NOT be read as `held: false`. The launcher MUST then log one line saying the tier screen could not answer, and proceed to take its ticket and continue to its next gate, where the Dispatcher's own refusal still applies. A verdict of `held: false` MUST leave the launcher's path unchanged: it takes its ticket and proceeds exactly as it would without the screen. This screen is a caller-side gate under this section's first paragraph. It MUST NOT stand in for the Dispatcher's spec-change-tier refusal, which remains authoritative, and a `drive` that still exits `5` is handled as a permanent refusal exactly as today.

**2. Same section, **Tenant credential wrapper** bullet.** In the sentence beginning "Launch-time commands include", insert `the spec-change tier screen,` immediately before `the host-only screen`, so the screen runs under the target repository's committed `credential_wrapper` like every other launch-time command.

**3. Same section, harness paragraph.** Immediately after the paragraph that begins "The `check-fleet-launch` harness cases MUST also cover the host-only screen and permanent refusals", insert:

> The `check-fleet-launch` harness cases MUST also cover the spec-change tier screen. With a stub `tier-screen` that reports the item `held: true` with reason `unratified-topic` and a linked topic, an impl launcher MUST exit without ever creating a FIFO ticket file. It MUST also take no mutex and run no preflight or drive, write one terminal line naming the item, ticket `none`, the cause `spec-change-tier`, the reason and the topic, and append one ledger comment naming the same. With a stub that reports `held: false`, the launcher MUST take its ticket and reach its stub drive. With a stub that exits non-zero, the launcher MUST log the unanswered screen, take its ticket and reach its stub drive, and a stub drive that then exits `5` MUST still end with a `refused` terminal line and no re-taken ticket. The new scenario in `scenarios.md` exercises these cases.

**4. `SPECIFICATION/scenarios.md`.** Append the scenario below, numbered at revise time:

```gherkin
## Scenario <number assigned at revise> — A fleet launcher screens its item against the spec-change tier hold before it takes a launch ticket

Governing clause: `contracts.md` §"Provisional fleet launch scripts".

Feature: A committed fleet-launch launcher spends no queue place on an item the spec-change tier holds
  Background:
    Given fleet-launch/config.sh values overridden to stub factory boards, a stub Dispatcher, a stub ledger that records comments, and throwaway queue, lock, in-flight and state directories

  Scenario: A tier-held item exits before it takes a ticket
    Given an impl launcher for bd-x
    And the stub Dispatcher's tier-screen command reports bd-x held true with reason unratified-topic and linked topic a-topic
    When the launcher starts
    Then no FIFO ticket file for bd-x is ever created
    And it takes no factory mutex, runs no launch-time preflight and invokes no drive
    And its sequence log ends with one terminal line naming bd-x, ticket none, the cause spec-change-tier, unratified-topic and a-topic
    And the stub ledger records one comment on bd-x naming ticket none, spec-change-tier, unratified-topic and a-topic

  Scenario: An item the tier does not hold proceeds exactly as before
    Given an impl launcher for bd-x whose stub tier-screen reports held false
    When the launcher starts
    Then it takes its FIFO ticket and reaches its stub drive

  Scenario: A tier screen that cannot answer does not admit or refuse the item
    Given an impl launcher for bd-x whose stub tier-screen exits 1
    And whose stub drive exits 5 writing "REFUSED: work-item bd-x is spec-change tier"
    When the launcher starts
    Then its sequence log carries one line saying the tier screen could not answer
    And it takes its FIFO ticket and reaches its stub drive
    And its sequence log ends with one terminal line naming bd-x, its ticket number and the cause refused
    And no launcher re-takes a ticket for bd-x
```

**5. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading (`test` MAY be `"TODO"` with a non-empty `reason`).

**In-flight alignment.** This proposal ALIGNS with the pending proposals that edit the same section: `a-committed-single-item-operator` (#5120), `fleet-launchers-log-and-retry` (#5073), `concurrent-git-fetches-into-one` (#5072), and the pending master files `a-fleet-launcher-holds-its`, `a-fleet-launcher-honours-a`, `check-fleet-launch-sub-case`, `each-gmktec-fabro-server-s`, `each-gmktec-fabro-server-s-2`, `the-committed-fleet-launch-launcher`, `the-fleet-launcher-reports-a`, `the-fleet-launcher-serializes-each` and `the-launcher-holds-one-wip-number`. None of them adds a tier screen. Because the bullet's scope is stated by Dispatcher path rather than by script name, it covers `override-item.sh` if #5120 is ratified, without either proposal depending on the other's order.

## Proposal: The Dispatcher answers the pre-dispatch wall's spec-change tier verdict for one item without dispatching it

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Today the only way to learn whether the pre-dispatch wall's spec-change-tier row would refuse an item is to dispatch it. `drive`'s tier judgement runs only inside a dispatch, and `classify-tier` (§"Dispatcher classify-tier invocation surface") records a tier for plan-child disposition but reports neither the hold nor the wall's variant exemption. This proposal adds a read-and-judge Dispatcher subcommand, `tier-screen`. It is a dry run of the wall's tier row: it runs the same composition for one named item and prints the verdict as one JSON object. It takes no claim, creates no run and changes no status. The fleet launcher's tier screen consumes it, and it is the tier verb canary screening needs.

### Motivation

Same work item and routing as the first proposal in this file (bd-ib-kix22a, plan bd-ib-ax3rds). legacy-coordinator-agent directed that the dry-run tier verb be folded in, because the gmktec-factory-placement canary screening also needs drive's tier judgement without a dispatch. The launcher screen in the first proposal needs a Dispatcher-owned verdict so that the launcher and the wall never disagree. That is the Definition of Done of bd-ib-kix22a: "The tier screen in the launcher uses the same predicate the Dispatcher's admission uses". The host-only screen gets its verdict the same way, through `dispatcher.py host-only`.

The hold read itself needs no model: `_spec_change_tier_hold.spec_change_hold` decides from the newest recorded classification and the ratified topics. But the wall's row CLASSIFIES first, under the reuse cap, so a dry run that only read the standing record would disagree with the wall whenever no current record exists. Taking the same reuse-capped classification and keeping the record means the drive that follows reuses it and pays no second judgement.

### Proposed Changes

**1. `SPECIFICATION/contracts.md`.** Insert a new H2 section immediately AFTER §"Dispatcher classify-tier invocation surface":

> ## Dispatcher tier-screen invocation surface
>
> The Dispatcher's `tier-screen` subcommand answers, for one named work item, the verdict the spec-change-tier row of the pre-dispatch wall would reach if that item were dispatched now, without dispatching it. Callers that decide WHEN to dispatch, such as a fleet launcher (§"Provisional fleet launch scripts") or a canary screen, use it so that they never re-derive the hold. Its governed CLI surface is:
>
> `tier-screen --repo <path> --item <work-item-id> [--workflow <name>] --json`
>
> - `tier-screen` MUST run exactly the composition the pre-dispatch wall's spec-change-tier row runs for the item: the same variant exemption for the workflow `--workflow` names (or the item's resolved workflow when it is omitted), then the same reuse-capped spec-stated classification, then the same hold read from the ledger and the governed spec history.
> - Its verdict MUST equal the wall's: for any item, ledger state and spec tree, `held` MUST be `true` exactly when a dispatch of that item through the same workflow would be refused at the spec-change-tier row.
> - It MUST NOT dispatch. It creates no Fabro run, takes no claim, and leaves the item's assignee, status and labels unchanged except as the hold already applies when a held spec-change tier is recorded, exactly as `classify-tier` states.
> - It MAY append at most one `livespec-spec-change-tier` record, with `stage: screen`, and only where the wall's own classification would append one at that point: the item carries no record, or its latest record's behaviour digest or spec identity differs from the current one. A record it appends MUST be reusable by a later dispatch under the existing reuse rule, so that the screen and the drive that follows take at most one judgement between them.
> - It MUST print one JSON object carrying `work_item_id`, `held` (boolean), `exempt` (boolean) and `classification` (`reused`, `recorded`, `did-not-run` or `exempt`). When `held` is `true`, the object MUST also carry `reason` (`no-linked-topic`, `unratified-topic` or `awaiting-rejudgement`), `linked_proposal_topic`, `verdict_kind`, `generalization_target` and `refusal`, the exact refusal text the wall would render.
> - When the classification cannot be obtained, it MUST answer from the standing record exactly as the wall does, reporting `classification: did-not-run`, and MUST exit `0`.
> - It MUST exit non-zero, printing no JSON object, when it cannot answer at all: the item is not in the tenant, the ledger cannot be read, or the repository's ledger connection cannot be resolved.

**2. `SPECIFICATION/scenarios.md`.** Append the scenario below, numbered at revise time:

```gherkin
## Scenario <number assigned at revise> — tier-screen reports the pre-dispatch wall's spec-change tier verdict for one item without dispatching it

Governing clause: `contracts.md` §"Dispatcher tier-screen invocation surface".

Feature: The Dispatcher answers the tier verdict a dispatch would reach, and dispatches nothing
  Scenario: A held item is reported held with the wall's refusal
    Given a ready work item bd-x whose latest spec-change tier record is current and links unratified topic a-topic
    When an operator runs dispatcher.py tier-screen --repo <path> --item bd-x --json
    Then it prints one JSON object with held true, reason unratified-topic, linked_proposal_topic a-topic and classification reused
    And its refusal field equals the REFUSED text dispatcher.py loop --item bd-x renders
    And no claim is taken, no factory run is created and no ledger comment is appended

  Scenario: An unclassified item is judged once and the record is reused by the dispatch
    Given a ready work item bd-y carrying no spec-change tier record
    When an operator runs dispatcher.py tier-screen --repo <path> --item bd-y --json
    Then exactly one livespec-spec-change-tier record with stage screen is appended
    And a following dispatch of bd-y takes no second judgement

  Scenario: An exempt variant takes no judgement
    Given a ready work item bd-z whose resolved workflow is the groom variant
    When an operator runs dispatcher.py tier-screen --repo <path> --item bd-z --json
    Then it prints held false, exempt true and classification exempt
    And no judgement is taken and no ledger comment is appended

  Scenario: An unreadable ledger is not an answer
    Given a repository whose ledger cannot be read
    When an operator runs dispatcher.py tier-screen against it
    Then it exits non-zero and prints no JSON object
```

**3. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new `## Dispatcher tier-screen invocation surface` heading and one for the new scenario heading (`test` MAY be `"TODO"` with a non-empty `reason`).

**In-flight alignment.** This proposal ALIGNS with `a-spec-change-tier-hold` (#5080) and `a-spec-change-tier-record` (#5068). Each changes what a tier record carries or how its topic is derived, and `tier-screen` inherits either change because it runs the wall's own composition rather than a copy. It also aligns with `a-fork-test-s-verdict-never` (#5084), which mentions the classifier only in its motivation.
