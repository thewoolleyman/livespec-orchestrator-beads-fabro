---
topic: credential-requirements-follow-resolved-provider-routes
author: claude-opus-5-5
created_at: 2026-11-01T01:58:46Z
---

## Proposal: Derive dispatch credential requirements from the resolved provider routes

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Amend `## Worker credential projection` so that the set of provider credentials a dispatch requires is derived from every route the submitted workflow graph can execute (every candidate, fallbacks included, of every potentially reachable ACP node, plus any other provider-consuming stage), resolved from the same defaults, configuration and overrides per-node selection uses. Required credentials keep every existing guarantee (non-rotatable projection, host ownership, freshness gate, credential-use deadline) and refuse before sandbox launch when unusable; credentials of providers outside the set are never probed, headroom-read, freshness-gated or projected and cannot refuse the dispatch; an unresolvable candidate provider refuses fail-closed, naming the node and candidate. The final paragraph stops leaving 'which credentials the freshness gate covers' implementation-owned.

### Motivation

Filed under plan bd-ib-ax3rds (spec-implementation-lockstep) assertion 7, R1 bd-ib-j6uvkj residual batch, on coordinator ruling (gitops-fleet-capacity-monitoring, 2026-11-01T00:21:09Z). Linked items: bd-ib-cwd3ld (the contract arc: 'Clarify credential requirements for Codex-only and mixed-provider factory dispatch') and bd-ib-3u3whu (its implementation: 'Derive factory credential validation and projection from resolved provider usage'). Both are owned by plan bd-ib-jquu6e (codex-review-pr-disposition-routing, 'Permanent Codex routing for review, PR, and disposition'); route the revise to that plan's reviewer. Judgement: FEATURE. Revalidated against v261, no ratified clause states which credentials a dispatch requires: `## Worker credential projection` says the Dispatcher MAY project more than one credential and explicitly leaves 'which projected credentials the freshness gate covers' implementation-owned, and Scenario 18 assumes both a valid Claude and a valid OpenAI credential. The measured consumer blocker (overseer-vrlthg, gate 20261008T225459Z-3019684, dispatcher 0.174.1) resolved all nine ACP nodes to Codex yet was refused by the run-config overlay on an unused CLAUDE_CODE_OAUTH_TOKEN returning HTTP 429, with zero sandboxes launched. That is a missing provider-aware capability, not a violation of a stated exclusion rule, so it is a feature, not a bug. The proposal amends the existing section rather than adding one and reuses the existing 'potentially reachable ACP node' and resolved-agent-provenance concepts from §'Factory-configurable ACP fallback priority' and the headroom clauses.

### Proposed Changes

Amend `SPECIFICATION/contracts.md` → `## Worker credential projection`. Insert the following paragraph IMMEDIATELY AFTER the second paragraph (the one ending "Each projected credential MUST independently satisfy the non-rotatability and host-ownership guarantees below."), and amend one sentence of the final paragraph as shown. No other text of the section changes.

Inserted paragraph:

```text
**Credential requirements follow the resolved provider routes.** For each dispatch, the Dispatcher MUST derive the set of REQUIRED providers from the routes the submitted workflow graph can actually execute: the provider of every candidate, primary and configured fallback alike, of every ACP node potentially reachable in that graph (§"Factory-configurable ACP fallback priority"), resolved with the same workflow defaults, committed repository configuration and per-dispatch overrides that per-node selection uses, together with every other stage of that graph that consumes a provider-subscription credential. A candidate's provider MUST be established from its resolved agent provenance (for example a resolved agent id of `claude-acp` or `codex-acp`, or a manual-form candidate recognized as a built-in adapter under the existing built-in byte-equality rule), never from display text, a model-name prefix, or the number of nodes resolved to one adapter. Admission, the freshness gate, the admission-time credential-usability probe, the session-headroom filters and projection MUST all consume that one derived set. A provider-subscription credential whose provider is in the set is required: it MUST be validated, freshness-gated and projected under every rule of this section, and when any required credential is absent, unusable, or fails the freshness gate, the Dispatcher MUST refuse the dispatch before any sandbox is launched, naming the provider. A credential whose provider is NOT in the set MUST NOT be probed, headroom-read, freshness-gated or projected for that dispatch, and its absence, exhaustion or rate-limit refusal MUST NOT refuse or delay the dispatch; a dispatch whose resolved routes require only Codex therefore launches with no Claude credential present. When the Dispatcher cannot establish the provider of a potentially reachable candidate or stage, it MUST refuse the dispatch before any sandbox is launched, naming the node and the candidate whose provider is unresolved, and MUST NOT silently omit a check that candidate might need. Scenario 284 in `scenarios.md` exercises this paragraph.
```

Final paragraph, sentence amended — replace:

```text
The projection mechanism — the per-provider projection shape, which projected
credentials the freshness gate covers, the credential file or field layout, and
the encoding that renders the snapshot non-rotatable — is implementation-owned
and MUST NOT be fixed by this contract.
```

with:

```text
The projection mechanism — the per-provider projection shape, the credential
file or field layout, and the encoding that renders the snapshot non-rotatable —
is implementation-owned and MUST NOT be fixed by this contract. Which credentials
a dispatch requires, and therefore which the freshness gate covers, is fixed by
"Credential requirements follow the resolved provider routes" above.
```

and in that same final paragraph replace "The behavior is exercised by Scenario 18,
Scenario 19 and Scenario 228 in `scenarios.md`." with "The behavior is exercised by Scenario 18,
Scenario 19, Scenario 228 and Scenario 284 in `scenarios.md`."


## Proposal: Scenario for Codex-only, mixed-provider and unresolved-provider dispatch credentials

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Narrow Scenario 18's universal 'host holds both a valid Claude and a valid OpenAI credential' precondition to the mixed-provider case it actually exercises, and add Scenario 284 covering a Codex-only dispatch admitted with the Claude credential absent or rate-limited, a mixed-provider dispatch refused when one required credential fails freshness, and a fail-closed refusal naming the node and candidate whose provider cannot be established.

### Motivation

Companion scenario to the preceding finding, for the same linked items bd-ib-cwd3ld and bd-ib-3u3whu of plan bd-ib-jquu6e (codex-review-pr-disposition-routing). Judgement: FEATURE. bd-ib-3u3whu's Definition of Done currently references Scenarios 18 and 19, which state non-rotatable projection and the freshness gate but not provider-route-derived requirements; once this is ratified, bd-ib-3u3whu's References line is re-pointed to Scenario 284 and it owns that scenario's heading-coverage entry.

### Proposed Changes

Amend `SPECIFICATION/scenarios.md`.

(a) In `## Scenario 18 — Dispatcher projects a non-rotatable subscription credential into a worker sandbox`, replace the first scenario's Given line

```text
  Given the orchestrator host holds a valid Claude-subscription credential and a valid OpenAI/ChatGPT-subscription credential whose usable lifetimes exceed the worker run budget
```

with

```text
  Given the resolved provider routes of the dispatch require both Claude and OpenAI/ChatGPT
  And the orchestrator host holds a valid Claude-subscription credential and a valid OpenAI/ChatGPT-subscription credential whose usable lifetimes exceed the worker run budget
```

so the mixed-provider case Scenario 18 already exercises is stated as the mixed-provider case rather than as a universal precondition. No other line of Scenario 18 changes.

(b) Insert a new scenario after the last existing scenario heading of the file (currently `## Scenario 281` on master, with 282-283 reserved for other pending proposals; if 284 is already taken at revise time, take the next free number and re-point the contract reference):

```text
## Scenario 284 — Dispatch credential requirements follow the resolved provider routes

```gherkin
Feature: The Dispatcher validates and projects only the credentials a dispatch's routes require
  As the Dispatcher admitting factory work on more than one provider subscription
  I want credential requirements derived from the routes the submitted graph can execute
  So that an unused provider's credential never refuses work, and a used one is never left unchecked

Scenario: A Codex-only dispatch launches without the unused Claude credential
  Given every candidate of every potentially reachable ACP node of the submitted graph resolves to `codex-acp`, including configured fallbacks
  And no other stage of the graph consumes a Claude-subscription credential
  And the host's Claude-subscription credential is absent, or returns a rate-limit refusal
  When the Dispatcher considers dispatching a ready work-item
  Then the Dispatcher does not probe, headroom-read, freshness-gate or project the Claude credential
  And it validates, freshness-gates and projects the Codex credential as a non-rotatable snapshot
  And the dispatch is admitted and a sandbox is launched

Scenario: A mixed-provider dispatch refuses when one required credential is unusable
  Given the resolved routes of the submitted graph include a `claude-acp` candidate on a potentially reachable node and `codex-acp` candidates on others
  And the host's Claude-subscription credential fails the freshness gate
  When the Dispatcher considers dispatching a ready work-item
  Then the Dispatcher refuses the dispatch before any sandbox is launched
  And the refusal names the Claude provider as the unusable required credential

Scenario: A candidate whose provider cannot be established refuses the dispatch
  Given a potentially reachable ACP node has a manual-form candidate that is not recognized as a built-in adapter
  When the Dispatcher derives the dispatch's required providers
  Then the Dispatcher refuses the dispatch before any sandbox is launched
  And the refusal names that node and that candidate as having an unresolved provider
  And no credential check is silently omitted
```
```

The heading-coverage co-edit (a `tests/heading-coverage.json` entry for the new scenario heading, owned by bd-ib-3u3whu) lands with the revise pass, not this proposal.

