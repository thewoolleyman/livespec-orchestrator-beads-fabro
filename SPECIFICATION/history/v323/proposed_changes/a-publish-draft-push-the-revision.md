---
proposal: a-publish-draft-push-the.md
decision: modify
revised_at: 2026-11-08T13:20:53Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Decided by legacy-coordinator-agent (session dbe006ec, model claude-opus-5-5) under R301 delegated authority and the maintainer's 2026-08-26 'I authorize all revises', on 2026-11-08 at about 13:2xZ: ACCEPT MODIFY on content digest b0c5ae9e.... This is the coordinator's decision, not the maintainer's; the plan seat publish-draft-green-work-loss (epic bd-ib-acrr56) drafted the bytes. Basis, as the coordinator stated it: the Publish repair paragraph routes only GH001 and pre-push hook refusals to fix, inside the shared two-round refresh-repair budget; protected-branch, non-fast-forward, unreachable-origin and authentication failures stay fail-closed; the accounting sentence names publish_draft; and the sentence forbidding LIVESPEC_REFRESH_REPAIR_ABSENT closes the mislabel class (bd-ib-abbb3j). The measured loss it closes: ob-td6fup run 01M6WF7GHVJX4NGBK1R4XHY8KW passed janitor and then ended at needs-human because GitHub refused the push with GH001 for two .pnpm-store files of 119 MB and 124 MB, a refusal the fix node could have repaired. An independent read-only sonnet review reported NO BLOCKERS on these exact bytes and independently confirmed the digest. Non-blocking note from the decider for the implementing carrier (bd-ib-7owmkq), not the spec: removing a GH001 path from unpushed commits can invalidate a rewritten Red-Green commit's TDD trailer checksums, so the fix turn should re-run Red-Green on that commit rather than amend the trailers by hand. Fleet scope: publish_draft is a node of the plugin's bundled implement-work-item workflow, so this governs every repository dispatched through it; forked workflow copies converge by their own re-sync.

## Modifications

Compared with the proposal: (1) the GH001 definition the proposal states as a note is folded inline into the 'The stages' sentence ('A GH001 rejection, origin refusing the push with GitHub's GH001 large-file error, MUST name ...'). (2) The four sentences the proposal quotes for replacement are wrapped across lines in contracts.md, so they did not match a single-line search; each was located by its text, and the wording matches the proposal. (3) 'Publish repair' adds that when a refused push would need a third round, the recovery artifact pointer 'Refresh-repair accounting' requires names the head whose push was refused, because a publish round has no pre-refresh head; Scenario 329's last case asserts it. (4) The proposal's 'A publish_draft refusal MUST NOT end the run at needs_human with LIVESPEC_REFRESH_REPAIR_ABSENT' reads 'Whichever route a publish_draft push refusal takes, it MUST NOT end the run at needs_human with LIVESPEC_REFRESH_REPAIR_ABSENT; a refusal that fails closed names its own cause', so that the fail-closed refusals are not read as forbidden from needs_human. (5) The new scenario is numbered 329, the next free number, and carries the repository's 'Governing clause:' line. Its heading-coverage and heading-coverage-debt entries are edited directly in the revise commit, owned by bd-ib-7owmkq, because resulting_files cannot reach tests/.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T13:18:56Z
verdict: NO BLOCKERS
proposal_stem: a-publish-draft-push-the
content_digest: b0c5ae9e66ad4346caf9cdc5ba3c1f2622dfe1f9c444a61036fb65e7f6d1b132
