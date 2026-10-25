---
topic: host-judgement-launch-isolation
author: claude-opus-5-5
created_at: 2026-10-25T21:21:55Z
---

## Proposal: Host judgements launch outside the interactive agent configuration

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Each host judgement (the Definition-of-Done takings, the governing-heading and classification verdicts, and the drift run's judgement) launches its candidate agent without the governed repository's or the operator's interactive agent configuration: no hooks, plugins, MCP servers or instruction files beyond what the judgement names, whichever agent the candidate runs.

### Motivation

Fleet coordinator ruling (gitops-fleet-capacity-monitoring, 2026-10-25) for work-item bd-ib-6bbcda. A 0.5 s process timeline of a gmktec dispatch on plugin v0.243.4 showed that each host judgement's headless `claude -p`, run with the governed repository as its working directory, booted the repository's SessionStart hooks (12 plugin CLI calls, the env wrapper, a Honeycomb MCP server) and PreToolUse guards on every tool call. That is most of the 4.7-6.8 CPU-minutes before launch, against a 3 CPU-minute bar. No clause governs how a host judgement is launched, so the implementing item cannot cite one. The clause is agent-neutral because factory item bd-ib-mfzvdl moves these judges Codex-first, and codex has its own hook, MCP and instruction-file configuration. It is one paragraph inside the existing H2, with no heading change and no scenario.

### Proposed Changes

In SPECIFICATION/contracts.md, inside section '## Dispatcher admission, WIP cap, and post-merge acceptance', insert this paragraph immediately after the paragraph that begins '**Host judgements take the resolved `dod_gate` chain.**', as its own paragraph separated by blank lines:

**A host judgement launches outside the interactive agent configuration.** Each host judgement the preceding paragraph names MUST launch its candidate agent without the interactive agent configuration of the governed repository or of the host's operator. No hook, plugin, MCP server or instruction file from the project-level or user-level configuration of the candidate's agent loads into the judgement's agent session, beyond what the judgement itself names on its own invocation. This holds whichever agent the resolved candidate runs. The judgement's subject, rubric and governing text reach the agent only through the judgement's own prompt and the tool allowance the judgement grants. The reason is cost, measured on 2026-10-25 on the gmktec factory host. Two or three host judgements per dispatch each launched `claude -p` with the governed repository as its working directory, so each one ran that repository's session-start hooks: twelve plugin marketplace and install calls, a credential wrapper and an MCP server. A guard hook also ran on every tool call. Together they made up most of the 4.7 to 6.8 CPU-minutes that a dispatch spent before its Fabro run started.

