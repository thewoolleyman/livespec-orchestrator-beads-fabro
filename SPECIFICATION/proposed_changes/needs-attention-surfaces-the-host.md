---
topic: needs-attention-surfaces-the-host
author: claude:legacy-dispatcher-agent
created_at: 2026-11-12T14:36:27Z
---

## Proposal: needs-attention lists the host Codex credential when its status surface raises the alarm

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add an orchestrator-owned attention fact, hygiene:codex-credential:<host>, that needs-attention carries whenever the host's Codex credential status surface reports its alarm, naming the expiry instant, the required lifetime and the governing figure, present with or without any dispatch attempt, clearing on renewal, and never reading an unreadable status as healthy.

### Motivation

Work item bd-ib-652xab, filed by legacy-dispatcher-agent on legacy-coordinator-agent's routing (2026-11-12 ~14:15Z, from central-credential-service); its filing judgement recorded tier spec-change, verdict unstated, generalization target §"The skill surface". The specification surfaces a Codex renewal need only when the freshness gate refuses a dispatch (§"Worker credential projection"). Orchestrator 93fa0e272 retired the host refresh timer and made the pre-claim credential gate the normal renewal path, so on a host where no dispatch runs nothing reports a credential approaching expiry; the runbook's "On-demand credential-status alarm" is operator-invoked only. On 2026-11-12 the host Codex credential on vmi3006760 expires 2026-11-18T16:07Z with refresh_due=false, and no surface would list it as it nears the requirement. A runbook fact, recorded here for context only and deliberately NOT proposed as specification: the retirement step's state capture `~/.local/state/livespec/codex-cred-refresh-timer-before-retirement.txt` is absent on vmi3006760; that is a host action tracked on bd-ib-652xab, not a behaviour. In-flight survey 2026-11-12 ~14:45Z: five open spec PRs (#5054, reserving Scenario 356; #5050; #5048; #5035; #5005) and the stale revise branches; none touches the needs-attention attention facts or the credential status surface (align). Scenario 358 follows Scenario 357, which the concurrent a-single-shot-claim-writer proposal reserves.

### Proposed Changes

**1. A host-credential attention fact (`contracts.md` §"The skill surface" → "Orchestrator-owned attention facts").** After the paragraph that begins "**Workflow-edit approval (`hygiene:workflow-edit-approval:<work-item-id>`).**", add:

> **Host Codex credential renewal (`hygiene:codex-credential:<host>`).** When `needs-attention` runs on a host that holds the Codex worker credential the Dispatcher projects (§"Worker credential projection"), and that host's credential status surface reports its alarm — the credential's remaining lifetime does not exceed the freshness requirement for the dispatch selection the status surface grades — the snapshot MUST carry exactly one attention item naming the host, the credential's expiry instant, the required lifetime, and which of the two figures of §"Worker credential projection" governed that requirement, with a handoff naming the manual renewal surface. The fact MUST be computed from the same grading the freshness gate uses, MUST NOT re-derive the requirement, and MUST be present whether or not any dispatch has been attempted, so a factory with no dispatch in flight still shows a credential nearing expiry. It clears when the status surface no longer reports the alarm. A status read that fails MUST surface as a visible failure rather than as an absence of this fact. Scenario 358 in `scenarios.md` exercises this paragraph.

The freshness-gate sentence "When the freshness gate cannot be satisfied, the Dispatcher MUST refuse the dispatch and MUST surface that the host credential requires renewal" is unchanged; this fact adds the standing awareness surface beside that refusal.

**2. Scenario (`scenarios.md`).** Append:

## Scenario 358 — needs-attention lists the host Codex credential when its status surface raises the alarm, with no dispatch attempted

```gherkin
Feature: The host Codex credential's renewal need is visible without a dispatch
  Scenario: A credential nearing expiry is listed while the factory is idle
    Given a host that holds the Codex worker credential the Dispatcher projects
    And no dispatch has been attempted since the credential's remaining lifetime fell below the freshness requirement
    When needs-attention runs on that host
    Then the snapshot carries exactly one hygiene:codex-credential item for the host
    And the item names the credential's expiry instant, the required lifetime and the figure that governed it
    And its handoff names the manual renewal surface

  Scenario: The fact clears after renewal
    Given the snapshot carried a hygiene:codex-credential item for the host
    And the credential has since been renewed so that the status surface no longer reports the alarm
    When needs-attention runs on that host
    Then the snapshot carries no hygiene:codex-credential item

  Scenario: An unreadable status is not read as healthy
    Given the host's credential status surface cannot be read
    When needs-attention runs on that host
    Then the snapshot reports the status read as a visible failure
```

**3. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading (carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit) with `test: "TODO"`, `work_item: "bd-ib-652xab"` and a non-empty `reason` naming the tier the owed test runs at, and one matching `tests/heading-coverage-debt.json` entry carrying `work_item: "bd-ib-652xab"` and `first_seen` set to the revise date. If the revise renumbers Scenario 358, the row and entry MUST carry the renumbered heading text.
