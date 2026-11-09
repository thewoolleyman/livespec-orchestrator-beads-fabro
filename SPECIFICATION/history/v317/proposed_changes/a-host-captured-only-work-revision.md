---
proposal: a-host-captured-only-work.md
decision: reject
revised_at: 2026-11-08T00:47:50Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

REJECT. The rule is not warranted as written, because its key does not separate the failure it targets from a route that works.

Premise measured false. The item's title says a host-captured-only item dies at dead_implementer by construction. In the ledger on 2026-11-07, 12 items whose every assertion sits under `### Host-captured`, with no `factory-safety:*` label, merged through factory-authored pull requests: #3471, #4423, #4458, #4145, #4591, #4168, #2880, #2652, #3366, #2904, #2712 and #2756. The first `captured` record on each of the 12 states that the item declares no `factory_captured` assertion, so the Definition of Done was host-captured-only when the run took it. 8 of them have since closed on a `host_verified` record and 4 rest in `acceptance` for the host leg. The run delivered the code and the host leg proved it. The rule would refuse every one of them at dispatch. A further 24 open non-epic items carry the same shape: 12 at `ready`, 5 at `pending-approval` and 7 at `backlog`.

The second half of the stated residual therefore does not hold. An item that owes a code change is not in the wrong route for having host-captured assertions: contracts.md `factory_safety` says writing code is factory-safe and applying host state is host-only, and "Per-assertion proof mode" says `host_captured` is a property of the assertion, independent of `factory_safety`. The first half is true but narrower than stated: the run's factory leg has nothing to prove, yet the run still delivers the change. The measured deaths are items that owed no change in the repository the run worked in: tdd-proof-lv352h; bd-ib-saf5ya, whose behaviour had already shipped; and bd-ib-lkta5g, run 01M6JV7J7V3G on 2026-11-04, whose ledger cause record reads LIVESPEC_DEAD_IMPLEMENTER and which later closed as not reproduced. The precedent livespec-dev-tooling-vxkmab took the host route because of its secrets, as its Reason line says, not because its assertions were host-captured.

The remedies are not truthful for every item caught. For an item that changes a stage prompt, such as bd-ib-w3l7rs, a `factory_captured` assertion on the prompt's released-build effect ends at needs-human under `## Scenario 272 — A factory-captured assertion whose proof surface no sandbox capability provides is named in the gate's finding`, which is the clause that sends it to `host_captured`. None of the four `factory_safety` reasons describes writing a prompt, so the host route would need a false label. Such an item would have no honest remedy.

Scenario 266 and its clause stand and are unchanged. They keep a correct no-op turn that declares already-satisfied from ending at dead_implementer. They do not stop the slot being spent, and a turn with no declaration still ends there, so a narrow residual remains: a no-code item spends a factory slot. This rule cannot reach it, because the key is the absence of a `factory_captured` assertion. A narrower rule needs a declared no-code scope, and contracts.md and scenarios.md hold no field or section declaring one (searched for no code change, no-code and no-change-needed; the hits, such as the incident-closure path close/no-change-needed, are unrelated). Designing one is new work under its own topic, not a modification of this one. It should also weigh that Scenario 266 rests a no-pull-request item in `acceptance` while the host-record primitive refuses an item with no merged pull request, which reads as a further gap for a host-captured-only no-code item (read from the text, not measured).

bd-ib-bomy33 is not contradicted and needs nothing from this decision.

Effect on the hold: this rejection does not ratify the topic, so it does not clear the spec-change hold on bd-ib-3asaxk. That item's Definition of Done still asks for the rejected rule, so it needs re-scoping or closing.

## Rejection Notes

Rejection rationale captured in §"Decision and Rationale" above. Future re-proposal would need to address that critique.
