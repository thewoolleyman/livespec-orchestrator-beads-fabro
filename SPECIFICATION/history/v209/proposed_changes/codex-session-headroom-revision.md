---
proposal: codex-session-headroom.md
decision: modify
revised_at: 2026-10-24T22:45:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in substance. The admission headroom filter covers only Claude candidates, so a Codex-primary chain reached its Claude fallback only after a run met the Codex limit mid-turn (bd-ib-4jdgcw; measured on dispatch e7733d07). The proposal supplies the explicit authentication binding the Claude clause requires before coverage may extend to another agent, and a measured, bounded, allowance-free usage read. Modified to resolve three ratification-review blockers before cutting. Independent read-only gpt-6-astra ratification review: pass 1 BLOCKERS (3), pass 2 BLOCKERS (1), pass 3 NO BLOCKERS; pass 4 NO BLOCKERS on the exact resulting bytes after resulting_files paths were made spec-target-relative. tests/heading-coverage.json and tests/heading-coverage-debt.json are co-edited in the same change, owned by bd-ib-4jdgcw. Reviewer Codex sessions: pass 3 01a17007-4451-7520-ab22-96760125d408, pass 4 01a1700b-0e89-7881-96a8-5259461a6c38, pass 5 (after rebasing onto the concurrent v207 and renumbering to Scenario 243) 01a17015-0451-7f03-9330-b0ef97b9f998 NO BLOCKERS on the exact resulting bytes, each started separately with codex exec -s read-only.

## Modifications

Three changes against the proposal text, each from an independent read-only gpt-6-astra review. (1) Reading validity is decided for the WHOLE reading: a reading is valid only when the response parses, rate_limit.allowed and rate_limit.limit_reached are both booleans, at least one window is present, and every present window is valid; a valid window beside a malformed one, or a missing or non-boolean flag, makes the reading unobservable and it is never admitted on its valid part. (2) Projection is attempted only for a valid reading that passes the floor with allowed true and limit_reached false; every other reading carries an explicit not-projected result with reason floor-zero, floor-skip, unobservable or codex-limit, kept distinct from unavailable. (3) Scenario 242 gains scenarios for allowed=false, for a malformed secondary window, for a secondary window's projection governing, and for a different-length window's baseline never being used; the limit-reached and not-allowed scenarios assert not-projected codex-limit. (4) The new scenario is numbered 243, not 242: the concurrent v207 (provisional-fleet-launch-scripts) took Scenario 242 before this pass was cut, so this revision was rebuilt on that master as v208. (5) Re-cut as v209: after pass 5 a concurrent v208 (bd-ib-y7372n, implement-turn re-entry, master 74859ba8d) landed first, so this revision was mechanically rebuilt on that master. The live-spec diff applied cleanly (the concurrent change touches one unrelated contracts.md line), the scenario stays 243, the only text change is the coverage reason's version label, and the history snapshot was regenerated from the merged live files; no ratified wording changed, so no further review pass was run.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-24T22:44:32Z
verdict: NO BLOCKERS
proposal_stem: codex-session-headroom
content_digest: bb18b08e016e88c9955ec0c5a959a13fe9efa998937ffbfe1b8a274452be89d4
