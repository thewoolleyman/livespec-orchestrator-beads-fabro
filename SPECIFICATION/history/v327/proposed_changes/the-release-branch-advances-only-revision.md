---
proposal: the-release-branch-advances-only.md
decision: modify
revised_at: 2026-11-09T03:08:27Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Decided by legacy-coordinator-agent (session e8d70af3) under R301 delegated authority on 2026-11-09: MODIFY on content digest 65b0bb83. This is a re-scope of its earlier ACCEPT (~01:3xZ), made at ~03:1xZ after the drafting session found a cross-repo ordering conflict. The proposal advanced `release` only after a release's canary samples. livespec-dev-tooling's ratified spec (v155, Orchestrator build adoption) starts a canary with an adopt step that installs only the commit `release` names, so as filed neither step could come first. The basis is otherwise unchanged. Every fleet clone's committed settings, and this host's single known_marketplaces.json entry, resolve this plugin at ref `release`. fast-forward-release-branch.yml advanced the unprotected `release` branch on every `release: published` event. So session starts adopted uncanaried builds: this repository at 2026-11-09T01:28:45Z (c0b28ad85bab -> 35cdda22389c, v0.307.0, seven minutes after publication), livespec-dev-tooling at 01:51:48Z, and livespec-overseer at 01:58:17Z. The re-scope conforms the realization to livespec-dev-tooling v155 option D. That option says a member adopts a build only through a named operator step. An independent read-only sonnet review reported NO BLOCKERS on these exact bytes at 2026-11-09T03:07:06Z, recomputed the digest itself, and checked that the paragraph composes with the adopt step and the canary-and-roll ordering without deadlock. Its non-blocking notes, for the implementing carrier bd-ib-sghxlk: the missing-tag case slightly exceeds the paragraph's text; Scenario 331 has no case for the hold-before-dispatch obligation, which is operator procedure; and the paragraph could later be split. Drafted by claude:gmktec-factory-placement (plan gmktec-factory-placement, epic livespec-dev-tooling-me5aqz).

## Modifications

(1) The release-branch dispatch STARTS a release's canary, at a time the operator chooses and never on publish, and the canary's clones then adopt the build `release` names. The proposal had placed the dispatch AFTER the canary samples and called it the roll step. (2) The roll step is now the fleet-wide adoption that follows the canary samples, and the paragraph says the roll step MUST follow them. (3) While a fleet clone's session-start refresh still installs whatever `release` names, an operator MUST hold factory launches from every such clone outside the canary before dispatching, until the canary samples are judged. (4) 'canary', 'canary samples' and 'roll step' are defined in the paragraph itself, with no section citation into another repository's specification. livespec-bpzy drops such a reference in this repository's CI doctor-static job, which is how livespec-orchestrator-beads-fabro#4691 was refused. (5) Scenario 331 is retitled 'The release branch advances only on an operator dispatch that starts a canary'. Its Feature line matches the new title, and its dispatch cases name an operator rather than the roll step. (6) Content is placed in house format: the H2 is outside the gherkin fence, followed by a Governing clause line and a Feature line, and the placeholder is filled as 331. (7) tests/heading-coverage.json gains one TODO row for the Scenario 331 heading, owned by bd-ib-sghxlk, through resulting_files path ../tests/heading-coverage.json. The proposal's other MUSTs are kept word for word: no advance on `release: published`, no job run for that event, fast-forward-only with failure and the commit kept, and the dispatch command.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T03:07:06Z
verdict: NO BLOCKERS
proposal_stem: the-release-branch-advances-only
content_digest: 65b0bb8312ada55e5a2e7a5e63f1753917741d212bceb23ae8633f884415b7a0
