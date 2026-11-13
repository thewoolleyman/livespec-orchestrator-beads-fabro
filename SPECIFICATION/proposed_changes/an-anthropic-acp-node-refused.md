---
topic: an-anthropic-acp-node-refused
author: claude:fabro-currency session 2032fcbc
created_at: 2026-11-13T10:37:39Z
---

## Proposal: An in-run Authentication required refusal at an anthropic ACP node re-probes the run's own slot and retries with bounded backoff, fleet-wide

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a clause to contracts.md section "Provider-limit permanence and root-cause surfacing" for a fourth, retry-resolvable refusal class: an agent refusal reading "Authentication required" at an anthropic-availability ACP node, on a credential slot the host can still use. The Dispatcher re-probes the run's own projected slot from the host before routing the node's outcome. A usable slot earns a bounded, backed-off retry of the node, and an unusable slot rests the item at blocked/needs-human naming the slot. Every probe is journaled by slot name and one-way identity, never by value, and takes a host session-headroom reading at the moment of the refusal. The clause binds every anthropic-availability node of every bundled factory workflow on every factory server. Add one scenario that exercises it.

### Motivation

Work item bd-ib-wqxgjf, filed on legacy-coordinator-agent's GO, is held at the spec-change tier (verdict unstated; generalization target this section; linked topic an-anthropic-acp-node-refused). Measured on 2026-11-13: two runs ended at needs_human on "the agent answered session/prompt with an error: Authentication required" (failure_class retry_requested, two attempts about 20 s apart, acp.turns 0). They were livespec-dev-tooling-5wybjq run 01M7A2P35VZH8WYX5VBVJ3YH9R at proof_verify about 09:48Z, and bd-ib-3h7dsf run 01M79K37K1D0K78FGBJ70AP03A at proof_capture@3 at 10:21:24Z. Both held slot CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_0 run-wide. That slot's journaled credential identity (sha256 of the value) was constant at a98e4044cc631956 across 114 rows from 2026-11-12T12:00Z to 2026-11-13T10:31Z, and a host probe at 10:31:25Z returned usable, HTTP 200. The same run's proof_capture had succeeded on the same token two minutes before proof_verify was refused. No rotation stranded a sandbox snapshot, and the refusal is not a ceiling, so neither the permanence classes of this section nor the admission-time credential-probe re-probe clause covers it, and today one transient refusal costs the whole run's tail. The coordinator ruled it a rework-cost class at fleet scope. The host session-headroom reader also had no reading of slot 0 between 09:30Z and 10:05Z, so the refusal was unobserved from the host.

### Proposed Changes

### contracts.md — §"Provider-limit permanence and root-cause surfacing"

Insert this clause after **CONTROL — an ordinary failure keeps its classification.**:

**An in-run authentication refusal on a usable slot is retried, not permanent.** A turn at an anthropic-availability ACP node that ends with the agent error "Authentication required" is NOT one of the permanent classes above, and it is NOT a provider usage or spend ceiling. The rules below bind every anthropic-availability node of every bundled factory workflow (including `proof_capture`, `proof_verify`, `review_fix`, `dod_gate` and `disposition`), on EVERY factory server the Dispatcher dispatches to. That is FLEET SCOPE: no factory, workflow or node is exempt.

- **Re-probe before routing.** Before the node's outcome is routed, the Dispatcher MUST probe, from the host, the credential slot the run was dispatched with: the slot admission chose and projected (§"Provider spend containment"), never a different slot. The probe MUST read the slot's value through the dispatch target's declared credential wrapper as it stands at the moment of the probe.
- **A usable slot is retried with bounded backoff.** When the probe reports the slot usable, the Dispatcher MUST run the node again after a backoff. It MUST allow at most three further attempts for one refusal, each wait MUST be at least 30 seconds, and each wait MUST be longer than the one before it.
- **An unusable slot rests the item, naming the slot.** When the probe reports the slot not usable, the Dispatcher MUST NOT retry. The work-item MUST rest at `blocked` with `blocked_reason: needs-human`, and the recorded cause MUST name the slot's environment-variable name and the probe's condition.
- **Exhausted retries rest the item, naming the attempts.** When the attempts are spent and the node is still refused, the work-item MUST rest at `blocked` with `blocked_reason: needs-human`, and the recorded cause MUST name the slot's environment-variable name, the number of attempts and the last probe verdict.
- **Every probe is journaled by identity, never by value.** Each probe MUST write one dispatch-journal row naming the work-item, the run id, the node, the slot's environment-variable name, the slot's one-way credential identity and the probe verdict. The row MUST NOT carry any credential value.
- **Every probe reads the slot's headroom.** Each probe MUST also record a host session-headroom reading of that slot, taken at the moment of the refusal, so a refusal is never unobserved from the host.
- **Boundary.** This clause governs a refusal DURING a run. The admission-time credential-probe refusal of §"Provider spend containment" still governs a refusal before claim. A refusal whose cause chain carries a provider usage or spend ceiling MUST still take the permanent classification above and MUST NOT be retried under this clause.

### scenarios.md — one new scenario, numbered at revise

```markdown
## Scenario NNN — An Authentication required refusal at an anthropic ACP node re-probes the run's own slot and retries only while the slot is usable

` ` `gherkin
Feature: A transient authentication refusal costs a retry, not a run

Scenario: A usable slot is retried with bounded backoff, and the probe is journaled without the value
  Given a run dispatched with credential slot S, at an anthropic-availability ACP node
  And the node's turn ends with the agent error "Authentication required"
  And a host probe of slot S reports it usable
  When the Dispatcher routes the node's outcome
  Then the node runs again after a wait of at least 30 seconds
  And at most three further attempts are made for that refusal, each after a longer wait than the last
  And one dispatch-journal row names the work-item, the run, the node, slot S's environment-variable name, its credential identity and the verdict usable, and carries no credential value
  And a host session-headroom reading of slot S is recorded at the moment of the refusal

Scenario: An unusable slot rests the item and names the slot
  Given the same refusal
  And a host probe of slot S reports it not usable
  When the Dispatcher routes the node's outcome
  Then the node is not retried
  And the work-item rests at blocked with blocked_reason needs-human
  And the recorded cause names slot S's environment-variable name and the probe's condition
` ` `
```

(The inner fence is written as "` ` `" so it survives inside this proposal. At revise it MUST be written as a normal triple-backtick gherkin fence, as every scenario in scenarios.md is.)

### Co-edits at revise time

The revise MUST add one `tests/heading-coverage.json` entry for the new `## Scenario NNN — ...` heading, as numbered at revise. It MAY carry `test: "TODO"`, its `reason` MUST name the tier the owed test runs at (integration tier or above: the Dispatcher's outcome routing driven against a stand-in ACP refusal and a stand-in probe), and it MUST carry `"work_item": "bd-ib-wqxgjf"`. The revise MUST regenerate `tests/heading-coverage-debt.json` with `uv run python -m livespec_dev_tooling.heading_coverage_debt` and stage the result, never hand-authoring the row. No other heading changes.
