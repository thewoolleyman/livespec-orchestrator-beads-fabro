---
proposal: autonomous-mode-arming-and-audit-contract.md
decision: accept
revised_at: 2026-07-10T13:29:24Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Driver ratified (independent Fable review NOTHING-BLOCKING). Pins dispatcher.autonomous_mode as the single persistent permission the console sets (a); the console factory-drain path as loop launcher (b); the per-run --mode autonomous flag on the Dispatcher loop subcommand, not drive (c); and the Dispatcher journal as the published Control-Plane audit surface. No H2 heading changes.

## Resulting Changes

- spec.md
- contracts.md
- scenarios.md
