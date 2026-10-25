---
proposal: host-judgement-launch-isolation.md
decision: accept
revised_at: 2026-10-25T21:10:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Fleet coordinator ruling for bd-ib-6bbcda, 2026-10-25: a measured process timeline shows that each host judgement's headless agent, launched in the governed repository, boots its interactive SessionStart hooks, plugins and MCP server and a per-tool-call guard, which is most of a dispatch's pre-launch CPU. This agent-neutral paragraph, inside the existing H2 '## Dispatcher admission, WIP cap, and post-merge acceptance', governs how a host judgement launches its candidate. The implementation lands through the factory, sequenced after bd-ib-mfzvdl.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-25T21:10:14Z
verdict: NO BLOCKERS
proposal_stem: host-judgement-launch-isolation
content_digest: 9c48bd92df27b7d270997e7184fc66d79c494bb75acdfdd959088cfcf347ce70
