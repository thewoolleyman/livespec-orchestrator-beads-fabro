---
topic: acp-turn-stop-reason-recorded
author: claude-opus-5-5
created_at: 2026-10-26T20:42:46Z
---

## Proposal: Record every ACP turn's stop reason in the run event stream and stage outcome

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Require the engine to record each ACP turn's session/prompt stop reason on the step-closing run event and in each ACP stage's outcome record, with an explicit absent marker when none is returned, so that refusals and turn or token ceilings stay distinguishable from end_turn in a run export. Add Scenario 253 to state the behaviour, and co-edit the heading-coverage map.

### Motivation

Today the Petri engine's AcpClient::prompt matches the session/prompt stopReason and then drops it: struct Turn carries only text, so end_turn and refusal are booked identically and a triager reading fabro inspect or fabro dump cannot tell why a turn ended. On bd-ib-3kqdln's run the implement step was booked success and the failure surfaced only later, invisible where a triager first looks. stop_reason rides only the OTel run_turn span (bd-ib-98c.7), never the run events. Per-run facts belong in the Fabro run event stream and stage outcome records, not in the Dispatcher's dispatch journal (dispatch-control-plane guidance, 2026-10-25). This is the spec-change slice of the bd-ib-odi6dr groom cut, approved by the fleet coordinator on 2026-10-26; the engine implementation is bd-ib-rmaxqf, which waits on this revision. Source reading: plan fabro-currency research note 014.

### Proposed Changes

Add a new H2 to `SPECIFICATION/contracts.md`, placed immediately after `## ACP node timeouts` and before `## Provider-limit permanence and root-cause surfacing`:

```markdown
## ACP turn stop reasons are recorded

Every ACP turn of a factory run ends with the stop reason the agent's
`session/prompt` response returns (for example `end_turn`, `max_tokens`,
`max_turn_requests`, `refusal` or `cancelled`). The engine MUST record that
stop reason, verbatim, on the run event that closes the step the turn belongs
to, and every ACP stage's outcome record, as `fabro inspect` and `fabro dump`
render it, MUST carry the stop reason of that stage's last turn. A turn whose
response carries no stop reason MUST be recorded with an explicit absent
marker rather than with a substituted default, so a missing value is
distinguishable from a reported `end_turn`.

A turn that ended with `refusal`, or with a turn or token ceiling, MUST stay
distinguishable from one that ended with `end_turn` in the run's own export,
whatever outcome the stage was booked with. The stop reason is a per-run fact:
it MUST be recorded in the run event stream and the stage outcome record, and
the Dispatcher's dispatch journal MUST NOT be extended to carry it. The stop
reason MUST NOT carry, or be derived from, any environment value or resolved
credential.
```

Add a new scenario to `SPECIFICATION/scenarios.md`, after Scenario 252:

```markdown
## Scenario 253 — A run export distinguishes a refused ACP turn from a completed one

```gherkin
Feature: An ACP turn's stop reason survives into the run's own record
  As a triager reading a factory run export
  I want each ACP turn's stop reason recorded where the step ends
  So that a refusal or a ceiling is not read as a normal turn end

  Scenario: Each ACP step records its turn's stop reason
    Given a factory run with two ACP stages
    And the first stage's agent ends its turn with stop reason end_turn
    And the second stage's agent ends its turn with stop reason refusal
    When the run is exported with fabro dump
    Then the event closing the first stage's step records stop reason end_turn
    And the event closing the second stage's step records stop reason refusal
    And each stage's outcome record carries its last turn's stop reason

  Scenario: A response with no stop reason is recorded as absent
    Given a factory run whose ACP agent answers session/prompt without a stopReason field
    When the run is exported with fabro dump
    Then that step's closing event records the stop reason as absent
    And the export does not record end_turn for that turn
```
```

Co-edit `tests/heading-coverage.json` in the same revision with two entries, each `test: "TODO"` with a non-empty reason naming the owning engine work-item: one for `## ACP turn stop reasons are recorded` (`spec_file: contracts.md`) and one for `## Scenario 253 — A run export distinguishes a refused ACP turn from a completed one` (`spec_file: scenarios.md`). The reason MUST say that the exercising proof is a host-captured gmktec run on a Petri engine build carrying `bd-ib-rmaxqf`, since no factory sandbox runs the engine.
