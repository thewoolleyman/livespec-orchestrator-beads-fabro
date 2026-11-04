---
proposal: test-performance-gates.md
decision: modify
revised_at: 2026-11-01T04:36:31Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:revise-test-performance-gates
---

## Decision and Rationale

Modified, then ratified under the repository's delegated decision mode (`spec_governance.revise_decision_mode: delegated`; maintainer ruling 2026-11-01 that plan implement-test-performance, epic livespec-dev-tooling-sv6m5p, runs autonomously). The four findings are the linked proposals of held items bd-ib-v3iw35, bd-ib-zneh24, bd-ib-hjo7lb and bd-ib-fapmpq, and each rests on measurement in livespec-dev-tooling plan/implement-test-performance/research/001-003. Per finding: (1) bd-ib-v3iw35, staged tests before the whole suite: MODIFIED. The direction is sound and orders the gate without narrowing it, as the maintainer's 2026-11-01 ruling requires. The text was written before v262, so it is re-cast for any Green-amend-shaped commit whoever makes it (`commit_green` or a hand commit on a host), because the hook still runs for both. Applied literally, its 'run the pre-commit aggregate exactly as before, including the whole-suite coverage members' would contradict contracts.md 'An implement or review_fix turn's commits run the affected-tests gate', under which `commit_green`'s hook runs the scoped `just check-changed` gate; the staged tests therefore precede the other test-running members of whichever gate the commit runs, and that gate then runs exactly as before, once. To agree with the ratified-but-unimplemented 'The check aggregate runs its independent targets concurrently' (bd-ib-6zy3zd), the staged tests are the first step of the pytest lane and the independent targets still run beside them, with their verdicts reported on refusal. The proposed second case became Scenario 289's second case, and a third (independent targets) and fourth (`commit_green`) case were added. (2) bd-ib-zneh24, worker count from allowed CPUs: MODIFIED. Applied to the projection paragraph as filed, with the quota rounding and the unchanged divisor and one-worker minimum stated so the clause is decidable, and the 'never from the host's visible core count' sentence narrowed to where a quota or narrower affinity mask applies, because on an unrestricted host the affinity mask IS the visible count. The scenario became new Scenario 290 rather than a case of Scenario 254, whose heading and paragraph govern the concurrent aggregate, not the resolver. Note for the implementer: a CI runner pod with no CPU limit and an unrestricted affinity mask still resolves to the node's count, so the measured 8-versus-18-worker variance (research 003, run 41266553603) disappears only once runner pods carry a CPU limit, which is runner configuration outside this repository. (3) bd-ib-hjo7lb, coverage omits tests/: ACCEPTED as filed. It conforms to livespec non-functional-requirements.md 'Code coverage thresholds' (an omit-only blocklist excluding test scaffolding); first-party source keeps 100% line and branch coverage. A decidable configuration constraint, so no scenario. (4) bd-ib-fapmpq, thirty slowest test phases: MODIFIED only to name both targets that can run the whole suite with coverage (`check-per-file-coverage`, and `check-coverage` when it finds no coverage data and runs the suite itself, as in CI), and to add a case to Scenario 254, which exercises that paragraph. No resolution departs from a design record. Scenario numbers 289 and 290 are the next numbers neither ratified (scenarios end at 285) nor claimed by a pending proposal (282-284 and 286-288 are). The independent sonnet reviewer returned NO BLOCKERS for these exact bytes on its first pass; its advisories (no scenario case for the not-skippable sentence, a larger quota example in Scenario 290, splitting the either-or Given of the new Scenario 254 case) are left to the implementing items. Step 3.5 stale-branch precondition skipped via `--skip-stale-branch-check` (delegated decision, 2026-11-01): it reported spec/host-judgement-isolation, spec/reprove-merged-item-v2 and spec/revise-label-and-sandbox-retention, recorded as non-blocking by the v262 pass, and spec/rebase-node-timeout-cut-proposal-v262 (b4524e99d), which edits only the pending proposal node-timeout-cut-retry-carries-the-cut-state; none cuts a version or edits the text changed here, and none was touched.

## Modifications

1. constraints.md '## Pre-commit staged pre-check': the opening sentence now says the section adds one leading step and runs a Green amend's staged tests ahead of the other tests its gate runs. The new paragraph 'A Green amend runs its staged tests before the rest of its gate's tests' defines a Green amend by shape whoever makes it (`commit_green` or a hand commit on a host); the staged tests (those the amend stages plus those HEAD's commit adds or modifies) finish before any other test-running member of the commit's gate, which is the pre-commit aggregate's whole-suite members or the affected-tests gate's scoped tests; they run as the first step of the pytest lane with independent targets beside them; on failure the hook refuses naming each test, starts no further test-running member and still reports the independent targets' verdicts; on success the rest of the gate runs exactly as before, once; the output names the refusing phase (staged pre-check, staged tests, or gate); not skippable; names Scenario 289.
2. contracts.md '### Sandbox test-worker parallelism', projection paragraph: the resolver sentences, with quota/period rounded down to whole CPUs, else the affinity mask; the MUST NOT narrowed to where a quota or narrower mask applies; divisor and one-worker minimum unchanged; names Scenario 290.
3. constraints.md '## Inherited from livespec': coverage bullet replaced as filed.
4. contracts.md 'The check aggregate runs its independent targets concurrently': the thirty-slowest-phases sentence names check-per-file-coverage and check-coverage when it runs the suite itself; Scenario 254 gains the case 'Every whole-suite coverage run names its slowest test phases'.
5. scenarios.md: new Scenario 289 (four cases) and Scenario 290 (three cases) appended after Scenario 285.

## Resulting Changes

- constraints.md
- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-01T04:35:53Z
verdict: NO BLOCKERS
proposal_stem: test-performance-gates
content_digest: f3b39efbf35e2b14b08180c90ab0573df1046e8d8f57905b040b2d9d674fcd1a
