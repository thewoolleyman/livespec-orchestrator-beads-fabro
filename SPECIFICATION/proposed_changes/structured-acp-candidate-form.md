---
topic: structured-acp-candidate-form
author: claude (factory-configurable-model-fallback-priority)
created_at: 2026-09-30T01:59:41Z
spec_commitments:
  impl_followups:
    - id_hint: acp-structured-candidate-dispatcher
      description: |
        Dispatcher: parse the structured candidate form, ship and load the committed agent and model catalogs with per-repository additions, render structured entries into manual-form candidates deterministically, derive identity from (agent, model), accept the structured form on the per-dispatch layer, refuse mixed or unresolvable entries before claim, and refuse dispatcher.codex_models with the equivalent acp_nodes entry printed.
    - id_hint: acp-candidate-config-options-fabro
      description: |
        Fabro fork (host-routed, factory-integration): carry per-candidate config_options in the acp.fallback_chain grammar, set model and effort through session/set_config_option after session/new and before the prompt, terminate typed before the prompt when the agent does not advertise the requested value, stamp the confirmed values on agent.acp.started, and advertise acp.candidate_config_options.v1 on GET /system/info.
    - id_hint: acp-catalog-pricing-and-signatures
      description: |
        Cost and classification: resolve pricing and availability signatures for a structured candidate through the model catalog first and the per-candidate override second; apply the exact-identity rule to the catalog key; seed the catalog from upstream Fabro's model catalog and the ratified Codex diagnostic; this re-cuts the plan's S6 draft.
---

## Proposal: Structured ACP candidate form: agent, model, effort

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Every ACP node candidate and fallback gains a STRUCTURED form (`agent`, `model`, optional `effort`) as the default spelling, rendered by the Dispatcher into the existing command/args/env candidate; the raw command form remains first-class as the manual escape hatch. Identity for the structured form derives from (agent, model) instead of rendered command bytes.

### Motivation

Maintainer direction 2026-09-30 on plan bd-ib-jxvgq5: the configuration must be as ergonomic as possible while allowing any model from any provider (Codex, Claude, open-source, xAI, z.ai, or any other), framed in standard APIs and prior art like ACP, with ergonomic defaults and a manual fallback for any model that does not support them. The plan's research note research/config-ergonomics-assessment-2026-09-30.md measured that the ratified v109 grammar is a raw command string with hand-typed identity, pricing and signatures, that only Claude and Codex have ergonomic entry points, and that across eleven fleet repositories every `acp_nodes` entry is a bare Claude command string.

### Proposed Changes

In §"ACP node adapter configuration", replace the paragraph "The per-node value" so that a node entry, and every entry of its `fallbacks` array, is EXACTLY ONE of two forms, and the Dispatcher MUST refuse before claim an entry that mixes them or matches neither.

**The structured form** carries `agent` (string; an agent id in the committed agent catalog of §"Agent and model catalogs"), `model` (string; a model reference the catalog resolves for that agent, either a bare model id or a `provider/model` reference for a multi-provider agent), and optional `effort` (string; one of the effort levels the catalog declares for that agent). It MAY also carry `display_name`, `candidate_key`, `availability_key`, `availability_signatures` and `pricing` as OVERRIDES; when absent they MUST derive from the catalog as §"Agent and model catalogs" specifies. The Dispatcher MUST render the structured form into the manual form below before any layer merge, journal, digest or run input, so every downstream rule of this section and of §"Factory-configurable ACP fallback priority" applies to the rendered candidate unchanged. The rendering MUST be deterministic: the same catalog snapshot and the same structured entry MUST render byte-identical adapter bytes.

**The manual form** is the existing table of `command`, `env`, `args` plus, for a fallback-enabled node, the explicit `display_name`, `candidate_key` and `availability_key` and optional `availability_signatures` and `pricing`. It is the escape hatch for any agent or wiring the catalog does not cover, including agents no registry lists, and it MUST remain accepted everywhere the structured form is. Nothing in the manual form is inferred: identity is never derived from command text, exactly as today.

In §"Factory-configurable ACP fallback priority", amend "Every explicitly identified candidate, and every candidate in a fallback-enabled chain, carries non-empty, non-secret `display_name`, `candidate_key`, and opaque `availability_key`" to add: for a structured-form candidate those three fields MUST derive, when not overridden, as `display_name` = the catalog's agent display name plus the model's display name, `candidate_key` = the canonical `<agent>/<provider>/<model>` triple, and `availability_key` = the catalog's account domain for that agent (the allowance the candidate draws on, e.g. the Anthropic subscription or the ChatGPT account). Two structured entries naming the same agent and model therefore share identity across nodes by construction, which is the intentional cross-node reuse the section already permits. Amend the same section's built-in-identity clause so that built-in identity attaches to a structured-form candidate by catalog resolution, not by byte-equality of the rendered command; byte-equality remains the rule for the manual form.

The per-dispatch layer `--acp-node <node>=<value>` MUST accept the structured form as a JSON object value in addition to the legacy adapter string, and the same refusal rules apply to it before claim.

Add Scenario 129 to `SPECIFICATION/scenarios.md`, "A structured candidate renders through the catalogs and keeps the manual form as the escape hatch", with these scenarios: (1) Given an `implement` entry `{"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"}` When the Dispatcher resolves the node Then the rendered candidate is byte-identical to the catalog's Codex launch distribution with that model and effort applied, its `candidate_key` is `codex-acp/openai/gpt-5.5`, and its `availability_key` is the catalog's ChatGPT account domain; (2) Given a fallback `{"agent": "opencode", "model": "zai/glm-5.2"}` When resolved Then the provider-qualified model is passed to the multi-provider agent and identity derives from the triple; (3) Given a fallback in the manual form with an explicit `command` and identity When resolved Then it is accepted unchanged and no field is derived; (4) Given an entry that mixes `agent` with `command`, or names an agent absent from the catalog, or a model the catalog does not declare for that agent When the Dispatcher validates configuration Then it refuses before claim naming the entry and the offending field; (5) Given the same catalog snapshot and the same structured entry on two dispatches Then the rendered adapter bytes are identical. The revise pass MUST add the Scenario 129 heading to `tests/heading-coverage.json` per the co-edit discipline.

## Proposal: Agent and model catalogs seeded from the ACP registry and the Fabro model catalog

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md

### Summary

Introduce two committed, versioned catalogs the structured form resolves through: an agent catalog (which program to launch, how it takes model and effort, which account domain it draws on) seeded from a pinned snapshot of the ACP agent registry, and a model catalog (provider, canonical model id, aliases, pricing, measured availability signatures) seeded from upstream Fabro's model catalog. Per-repository additions and per-candidate overrides remain possible; the catalogs are snapshots, never live fetches at dispatch time.

### Motivation

The ACP registry (agentclientprotocol/registry, 45 agents on 2026-09-30) already gives every agent a stable id and a launch distribution (npx package and args, uvx, or per-platform binary), including claude-acp, codex-acp, grok-build (xAI), glm-acp-agent (z.ai), opencode, goose, gemini, kimi, minimax-code and poolside. Upstream Fabro's model catalog already separates provider, canonical slug, alias and per-model cost and resolves provider/model references. The plan's grammar has neither, so pricing and availability signatures are hand-typed per candidate and drift between repositories.

### Proposed Changes

Add a new H2 section to `SPECIFICATION/contracts.md`, "Agent and model catalogs", immediately before §"Factory-configurable ACP fallback priority".

**The agent catalog.** The plugin MUST ship a committed, versioned agent catalog whose entries are keyed by ACP registry agent id. Each entry MUST carry: the launch distribution (`command`, `args`, `env` in the manual-form shape) rendered from the registry's `npx`, `uvx` or per-platform `binary` distribution at a pinned agent version; the agent's display name; its account domain, an opaque `availability_key` naming the allowance the agent draws on; the mechanism by which the agent takes `model` and `effort`, EXACTLY ONE of `protocol` (ACP session config options, §"In-protocol model and effort selection") or an explicit per-agent environment or argument mapping; whether the agent is multi-provider, in which case `model` MUST be a `provider/model` reference; and the effort levels it declares. The catalog MUST record the ACP registry snapshot digest and date it was seeded from. A repository MAY add or override agent entries under `dispatcher.agent_catalog` in its `.livespec.jsonc`, subject to the same closed grammar; unknown keys refuse before claim. The Dispatcher MUST NOT fetch the registry at dispatch time; a dispatch depends only on the committed snapshot.

**The model catalog.** The plugin MUST ship a committed, versioned model catalog keyed by `provider/model`, carrying the canonical model id, aliases, the four USD-per-million prices in the existing `pricing` shape, and the measured availability signatures in the existing signature grammar. It MUST be seeded from upstream Fabro's model catalog where that catalog carries the model and extended for models it does not, including the Codex ChatGPT-account diagnostic already ratified. A repository MAY add or override entries under `dispatcher.model_catalog`. Per-candidate `pricing` and `availability_signatures` on a structured entry remain OVERRIDES of the catalog value, and the contract's all-or-none pricing rule applies to the catalog entry and the override alike.

**Resolution.** For a structured candidate the Dispatcher MUST resolve `agent` in the agent catalog, then `model` in the model catalog for that agent's provider (or the provider named by a `provider/model` reference), and MUST refuse before claim when either lookup fails or when `effort` is not one of the agent's declared levels. The resolved entries supply the rendered adapter, the derived identity, the pricing and the signatures. The cost slice MUST price a structured candidate through the model catalog first and the per-candidate override second, and the exact-identity rule (one trailing `-YYYYMMDD` suffix stripped, no broader prefix match) applies to the catalog key.

In `SPECIFICATION/constraints.md` §"Fabro runtime constraints", add that the agent catalog's pinned agent versions are part of the factory's pinned surface: the sandbox image and the catalog MUST agree on the baked adapter path for any agent the image bakes (today codex-acp), and changing a pinned agent version is a committed change with the same rebuild and re-pin duty the section already imposes on the Fabro build.

## Proposal: In-protocol model and effort selection through ACP session config options

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Where an agent advertises model or effort as ACP session config options, the Fabro ACP handler MUST set them over the protocol after `session/new` and before the prompt, instead of relying on agent-specific environment variables; a requested value the agent does not advertise is a typed pre-turn refusal, never a fallback trigger. The fallback chain grammar carries per-candidate config options and the capability is advertised additively.

### Motivation

The ACP specification defines `session/set_config_option` with a `model` category and option ids such as `effort`, and names config options the preferred way to expose session configuration. The agent-client-protocol crate the Fabro fork pins (0.11.1) already carries the `session/set_config_option` and `session/set_model` wire methods, so no dependency change is needed. The Claude adapter this fleet runs implements config options `model`, `effort` and `mode`, and the Codex adapter documents model and reasoning-effort configuration the same way. Today the handler calls `session/new` then `session/prompt` and every model choice rides `ANTHROPIC_MODEL` or a `CODEX_CONFIG` blob, which is what forces every ergonomic entry point to be agent-specific.

### Proposed Changes

Add a new H3-level paragraph block, "In-protocol model and effort selection", to §"Factory-configurable ACP fallback priority" immediately after "Reactive fallback is one bounded node visit".

For a candidate whose agent catalog entry declares the `protocol` mechanism, the rendered chain candidate MUST carry a `config_options` object mapping ACP config option ids to requested values (`model` and, when set, `effort`), and the Fabro ACP handler MUST, after `session/new` and before the first `session/prompt`, read the agent's advertised `configOptions`, and set each requested option through `session/set_config_option`. The handler MUST NOT start the prompt until every requested option is confirmed set. When the agent does not advertise a requested option id, or advertises it without the requested value among its options, the candidate MUST terminate as a typed pre-turn refusal with cause `model_unsupported` at candidate scope when the option is `model`, and as `malformed_configuration` otherwise; in both cases the failure MUST be recorded with its own identity, MUST mint no hold, and MUST NOT trigger reactive fallback. For a candidate whose agent entry declares an environment or argument mechanism, the Dispatcher MUST render `model` and `effort` into the adapter exactly as the catalog mapping states and the handler sets no option; the two mechanisms MUST NOT be combined for one candidate.

The `agent.acp.started` event MUST carry the confirmed model and effort values as additive non-secret fields so a reader can verify which model actually ran without reading the command; the redaction rules of "Events and projection are compatible, idempotent, and leak-free" apply unchanged. The Fabro server MUST advertise the additive capability `acp.candidate_config_options.v1` alongside `acp.fallback_chain.v1`, and the Dispatcher MUST refuse before claim a chain that carries `config_options` when the resolved factory server does not advertise it, exactly as the existing capability gate does.

Amend Scenario 127 by adding one scenario: "Model and effort are set over the protocol and an unadvertised model refuses before the prompt": Given a structured candidate whose agent declares the protocol mechanism When the handler opens the session Then it sets `model` and `effort` through `session/set_config_option` before the first prompt And the `agent.acp.started` event carries the confirmed values But when the agent does not advertise the requested model the candidate terminates typed before any prompt, mints no hold, and does not trigger reactive fallback.

## Proposal: Retire dispatcher.codex_models and the class-shaped Codex pins into per-node structured entries

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

`dispatcher.codex_models` and the implementer/publish CLASS tiers of §"Codex ACP node model pins" are retired: the built-in fleet defaults become structured per-node entries in the workflow defaults, a configuration that still sets `codex_models` refuses before claim and prints the equivalent `acp_nodes` entry, and Scenarios 64, 86, 90 and 127 are re-expressed in the structured form. The pinned-Codex rules that remain load-bearing (every Codex candidate carries a model and effort; the baked path; the empty-model opt-out) are restated against the agent catalog entry for `codex-acp`.

### Motivation

Maintainer ruling 2026-09-30: `codex_models` and `acp_nodes` are the same functionality spelled twice, and the plan owns that functionality, so the redundancy is a defect in the plan's own deliverable. Measured 2026-09-30, no repository under /data/projects sets `codex_models`; the only thing keeping it alive is seventeen mentions in this contract. The class-shaped tiers (implementer versus publish) are a special case of per-node configuration that the structured form expresses directly.

### Proposed Changes

Rewrite §"Codex ACP node model pins" as follows. Remove the `dispatcher.codex_models` grammar, the per-class tier tables, the per-key degradation to built-in Codex defaults, and the paragraph "Tiers resolve from the dispatch target's own configuration". Retitle the section "Built-in ACP node defaults" and restate its surviving rules: (a) the workflow defaults for `implement`, `fix`, `review_fix` MUST be the structured entry `{"agent": "claude-acp", "model": "claude-opus-5", "effort": "high"}` and for `pr` the entry `{"agent": "claude-acp", "model": "claude-haiku-4-5", "effort": "high"}`, rendered through the agent catalog so their bytes remain the ratified v107 strings until the catalog's `claude-acp` entry changes; (b) every candidate whose agent is `codex-acp` MUST carry a `model` and an `effort`, because the baked adapter falls back to a stale static list when unpinned, and the catalog entry for `codex-acp` MUST render the baked path `/opt/livespec/codex-acp/bin/codex-acp`, `INITIAL_AGENT_MODE`, and the `CODEX_CONFIG` shape this section already ratifies; (c) the empty-model opt-out is expressed as the manual form carrying the bare adapter command, not as `"model": ""`; (d) the verification-run guidance after a default change is unchanged; (e) the no-environment-override rule is unchanged.

Add to §"ACP node adapter configuration": a `.livespec.jsonc` that sets `dispatcher.codex_models` MUST refuse before claim, and the refusal MUST print the equivalent `dispatcher.acp_nodes` structured entries so the migration is a copy. Remove the paragraph "`dispatcher.codex_models` is the per-repository shorthand for the Codex tiers and remains valid" and the shorthand-expansion ordering rule in §"Factory-configurable ACP fallback priority" ("Resolve the primary before attaching the chain" keeps its substance with `codex_models` struck: candidate zero resolves through the workflow default, the explicit repository entry, and the per-dispatch layer, in that order, before identity or fallbacks attach). Strike `dispatcher.codex_models` from the committed-configuration-only class in §"Control surface and audit" and wherever else the contract lists it; `dispatcher.acp_nodes`, `dispatcher.agent_catalog` and `dispatcher.model_catalog` take its place in that class.

Re-express Scenarios 64, 86 and 90 in `SPECIFICATION/scenarios.md` so every Given that names a `dispatcher.codex_models` block or tier names the equivalent `dispatcher.acp_nodes` structured entry instead, and every Then that asserts a rendered Codex or Claude string asserts the same bytes rendered from the catalog; add to Scenario 64 one scenario asserting that a configuration setting `codex_models` refuses before claim and prints the equivalent `acp_nodes` entry. Amend the first scenario of Scenario 127 so its Given reads "the pr node has no acp_nodes entry and no new-grammar metadata" and its final And reads "when the pr node carries an explicit structured entry, identity-only or fallback-only fields attach after that primary renders". Scenario titles MUST remain stable where the heading is already bound in `tests/heading-coverage.json`; a title that must change is a co-edit of that file in the same revise pass.
