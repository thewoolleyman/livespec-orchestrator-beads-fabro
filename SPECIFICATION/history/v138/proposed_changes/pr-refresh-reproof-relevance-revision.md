---
proposal: pr-refresh-reproof-relevance.md
decision: modify
revised_at: 2026-10-15T04:05:19Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5-plan-pr-refresh-reproof-relevance
---

## Decision and Rationale

Approved under the maintainer's delegation, not typed by the maintainer in this session. The maintainer authorized the freeze driver (gitops-fleet-capacity-monitoring) to approve spec revises after a Fable subagent review, in rulings recorded verbatim as scope events on livespec-dev-tooling-dfixhe at 00:08Z, 02:43Z and 02:46Z on 2026-10-15. The driver's Fable review #4 of these bytes returned APPROVE, recorded on dfixhe at 00:41Z, and the driver directed this session to revise and approve as v138, also recorded on dfixhe, at 04:01Z. The maintainer's original ruling was 'If the changes were not likely to be relevant or cause a difference in the definition of done, no need to re-run proof', and the rule had to be deterministic, conservative, and free of any LLM in the decision. The motivation is research note 001 of plan pr-refresh-reproof-relevance: 4 of the 5 runs that reached pr_refresh from 2026-10-11 to 2026-10-14 spent 64.1 min on 5 re-proof laps. The coordinator reports a further seven runs killed by the re-proof loop on 2026-10-14 under the stability freeze. The revise stale-branch precondition was skipped for exactly one branch, spec/plan-proof-release-rule-names-the-build-repository. Its whole diff against master is one added proposal file and cuts no history/ version, so it cannot collide with v138. The skip was authorized by the driver under the same delegation at 04:0xZ on 2026-10-15, and no other branch failed the check.

## Modifications

The proposal's 'not named by the item' relevance test is replaced, at the maintainer's choice, by a positively established observation scope. Rounds 1-11 of the gpt-6-astra ratification review then hardened it as follows:
(1) Round 1: a proof can read plan/ without naming it (list-plans), and path extraction from prose is not deterministic. Fix: a closed direct-read command grammar over literal canonical file paths, with pinned git invocations for the incoming paths, item paths and patch identity.
(2) Round 2: a hidden substitution inside double quotes, and symlink traversal behind '..'. Fix: every metacharacter is rejected outside single quotes, '$', backtick, '\' and '!' are rejected inside double quotes, '..' operands are rejected, and the path components must not be symlinks. Coverage was added for the posting failures, carry-forward resume, the pointer, and skipping reproof_required.
(3) Round 3: the working directory was not established, a read could take stdin, and the git show operand was undefined. Fix: the record must state 'Working directory: .' (proof_capture and proof_verify write it); each command has an exact production with required file operands and no '-'; git show HEAD:<path> extracts <path>.
(4) Round 4: an option-shaped bare grep pattern. Fix: such a pattern must not begin with '-', and counts must be decimal.
(5) Round 5: stable patch identity ignores whitespace. Fix: blob identities must be equal at both heads.
(6) Rounds 6-7: equal blobs can still materialize to different bytes. Fix: proof_verify records Read: <path> <git hash-object --no-filters> lines, and the new head's working-tree bytes must hash to them.
(7) Round 8: identical bytes can be interpreted differently (locale). Fix: a mechanical replay at the new head, under LC_ALL=C.UTF-8 with stdin closed, must print exactly each step's captured fenced text proof.
(8) Rounds 9-10: coverage of a replay that cannot execute and of a malformed proof block, plus the case count. Round 11 returned NO BLOCKERS.
(9) v138 re-cut: rebased past v137 (Scenario 179); Scenario 178 is inserted before 179. The inert history directories are anchored to <spec_root>/history/ and <spec_root>/templates/<name>/history/ per Fable review #4. The proposal text names the inserted section 'Proof carry-forward across a refresh'; it lands as three paragraphs, 'Proof carry-forward across a refresh', 'The observation scope' and 'The decision'.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-15T04:03:58Z
verdict: NO BLOCKERS
proposal_stem: pr-refresh-reproof-relevance
content_digest: ea32b40d0b887c8a4cbd27e60034125865d870ded7c64d1d55c808c5efb9cef4
