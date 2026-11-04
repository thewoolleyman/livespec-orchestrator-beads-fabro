---
proposal: fleet-launch-launcher-parity-gates.md
decision: modify
revised_at: 2026-11-04T17:20:50Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:gmktec-factory-placement
---

## Decision and Rationale

Decided in delegated mode by claude:gmktec-factory-placement under legacy-coordinator-agent ruling R301 (2026-11-04 ~13:10Z). This is a RE-CUT: the same decision was cut locally as v295 (commit 54b653897, never pushed), but orchestrator PR #4387 took v295 on master (merged 2026-11-04T17:17:07Z), so the branch was rebased onto that master and the identical modification re-applied (the only change to the resulting bytes is the new base). The proposal states, as MUST rules under §"Provisional fleet launch scripts", the six caller-side launcher gates whose absence from the committed fleet-launch/ launchers blocks the bd-ib-x7bwug cutover (work item bd-ib-3ufx6l): the red-master repository hold, the repository WIP gate before the launch-time preflight, the breakage exception at wip_cap+1, the early-exit re-ticket, the gmktec factory hold file read by the launcher itself, and the gmktec target setting with its candidate cap, plus harness coverage of each. It only adds text; no whole-host idle gate is added, because the section already requires factory-class pressure.

## Modifications

Unchanged from the v295 cut. First, per the revise authoring discipline (behaviour needs a clause and a scenario), it adds Scenario 307 to scenarios.md, one Gherkin scenario per gate. Second, the first independent review found one blocker: the WIP gate read a raw active work-item count, which would make the launcher a second repository-capacity authority contrary to §"Dispatcher admission, WIP cap, and post-merge acceptance" and §"Per-repo WIP cap". The gate, the harness paragraph and Scenario 307 read the counted-claims count through the authoritative capacity projection of §"Orchestrator-owned attention facts" → "Capacity single authority", and the launcher MUST NOT derive it from its own count of status-active rows. Third, from the review nits: the breakage-exception list is named fleet-launch/breakage-exception with its path a config.sh host value; "admits" became "does not hold", with a sentence that the Dispatcher's own WIP cap still applies; and the gmktec hold-path sentence says the launcher reads the path from its config.sh host value into a variable of its own. The re-review of the rebased final bytes found NO BLOCKERS.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-04T17:20:14Z
verdict: NO BLOCKERS
proposal_stem: fleet-launch-launcher-parity-gates
content_digest: 3357dceb41294ffb9bed7f4c4262e0b30596580a475c48e691e0785ab10ff35e
