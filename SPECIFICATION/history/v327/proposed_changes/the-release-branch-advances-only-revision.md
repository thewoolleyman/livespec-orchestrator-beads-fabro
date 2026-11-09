---
proposal: the-release-branch-advances-only.md
decision: accept
revised_at: 2026-11-09T02:41:25Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Decided by legacy-coordinator-agent (session e8d70af3) under R301 delegated authority on 2026-11-09 (~01:3xZ UTC): ACCEPT as filed, on content digest f750f47a. The decision covers the release-channel paragraph in contracts.md §"Self-contained plugin dispatch" and the new scenario with its four cases. Basis: every fleet clone's committed settings and this host's single known_marketplaces.json entry resolve this plugin at ref release, and fast-forward-release-branch.yml advanced the unprotected release branch on every release: published event, so session starts adopted uncanaried builds (this repository's registration c0b28ad85bab -> 35cdda22389c at 2026-11-09T01:28:45Z, seven minutes after v0.307.0 was published; livespec-dev-tooling at 01:51:48Z; livespec-overseer at 01:58:17Z). The spec never stated the release contract; this conforms the realization to livespec-dev-tooling v155 option D (a member adopts a build only when a committed fleet record names it). The content was placed in house format, which leaves its words unchanged: the scenario H2 sits outside the gherkin fence with a Governing clause line and a Feature line, and the proposal's own "<next free number>" placeholder is filled as 331, the next free number on master 8792b7c94. Per the proposal's closing line, tests/heading-coverage.json gains one TODO row for the Scenario 331 heading, owned by bd-ib-sghxlk, through resulting_files path ../tests/heading-coverage.json. An independent read-only sonnet review reported NO BLOCKERS on these exact bytes at 2026-11-09T02:40:44Z and recomputed the digest itself. Its non-blocking notes, for the implementing carrier bd-ib-sghxlk: the missing-tag scenario exercises a failure the clause does not name (it is the proposal's own wording), and the canary-samples ordering is a roll-step precondition the workflow cannot enforce. Drafted by claude:gmktec-factory-placement (plan gmktec-factory-placement, epic livespec-dev-tooling-me5aqz).

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T02:40:44Z
verdict: NO BLOCKERS
proposal_stem: the-release-branch-advances-only
content_digest: f750f47a2764324dfbafe50b54bf1c8498fb03eef19d9a9142b82646b1905361
