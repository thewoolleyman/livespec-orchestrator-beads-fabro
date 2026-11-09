---
proposal: a-sandbox-runs-tools-from-a-pinned-clone-and-works-in-the-latest.md
decision: modify
revised_at: 2026-11-09T16:17:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:kubernetes-sandbox-backend
---

## Decision and Rationale

Accepted in substance under delegated decision mode. It ratifies the maintainer's 2026-11-09 ~09:15Z ruling, recorded verbatim as a scope event on plan epic bd-ib-nmuyjc: tools RUN from a separate shallow, pinned, read-only clone at the known-good version, and WORK happens in the latest, writable, history-carrying clone. The incident it answers (run 01M6Y1Q7ZFWZ, bd-ib-bacahf, a check-doctor-static RecursionError from a livespec sibling cloned at a 0.47.0-era tip while the tree under test pinned v0.47.1 and CI passed) shows that the sandbox's checker version was set by pod start time rather than by the tree under test. Re-resolving the run-from clone at the janitor refresh closes that gap, and work clones stay at the latest commit so cross-repository reads and debugging keep working. The independent read-only sonnet review found no blockers. Its non-blocking notes: the lead sentence's 'clones of other repositories' loosely includes the target's own work clone, wording inherited from the proposal that does not change the normative content; the tests/heading-coverage.json row for Scenario 336 is added in the same change, owned by plan epic bd-ib-nmuyjc until the run/work-clone implementation child is filed under it.

## Modifications

(1) NNN resolved to Scenario 336. (2) The proposal's 'A tool MUST NOT execute from a work clone.' is narrowed to 'A tool from a repository other than the target MUST NOT execute from a work clone; the target repository's own tooling runs from the target's clone, which is the tree under test.' The proposal itself defines the target repository's clone as a work clone, so the unnarrowed sentence would have forbidden the target's own just check; the narrowed sentence keeps the intent that other repositories' tools run only from run-from clones. (3) This decision's resulting files are cumulative on the preceding decision's. (4) The Governing clause line uses the file's existing convention.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T16:15:08Z
verdict: NO BLOCKERS
proposal_stem: a-sandbox-runs-tools-from-a-pinned-clone-and-works-in-the-latest
content_digest: 53764bfe426f849db167d7ac0c64e3e5d23fd7783bf11fad47a5282131ea63b0
