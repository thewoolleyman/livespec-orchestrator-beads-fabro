---
proposal: sandbox-path-protection.md
decision: modify
revised_at: 2026-10-15T09:52:44Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5-plan-checkpoint-commit-hook-failures
---

## Decision and Rationale

Accepted with two modifications ordered by this revise's independent ratification review. gpt-6-astra round 1 (codex session 01a13ef6-ca84-77a2-933a-77adac3dac2f, completed 2026-10-15T09:50:19Z) returned BLOCKERS on the proposal as written: (1) the sentence exempting removals under a scratch directory or inside the repository tree contradicted the refusal rule for a mixed-target command such as 'rm -rf /tmp/layout-sim /workspace'; (2) Scenario 180 omitted the clause's premise that the agent's adapter runtime offers a pre-shell-command hook. Round 2 (codex session 01a13ef8-dc2c-7df1-96f0-e50f6e7ebfab) returned NO BLOCKERS on these final bytes. Decision authority: the maintainer authorized the freeze driver (session gitops-fleet-capacity-monitoring) to approve spec revises after a Fable review; that authorization is recorded on livespec-dev-tooling-dfixhe (scope event, 2026-10-15T00:08Z). The driver directed this revise as v142 and chose it as this plan session's next step; this session did not receive the authorization from the maintainer directly, and the driver's Fable review gates the merge. Step 3.5 note: the stale-branch precondition was skipped explicitly. Its findings were spec/plan-proof-release-rule-names-the-build-repository (owner k3s-on-gmktec-for-vps-usage) and spec/factory-addresses-from-a-gitops-registry (owner petri-factory-on-gmktec); outside plan/ each adds only its own proposed-change file and touches none of this revision's resulting files. The driver authorized the skip for exactly these two branches. Implementation carrier: bd-ib-jgedjo (plan checkpoint-commit-hook-failures, epic bd-ib-hcwmnq), which owns the Scenario 180 heading-coverage TODO and debt row added in the same commit.

## Modifications

contracts.md: the 'The run's working tree survives the agent.' paragraph is inserted directly after 'A commit leg completes past one tool call.', verbatim from the proposal except that the allowance sentence now reads 'A command none of whose executed segments would remove, move, or replace a protected path MUST NOT be refused, including one that removes, moves, or replaces a path under a scratch directory such as `/tmp`, or a file or directory inside the repository tree.' (round 1 blocker 1). scenarios.md: Scenario 180 is inserted between Scenario 179 and Scenario 181 with the proposal's four scenarios, plus a Background step 'Given the implement-stage agent's ACP adapter runtime offers a hook that runs before each shell command' (round 1 blocker 2) and a fifth scenario 'a command that also removes a protected path is refused' for 'rm -rf /tmp/layout-sim /workspace' (round 1 blocker 1).

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-15T09:52:10Z
verdict: NO BLOCKERS
proposal_stem: sandbox-path-protection
content_digest: 156dcc6e2cf468eeef5393edf08c5fcde3a2529f1b606081032397bfa8393d58
