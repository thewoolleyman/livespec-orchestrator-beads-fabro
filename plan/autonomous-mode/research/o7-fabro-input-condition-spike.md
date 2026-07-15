# O7 SPIKE — Can a Fabro workflow edge condition reference a workflow input?

- **Work-item:** `bd-ib-lmnxrm` (O7) in the `thewoolleyman/livespec-orchestrator-beads-fabro` beads tenant.
- **Parent epic:** `bd-ib-24j5uy` — "Realize the ratified v034 dispatcher policy settings (retire Full autonomous mode)".
- **Gates child:** `bd-ib-6ytmik` (O8) — "Review gate becomes BLOCKING; configurable `review_fix_cap` + `merge_on_review_cap`".
- **Acceptance policy:** `human-only` — this verdict is a design finding; the AI produces it, the maintainer accepts it.
- **fabro binary exercised:** `fabro 0.254.0 (15b89ab 2026-07-14)` at `/home/ubuntu/.local/bin/fabro` — the version the orchestrator's `workflow.fabro` targets (its own comments cite "fabro v0.254.0").

## Verdict: YES — but via template-time baking, not runtime evaluation

A Fabro edge condition **can** be made to reference a workflow input value, and the input value **does** drive edge routing. This is **empirically proven** on the installed fabro 0.254.0 (see "Executed proof" below).

The mechanism is precise and matters for O8:

- **The input reaches the condition as a `{{ inputs.* }}` template token that fabro renders into the condition STRING at run-create time.** By the time the graph executes, `condition="context.internal.node_visit_count < {{ inputs.review_fix_cap }}"` has already become `condition="context.internal.node_visit_count < 3"` (or whatever value the run was given). The cap is a compile-time constant baked per run.
- **It is NOT a runtime dynamic read.** The routing engine's condition evaluator has no access to workflow inputs. Its entire evaluation context is `(outcome, Context)`, and the `Context` key→JSON map is never seeded with input values under any spelling. Conditions written as `inputs.branch=yes`, `context.inputs.branch=yes`, or `context.branch=yes` do **not** see a `-I branch=yes` input at runtime — proven below, all three fall through to the fallback edge.

So "reference an input" is true in the sense O8 needs (the cap value reaches the guard), but the plumbing is fabro's `{{ }}` template pass, identical to how the existing graph already injects `{{ inputs.acp_adapter }}` into node commands — not a new runtime binding.

### Load-bearing caveat — this behavior is version-sensitive

The template pass's scope **differs between fabro versions in this environment**:

| fabro build | Where it lives | Templates a `condition`? | Evidence |
|---|---|---|---|
| **0.254.0** (installed; orchestrator's pinned target) | `/home/ubuntu/.local/bin/fabro` | **YES** — `condition` is in the broad "all string attributes" template set | Empirically executed (below); `fabro validate` on a `{{ inputs.want }}` condition emits `template_undefined_variable ... attribute condition`, i.e. the engine tries to render it |
| **v0.289.0-nightly** (commit `d5dcd1179`) | `/data/projects/fabro` checkout | **NO** — template scope narrowed to node `prompt` and graph `goal` ONLY; `condition` is explicitly demoted | Source: `lib/crates/fabro-workflow/src/transforms/variable_expansion.rs:384-392` + its test `template_transform_renders_prompt_and_leaves_other_attrs_literal` |

In the 0.289 checkout, `variable_expansion.rs` renders only `prompt` and `goal`; every other string attribute — the code comment names `condition` by name — is "no longer a template", left literal, and flagged with a `detemplated_attribute` warning. Under that behavior, `condition="... < {{ inputs.review_fix_cap }}"` would keep the literal braces, never match numerically, and silently change routing (only a validate-time warning would fire).

The two builds' version-vs-date ordering is non-monotonic (0.254.0 release is dated 2026-07-14; the 0.289.0-nightly commit is dated 2026-07-09), so I do not assert a definite upgrade trajectory — that is a fabro-pin question for the maintainer. What is certain: **at least one fabro build in this environment removes condition templating, so any O8 design resting on it is coupled to fabro's template scope and must be validate-gated.** Note this exposure is not new to O8 — the *current* production `workflow.fabro` already depends on 0.254's broad templating for `acp.command="{{ inputs.acp_adapter }}"` (a non-`prompt` node attribute), which the 0.289 narrowing would also break.

## Evidence — the source (fabro 0.289 checkout, corroborated by 0.254 runtime behavior)

**Runtime condition evaluation reads only `outcome` + `Context`, never inputs:**

- `lib/crates/fabro-workflow/src/graph/routing.rs:22-48` — `select_edge(...)` filters edges by `evaluate_condition(c, outcome, context)`. The only data in scope is `outcome` and `context`.
- `lib/crates/fabro-workflow/src/condition.rs:15-58` — `resolve_key` resolves `outcome`, `preferred_label`, `context.<path>` (via `context.get`), and bare keys (via `context.get`). There is no `inputs` branch; an input can only match if something put it into the `Context` map.
- `lib/crates/fabro-workflow/src/context.rs:1-133` — the `keys` module enumerates every context key the engine populates (`internal.*`, `response.*`, `command.*`, `human.gate.*`, `parallel.*`, `graph.goal`, `outcome`, `preferred_label`, …). **There is no input key and no `inputs.*` prefix.** Workflow inputs are never written into the runtime `Context`.
- `lib/crates/fabro-workflow/src/services.rs:239-240` — `inputs: HashMap<String, toml::Value>` is documented as "Typed values from `[run.inputs]`, **available to prompt templates**" — i.e. inputs feed the *template* context, not the runtime condition context.

**Inputs feed only the template pass:**

- `lib/crates/fabro-workflow/src/transforms/variable_expansion.rs:292-310` — `TemplateTransform::new(inputs)` builds `TemplateContext::new().with_inputs(inputs)`; this is the ONLY place inputs enter graph processing. It "Expands `{{ goal }}` / `{{ inputs.* }}` / `{{ vars.* }}` across [string] attributes."
- Same file, `:356-397` (`render_attrs`) — in the 0.289 checkout this renders ONLY `prompt`/`goal` and demotes the rest (including `condition`). In 0.254 the render set is broad enough to include `condition` (proven at runtime).

## Executed proof (fabro 0.254.0, throwaway graphs, six runs)

All graphs use `script` (command) nodes — no LLM backend. Runs used `fabro run <graph> -I <k=v> --auto-approve`.

**1. Input baked into a condition via `{{ inputs.want }}` — routes differently for two input values (this is the criterion-#2 working proof).**
Graph: `emit -> took_input [condition="outcome={{ inputs.want }}"]`, else `-> took_fallback`.

| Run | Rendered condition | Node reached | Status |
|---|---|---|---|
| `-I want=succeeded` | `outcome=succeeded` (matches emit's outcome) | `took_input` | SUCCEEDED |
| `-I want=failed` | `outcome=failed` (no match) | `took_fallback` | SUCCEEDED |

The **same graph** routed to different terminals purely because the input value changed — the input drove the edge.

**2. Numeric cap guard mirroring O8's exact shape — `context.internal.node_visit_count < {{ inputs.cap }}`.**
Graph: `emit -> under_cap [condition="context.internal.node_visit_count < {{ inputs.cap }}"]`, else `-> at_cap`. On first entry `node_visit_count == 1`.

| Run | Rendered condition | Node reached |
|---|---|---|
| `-I cap=5` | `... < 5` → `1 < 5` true | `under_cap` |
| `-I cap=1` | `... < 1` → `1 < 1` false | `at_cap` |

Numeric template-baking works — exactly what O8 needs to make `review_fix_cap` / `merge_on_review_cap` configurable.

**3. Runtime read of an input in a condition — does NOT work (confirms the mechanism is template-only).**
`emit -> took_input [condition="inputs.branch=yes"]` with `-I branch=yes` → routed to **`took_fallback`**. `inputs.branch` (no braces) is a literal runtime key looked up in `Context`, which never holds inputs, so it resolves empty.

**4. Same, with the `context.*` spellings — also does NOT work.**
`context.inputs.branch=yes` and `context.branch=yes`, both with `-I branch=yes` → routed to **`took_fallback`**. Neither spelling reads the input at runtime.

**5. Positive control — proves the condition engine routes at all (so #3/#4 are true negatives).**
`emit -> took_input [condition="outcome=succeeded"]`; emit exits 0 → outcome succeeded → routed to **`took_input`**. The engine does route on an in-scope key; the fallbacks above are real, not a broken harness.

**6. `fabro validate` diagnostic corroboration (0.254).**
`fabro validate` on a graph whose condition is `outcome={{ inputs.want }}` (no input bound) emits:
`warning: ...:11:69: undefined template variable \`inputs.want\` in edge \`emit -> took_input\` attribute \`condition\` (template_undefined_variable)` — the 0.254 engine explicitly treats the `condition` attribute as a template render site. (On the 0.289 source this would instead be a `detemplated_attribute` warning.)

## Recommendation for O8

O8 wants `review_fix_cap` and `merge_on_review_cap` VALUES to reach the review-gate edge guards in `implement-work-item/workflow.fabro` (currently the hardcoded `< 3` on `janitor -> fix` and the `context.internal.node_visit_count < 3` on `review -> review_fix`). Two viable designs:

### Option A (Recommended) — native input-templated conditions
Because 0.254 templates conditions, O8 is a minimal, native change with **no new render seam**:

1. Declare the caps in `.claude-plugin/.fabro/workflows/implement-work-item/workflow.toml` under the existing `[run.inputs]` table (which already declares `acp_adapter` / `review_adapter`), with default values:
   ```toml
   [run.inputs]
   review_fix_cap = 3
   merge_on_review_cap = 3
   ```
2. Rewrite the guards to reference them, e.g.
   `review -> review_fix [condition="preferred_label=fix && context.internal.node_visit_count < {{ inputs.review_fix_cap }}"]`
   and the analogous `janitor -> fix` / merge-on-review-cap edges.
3. The Dispatcher optionally overrides them per run via the seam it **already uses** for adapters — `fabro run --input review_fix_cap=N ...` (assembled in `_dispatcher_run_commands.py`, the same path that passes `--input acp_adapter=...`). With no override, the `workflow.toml` defaults apply.

- **Pro:** smallest diff; reuses the existing input-passing seam; consistent with how the graph already parameterizes node commands.
- **Con:** couples the cap plumbing to fabro's template scope. It breaks under a 0.289-style narrowing. **Mitigation is mandatory:** keep a `fabro validate` gate in the janitor/CI that fails on a `detemplated_attribute` warning for the condition attributes, so an upgrade that narrows templating is caught loudly rather than silently misrouting. (This same gate also protects the pre-existing `acp.command` templating.)

### Option B (version-robust fallback) — Dispatcher renders the graph per-run
If the maintainer wants zero coupling to fabro's template scope: the Dispatcher reads `workflow.fabro` as a template, substitutes the cap values (and the adapter commands) with its **own** string rendering before invoking `fabro run`, and passes the rendered graph.

- **Render seam:** `_dispatcher_run_commands.py` (where the `fabro run` argv is assembled today).
- **Template location:** `.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro` becomes (or spawns) a `.fabro.tmpl`; the Dispatcher writes the rendered `.fabro` into the run's config/goal directory.
- **How it reaches the sandbox:** fabro clones the repo into the sandbox and reads the workflow path handed to `fabro run`; the Dispatcher points `fabro run` at the rendered file (or overlays it in the run config), so the sandbox executes the per-run-baked graph. No dependency on fabro's `{{ }}` pass at all.
- **Pro:** immune to fabro template-scope changes; the cap edge set can even vary structurally per run. **Con:** more moving parts; re-implements substitution fabro already does in 0.254.

**Bottom line for O8:** proceed with **Option A** (it is proven working today and is the smallest change), but land it together with a `fabro validate` guard that fails on condition-attribute detemplation, and record the fabro-version coupling explicitly. Escalate to Option B only if the maintainer decides fabro's template-scope narrowing is on the near-term upgrade path.

## Status
O7 verdict delivered and recorded (this doc; plus a summary `bd note` on `bd-ib-lmnxrm`). **Awaits the maintainer's human-only acceptance** (acceptance policy `human-only`); the AI does not drive the accept valve. The throwaway proof graphs were run in an agent scratch dir and are not part of any repo's product source.
