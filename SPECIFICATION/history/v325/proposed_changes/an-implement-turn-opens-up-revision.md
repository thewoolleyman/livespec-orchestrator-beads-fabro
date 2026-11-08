---
proposal: an-implement-turn-opens-up.md
decision: accept
revised_at: 2026-11-08T16:38:17Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Decided by the sandbox-commit-gate-ceiling plan session (epic bd-ib-qy5wol, model claude-opus-5-5) on legacy-coordinator-agent's ruling (session a7ae0ef6, 2026-11-08 ~16:3xZ: 'v325 is YOURS for bd-ib-hfhezo's an-implement-turn-opens-up revise ... Rebuild resulting_files on 57024146f2, take a fresh review, cut'), under R301 delegated authority and the maintainer's 2026-08-26 'I authorize all revises': ACCEPT on content digest 8323d37c.... This is a delegated decision, not the maintainer's. Basis: measured 2026-11-08 from factory run exports, implement turns open up to nine concurrent commit-runner waits on one commit run, and each return is its own full-context LLM round trip (102 of 110, 81 of 84 and 67 of 69 wait-only round trips carry exactly one wait return; such trips carry 76% and 62% of togi6z 01M6XM2HXR8T's implement-turn input tokens, 27% of nvh3dl 01M6X8DXM600's). The existing per-visit rule for fix and review_fix refuses only a wait following an earlier 'running' report; nothing refused a wait while another on the same run was still open. The new rule is stage-independent, returns at once non-zero with the run's current state, leaves the run untouched, and does not refuse sequential waits or waits after a killed one. resulting_files were rebuilt on post-v324 master 57024146f; the 15:48:15Z review of the pre-v324 bytes is void for these bytes. An independent read-only sonnet review reported NO BLOCKERS on these exact bytes at 2026-11-08T16:37:39Z and independently recomputed the digest. Its non-blocking notes, for the implementing carrier bd-ib-hfhezo rather than the spec: 'open' is defined by exclusion, so the implementation must detect a killed wait by liveness of the waiting process, not by a lock file that survives a kill; and whether a concurrency refusal counts toward fix/review_fix's per-visit single wait is left unspecified. Fleet scope: the runner ships in the plugin's bundled implement-work-item workflow, so this governs every repository dispatched through it.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T16:37:39Z
verdict: NO BLOCKERS
proposal_stem: an-implement-turn-opens-up
content_digest: 8323d37c8705e2f16b89fe2e8c91b749f357103baddcb187ba274e4cb3f1de6b
