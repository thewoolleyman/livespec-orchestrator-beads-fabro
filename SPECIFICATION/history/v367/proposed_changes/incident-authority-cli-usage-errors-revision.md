---
proposal: incident-authority-cli-usage-errors.md
decision: modify
revised_at: 2026-11-13T08:20:09Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:expedited-incident-hardening
---

## Decision and Rationale

The proposal carries the two of the three non-blocking notes from the independent re-review of revise v366 (livespec-orchestrator-beads-fabro#5125) that legacy-coordinator-agent ruled into one follow-up. (1) v366's reply clause said the incident authority CLI "MUST answer every action with exactly one JSON reply object on stdout", which is literally untrue for an invocation that fails argument parsing: `_parse` in commands/incident_authority.py is argparse, and both `parse_args` failures and `parser.error(...)` print usage on stderr and exit 2 before any reply is built. Scoping the clause to parsed actions and stating what a failed parse does keeps a test written from the clause from contradicting shipped code. The independent reviewer confirmed each named example live on orchestrator master: an omitted required argument (`read-current` without `--owner`: 0 bytes on stdout, the argparse error on stderr, exit 2), an unknown action (invalid choice, exit 2), and a payload argument given to an action that does not take it (`--successor-json` on `read-current`, exit 2). livespec-dev-tooling's shared client already treats any exit other than 0 or 78 as the named refusal incident-authority-exit, so a usage error authorizes nothing in every existing consumer. (2) Scenario 365's moved-head case did not assert the exit 78 that the reply clause gives every refusal. The third note (read-current's other chain-fault refusals are not enumerated) needs nothing, because the text makes no exhaustive claim (coordinator ruling). legacy-coordinator-agent graded the proposal PASS at 0577d10fa, merged it as #5132, and assigned this revise the next orchestrator slot, ahead of vpvdn4, because it serves the incident priority. No H2 heading is added, removed or renamed.

## Modifications

One modification, ruled by legacy-coordinator-agent in its PASS grade of #5132 as an optional wording fix: in Scenario 365 the existing case name "A stale or partial fence is refused and authorizes nothing" becomes "A stale or mismatched fence is refused and authorizes nothing", so that "partial" no longer names both the exit-78 refusal case and the new exit-2 usage-error case ("A read-current invocation that omits part of the fenced identity is a usage error, not an action"). The renamed case's body (a superseded generation, or a different owner or operation) is a mismatch, so the new name fits it. Everything else is the proposal's Proposed Changes applied verbatim. Co-edit outside the spec target, in the same commit: the Scenario 365 row of tests/heading-coverage.json (owned by bd-ib-txbv7i) gains the moved-head exit 78 and the usage-error observables in its reason. No row or debt entry is added or removed.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T08:18:05Z
verdict: NO BLOCKERS
proposal_stem: incident-authority-cli-usage-errors
content_digest: 11ea0753bf3d31241b1fed2c6ccd4adcdaff9cf9ae7ea75310dac4306969a573
