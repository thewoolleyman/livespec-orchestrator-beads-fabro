---
proposal: a-plain-dispatch-has-no.md
decision: modify
revised_at: 2026-11-05T16:57:14Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:publish-draft-green-work-loss
---

## Decision and Rationale

Accepted as MODIFIED in delegated mode. legacy-coordinator-agent ruled under R301 on 2026-11-05 to ACCEPT this proposal as modified, on digest 190357748cb8c0be9f057963a0b37300343fd73c8df57cac1438e53d57e63049, for bd-ib-ltlg4i (plan publish-draft-green-work-loss, epic bd-ib-acrr56). Both proposals close the defect class measured on 2026-11-05, in which recovery routing silently passed over a ruled or hand-named needs-human tree. bd-ib-abbb3j run 01M6P62T6XV0 was seeded from the oldest, reference-only tree, and bd-ib-hap62u routed fresh. A ruled seed is now honoured by name or held by name, and never falls through. A needs-human tree is recognised by the run it carries and reported when passed over. No ## heading is added or removed, so heading coverage is unchanged. An independent read-only sonnet reviewer found NO BLOCKERS on the exact final bytes in its second round. Its first round had blocked on MUST clauses that had no scenario, and those scenarios were added.

## Modifications

Against the filed proposal: (1) Ruling currency and consumption moved from the host journal to the ledger, because ledger writers are multi-host. A ruling is CURRENT until a livespec-seed-ruling-consumed ledger comment names it, and routing reads rulings from ledger comments, never from a host journal alone. The consumed comment is written once the run exists, names the dispatch id and the run id, and is backfilled by reconciliation when it is missing. The ruling comment must pass the shared template-opener detector. (2) Reviewer-driven clarifications: the across-dispatch pre-claim refusal is still graded first for a ruled item; a missing or moved ruled ref is stated as a held cause in its own right; the item's earlier-run identifiers are defined; and the needs-human identification is taken once per routing pass by one listing. (3) Scenarios: ten scenarios added beyond the filed six (sixteen in all, inside Scenario 185's fence). They cover the seed-ruling command's success and exit-3 refusal, ruling over an admissible resume, a non-fallback refusal holding a ruled item, a later ruling replacing an earlier one, the reconciliation backfill, both needs-human tie-break branches, the empty passed_over_needs_human list, and one identification per pass.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T16:55:30Z
verdict: NO BLOCKERS
proposal_stem: a-plain-dispatch-has-no
content_digest: 190357748cb8c0be9f057963a0b37300343fd73c8df57cac1438e53d57e63049
