# Fabro parallel / multi-reviewer node support

Question investigated: does fabro support running MULTIPLE REVIEW NODES
concurrently (fan-out to several reviewers, join before routing
onward), in case the factory wants a multi-reviewer gate? Source
citations are files under `/data/projects/fabro` (fork checkout; read
on `main` v0.289-nightly — machinery matches live docs, v0.254 not
diffed).

Bottom line: **fabro has first-class, documented parallel fan-out /
fan-in, and its canonical tutorial is literally a multi-reviewer
graph — but two constraints make it a poor fit for THIS graph as
wired** (no proven ACP-in-parallel path; the native fan-in judge needs
API-backend credentials the OAuth-only server deliberately withholds).
Given the failure telemetry (review is not the bottleneck —
failure-telemetry-2026-07-23.md), this is recorded as capability
knowledge, not a recommendation.

## Plain nodes are single-active; concurrency needs an explicit fork

A normal node does NOT run its out-edges concurrently — the executor
picks ONE next node via the cascade (condition → preferred_label →
suggested_next → unconditional, highest weight) and advances to that
single target (`fabro-core/src/executor.rs:169,260-272`;
`docs/public/workflows/transitions.mdx:8-17`). Concurrency is triggered
only by node SHAPE (`fabro-types/src/graph.rs shape_to_handler_type`):

| Primitive | How | Source |
|---|---|---|
| Fan-out | `shape=component` — ALL out-edges become concurrent branches | `graph.rs`; `docs/public/tutorials/parallel-review.mdx:46` |
| Merge / fan-in | `shape=tripleoctagon`; branch results exposed as `parallel_results.json` | `docs/public/workflows/stages-and-nodes.mdx:180-195` |
| Join policy | `wait_all` (default) or `first_success` — only these two; NO numeric k-of-n quorum | `handler/parallel.rs:31-49,597-605` |
| Concurrency cap | `max_parallel` (default 4) | `parallel.rs:176-181` |
| Per-branch isolation | isolated context copy + own sandbox/worktree + `parallel_base` git checkpoint | `parallel.rs:130-208` |

The merge node CAN be an LLM adjudicator: with a `prompt` + backend it
runs `llm_evaluate` to select the best candidate across branches
(`handler/fan_in.rs:70-100`), else a heuristic pick; it fails only if
ALL branches fail. That is pick-best/synthesize, not a vote — a true
quorum needs a downstream node reading `parallel_results.json`.
Canonical multi-reviewer example:
`test/docs/tutorials/parallel-review/parallel.fabro`
(`fork[component] -> {security, architecture, quality} ->
merge[tripleoctagon] -> report`).

## Distinct adapters/models per node — no engine limit

Each ACP node independently resolves its own `acp.command`/`acp.config`
(`docs/public/core-concepts/agents.mdx:36-55`); this graph already runs
two adapters (`inputs.acp_adapter`, `inputs.review_adapter`). N
reviewer branches could each carry a distinct adapter/model; nothing in
the engine caps the count.

## The two constraints for THIS factory

1. **No proven ACP-in-parallel-branch path.** A grep across the whole
   corpus (bundled examples, tutorials, public third-party workflows)
   found ZERO `.fabro` placing `backend="acp"` under a `component`
   fork — all parallel examples use API/prompt-backend branches.
   Plausibly compatible (per-branch worktree + ACP), but untested in
   the shipped corpus.
2. **The native fan-in LLM judge runs on the API backend**
   (`make_backend()` — not ACP). It would need `ANTHROPIC_API_KEY` on
   the server, which the OAuth-only posture deliberately withholds
   (CLAUDE.md §"Host Fabro server"). The current review node is ACP
   precisely to bill the subscription and pin the model via adapter
   env.

## ACP/OAuth-compatible approximation (if ever wanted)

Chained sequential reviewers `review_a -> review_b -> ...`, each an ACP
node with its own adapter/model/lens, each emitting
`preferred_next_label`; aggregate verdicts via `context_updates` keys +
edge conditions (`contains`, numeric comparison, `&&`/`||`). Engine
gotcha: `context.internal.node_visit_count` is PER-NODE, so the current
graceful cap-guard trick on `review`'s visit count
(`workflow.fabro:284`) does not transfer across multiple reviewer
nodes — round-tracking would move to a shared `context_updates`
counter, with per-node `max_visits` as the ungraceful backstop.

## Not determined

Whether ACP nodes actually execute under a `component` fork (untested);
whether the fan-in `llm_evaluate` judge can be pointed at an ACP/OAuth
adapter (wired to the API backend; no override seen); exact
`first_success` branch-cancellation semantics.
