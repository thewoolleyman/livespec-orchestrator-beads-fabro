# factory-configurable-model-fallback-priority — opening research

_Author: fix-gpt-mini-in-factory session (Claude Opus 4.8). Written 2026-09-09
immediately after landing the `pr`-node Haiku-default fix (PR #2384, spec v107),
which motivated this plan._

## 1. Why the outage happened, and why it was a HARD failure

The factory's ACP nodes (implement / fix / review_fix / pr / review / disposition)
each resolve to **exactly ONE adapter string** — one command, one model, one
provider — through the three-layer merge in
`_acp_node_layers.resolve_acp_nodes` (workflow default < repository
`dispatcher.acp_nodes` / `codex_models` < per-dispatch `--acp-node`). That one
adapter is rendered into the node's `fabro run --input <node>_adapter=...` and
Fabro launches the node with it. **There is no notion of an alternative.**

When `gpt-5.4-mini` (the baked Codex `pr` default) was dropped from the
ChatGPT-account Codex catalog, the `pr` node's single adapter pointed at a model
the account could no longer invoke. The node returned HTTP 400 "model is not
supported when using Codex with a ChatGPT account" (an equivalent case is 404
"model does not exist", exit 127 on a de-templated command, or 429 usage-limit).
Because the resolution layer holds one adapter and the dispatch loop has no
"try the next one" path, the whole run died at `pr` after ~40 min of correct
implement/review work. The just-landed fix moved the `pr` FLEET DEFAULT to a
model-agnostic Claude Haiku adapter and made Codex opt-in — but that is a better
DEFAULT, not resilience. **The structural gap remains: any single pinned model,
on any node, on any provider, is a single point of failure.**

## 2. Goal (maintainer-stated 2026-09-09)

Every factory node should carry a **per-node, ordered list of fallback models**,
spanning ANY provider — Anthropic, OpenAI/Codex, z.ai, and self-hosted/local
models — and fall back **automatically, in priority order**, when the current
choice is unavailable, so a provider/catalog outage never breaks a dispatch again.

Requirements:
- **Per-node configuration** of an ordered fallback priority list.
- **Any model / any provider** — the config surface must not hard-code a
  provider taxonomy.
- **Automatic, in-order** fallback on an availability/capacity failure.
- **Warn, don't hide**: when the primary (first choice) is NOT the one used,
  emit a warning naming the primary and the model actually used, WITH directions
  to surface it to a human so they can investigate the primary provider's problem.
- Fallback is for **availability/capacity** failures only — never a mask for a
  genuine code/test failure (that must still fail the run honestly).

## 3. What already exists to build on (in-context code map)

- **`_acp_node_adapters.py`** — the `AcpAdapter` (command/env/args) type, its
  render/parse round-trip, `NODE_INPUT_CANDIDATES` (node → workflow input
  name), and the per-field layer merge. THE model-agnostic surface already
  lives here: any provider is expressible as an adapter string (Anthropic =
  `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`/`ANTHROPIC_MODEL`; OpenAI-compatible
  incl. z.ai/local = `-c model_provider=<name>` + provider def in args; Codex =
  `CODEX_CONFIG`). This is the atom a fallback LIST holds.
- **`_acp_node_layers.py`** — `resolve_acp_nodes(...)` merges the three layers
  into ONE `ResolvedAcpNode` per node. This is where a single adapter is chosen
  today; a fallback design must let a node resolve to an ORDERED LIST of
  adapters (primary first) instead of one.
- **`_acp_node_repository.py`** — `repository_acp_overlays` + the
  `codex_models` shorthand → overlays. Repo-layer config parsing lives here.
- **`_codex_model_tiers.py`** — the Codex per-tier pins (now partial-table
  fallback only). Its `CodexModelTier` and per-key degradation is a template
  for a list-shaped tier.
- **`_dispatcher_acp_nodes.py`** — `workflow_adapter_inputs` reads the workflow
  layer from committed `workflow.toml`; `prepare_acp_nodes` resolves + journals.
  The `--input <node>_adapter=` rendering is `_run_inputs` in `_acp_node_layers`.
- **`workflow.toml` `[run.inputs]`** — ONE `<node>_adapter` input per node
  (the single-source default). Fabro consumes exactly one value per input.
- **Dispatch engine / failure classification** — `_dispatcher_engine.py`,
  `_fabro_port.fabro_failure_detail_from_payload`, `_dispatcher_watchdog.py`.
  The reactive fallback loop (detect availability failure → re-render with next
  adapter → re-dispatch) would live in the engine. Failure SIGNATURES already
  parsed: `_CODEX_PROVIDER_LIMIT` (usage_limit_exceeded / 429),
  transient_infra/acp categories (see `test_dispatcher_codex_pins_and_provider_limits_scenarios64_65.py`).
- **Provider spend containment** (`_dispatcher_cost*.py`, contracts.md
  §"Provider spend containment") — already models an **observed
  provider-exhaustion record** that refuses admission when a provider is
  exhausted, with bounded expiry + dispatch-outcome falsification + operator
  clearance retirement routes, and an admission-time credential-usability
  re-probe (`dispatcher.credential_reprobe_interval_seconds`). Fallback should
  COMPOSE with this, not duplicate it: an exhaustion record on the primary's
  provider is exactly a "fall back to the next" signal.
- **Attention / warning surface** — `hygiene:*` attention facts + the journal
  (contracts.md §"Orchestrator-owned attention facts", the needs-attention
  machine envelope). The "primary not used" warning belongs here (a warn-only
  fact + a journal record), NOT a refusal.
- **Spec** — contracts.md §"Codex ACP node model pins" and §"ACP node adapter
  configuration"; scenarios.md Scenarios 64/86/87/90. The fallback surface is a
  ratified spec change (propose-change → revise), like v107 was.

## 4. Key design decisions (to ratify with the maintainer)

1. **Reactive vs. pre-flight.** Two complementary mechanisms:
   - *Pre-flight selection*: before dispatch, pick the first fallback entry not
     covered by an unexpired provider-exhaustion record (cheap, composes with
     existing containment; no failed-run cost). Recommended as the FIRST line.
   - *Reactive fallback*: if the launched node fails with an
     availability/capacity signature, re-render with the next entry and
     re-dispatch. Needed for outages that only surface at run time (catalog
     drift like this one, mid-run 401/404/429). Recommended as the SECOND line.
   A full design likely needs BOTH; a first slice can deliver pre-flight +
   exhaustion-record integration, with reactive as a later slice.

2. **Where fallback executes.** Fabro runs the whole workflow and has no native
   per-node adapter fallback (verify against the pinned fork
   `factory-integration`). So fallback is **Dispatcher-side**: either
   (a) re-dispatch the run with the next adapter for the failed node, or
   (b) if Fabro can restart a single node, restart just that node. (a) is
   simpler and matches the existing re-dispatch/reconcile machinery; its cost is
   re-running earlier nodes unless a checkpoint is reused. INVESTIGATE whether a
   failed run's checkpoint (`fabro dump`/checkpoint sha) lets the next-adapter
   re-dispatch resume rather than restart.

3. **Failure discrimination — the sharp edge.** Fall back ONLY on
   availability/capacity signatures (400 model-not-supported, 404
   model-not-found, 401 auth-expired-for-provider, 429/usage_limit,
   provider-limit, exit 127 de-templated command). NEVER on a genuine
   implement/review failure, a test failure, or a non-convergence — those must
   fail honestly. Enumerate the signature set in the spec and in `_fabro_port`.
   Getting this wrong in the permissive direction masks real breakage; in the
   strict direction it fails to fall back. This is the highest-risk clause.

4. **Config shape (per-node, ordered, any provider).** Proposal:
   `dispatcher.acp_nodes.<node>.fallback = [ <adapter>, <adapter>, ... ]` where
   each entry is a full adapter string OR the `command`/`env`/`args` table the
   existing surface already accepts — so ANY provider is expressible with no
   code change (Anthropic/OpenAI/z.ai/local all already are). The existing
   single `acp_nodes.<node>` value is entry 0 (the primary) by construction; the
   `codex_models` shorthand expands to a single Codex entry. Keep the model-agnostic
   value names rule (maintainer 2026-08-31): descriptive, provider-self-describing.
   The workflow.toml `[run.inputs]` default stays the primary; the fallback list
   is a repository-layer (and per-dispatch) concept resolved by the Dispatcher.

5. **Warning contract.** When the used adapter != the primary: (a) a journal
   record naming primary, used, node, run id, and the failure signature that
   triggered fallback; (b) a warn-only attention fact
   (`hygiene:model-fallback:<repo>:<node>`?) carrying the same, with directions
   to investigate the primary provider; (c) it CLEARS when a later dispatch uses
   the primary again. Never refuses. Mirrors the idle-factory/exhaustion fact
   shape.

6. **Cost observability.** `_dispatcher_cost_pricing._PRICE_TABLE` must price
   every model any fallback list can reach, or the spend cap under-counts. A
   fallback list widens the model set; the cost table (or its resolution) must
   keep pace, ideally without a hard-coded per-model table (consider a
   per-adapter configured price).

## 5. Proposed slices (dependency-layered; to be groomed/ratified)

- **S0 (spec):** propose-change → revise adding the per-node fallback config
  surface, the availability-failure signature set, the automatic in-order
  fallback contract, and the warn-and-surface (never-refuse) rule to
  contracts.md §"ACP node adapter configuration" / §"Codex ACP node model pins"
  + scenarios. Blocks everything below.
- **S1 (resolution):** extend `_acp_node_layers` / `_acp_node_repository` so a
  node resolves to an ORDERED LIST of adapters (primary first), parsing the
  `fallback` config; journal the full list. Pure, hermetic, TDD.
- **S2 (pre-flight selection):** Dispatcher picks the first list entry not under
  an unexpired provider-exhaustion record; integrate with
  §"Provider spend containment". Emits the fallback warning when entry 0 is
  skipped.
- **S3 (reactive fallback):** on an availability-failure terminal, re-render
  with the next entry and re-dispatch (investigate checkpoint reuse); record an
  exhaustion record for the failed provider so pre-flight learns.
- **S4 (warning/attention surface):** the warn-only fallback attention fact +
  journal record + clear-on-primary-restored, per §4.5.
- **S5 (cost coverage):** ensure the spend seam prices every reachable fallback
  model; prefer per-adapter configured pricing over a widening hard-coded table.
- **S6 (optional):** an operator/pre-dispatch availability probe (reusing the
  catalog-probe technique this session used) to validate a fallback list before
  it is relied on.

## 6. Prior art to scan BEFORE designing (do this first on resume)

Per repo discipline, scan the ledger `--status all` (incl. closed/acceptance/
blocked) for: existing fallback/retry/model-selection work; the
provider-exhaustion / spend-containment epic (it already has half of S2/S3);
`bd-ib` items on `dispatcher.acp_nodes` / `codex_models` / adapter resolution;
and any Fabro-side per-node retry capability on the `factory-integration` fork.
Read maintainer rulings there — several bind this design (model-agnostic enum
value names 2026-08-31; no fail-open checks; observed-not-predicted for provider
state).

## 7. Immediate next action

Groom S0–S6 into ready, dependency-layered slices with the maintainer (the
`groom` skill), starting from the prior-art scan in §6; ratify the config shape
(§4.4), the failure-signature set (§4.3), and the reactive-vs-pre-flight split
(§4.1) as the three load-bearing decisions before filing any implementation
child. S0 (spec) gates all implementation slices.
