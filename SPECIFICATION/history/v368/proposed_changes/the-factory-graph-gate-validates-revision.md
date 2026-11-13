---
proposal: the-factory-graph-gate-validates.md
decision: accept
revised_at: 2026-11-13T12:05:29Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:fabro-currency
---

## Decision and Rationale

The proposal closes the gap that let check-fabro-graph-validity pass on master while the committed groom-work-item graph failed `fabro validate` (attractor.exit_unreachable plus five unreachable nodes) under both Petri-era clients the factory uses: the gate validated with a 0.254.0 client (the CI pin v0.254.0 and the dispatching host's legacy ~/.fabro/bin/fabro), whose validator accepts graphs the engine the factory moves onto rejects. The current bullet fixes only HOW the installer fetches the pin, so both the 0.254 pin and a silent fall-through to a legacy local client conform today; the launch pre-screen held bd-ib-3lxeqf at spec-change tier on exactly that, and legacy-coordinator-agent ruled it a genuine gap and ordered the proposal. Accepted as filed: the replacement bullet is applied verbatim (its first and installer sentences unchanged in meaning; it adds the 0.396.0 release-triple floor for the pin, a client-version control on every host that fails with a control finding and validates nothing below the floor or with no parseable version, no fallback to another client, and a per-graph version report), and the numberless scenario is added as Scenario 366, the next free number, as the proposal directs. The proposal passed two coordinator grades with fixes (merged as #5078, then #5121 adding the generated-debt-register rule). It is time-bound: the non-renewable Petri transition ends 2026-11-14T00:00:00Z. This revise was cut under legacy-coordinator-agent's time-conditioned order (not revised by 2026-11-13T12:00Z, so ahead of everything except priority 1, whose proposal is not yet merged), confirmed by the coordinator at 12:0xZ. The independent sonnet reviewer found no blockers, no collateral edits, clause-scenario agreement for all five cases, and no conflict with the 0.254 transition bullets (the gate binary is outside "the factory"). Co-edit outside the spec target in the same commit: tests/heading-coverage.json gains the Scenario 366 row (test TODO, owned by bd-ib-3lxeqf, preserved implementation at needs-human/f45193625cd243e5b39d7921ef8d295e), and tests/heading-coverage-debt.json is regenerated with `uv run python -m livespec_dev_tooling.heading_coverage_debt`. One H2 heading is added; none is changed or removed.

## Resulting Changes

- constraints.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T12:04:09Z
verdict: NO BLOCKERS
proposal_stem: the-factory-graph-gate-validates
content_digest: e180be083c0764618ef4fb3409cef9ace38fde9355651fdbff293517337cca92
