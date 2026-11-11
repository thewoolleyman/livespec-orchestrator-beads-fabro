---
proposal: fetch-dispatch-helper-programs-in.md
decision: accept
revised_at: 2026-11-11T06:21:19Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as filed. The maintainer chose this design (option D) on 2026-11-10, recorded as scope event dpp-ruling-option-d-20261110 on plan epic bd-ib-x5ypbf (dispatch-payload-packaging): "Option D is basically putting a new node at the beginning of the workflow so that it will pull the stuff directly rather than jamming it in as a parameter." then "Yes, do that. Make it happen." The Dispatcher holds work item bd-ib-jrawlp at its spec-change-tier gate for exactly this topic (hold reason unratified-topic), naming ## Self-contained plugin dispatch as the heading to generalize. The proposal amends that section's body: the rendered run configuration carries a helper manifest (repository, installed build commit, one sha256 per composed helper) and no helper source; a setup step fetches the plugin source at that commit, composes and writes every helper with its file mode, and verifies every digest, re-running on resume; a digest mismatch, an unfetchable commit or a missing source path fails the run before dod_gate as LIVESPEC_PREPARE_PAYLOAD_DIGEST_MISMATCH with <helper>: <reason>; an installed build commit the forge does not have is refused before any claim; no gzip+base64-packed helper payload remains, while per-dispatch data may stay inline, packed; and the setup script stays short. The section's opening is reconciled so it still says the host needs no orchestrator clone, and no longer says the dispatch path clones only the target, which the pinned run-from clones paragraph (Scenario 336) had already made untrue. The behaviour is stated as BCP14 clauses with four new gherkin scenarios in Scenario 336's block, so placement split (i) holds; it is an orchestrator realization contract in this repository's contracts.md, so splits (ii) and (iii) hold. No H2 heading is added, renamed or removed, so tests/heading-coverage.json is unchanged. It composes with the setup-node migration of bd-ib-dpsiwz, because 'a setup step' holds whether setup is the run configuration's prepare table or run_prepare_N command nodes. No design record is contradicted: plan/dispatch-payload-packaging/research/002-direction-options-2026-11-10.md recommends this design.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T06:21:04Z
verdict: NO BLOCKERS
proposal_stem: fetch-dispatch-helper-programs-in
content_digest: 9bdaa126a40a683eb0ef1b5d0338a9742e6065571e453b3ee6994318e1765003
