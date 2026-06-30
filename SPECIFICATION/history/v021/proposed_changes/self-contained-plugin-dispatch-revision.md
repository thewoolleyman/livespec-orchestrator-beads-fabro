---
proposal: self-contained-plugin-dispatch.md
decision: accept
revised_at: 2026-06-30T03:01:23Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Codifies clause #6 of the orchestrator-plugin-self-containment fix: the Fabro implement-work-item workflow ships in the plugin payload and the Dispatcher resolves it via the plugin root, so the factory dispatches from the enabled plugin alone with no orchestrator-source checkout. Adds the new contracts.md H2 and cross-references it from the dispatch-time baseline conformance gate section; co-edits tests/heading-coverage.json for the new H2. Clause-only contract, consistent with the existing dispatch-time baseline conformance gate precedent (no new Gherkin scenario).

## Resulting Changes

- contracts.md
- ../tests/heading-coverage.json
