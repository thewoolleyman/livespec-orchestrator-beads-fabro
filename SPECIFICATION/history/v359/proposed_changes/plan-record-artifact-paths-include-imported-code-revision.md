---
proposal: plan-record-artifact-paths-include-imported-code.md
decision: modify
revised_at: 2026-11-12T05:16:34Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modify. As filed, the proposal makes a record's artifact paths include released library code that an executing artifact imports, and requires a byte-identity disclosure where a component's tag is named only because of such an import. But it leaves untouched the sentence of the same paragraph requiring that, where a release applies, the steps run the released artifact installed through its normal installation path. An unreleased artifact that imports a component's code from the default-branch tree can never meet that sentence, so ratifying as filed would leave such a plan with no truthful record. The round-2 independent replay of homelab plan secret-writer-stored-key-alias (epic homelab/hl-bvycoc; codex session 01a1cdb4-76c2-7eb3-a163-09acdf556a44, 2026-11-12T03:16:41Z) returned not_reproduced on exactly that ground. Its writer, infra/shared-credentials/write-secret.sh, has no released form and imports tools/shared_credentials/ (component shared-credentials) from main, and write-secret.sh pins that import path. Modifications: (1) keep the imported-code inclusion rule. (2) For a component the steps reach SOLELY through code imported or invoked by an executing artifact with no released form, the released-artifact requirement is met exactly when the commit's tree under the component's paths is byte-identical to the named tag's tree, and the record says so. (3) A step running a component's OWN released entry point must still run it installed through its normal path, and a replaying party must not verify a record that ran one from the tree. (4) The identity is not left to prose. The record claims the route on an `imported code:` line in its build identity, which the posting primitive renders from an optional imported_components array, refusing a malformed value. For every record whose `imported code:` line names a component, the archive gate in a component-declaring repository compares the commit's tree with the named tag's tree under that component's paths. It rejects on difference, naming the first differing path, including a one-sided path. It also rejects a line naming an undeclared component, a component that owns no named tag, or a record with no commit. A record without the line is judged exactly as before, so the ordinary installed-release route gains no new requirement (narrowed per legacy-coordinator-agent's grade of #4999). (5) The scenario is replaced by six cases: identical trees accepted, a differing tree rejected naming the path, the primitive rendering and refusing the line, no comparison without the line, release none still refused, and an own entry point run from the tree not verified. Scope and conditions (1)-(3) were set by legacy-coordinator-agent (session 72dc4e8c) under R301, reported to the maintainer for objection because the change relaxes a proof rule. The implementation carrier livespec-orchestrator-beads-fabro/bd-ib-y2s76v owns the spec-first TODO coverage row and the debt row.

## Modifications



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
reviewed_at: 2026-11-12T05:16:04Z
verdict: NO BLOCKERS
proposal_stem: plan-record-artifact-paths-include-imported-code
content_digest: ea276cff5db9e3bf2c34ed9f29e6372ce103b1c1dd91b1f5ebd731bc16c2064e
