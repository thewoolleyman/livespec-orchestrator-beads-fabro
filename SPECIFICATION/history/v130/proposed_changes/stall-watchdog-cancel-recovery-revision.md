---
proposal: stall-watchdog-cancel-recovery.md
decision: modify
revised_at: 2026-10-13T09:07:28Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratifies the maintainer's 2026-10-12 decision (session stall-watchdog-false-kills-plan, plan stall-watchdog-false-kills, epic bd-ib-laf735) to accept proposal stall-watchdog-cancel-recovery as proposed. The Dispatcher's progress watchdog gains a governing clause: progress is the newest of the heartbeat and the run's event stream, and an open command node is bounded by its node timeout. A stall cancel is never non-convergence. A first cancel is released and recovered through v127's provider-limit release-and-recovery mechanism, and a second consecutive cancel rests at blocked / needs-human. resume --item may anchor on the watchdog-stall-cancel record when no proof record exists yet. The proposal was vetted before filing by independent Opus and Codex reviewers, whose defects were folded in before the maintainer ratified it. No design record is contradicted: the resume clause's single-exception sentence is amended in place to admit the second exception, and v127's release semantics are reused unchanged.

## Modifications

Two sets of modifications, both inside the ratified design. (1) One wording repair to the amended resume-clause sentence: with two exceptions now named, 'for it the Dispatcher itself invokes this resume' reads 'for each the Dispatcher itself invokes this resume'. (2) The three required changes of the independent ratification reviewer (OpenAI Codex gpt-6-astra, read-only), applied verbatim. (a) Stage-source precedence: the factory's own record of the run decides the stage while the factory holds the run, and the cancel record decides it, and is named as the source, only when the factory authoritatively reports it no longer holds the run; Scenario 142's stall-cancel sub-scenario gains that Given. (b) The second-cancel comment preserves every applicable remedy of the resume refusal ladder, including resolve-blocked:<id>:ready for the needs-human rest, and names a plain dispatch only where that is the specified remedy. (c) Scenario 170's before-publishing sub-scenario now asserts the seeded recovery, and new sub-scenarios cover first-release replay safety and budget/count treatment, a second stall as an item-attributable terminal, cancel-head provenance, an unreadable published head, the anchor between publication and capture, proof-record precedence over a cancel anchor, and a refused anchor for a cancel during rework. (3) The new scenario is numbered 172, not 170: v128 already carries a Scenario 170 (the failed engine checkpoint commit), and v129, ratified on master while this pass was first in review and then replayed, carries a Scenario 171 (the master-CI preflight wait). This pass was first cut as v129 with the scenario numbered 171 and never pushed; it was replayed onto master eff9143f as v130 by a three-way merge, and the same read-only reviewer confirmed the replayed bytes. The heading, the contract's 'exercises this subsection' sentence and both heading-coverage entries name Scenario 172; the archived proposal's references to 'Scenario 170' mean this scenario.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-13T09:06:41Z
verdict: NO BLOCKERS
proposal_stem: stall-watchdog-cancel-recovery
content_digest: 892d4dbe67d6218e3771bc5247a69caa46b4a36b4fc4f652a1dce6152cdaa347
