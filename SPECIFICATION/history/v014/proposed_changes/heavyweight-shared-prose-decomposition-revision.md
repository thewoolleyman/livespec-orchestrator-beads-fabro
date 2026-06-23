---
proposal: heavyweight-shared-prose-decomposition.md
decision: accept
revised_at: 2026-06-23T03:56:22Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: p3bspec
---

## Decision and Rationale

Resolves the internal contradiction between constraints.md §"Skill orchestration constraints" (which mandated SKILL.md-resident heavyweight orchestration) and the same file's Codex-support bullet (which forbids Codex bindings from copying Claude-specific SKILL.md bodies): the heavyweight orchestration moves to a shared, harness-neutral .claude-plugin/prose/<op>.md artifact that both runtimes bind thin, mirroring livespec CORE's prose + thin-Driver-binding architecture. Pure architecture/spec amendment, zero behavior change. Also reconciles the heavyweight-skill count to FIVE and folds groom into the heavyweight membership across the header, the consent-discipline section, and the augmented-vs-new section. No new ## H2 heading, no scenarios.md change.

## Resulting Changes

- constraints.md
- contracts.md
