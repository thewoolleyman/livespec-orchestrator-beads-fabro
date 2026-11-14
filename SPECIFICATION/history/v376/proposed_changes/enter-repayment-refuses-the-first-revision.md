---
proposal: enter-repayment-refuses-the-first.md
decision: modify
revised_at: 2026-11-14T12:26:43Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:expedited-incident-hardening
---

## Decision and Rationale

Ratified under delegated decision. legacy-coordinator-agent graded the draft PASS (2026-11-14) and ordered it after v375 in the orchestrator revise queue. It releases bd-ib-ah5t7i: enter-repayment admits the first complete green descendant master run when every red job on the landed commit's own run is pre-existing and attributed to another recorded incident, which livespec-dev-tooling-xdt4ue's repayment needs.

## Modifications

(1) Condition 3 reads 'the admitted run's head or an ancestor of it', because the filed text refused the measured xdt4ue case, where ii557b's fix 3324c2392 is the green run's head. (2) L is pinned as the latest landed commit of the attempt from which the run's head descends. (3) Condition 1 adds that no complete normal master run of L succeeded, to cover re-runs. (4) Job names and conclusions are read from the forge. (5) The refusal names the first failed condition in listed order, and the job's name for a job condition. (6) The evidence names each run by its run id. (7) A spec-first sentence names _incident_repayment_plan._master_ci_complete and bd-ib-ah5t7i. (8) The scenario is numbered 373, gains As/I want/So that lines and a Given that the attributing incident records F as landed, and its refusal Then names the condition and job. (9) A third case refuses when an earlier green descendant run exists. Items 2-4 and the F Given came from a doctor-style walk through the live code. Items 6 and 9 came from the coordinator's grade.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T12:26:04Z
verdict: NO BLOCKERS
proposal_stem: enter-repayment-refuses-the-first
content_digest: 09ec21d53b7ac5d6f1d0848c745fb1109146e37aa95937d554b4d560972f9e78
