---
proposal: a-launcher-stops-a-drive-a-hold-precedes-admission.md
decision: modify
revised_at: 2026-11-08T22:29:51Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Decided by the dispatcher-run-watch-cost plan session (epic bd-ib-k7ymgx, session 4cac6999, model claude-opus-5-5) for its held child bd-ib-j6rbdx, under the repository's delegated revise decision mode and the maintainer's 2026-08-26 'I authorize all revises': MODIFY on content digest f4b7e6f2.... This is a delegated decision, not the maintainer's. Basis: on 2026-11-04 bd-ib-ke5wkf's launcher logged LAUNCH at 09:46:45Z, hold-gmktec was set at 09:54:01Z, and run 01M6K0FV7RM5 still submitted to petri :32276 after about 22 minutes in the master-CI preflight wait, blocking a factory restart; the launch-point re-read runs only under the mutex before drive starts, so nothing stated a check during the drive. The premises were re-verified on master 27736d244: dispatch_preamble refuses provably before admission (_dispatcher_run_checks.py), so a drive stopped while the item reads ready has written no claim, and §"Stranded claim release" → "Stale assignee clearance" exists as cited. Admission rather than Fabro submission is the boundary because a stop after admission strands a pending-stamp claim. An independent read-only sonnet review reported NO BLOCKERS on these exact bytes at 2026-11-08T22:29:07Z and recomputed the digest itself. Its non-blocking note, for the implementing carrier bd-ib-j6rbdx: the Terminal line bullet does not list stopped-after-admission among its trappable causes by name; its generic wording covers it.

## Modifications

(1) Scenario 325 is taken on master (the highest is 329), so the new scenario is numbered 330 and the harness paragraph names Scenario 330, as the proposal itself directs. (2) The proposal's sentence 'Stopping a drive under this rule is neither an early exit nor a non-run exit, because the launcher itself does not exit.' reads 'A drive stopped under this rule does not trigger the "Early-exit re-ticket" bullet, and the stop is not itself a non-run exit, because the launcher does not exit.' The stopped drive does exit non-zero before its run lists, which the Early-exit re-ticket bullet would otherwise govern, and the later stopped-after-admission case is a non-run exit; the new wording names the carve-out exactly. (3) tests/heading-coverage.json gains one TODO entry for the Scenario 330 heading, owned by bd-ib-j6rbdx, through resulting_files path ../tests/heading-coverage.json. Every other word of the bullet, the harness paragraph and the scenario is the proposal's.

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
reviewed_at: 2026-11-08T22:29:07Z
verdict: NO BLOCKERS
proposal_stem: a-launcher-stops-a-drive-a-hold-precedes-admission
content_digest: f4b7e6f2578fc63af39d4807db0b9f482bf5d90942644fe084c0f759626560f8
