---
topic: dispatch-trace-correlation
author: claude-opus-5-5
created_at: 2026-10-11T04:34:07Z
---

## Proposal: Dispatch trace correlation

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add an H3, "Dispatch trace correlation", under contracts.md section "Bounded session waits and observable inventory". It requires every fabro run the Dispatcher launches to carry the correlation triple (work.item.id, livespec.dispatch.id, livespec.dispatch.factory) as --label run labels, defines an identifier-shaped value, requires one dispatch span per dispatch with ids derived deterministically from the dispatch id, and requires TRACEPARENT in the fabro run environment to name that span.

### Motivation

Plan fabro-currency item bd-ib-5jvgfr implements the Dispatcher half of the Petri-era trace join (bd-ib-6vhgqg); the fork branch carrier-petri-v0.382 already copies these three labels onto run spans and turns TRACEPARENT into the run's parent. The factory's Definition-of-Done gate refused bd-ib-5jvgfr on 2026-10-11 (run 01M4M5AAW9WVT71KNYMSHPWS3E) because no ratified heading states the labels, the TRACEPARENT handoff, the dispatch span or the identifier shape: the only ratified telemetry vocabulary, in this section, names dispatch.id while the code keys livespec.dispatch.id (commands/_otel_enrich.py, commands/_otel_scrub.py). The gate named this section as the nearest home, since it owns the receiver allowlist and the shared vocabulary. The identifier shape is the one the fork accepts (lib/foundation/fabro-types/src/trace_link.rs, is_identifier and MAX_CORRELATION_VALUE_LEN = 128).

### Proposed Changes

Insert the following H3 into SPECIFICATION/contracts.md between "### First-event waits and operational inventory" and "### Launch obligations and consumed recovery". No H2 is added or removed, so tests/heading-coverage.json is unchanged.

### Dispatch trace correlation

This subsection extends the shared attribute vocabulary above to the Dispatcher's own launches. The vocabulary's `dispatch.id` field is carried on spans and run labels as `livespec.dispatch.id`, beside `work.item.id` and `livespec.dispatch.factory`; together these three are the correlation triple, and the receiver allowlist MUST admit all three.

Every `fabro run` the Dispatcher launches MUST pass the correlation triple as run labels: `--label work.item.id=<work-item id>`, `--label livespec.dispatch.id=<dispatch id>` and `--label livespec.dispatch.factory=<factory name>`, each carrying that dispatch's own value. A correlation value is identifier-shaped when it is 1 to 128 bytes long and every byte is an ASCII letter, an ASCII digit, `.`, `_`, `:` or `-`, so hyphenated work-item ids such as `bd-ib-5jvgfr` and factory names such as `hp-candidate` are identifier-shaped. A value that is not identifier-shaped MUST be left out of the argv, and leaving it out MUST NOT fail the dispatch.

The Dispatcher MUST emit one dispatch span per dispatch through its existing OTLP export path, carrying the correlation triple as span attributes. The span's trace id and span id MUST be derived deterministically from the dispatch id: re-deriving them for the same dispatch id MUST yield the same trace id and span id, and two different dispatch ids MUST yield different trace ids. The Dispatcher MUST set `TRACEPARENT` in the `fabro run` environment to `00-<trace id>-<span id>-01`, using that dispatch span's ids, so that a factory which honours the run labels and the caller's trace parent places its run spans under the dispatch span. A factory that ignores either MUST NOT cause the dispatch to fail.


