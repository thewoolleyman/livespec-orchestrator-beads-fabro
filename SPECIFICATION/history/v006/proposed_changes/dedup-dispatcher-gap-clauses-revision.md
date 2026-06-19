---
proposal: dedup-dispatcher-gap-clauses.md
decision: accept
revised_at: 2026-06-19T18:00:52Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accept the deduplication: the three Dispatcher behavior clauses (4 refuse human-gated, 5 non-convergence bounce, 6 calibration telemetry) are removed from the "### Gap-detectable behavior clauses" H3 and retained ONLY in their authoritative "### Dispatcher grooming behavior" location (byte-unchanged, keeping gap-dpk6g22t/gap-rs4tkntz/gap-ajq7ynr4 stable for the OPEN items cjey2z/n5kina/yfsv4j). The five genuinely-new H3 clauses (behaviors 1,2,3,7,8) remain; the H3 intro gains a one-line cross-reference. No new behavior is introduced, so all Gherkin Scenarios 1-15, Open realization choices, and the compose-next note are preserved verbatim; no H2 heading changes (no tests/heading-coverage.json edit). Mechanically verified: the detector drops the three duplicate gap-ids (gap-vihl76nl/gap-6sjw3ezu/gap-mt7eycbr, zero work-items) while the three OPEN-item-tied gap-ids survive.

## Resulting Changes

- contracts.md
