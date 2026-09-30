# Does the plan's config let an operator name any model from any provider ergonomically?

Written 2026-09-30 after the maintainer asked the question in those terms:
"an ergonomic config, or as ergonomic as possible, that still allows any
model to be specified from any provider ... framed in standard APIs and prior
art like ACP, with ergonomic defaults, but the ability to fall back to manual
configuration for any model that does not directly support the ergonomic
defaults." Everything below was measured on 2026-09-30 unless dated
otherwise.

## Verdict

**No.** The plan as ratified (v109) and as built through S4 is
provider-generic in the weakest sense: any adapter is expressible because a
candidate is a raw process command string. Nothing in the grammar knows what
an *agent*, a *model*, or an *effort level* is, so the "ergonomic default"
half of the maintainer's requirement does not exist, and the two ergonomic
surfaces that do exist (`dispatcher.codex_models` and the built-in Claude
defaults) are hard-coded to exactly two agents. The manual escape hatch the
requirement asks for is the ONLY layer we have. This is fixable inside the
plan without discarding S1 through S4: the fix adds a structured layer that
*renders down to* the existing candidate, and moves model selection onto the
protocol where the agent supports it.

## What we have today

A candidate (`_acp_candidate_schema.CANDIDATE_KEYS`) is exactly:
`command`, `args`, `env`, `display_name`, `candidate_key`,
`availability_key`, `availability_signatures`, `pricing`. To route the
`implement` step to Codex GPT-5.5 as a fallback an operator writes the
literal adapter invocation and everything around it by hand:

```jsonc
{
  "display_name": "Codex GPT-5.5", "candidate_key": "codex-gpt-5.5",
  "availability_key": "chatgpt", 
  "command": "CODEX_CONFIG='{\"approval_policy\":\"never\",\"model\":\"gpt-5.5\",\"model_reasoning_effort\":\"high\",\"sandbox_mode\":\"danger-full-access\"}' INITIAL_AGENT_MODE=agent-full-access /opt/livespec/codex-acp/bin/codex-acp",
  "pricing": {"model": "gpt-5.5", "input_usd_per_million": 5.0, "output_usd_per_million": 30.0,
              "cache_write_usd_per_million": 6.25, "cache_read_usd_per_million": 0.5}
}
```

Three consequences of that shape, each measured:

- **Identity is by byte-equality of the rendered command**
  (`_acp_builtin_candidates.py`), so a repository that changes one env var
  loses built-in identity, holds, signatures and pricing at once. The module
  records this as deliberate ("never inferred from command text"), which is
  correct given the grammar, and is exactly why the grammar is the problem.
- **Only two agents have ergonomic entry points**: `codex_models`
  (`{model, reasoning_effort}` per node class, Codex only) and the workflow's
  Claude defaults. Both render agent-specific env (`CODEX_CONFIG`,
  `ANTHROPIC_MODEL`, `CLAUDE_CODE_EFFORT_LEVEL`). Measured across the eleven
  repositories under `/data/projects`, `codex_models` is set in none and
  `acp_nodes` in five, every one of them a bare Claude command string.
- **Pricing and availability signatures are hand-typed per candidate.**
  There is no catalog, so two repositories naming the same model type the same
  numbers twice and drift independently.

## Prior art that already solves the pieces

**The ACP standard has model selection.** The current protocol defines
`session/set_config_option`, with a `model` category and arbitrary option ids
such as `effort`, and the older `session/set_model`; the spec marks config
options as the preferred way to expose session configuration. The
`agent-client-protocol` crate Fabro's fork pins (0.11.1) already carries both
wire methods (`"session/set_config_option"`, `"session/set_model"` appear in
its source), so in-protocol selection needs no dependency bump; the latest
crate is 2.2.0. The Claude adapter this fleet runs (`claude-agent-acp` 0.44.0
on this host; registry stable is 0.84.0) implements config options with ids
`model`, `effort` and `mode`, and the Codex adapter's README lists "model,
reasoning effort, fast mode, approval, and sandbox mode configuration" as
config options. Today Fabro's ACP handler calls `session/new` then
`session/prompt` and never sets an option; every model choice rides
adapter-specific env instead.

**The ACP registry is the agent catalog.** `agentclientprotocol/registry`
lists 45 agents, each with a stable id and a launch distribution (`npx`
package plus args, `uvx`, or per-platform binary). It includes both agents we
run (`claude-acp`, `codex-acp`), the providers the maintainer named
(`grok-build` for xAI as `@xai-official/grok agent stdio`; `glm-acp-agent`
for z.ai, which advertises mid-session model switching), and multi-provider
open-source agents (`opencode`, `goose`, `gemini`, `kimi`, `minimax-code`,
`poolside`, `cline`, `qwen-code`). An `agent` field naming a registry id is
therefore a standard, portable way to say "which program" without spelling
the command, and the registry's `distribution` block is the rendering rule.

**Upstream Fabro's native path is the model-catalog prior art.** Upstream
`docs/public/core-concepts/models.mdx` separates provider, canonical model
slug, alias, family and API id; resolves `provider/model` or `provider:model`
references and bare aliases against a catalog that carries per-model costs,
context limits and `reasoning_effort` controls; supports `[llm.providers.<x>]`
entries for any OpenAI-compatible gateway; and runs `run.model.fallbacks`
with provider-aware resolution. That path is the API-key backend, not the
ACP agent backend the factory uses on subscriptions, so we cannot adopt it
wholesale, but its catalog shape and reference grammar are what our
candidate grammar lacks, and the same fork could expose the catalog to the
ACP handler.

## What the ergonomic layer should look like

One candidate grammar with two forms. The structured form is the default;
the manual form is the escape hatch and is exactly today's candidate.

```jsonc
"acp_nodes": {
  "implement": {
    "agent": "claude-acp",                 // ACP registry id; rendering comes from the registry distribution
    "model": "claude-opus-5",              // set in-protocol via session/set_config_option id=model
    "effort": "high",                      // likewise, id=effort, only when the agent advertises it
    "fallbacks": [
      { "agent": "codex-acp",  "model": "gpt-5.5", "effort": "high" },
      { "agent": "opencode",   "model": "zai/glm-5.2" },          // multi-provider agent: provider-qualified model
      { "agent": "grok-build", "model": "grok-4" },
      { "agent": "glm-acp-agent", "model": "glm-5.1" },
      {                                                            // manual form: any program, any wiring
        "display_name": "Local Qwen via OpenCode", "candidate_key": "qwen3-local",
        "availability_key": "homelab-ollama",
        "command": "opencode acp", "env": {"OPENCODE_CONFIG": "/etc/opencode/homelab.json"}
      }
    ]
  }
}
```

Rules the layer needs, each of which S1 through S4 already enforce for the
manual form and which the structured form must render into:

- `agent` resolves through a committed, versioned agent catalog (the ACP
  registry snapshot plus per-repository additions and pins) to a launch
  command; unknown agent ids refuse before claim. The registry entry's
  `npx`/`binary`/`uvx` distribution is the rendering rule, so the operator
  never types `npx -y @agentclientprotocol/...`.
- `model` and `effort` are applied over the protocol when the agent
  advertises the option (`configOptions` with category `model`, option id
  `effort`), and otherwise through a per-agent env mapping the catalog
  carries (`ANTHROPIC_MODEL`, `CODEX_CONFIG.model`, `MODEL_PROVIDER`). A
  model the agent does not advertise refuses before claim unless the entry
  says `"model_check": "skip"`.
- Identity derives from `(agent, model)` for the structured form instead of
  from command bytes; `availability_key` defaults to the agent's account
  domain (the catalog's `availability_domain`, e.g. `anthropic-max`,
  `chatgpt`) and is overridable. The manual form keeps explicit identity.
- Pricing and availability signatures come from a model catalog keyed by
  `provider/model` (upstream Fabro's catalog is the seed), overridable per
  candidate exactly as today. S6 then prices by catalog lookup, and the
  hand-typed `pricing` table becomes the override, not the norm.
- `codex_models` is retired: it becomes the structured form with
  `agent: codex-acp`, and a refusal prints the equivalent entry.

## What this changes in the plan

- **Spec.** A proposed change to §"Factory-configurable ACP fallback
  priority" and §"ACP node adapter configuration": the structured candidate
  form, the agent and model catalogs, in-protocol option setting, derived
  identity, and the retirement of `codex_models` and the class-shaped
  `Codex ACP node model pins` in favour of per-node entries. This is the
  same functionality the plan owns, so it is a plan scope event plus
  `propose-change`, not a separate plan.
- **Fabro fork (a second host-routed slice like S4).** The ACP handler
  applies `config_options` per candidate after `session/new` and before the
  prompt; the `acp.fallback_chain` grammar gains a per-candidate
  `config_options` object; a candidate whose advertised options do not
  include the requested model is a typed pre-turn refusal, not a fallback
  trigger.
- **Dispatcher.** Catalog loading and pinning; structured-to-manual
  rendering; identity derivation; the `codex_models` refusal.
- **S5 and S6 drafts.** S5 is unchanged in substance. S6 changes: pricing
  resolves through the catalog first, then the per-candidate override, and
  the "exact identity plus one trailing date suffix" rule applies to the
  catalog key.
- **S7.** Unchanged: it still pins the capability-bearing build and proves
  the journey, now with a structured chain.

## What does not change

The reactive-fallback mechanics S4 built (one visit, one deadline, typed
eligibility, side-effect onset ledger, versioned events), the S2 holds, and
the S3 preflight all operate on rendered candidates and are indifferent to
how the candidate was spelled. The manual form stays first-class so any
agent, including ones no registry lists, remains reachable.
