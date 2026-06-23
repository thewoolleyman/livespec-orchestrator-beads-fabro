---
proposal: orchestrate-operator-ux.md
decision: accept
revised_at: 2026-06-22T23:59:21Z
author_human: E2E Test <e2e-test@example.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Maintainer-approved ACCEPT. Codifies the orchestrate operator-surface UX: a bare `orchestrate` invocation presents an interactive operator walkthrough instead of erroring on a missing subcommand; `--repo` defaults to the current working directory's repo when omitted (still overridable); and console output defaults to human-readable Markdown with `--json` as the explicit machine-readable opt-in. The explicit `plan`/`run` + `--repo` + `--json` forms remain available for scripts, CI, and the Dispatcher, and the JSON payload shape is unchanged. Carries the matching `## Scenario 17 — orchestrate operator-surface defaults` Gherkin scenario in scenarios.md per the Behavior=>Gherkin authoring discipline, and co-edits tests/heading-coverage.json to register that new H2 with a TODO baseline-backfill entry per the self-application co-edit rule.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
