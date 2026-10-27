---
proposal: post-host-record-refuses-an-item-without-its-own-merged-pull-req.md
decision: modify
revised_at: 2026-10-27T04:45:21Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratified, modified to harmonize with v242. This is the spec-first clause for bd-ib-56ruqk (post-host-record posted a PR-less item's host record onto an unrelated merged pull request). The filed proposal came from the plan's capture-spec-drift pass. A separate read-only Codex reviewer (gpt-6-astra, a configured ratification reviewer) returned NO BLOCKERS on the modified text in its first round.

## Modifications

Modified to harmonize with v242, which ratified the --pr selector and defined, for an item that no factory run merged, the pull request of its latest merged run as the pull request of its latest green reconcile-merged. v242 also added the refusal for an item with neither a merged run nor such a reconciliation. The filed text resolved the target "only from the pull requests that a dispatch of the named work item produced", which would forbid v242's reconciled pull request, and it restated a refusal v242 already carries. The inserted contracts.md text therefore now says the primitive MUST post only on "the pull request of the latest merged run for the named work item, as defined above". It keeps the filed no-fallback prohibition and the not-evidence sentence, and it adds that the refusal states the item has no merged pull request of its own. The two Scenario 136 cases are kept as filed, except that the refusal case also says no reconcile-merged reconciled the item.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-27T04:45:03Z
verdict: NO BLOCKERS
proposal_stem: post-host-record-refuses-an-item-without-its-own-merged-pull-req
content_digest: 49c044a62db940ad777727b306cffa9d35b58de95a1856a5fd1bf3ba556627bb
