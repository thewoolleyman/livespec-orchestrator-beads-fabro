---
topic: factory-spend-telemetry-carriers
author: claude-opus-5-5
created_at: 2026-11-01T21:22:59Z
---

## Proposal: Factory Codex response spans keep their measured cache-token counts

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Name the two Codex cache-token counts in the receiver-allowlist vocabulary, so a factory Codex `handle_responses` span reaches Honeycomb carrying the cached-input count it measured. Today the receiver allowlist strips both keys, and factory Codex spend is priced from an assumed cached share instead of a measurement.

### Motivation

Plan factory-spend-accuracy in livespec-dev-tooling (epic livespec-dev-tooling-fwq26r), relay R1, work item bd-ib-3k3nxw. Codex 0.153.x records `gen_ai.usage.cache_read.input_tokens` and `gen_ai.usage.cache_write.input_tokens` on `handle_responses`. The forwarding stage rebuilds attributes from `_otel_scrub.ATTRIBUTE_ALLOWLIST`, which names neither key, so dataset `codex-app-server` has neither column. The host prices factory Codex input at a fixed 0.90 cached share, while measured local Codex runs at 0.21-0.22. That is a large, silent mispricing.

### Proposed Changes

In `contracts.md` §"Factory step span attributes", after the paragraph that ends "The receiver allowlist that this orchestrator owns MUST admit every attribute this section names.", add a sub-section:

### Factory Codex response token counts

A Codex `handle_responses` span that a factory run exports MUST reach the Honeycomb export with `gen_ai.usage.cache_read.input_tokens` and `gen_ai.usage.cache_write.input_tokens` present whenever the Codex runtime recorded them, each as the non-negative integer it recorded. The receiver allowlist MUST admit both keys beside `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens`. The forwarding stage MUST NOT rename, sum, default or derive either value. A span on which the runtime recorded neither key MUST pass through with neither key, and MUST NOT be given a zero.

In `scenarios.md`, add:

## Scenario 292 — A factory Codex response span keeps its measured cache-token counts

```gherkin
Feature: Factory Codex response spans keep their measured cache-token counts
  As the host pricing factory Codex spend
  I want each factory Codex response span to carry the cached-input count Codex measured
  So that cost is priced from the measurement rather than an assumed cached share

  Scenario: A handle_responses span carrying both cache counts
    Given a factory Codex run whose handle_responses span records gen_ai.usage.cache_read.input_tokens and gen_ai.usage.cache_write.input_tokens
    When the receiver forwards the span to Honeycomb
    Then the forwarded span carries both keys with the integer values Codex recorded

  Scenario: A handle_responses span with no cache counts
    Given a factory Codex handle_responses span that records neither cache key
    When the receiver forwards the span
    Then the forwarded span carries neither key
```

The revise commit MUST add the matching `tests/heading-coverage.json` row for the new scenario heading.

## Proposal: Factory Claude API-request records carry the cache-write split by lifetime

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Require each factory Claude API-request record forwarded to Honeycomb to carry its cache-write tokens split into the 5-minute and 1-hour lifetimes, plus the dispatch id, beside the existing per-call `request_id`. The two lifetimes are priced differently, and today only an undivided `cache_creation_tokens` arrives.

### Motivation

Plan factory-spend-accuracy, relay R2, work item bd-ib-t7yjrb. The Anthropic usage block reports `cache_creation.ephemeral_5m_input_tokens` and `cache_creation.ephemeral_1h_input_tokens`. A 5-minute write is billed at 1.25x base input and a 1-hour write at 2x. Dataset `claude-code` carries only `cache_creation_tokens`, so the host cannot price factory Claude cache writes per lifetime, or attribute them to a dispatch.

### Proposed Changes

In `contracts.md` §"Factory step span attributes", add a sub-section after the Codex sub-section:

### Factory Claude cache-write lifetimes

Every Claude API-request record that a factory run exports MUST reach the Honeycomb export carrying `cache_creation_5m_tokens` and `cache_creation_1h_tokens`, with the values the API response's usage reported for 5-minute and 1-hour cache writes, as non-negative integers. It MUST also carry `livespec.dispatch.id`, with the value of the run's correlation label, and its existing `request_id`, which is the key that joins it to its API call. The sum of the two lifetime counts MUST equal the record's `cache_creation_tokens` when the response reported both lifetimes. When the response did not report a lifetime split, the record MUST omit both lifetime keys rather than assign the undivided count to either. The receiver allowlist MUST admit `cache_creation_5m_tokens` and `cache_creation_1h_tokens`.

In `scenarios.md`, add:

## Scenario 293 — A factory Claude API-request record carries its cache-write lifetimes and dispatch id

```gherkin
Feature: Factory Claude cache writes are split by lifetime
  As the host pricing factory Claude spend
  I want each factory Claude API-request record to carry its 5-minute and 1-hour cache-write counts and its dispatch id
  So that each lifetime is priced at its own rate and the spend is attributed to its dispatch

  Scenario: A response reporting both lifetimes
    Given a factory Claude run whose API response reports 5-minute and 1-hour cache-write tokens
    When the record is forwarded to Honeycomb
    Then it carries cache_creation_5m_tokens and cache_creation_1h_tokens with the reported values
    And their sum equals its cache_creation_tokens
    And it carries livespec.dispatch.id and request_id

  Scenario: A response reporting no lifetime split
    Given a factory Claude API response whose usage carries no lifetime split
    When the record is forwarded
    Then it carries neither lifetime key
```

The revise commit MUST add the matching `tests/heading-coverage.json` row for the new scenario heading.

## Proposal: The Dispatcher emits one terminal span per dispatch with its outcome and attempts

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Require the Dispatcher to emit a terminal span when a dispatch ends. It carries a bounded run-outcome value, and has one child span per attempt naming that attempt's window, model and whether it ran on a fallback candidate. Factory cost can then be broken down by run outcome and by fallback.

### Motivation

Plan factory-spend-accuracy, relay R3, work item bd-ib-welwbc. The fabro `run` span ends with status_code 0 and no outcome. `livespec.outcome` appears only on `reflection.stall`. `livespec.cost.model_resolved` reports model resolution, not fallback. Nothing in Honeycomb records how a dispatch ended or whether its spend ran on a fallback model, so the plan's per-run, per-day cost-by-outcome board has nothing to group by.

### Proposed Changes

In `contracts.md` §"Bounded session waits and observable inventory" → "Dispatch trace correlation", after the paragraph defining the dispatch span, add:

When a dispatch reaches a terminal state, the Dispatcher MUST emit exactly one terminal span named `livespec.dispatch.terminal` to service `livespec-dispatcher`. Its parent MUST be the dispatch span, and it MUST carry the correlation triple. It MUST carry `livespec.dispatch.outcome`, exactly one of:

- `succeeded`: the dispatch's work merged or was accepted;
- `failed`: the run ended in a terminal failure;
- `cancelled`: the run was cancelled;
- `rework`: acceptance returned the item for rework;
- `abandoned`: the dispatch ended without a terminal run outcome, for example a run that never started or was reaped as an orphan.

The terminal span MUST also carry `livespec.dispatch.attempt_count`. For each attempt the dispatch made, the Dispatcher MUST emit one child span of the terminal span, named `livespec.dispatch.attempt`. Its start and end times MUST be the attempt's start and end. It MUST carry `livespec.dispatch.id`, `livespec.dispatch.attempt.index` (0-based), `acp.model` naming the model the attempt ran on, and `livespec.dispatch.attempt.fallback`, which is true exactly when the attempt ran on a candidate after the first in its fallback chain. A value the Dispatcher cannot observe MUST be omitted, never fabricated, and named in `livespec.dispatch.unavailable_fields`. The receiver allowlist MUST admit every attribute this paragraph names. Emitting these spans follows this section's bounded asynchronous telemetry rules: an export failure MUST NOT fail, delay or alter the dispatch's recorded outcome.

In `scenarios.md`, add:

## Scenario 294 — A terminated dispatch emits one terminal span with its outcome and one span per attempt

```gherkin
Feature: Terminal dispatch span
  As the host reporting factory cost by run outcome
  I want each terminated dispatch to emit its outcome and its attempts
  So that spend can be grouped by how the run ended and by fallback

  Scenario: A dispatch whose second attempt ran on a fallback model and merged
    Given a dispatch whose first attempt failed on its primary model and whose second attempt ran on the next candidate and merged
    When the dispatch terminates
    Then dataset livespec-dispatcher holds exactly one livespec.dispatch.terminal span for its dispatch id, carrying livespec.dispatch.outcome succeeded and livespec.dispatch.attempt_count 2
    And it holds two livespec.dispatch.attempt spans under it, with index 0 carrying fallback false and index 1 carrying fallback true, each naming its acp.model

  Scenario: A cancelled dispatch
    Given a dispatch whose run is cancelled
    When the dispatch terminates
    Then its terminal span carries livespec.dispatch.outcome cancelled
```

The revise commit MUST add the matching `tests/heading-coverage.json` row for the new scenario heading.
