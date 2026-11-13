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

Add a clause to contracts.md section "Provider-limit permanence and root-cause surfacing" for a refusal a re-dispatch can resolve: an agent refusal reading "Authentication required" at an anthropic-availability ACP node, which ends the run at its needs_human terminal after the node's declared in-run retries. After that run terminates, the host Dispatcher compares the run's dispatched credential identity with the slot's current one. Only if they are equal does it probe the slot. A usable, unchanged slot is released back to ready for a backed-off re-dispatch from preserved work, through the same between-runs mechanism as the provider-limit release, with at most three consecutive releases in addition to the node's own retries. A changed identity, an unusable slot, or a fourth refused run rests the item at blocked/needs-human, naming the slot and identities, never a value. Every probe is journaled by identity and takes a host session-headroom reading. The clause binds every anthropic-availability node of every bundled factory workflow on every factory server. Add one scenario heading that exercises it.

### Motivation

Work item bd-ib-wqxgjf, filed on legacy-coordinator-agent's GO, is held at the spec-change tier (verdict unstated; generalization target this section; linked topic an-anthropic-acp-node-refused). Measured on 2026-11-13: two runs ended at needs_human on "the agent answered session/prompt with an error: Authentication required" (failure_class retry_requested, two attempts about 20 s apart, acp.turns 0). They were livespec-dev-tooling-5wybjq run 01M7A2P35VZH8WYX5VBVJ3YH9R at proof_verify about 09:48Z, and bd-ib-3h7dsf run 01M79K37K1D0K78FGBJ70AP03A at proof_capture@3 at 10:21:24Z. Both held slot CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_0 run-wide. That slot's journaled credential identity (sha256 of the value) was constant at a98e4044cc631956 across 114 rows from 2026-11-12T12:00Z to 2026-11-13T10:31Z, and a host probe at 10:31:25Z returned usable, HTTP 200. The same run's proof_capture had succeeded on the same token two minutes before proof_verify was refused. No rotation stranded a sandbox snapshot, and the refusal is not a ceiling, so neither the permanence classes of this section nor the admission-time credential-probe re-probe clause covers it, and today one transient refusal costs the whole run's tail. The coordinator ruled it a rework-cost class at fleet scope. The host session-headroom reader also had no reading of slot 0 between 09:30Z and 10:05Z, so the refusal was unobserved from the host.

### Proposed Changes

### contracts.md — §"Provider-limit permanence and root-cause surfacing"

Insert this clause after **CONTROL — an ordinary failure keeps its classification.**:

**An authentication refusal on the run's own usable slot is released for re-dispatch, not permanent.** A turn at an anthropic-availability ACP node that ends with the agent error "Authentication required" is NOT one of the permanent classes above, and it is NOT a provider usage or spend ceiling. The rules below bind every anthropic-availability node of every bundled factory workflow (including `proof_capture`, `proof_verify`, `review_fix`, `dod_gate` and `disposition`), on EVERY factory server the Dispatcher dispatches to. That is FLEET SCOPE: no factory, workflow or node is exempt.

- **Who acts, and when.** Node outcome routing and a node's own declared retries (its `max_retries` in the workflow graph) happen inside the factory run, and this clause changes neither. The node's declared retries are spent first, inside the run. If the node is still refused, the run ends exactly as it does today, at the workflow's `needs_human` terminal, with its work preserved by the published head or the preservation ref. Everything below is done by the host Dispatcher AFTER that run terminates, when it derives the run's outcome (§"A factory run never awaits a human"), using the same between-runs mechanism as "Provider-limit release and re-dispatch" of §"Factory-configurable ACP fallback priority". No step asks the host from inside a running sandbox.
- **Probe the run's token, not the vault's.** When the failing node's recorded failure carries the agent error "Authentication required", the Dispatcher MUST read, through the dispatch target's declared credential wrapper, the current value of the slot the run was dispatched with: the slot admission chose and projected (§"Provider spend containment"; Scenario 18), never a different slot. It MUST compute that value's one-way credential identity and compare it with the identity journaled for the run at admission. It MUST probe the slot only when the two identities are EQUAL, because only then is the probed token the token the run held.
- **A matching, usable slot is released for re-dispatch.** When the identities are equal and the probe reports the slot usable, the Dispatcher MUST, without a human: (1) journal one `authentication-refusal-release` record naming the work-item, the run id, the factory, the failing node attempt, the slot's environment-variable name, its credential identity, the probe verdict and the preserved-work reference (or its confirmed absence); (2) release the item's dispatch claim and return it to `ready`, NOT to `blocked`; and (3) leave the item to the ordinary admission valve and recovery routing, which re-dispatch it from its preserved work with every node selected afresh. The re-dispatch MUST NOT be admitted before a backoff has elapsed since the refused run ended: at least 30 seconds after the first such release, and longer after each later consecutive one.
- **Bound on attempts.** These releases are IN ADDITION to the node's declared in-run retries, which are unchanged. At most three consecutive authentication-refusal releases MAY follow one another for one work-item, so one refusal sequence spans at most four runs of the item: the original run and at most three re-dispatches, each spending its own node's declared retries. A release MUST NOT consume any budget of §"The three rework caps".
- **A mismatched identity rests the item, naming both identities.** When the identities differ, the Dispatcher MUST NOT probe or release. The work-item MUST rest at `blocked` with `blocked_reason: needs-human`, and the recorded cause MUST name the slot's environment-variable name, the run's dispatched credential identity and the slot's current credential identity, and never a value.
- **An unusable slot rests the item, naming the slot.** When the identities are equal and the probe reports the slot not usable, the Dispatcher MUST NOT release. The work-item MUST rest at `blocked` with `blocked_reason: needs-human`, and the recorded cause MUST name the slot's environment-variable name and the probe's condition.
- **Exhausted releases rest the item, naming the count.** When a fourth consecutive run of the item ends with the same refusal, the work-item MUST rest at `blocked` with `blocked_reason: needs-human`, and the recorded cause MUST name the slot's environment-variable name, the number of runs refused and the last probe verdict.
- **Every probe is journaled by identity, never by value.** Each probe, and each identity comparison that withholds a probe, MUST write one dispatch-journal row naming the work-item, the run id, the node, the slot's environment-variable name, the run's dispatched credential identity, the slot's current credential identity and the verdict. The row MUST NOT carry any credential value.
- **Every probe reads the slot's headroom.** Each probe MUST also record a host session-headroom reading of that slot, so the refusal is never left unobserved from the host.
- **Boundary.** This clause governs a refusal that ended a run. The admission-time credential-probe refusal of §"Provider spend containment" still governs a refusal before claim. A refusal whose cause chain carries a provider usage or spend ceiling MUST still take the permanent classification above, and its release route, and MUST NOT be released under this clause.

### scenarios.md — one new scenario (four Gherkin scenarios under one heading), numbered at revise

```markdown
## Scenario NNN — An Authentication required refusal that ends a run is released for re-dispatch only while the run's own slot is unchanged and usable

` ` `gherkin
Feature: A transient authentication refusal costs a re-dispatch from preserved work, not a human decision

Scenario: The run's unchanged, usable slot is released for a backed-off re-dispatch, and the probe is journaled without the value
  Given a run dispatched with credential slot S, whose credential identity I was journaled at admission
  And an anthropic-availability ACP node of that run is refused with the agent error "Authentication required" on every one of its declared in-run retries
  And the run ends at the workflow's needs_human terminal with its work preserved
  And slot S's current value has credential identity I, and a host probe of it reports usable
  When the Dispatcher derives the run's outcome
  Then one authentication-refusal-release record names the work-item, the run, the node, slot S's environment-variable name, identity I, the verdict usable and the preserved-work reference, and carries no credential value
  And a host session-headroom reading of slot S is recorded
  And the item returns to ready, not blocked, and is not re-dispatched until at least 30 seconds after the run ended

Scenario: A changed slot rests the item and names both identities
  Given the same refusal and terminal
  And slot S's current value has a credential identity J different from I
  When the Dispatcher derives the run's outcome
  Then the slot is not probed and the item is not released
  And the work-item rests at blocked with blocked_reason needs-human
  And the recorded cause names slot S's environment-variable name and identities I and J, and no credential value

Scenario: An unusable slot rests the item and names the slot
  Given the same refusal and terminal
  And slot S's current value has identity I, and a host probe of it reports not usable
  When the Dispatcher derives the run's outcome
  Then the item is not released
  And the work-item rests at blocked with blocked_reason needs-human
  And the recorded cause names slot S's environment-variable name and the probe's condition

Scenario: A fourth consecutive refused run rests the item
  Given three consecutive authentication-refusal releases of one work-item
  When a fourth consecutive run of that item ends with the same refusal
  Then the item is not released
  And the work-item rests at blocked with blocked_reason needs-human, naming the slot, the four refused runs and the last probe verdict
` ` `
```

(The inner fence is written as "` ` `" so it survives inside this proposal. At revise it MUST be written as a normal triple-backtick gherkin fence, as every scenario in scenarios.md is.)

### Co-edits at revise time

The revise MUST add one `tests/heading-coverage.json` entry for the new `## Scenario NNN — ...` heading, as numbered at revise. It MAY carry `test: "TODO"`, its `reason` MUST name the tier the owed test runs at (integration tier or above: the Dispatcher's outcome routing driven against a stand-in ACP refusal and a stand-in probe), and it MUST carry `"work_item": "bd-ib-wqxgjf"`. The revise MUST regenerate `tests/heading-coverage-debt.json` with `uv run python -m livespec_dev_tooling.heading_coverage_debt` and stage the result, never hand-authoring the row. No other heading changes.
