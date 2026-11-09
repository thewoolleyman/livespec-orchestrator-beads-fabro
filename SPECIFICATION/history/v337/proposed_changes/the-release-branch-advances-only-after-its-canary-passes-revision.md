---
proposal: the-release-branch-advances-only-after-its-canary-passes.md
decision: modify
revised_at: 2026-11-09T22:19:42Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted with one modification, on the maintainer's ruling given in the gmktec-factory-placement session at about 17:0xZ on 2026-11-09 (recorded as a scope event at 17:02:45Z on livespec-dev-tooling-me5aqz). The maintainer chose accept over 'reject, keep v327' and 'defer until 7upzav ships'. The release branch advances only at the roll step, after a release's canary samples pass. Canary clones adopt the release by a named-build adopt naming its tag, and release keeps naming the last rolled build throughout the canary. The evidence is the 2026-11-09 0.308.0 canary, whose session-start leaks left six projects on a broken build. This deliberately departs from v327 (livespec-orchestrator-beads-fabro#4708), which this decision supersedes.

## Modifications

Scenario 331's body is replaced as proposed, but its heading text is KEPT ('The release branch advances only on an operator dispatch that starts a canary'), because this repository's heading-coverage debt register refuses a revise that removes an H2 from a file in which new TODO debt is registered (register_grew); renaming cannot reset debt. The heading no longer describes the order the body states. Renaming it is owed by the change that gives Scenario 331 a real test (bd-ib-sghxlk), and the heading-coverage row's reason was updated to the new behaviour. After the pre-merge LLM doctor phases (high findings 1 and 2): the named-build adopt is named as livespec-dev-tooling's just adopt-orchestrator-build <clone> <tag>, the tag form that pending proposal a-canary-clone-adopts-a adds (owner livespec-dev-tooling-zpqvnr). Until that tag form exists, a new orchestrator release MUST NOT be canaried and release MUST NOT advance, except by a corrective roll-forward the operator records as one; the roll-step sentence names that exception. A clone MAY serve as a canary clone only while its session reconcile holds its installed orchestrator build (livespec-dev-tooling-7upzav). Each canary sample records the clone's install-record gitCommitSha, and a sample not on the tag's commit is discarded, not judged; Scenario 331 gains a matching And-line. The sentence requiring release to name a build whose canary has passed now names the corrective roll-forward exception, matching the roll-step sentence. A corrective roll-forward is defined: a release whose only purpose is to replace a rolled build that has failed, advanced through the same fast-forward-only workflow, and recorded on the roll's tracking work item naming the failed build. The canary sample record is the launching launcher's verdict file, naming the full gitCommitSha of the canary clone's install record read at launch. The adopt step leaves the host's marketplace registration unchanged when it ends, and another clone's install MUST NOT move while it runs.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T22:19:09Z
verdict: NO BLOCKERS
proposal_stem: the-release-branch-advances-only-after-its-canary-passes
content_digest: f5d5947d952e75b93f726f179c09c8cefc6e7ffc5aa5663b2ac25348ed5d417a
