---
topic: factory-step-span-attributes
author: claude-opus-5-5
created_at: 2026-10-30T19:52:39Z
---

## Proposal: Every factory step emits one span that says why the step ended

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a contracts.md H2 'Factory step span attributes' requiring the factory to emit one span per step visit of a run. The span carries the correlation fields plus the facts that say why the step ended: the ACP stop reason, the last tool call and whether it completed, a gate step's verdict and failed targets, and the context tokens used against the context window. One Honeycomb query filtered by run id then answers 'why did each step end' without a run dump. Add a scenario and co-edit the heading-coverage map.

### Motivation

Coordinator gitops-fleet-capacity-monitoring ruled on 2026-10-30 that this proposal be filed for livespec-dev-tooling-ipcm33 ('Factory step telemetry: each step's span says why it ended'). That item's Definition of Done cannot carry a References line because no H2 in either the dev-tooling or the orchestrator spec governs per-step span attributes. The emitter lives on the factory path, which this repository's spec governs. Motivating case: item 3kqdln, run 01M5QW46JGG0, ended voluntarily partway through `just check` at 88% context, and learning that took a run dump with a special client. Today only the OTel run_turn span (bd-ib-98c.7) carries per-turn facts, and the Dispatcher's dispatch span carries only the correlation triple. The stop-reason attribute takes its value from the companion proposal acp-turn-stop-reason-recorded ('ACP turn stop reasons are recorded'), so the two land in the same revise batch and ipcm33 can carry one References line naming this heading.

### Proposed Changes

Add a new H2 to `SPECIFICATION/contracts.md`, placed immediately after `## ACP turn stop reasons are recorded` (proposed change acp-turn-stop-reason-recorded, ratified in the same batch):

```markdown
## Factory step span attributes

Every visit of every node of a factory run MUST emit exactly one step span
through the run's OTLP export route, parented under the dispatch span that
§"Bounded session waits and observable inventory" defines when the run
carries that dispatch's trace parent. The span MUST end when the step ends,
whatever outcome the step is booked with, so a failed, cancelled or
timed-out step still has its span.

Every step span MUST carry these attributes:

- `work.item.id` and `livespec.dispatch.id`, with the values the run's
  correlation labels carry;
- `fabro.run_id`, the run id;
- `fabro.node`, the node name, and `fabro.node.visit`, the 1-based visit
  count of that node within the run;
- `fabro.step.outcome`, the outcome the step was booked with;
- `fabro.step.duration_ms`, the step's wall duration as a non-negative
  integer.

A step span of an ACP node MUST additionally carry:

- `acp.model`, the model the turn ran on, and `acp.candidate.index`, the
  0-based index of the fallback-chain candidate that ran it;
- `acp.stop_reason`, the stop reason of the step's last turn, with the
  value §"ACP turn stop reasons are recorded" requires the engine to record,
  including its explicit absent marker;
- `acp.last_tool.name`, the name of the last tool call the agent made in the
  step, and `acp.last_tool.state`, one of `completed`, `failed` or
  `in_flight`, where `in_flight` means the call had not reported a terminal
  status when the step ended;
- `acp.context.used_tokens`, the context tokens in use when the step ended,
  and `acp.context.window_tokens`, the context window size of the model the
  turn ran on, both as non-negative integers.

A step span of a gate node, one that runs a deterministic check and books a
pass or a fail (for example the janitor's check aggregate or a merge gate),
MUST additionally carry `gate.verdict`, either `pass` or `fail`, and, when
the verdict is `fail`, `gate.failed_targets`, the names of the targets that
failed.

A value the factory cannot observe MUST be omitted rather than fabricated,
and the span MUST then carry `fabro.step.unavailable_fields`, naming each
omitted attribute. In particular a step whose agent made no tool call MUST
omit both `acp.last_tool` attributes and name them there, and an unknown
context size MUST NOT be exported as zero. `acp.stop_reason` follows its own
absent marker instead of this rule.

The span MUST NOT carry tool-call arguments or output, prompts, transcripts,
command text, environment values, resolved credentials or credential-bearing
paths or URLs. The receiver allowlist that this orchestrator owns MUST admit
every attribute this section names. Emitting and exporting a step span
follows the bounded asynchronous telemetry rules of §"Bounded session waits
and observable inventory": an export failure MUST NOT fail, delay or alter
the step or the run.

As a result, one query over the Honeycomb environment that receives factory
spans, filtered by `fabro.run_id`, MUST return one row per step visit of
that run, giving why the step ended (its outcome, its stop reason, its last
tool call and that call's state, its gate verdict and failed targets, and
its context used against window size) without a run dump.
```

Add a new scenario to `SPECIFICATION/scenarios.md`, numbered with the next unused scenario number at ratification:

```markdown
## Scenario NNN — One query by run id says why each factory step ended

```gherkin
Feature: Factory step spans say why each step ended
  As a triager of a factory run
  I want each step's span to carry why the step ended
  So that one telemetry query replaces a run dump

  Scenario: An ACP step that stopped mid-tool-call and a failed gate step
    Given a factory run of a work item
    And its implement step's agent ends its turn with stop reason end_turn while a just check tool call is still running
    And its janitor gate step fails on the targets check-types and check-lint
    When the run's spans are queried in Honeycomb filtered by the run id
    Then the implement step's span carries the work item id, the run id, the node name and visit, the model, the candidate index and the duration
    And it carries stop reason end_turn, last tool call state in_flight, and context used tokens against context window tokens
    And the janitor step's span carries gate verdict fail with failed targets check-types and check-lint

  Scenario: An unobservable value is named rather than fabricated
    Given a factory ACP step whose agent made no tool call
    When the step's span is exported
    Then the span carries no last tool call attributes
    And the span names them in its unavailable fields
```
```

Co-edit `tests/heading-coverage.json` in the same revision with two entries, each `test: "TODO"` with a non-empty reason: one for `## Factory step span attributes` (`spec_file: contracts.md`) and one for the new scenario heading (`spec_file: scenarios.md`). The reason MUST name livespec-dev-tooling-ipcm33 as the owning work item and MUST say that the exercising proof is a host-captured Honeycomb query over spans from a real factory run, and that the stop-reason attribute additionally waits on bd-ib-rmaxqf.
