---
proposal: gap-signal-from-heading-coverage.md
decision: modify
revised_at: 2026-10-20T01:51:09Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-1:spec-implementation-lockstep
---

## Decision and Rationale

Accepted with modifications under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep for plan epic bd-ib-ax3rds (Definition of Done assertion 10: gap detection reports only spec headings that have no exercising test, not clauses that lack a work-item), carrying out the typed next action recorded on the epic. The nine edits retire the clause-enumeration gap signal, which surfaced 752 to 1,233 candidates per run on this repository without one completed pass, in favour of the heading-coverage map that already exists mechanically in tests/heading-coverage.json, and add Scenario 205 so every new MUST clause has a Gherkin scenario; the coverage map gains the Scenario 205 entry in the same change, owned by the implementing child bd-ib-4dlokv. The configured ratification reviewer, gpt-6-astra in a separate read-only Codex session, returned NO BLOCKERS on the exact resulting bytes.

## Modifications

Three independent ratification reviews (gpt-6-astra, 2026-10-20T01:39:35Z, 01:45:59Z and 01:48:45Z) found blockers in text the proposal left untouched and in scenario coverage of the new clauses; the resulting bytes carry the proposal's nine edits plus these modifications, re-reviewed on their exact bytes:
- M1/M6: the two closure-anchor parentheticals in contracts.md (gap-tied completion bullet of implement; the consumers list of detect-impl-gaps) no longer describe a gap_id as hashing a hard-wrapped line; they say a gap_id identifies a heading, not the check that settles a clause beneath it.
- M2: the detect-impl-gaps detection clause now matches a coverage entry on spec root, spec file and heading; treats an entry naming a test that does not exist as uncovered; and requires a dangling or malformed entry to be reported as an uncovered heading AND a surfaced finding, never a clean absence (research/005 row 9, which the proposal text had not carried).
- M3: the caller-caution paragraph says headings, not clauses.
- M4: the migration paragraph states completion-of-implementation semantics and lets the detector and the live re-labelling land as separate changes in that order (research/005 row 8).
- M5: the default human output line says the heading the gap-id derives from.
- M7: the pass-through sentence names the Spec Reader heading enumeration and the heading-coverage map.
- M8: the closed-item-integrity check resolves a heading-derived gap-id directly to its heading's coverage entry and a historical clause-derived id (kept by closed items) through the clauses[] map; its primitives paragraph and precondition (b) are scoped accordingly.
- S1: Scenario 1 gains an uncovered-heading precondition and drops the "loads the rule set" framing.
- S2: Scenario 205 gains an absent-entry sub-scenario asserting repeat-run gap-id stability, a dangling-entry sub-scenario, and a closed-label-preservation line.
- Round 3, R3-M1: the migration paragraph now states the re-labelling and closed-label preservation as MUST clauses; the separate-landing permission stays a MAY.
- Round 3, R3-M2: the detection clause defines dangling and malformed entries and states that a heading with no entry is uncovered without a finding.
- Round 3, R3-M3: the Gap-detectable behavior clauses subsection's rationale no longer assumes the retired clause detector (the H3 heading text is unchanged; only H2 headings carry coverage entries).
- Round 3, R3-S1: Scenario 16 gains a sub-scenario for a closed item carrying a heading-derived gap-id, resolved through its heading's own coverage entry, with finding and no-finding outcomes.
- Round 4, R4-M1: the detection clause splits the round-3 malformed case: an incomplete entry (identifies a live heading but lacks test) is an uncovered heading plus a finding; an unidentifiable entry (missing spec_root, spec_file or heading, or naming a heading the live tree lacks) is a finding only, never a gap or gap-id, and covers nothing.
- Round 4, R4-S1: Scenario 205 renames the round-3 malformed sub-scenario to incomplete and adds an unidentifiable-entry sub-scenario.
- Round 3, R3-S2: Scenario 205 gains a malformed-entry sub-scenario contrasted with an absent entry, and a fully-qualified-matching sub-scenario across two spec files.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-20T01:50:49Z
verdict: NO BLOCKERS
proposal_stem: gap-signal-from-heading-coverage
content_digest: 1dd5e86a82c6d784ddd034fcd9cbd426e98bc03cdd498ba968bbf15bd51ddb0c
