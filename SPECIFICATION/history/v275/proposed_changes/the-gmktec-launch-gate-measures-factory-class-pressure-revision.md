---
proposal: the-gmktec-launch-gate-measures-factory-class-pressure.md
decision: accept
revised_at: 2026-11-02T07:46:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

ACCEPT. Ratifies what bd-ib-nmuyjc.6 asks for: a provisional launcher's gate on a shared factory node measures factory-class pressure (the factory namespaces' pods plus system.slice), not whole-host idle. The dispatcher refused .6 pre-dispatch at 2026-11-02T06:37:43Z as spec-change tier (PARTIAL; heading to generalize: Provisional fleet launch scripts). Decided under delegated revise_decision_mode by seat kubernetes-sandbox-backend (plan epic bd-ib-nmuyjc), on coordinator legacy-coordinator-agent's 2026-11-02 ruling recorded on livespec-dev-tooling-6tgd2z. The spec is led from measurement (gmktec-xubuntu at under 1 percent idle in CI bursts, about 02:14-02:29Z), not drift-origin. No design record is contradicted. The clause stays a caller-side gate under contracts §'Dispatcher admission, WIP cap, and post-merge acceptance'. Independent review: two separately spawned read-only reviewers returned NO BLOCKERS on these exact bytes, each in its first round: opus, and then sonnet, the model .livespec.jsonc configures as ratification_reviewer_model. Its nits are left to .6's implementation: point line 5695's 'measured idle CPU' example at factory-class pressure; give Scenario 296 a concrete stub idle value; make the factory namespace list and the sample window FLEET_LAUNCH_ values; say whether the mi-homelab path adopts the gate; add 'under its ceiling' to Scenario 296's first Given; and state the threshold's units. Further sonnet nits: add an equality case at the threshold; treat an out-of-range reading as unparseable; and say whether capacity means cores or allocatable. RE-LANDED as the next version: a concurrent revise (master-ci-green-ancestor-passes-preflight) took v274 first, and PR #4164 conflicted. The same edits were reapplied onto current master's contracts.md and scenarios.md, and a fresh separately spawned read-only sonnet review returned NO BLOCKERS on these exact bytes. Its further nits are left to .6: state whether FLEET_LAUNCH_GMK_MIN_IDLE is removed; say which factories the launcher config marks as shared-node.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T07:46:04Z
verdict: NO BLOCKERS
proposal_stem: the-gmktec-launch-gate-measures-factory-class-pressure
content_digest: 31ccfa41d45cb754e6a414ddc0baf91bc7aaea9768ed762b82e0d89ac7685805
