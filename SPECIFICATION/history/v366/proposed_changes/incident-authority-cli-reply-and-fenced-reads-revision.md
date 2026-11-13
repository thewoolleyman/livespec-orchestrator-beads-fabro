---
proposal: incident-authority-cli-reply-and-fenced-reads.md
decision: modify
revised_at: 2026-11-13T04:40:22Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:expedited-incident-hardening
---

## Decision and Rationale

The proposal settles the one follow-up legacy-coordinator-agent ruled in its PASS grade of livespec-orchestrator-beads-fabro#5116 (v364, bd-ib-txbv7i): v364's read-head paragraph names `read-current` and "the full fenced identity", which the specification defines nowhere else, and says an item with no incident authority genesis reads absent without saying how a machine tells absent apart from a reading or a refusal. The new paragraph, placed immediately before the read-head paragraph because the specification lists none of the writer CLI's actions and that paragraph is the first place its reads are specified, defines the CLI reply (schema 1, status, result, authorizes_current_effects, normal_factory_proof false; exit 78 for a refusal, 0 otherwise), an attempt's full fenced identity (repository, canonical incident item id, attempt id, incident phase, generation, operation id, owner), and read-current, which verifies only the current head's full fenced identity, refuses incident-authority-identity-mismatch when the attempt id, incident phase, generation, operation id or owner differs from the current head's and incident-authority-changed when the head moves after selection, refuses a repository that does not match the item's incident authority genesis with that genesis read's named refusal, and is the only action whose reply authorizes a side effect. As ratified, each of those matches shipped code (`_reply`, `query_matches`, `_select`, `_reading`, `read_genesis` on orchestrator master at 3271c2f85). The proposal's own wording, "when any field differs", did not: `_select` calls `read_genesis` first, which refuses a mismatched repository as incident-authority-invalid-genesis, and the item id cannot differ because it selects the head; modification (b) corrects it. read-head's absent reply is pinned as status `absent`, exit 0, carrying the repository and item id and no phase or generation, with authorizes_current_effects false. A distinct status was chosen over a verified reply with a presence flag because livespec-dev-tooling's shared incident authority client treats an exit-0 reply whose status is not `verified` as the refusal incident-authority-not-verified, so absence fails closed in every existing consumer; the one consumer that wants absence, livespec-dev-tooling's incident fleet audit (livespec-dev-tooling-io6hyk), reads the status directly. read-head and the absent status are not yet built: bd-ib-txbv7i owes them, and the coordinator holds its approve until this revise merges so the factory builds read-head once. legacy-coordinator-agent accepted this design for grading, merged the proposal as #5122, and assigned this revise the slot immediately after v365 (bd-ib-5psq3e). Coherence with open proposal incident-read-history-returns-only (#5048), which spells the same fenced identity inline for read-history: the field set is identical, so whichever revises later may refer to the defined term. No existing H2 heading is added, removed or renamed in contracts.md.

## Modifications

Two modifications. (a) In the read-head paragraph, "It MUST report the item's current incident phase and generation from the canonical incident authority chain, reporting `drill-closed` for a `drill-closed` head." gains ", in a reply whose `status` is `verified`," after "authority chain". The proposal's Proposed Changes prose states "A reading of a present item replies `verified`." and its Scenario 364 edit asserts that status, but its quoted replacement text never stated it; without the clause, a scenario would assert behaviour no clause states (core revise split (i)). (b) Decided by legacy-coordinator-agent's PASS-WITH-FIXES grade of livespec-orchestrator-beads-fabro#5125 (2026-11-13): in the new paragraph, "It MUST refuse with the named reason `incident-authority-identity-mismatch` when any field differs" now reads "... when its attempt id, incident phase, generation, operation id or owner differs from the current head's", and the sentence "A repository that does not match the item's incident authority genesis MUST refuse with that genesis read's named refusal." follows that sentence. As proposed, the clause named the wrong refusal for an ordinary, reachable input: `_select` calls `read_genesis` first, and a repository that does not match the genesis record refuses there as incident-authority-invalid-genesis (asserted by tests/test_incident_receipt_source.py and tests/test_incident_authority_cases.py); the item id cannot differ because it selects the head. Everything else is the proposal's quoted text and its listed Scenario 364 edits, applied verbatim, and its Scenario 365 appended unchanged. 365 keeps its number: master tops at Scenario 364 (v365 added no scenario) and none of the 74 open pull requests nor any other pending proposal claims it, scanned at 2026-11-13T04:37Z. Co-edit outside the spec target, in the same commit: tests/heading-coverage.json gains a TODO row for Scenario 365 owned by bd-ib-txbv7i (integration tier or above), the Scenario 364 row's reason gains the status and exit-code observables, and tests/heading-coverage-debt.json gains the Scenario 365 debt entry.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T05:15:05Z
verdict: NO BLOCKERS
proposal_stem: incident-authority-cli-reply-and-fenced-reads
content_digest: 85921f7fca9ff720330019ebf0d83ea4d1f78513bc8b2db33c4dbe0f2efc726a
