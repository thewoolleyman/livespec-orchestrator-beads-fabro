---
proposal: a-janitor-green-run-cancelled.md
decision: modify
revised_at: 2026-11-04T10:12:23Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted design (delegated revise_decision_mode; claude-opus-5-5 as delegated decider for the publish-draft-green-work-loss plan, bd-ib-vraou4). A factory restart must cancel active runs rather than wait for them (maintainer direction 2026-10-24), and on 2026-11-04 the petri restart cancel lost two janitor-green commits (bd-ib-uq2ocd run 01M6JSNVH32S8CDNX0P4TS7DWB, bd-ib-xuo54m run 01M6JC00SX2G) because only the sandbox held them. Extending the Scenario 183 hookless preserved-publish rule to janitor-green runs, through a Dispatcher cancel-for-restart command and a best-effort publication when an outside cancel is reported, preserves finished work without holding the restart or changing any dispatch outcome. The Step 3.5 stale-branch precondition was skipped (--skip-stale-branch-check), decided by legacy-coordinator-agent under R301: the check failed only on other threads' branches spec/host-judgement-isolation (5cbf3f823), spec/incident-authority-genesis-and-carrier (1279d21d2) and spec/reprove-merged-item-v2 (e942de03e), none of which touches the edited contracts.md paragraph or Scenario 306, and this is an --only-topic pass on a fresh branch from origin/master.

## Modifications

Wording only. The new paragraph's bold lead-in 'A janitor-green run cancelled outside the Dispatcher is published to a preservation ref.' became 'A janitor-green run that a factory restart or an outside cancel ends is published to a preservation ref.', because its main rule covers cancels made through the Dispatcher's own cancel-for-restart command. The forward reference 'record the failed step as the next sentence requires' became 'record the failed step in the `livespec-preserved-tree` ledger comment that this paragraph requires below', because the next sentence is the outside-cancel rule, not the comment rule (ratification reviewer note). Scenario 306 was appended after Scenario 305 as proposed, and its tests/heading-coverage.json entry is TODO, carried by bd-ib-vraou4.

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
reviewed_at: 2026-11-04T10:11:30Z
verdict: NO BLOCKERS
proposal_stem: a-janitor-green-run-cancelled
content_digest: 0be6a6d135becbf6f4f7027c759495678f9acf9bd5611bc8de4a9c45fe5b5018
