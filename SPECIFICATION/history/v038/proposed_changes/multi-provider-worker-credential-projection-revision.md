---
proposal: multi-provider-worker-credential-projection.md
decision: accept
revised_at: 2026-07-17T04:25:44Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accepted after four rounds of independent Fable-model adversarial review returned a
final NO-BLOCKERS verdict (the maintainer's standing pre-ratification rule); the
accept is maintainer-delegated (the maintainer directed "groom it then work them
autonomously" for work-item `bd-ib-ss7rkr`). This is a spec-lags-impl de-drift:
§"Worker credential projection" and Scenarios 18/19 are realigned to the
multi-provider worker path the Dispatcher already ships — an ADDITIVE projection
that carries both a Claude-subscription OAuth env credential and an OpenAI/ChatGPT
(Codex) file credential into a single worker sandbox, each rendered non-rotatable.
The contract now states the host MAY hold and project credentials for more than one
provider at once, so one worker MAY authenticate more than one coding-agent runtime
(A.1); scopes the per-credential universal to non-rotatability + host-ownership and
marks the projection mechanism MAY-be-provider-specific and implementation-owned
(A.1); re-arities the non-rotatable and host-owner guarantees to each projected
credential (A.2, A.4); and re-arities the freshness gate to the credentials it
covers while leaving that coverage implementation-owned (A.3, A.5) — matching the
shipped gate, which lifetime-gates the Codex credential and only presence-checks the
Claude one. Scenarios 18 (both credentials projected non-rotatably into the same
sandbox) and 19 (freshness-gate refusal on a gate-covered credential) are realigned
in place with no `## ` H2 heading change, so `tests/heading-coverage.json` is
unchanged and its two integration bindings remain correct. The guarantees are
preserved in substance; only their arity (one → one-or-more projected credentials),
the guarantee/mechanism split, and the freshness gate's coverage arity change.
Design record (intent tiebreaker per `contracts.md` §"Intent preservation"): this
repo, `plan/codex-credential-broker/handoff.md` §"ACTIVE — `bd-ib-ss7rkr`
docs/contract realignment (adopted 2026-07-16)". Work-item `bd-ib-ss7rkr`.

## Resulting Changes

- contracts.md
- scenarios.md
