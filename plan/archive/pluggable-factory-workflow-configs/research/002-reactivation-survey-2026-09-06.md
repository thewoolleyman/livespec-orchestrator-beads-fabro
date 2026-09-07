# pluggable-factory-workflow-configs — reactivation survey (2026-09-06)

This note re-measures the 2026-08-17 initial research
(`001-initial-research.md`) against the code, the spec and the fleet as
they stand on 2026-09-06, records what changed while the plan was
dormant, and fixes the design the scope event and the child work-items
are cut from. Every claim below names the surface it was measured on.

## Why the plan is live again

The 2026-08-30 handoff parked this plan on one condition: hold until
`typed-repo-integration-contract` C5 lands, and when built, make the
variant registry satisfy R4's seam-equivalence check for every
registered variant. That condition is met. Plan epic `bd-ib-vblnq2` and
every child of it are `closed` in the ledger, including both C5 halves —
`bd-ib-b7xpzl` (typed workflow inputs) and `bd-ib-yn55u6` (the
seam-equivalence CI check) — measured on 2026-09-06 through
`bd list --status all --limit 0 --json`.

The v092 seam changed what a variant IS. Adopter-neutrality now rides on
typed inputs (`prepare_toolchain_*`, `conformance_*`, `default_branch`,
`merge_mode`, `sandbox_check_suite` in `workflow.toml` `[run.inputs]`),
so an adopter needs no workflow copy to change its toolchain, its default
branch or its merge strategy. What is left for a NAMED VARIANT is a
genuinely different graph or run configuration: a different node set, a
different retry or review discipline, a different sandbox image family,
or a different prompt set. That is a smaller, sharper driver than the
one the initial research had, and it is the only one this plan builds
for.

## What still holds from the initial research

Measured 2026-09-06 on `master` at `efb1a4b2`:

- `commands/_dispatcher_paths.py` still hardcodes the workflow name in
  `_WORKFLOW_SUBPATH = (".fabro", "workflows", "implement-work-item",
  "workflow.toml")`, and `workflow_toml()` still resolves over the same
  three steps: explicit `--workflow <path>` → the dispatch target's own
  committed `<repo>/.fabro/workflows/implement-work-item/workflow.toml`
  → the plugin's bundled default. There is no registry of named
  variants, no default-selection key, and no ledger-recorded retry
  consistency for the choice.
- `commands/_config.py::resolve_fabro_factory` and
  `commands/_dispatcher_factory_ledger.py::resolve_dispatch_factory_target`
  remain the shapes to mirror: a named registry (`dispatcher.factories`),
  a default (`dispatcher.default_factory`), an explicit argument, and a
  ledger-pinned prior choice (`dispatch_factory` item metadata, written
  by `_store_dispatch_factory.py::record_dispatch_factory`) so a retry
  reuses the same target.
- The complete-variant principle holds and is now stronger, not weaker:
  the repo-local override already REPLACES the bundle wholesale, and the
  v092 seam check reads a payload as one unit (`workflow.fabro` plus
  `workflow.toml`). A partial overlay would have no seam to be checked
  against.

## What changed while the plan was dormant

1. **The bundle is `workflow.fabro` + `workflow.toml`, both tracked.**
   The graph lives in `workflow.fabro`; the run configuration, the
   `[run.inputs]` declarations and the sandbox image table live in
   `workflow.toml`. Both ship in the plugin payload under
   `.claude-plugin/.fabro/workflows/implement-work-item/`. A variant is
   therefore a DIRECTORY (graph, config, prompts), never a single file.
2. **Per-node model choice is already configuration.** The ACP node
   adapter contract (`SPECIFICATION/contracts.md` §"ACP node adapter
   configuration", realized in `_acp_node_layers.py`,
   `_acp_node_repository.py`, `_dispatcher_acp_nodes.py`) resolves
   every ACP node's adapter through three layers — workflow defaults →
   the target's `dispatcher.acp_nodes` / `codex_models` → a recorded
   `--acp-node` dispatch argument. "Different steps, different models"
   needs no variant. A variant is for a different GRAPH.
3. **The adapter contract has NO environment layer, on purpose.** Its
   rationale, quoted from `_acp_node_layers.py`: "an ad-hoc shell cannot
   re-provider the whole factory with nothing in the committed record or
   the journal to show for it." The initial research proposed a
   `LIVESPEC_FABRO_WORKFLOW` environment override mirroring
   `LIVESPEC_FABRO_FACTORY`. That mirror is now the WRONG precedent:
   which graph runs is at least as consequential as which adapter runs,
   so the workflow selector follows the adapter contract (recorded
   argument, never environment), not the older factory one.
4. **The dispatch record already names the workflow path.**
   `_dispatcher_dispatch_id_journal.py` writes `workflow_toml` (the
   resolved committed path) on every dispatch-id record, and
   `_dispatcher_loop.py` threads `committed_workflow` into the plan
   build. The variant NAME is the one fact missing from that record.
5. **The dispatch payload is materialized per run.**
   `_dispatcher_loop_materialize.py` copies the whole committed workflow
   directory to a per-dispatch payload dir, renders node timeouts into
   the graph, and resolves ACP adapters — all keyed on the ONE path
   `workflow_toml()` returns. Parameterizing that path by variant
   directory is the entire mechanical seam; nothing downstream reads the
   literal `implement-work-item` name.
6. **The v092 checks are bound to the bundle path only.**
   `dev-tooling/checks/seam_equivalence.py` reads
   `_PAYLOAD_RELPATH = (".claude-plugin", ".fabro", "workflows",
   "implement-work-item")` and asserts the three integration-input
   surfaces agree, with a DISCOVERY control that the scan reached the
   real payload. `check-no-fleet-toolchain-literals` scans the same
   payload. A registered variant that neither check reads can carry a
   fleet literal or an unrendered token and pass CI, which is exactly
   the R4 gap the 2026-08-30 handoff named.

## Corrections to the initial research

- **The CI preflight does not use the dispatcher's `--workflow`.** The
  initial note kept the raw `--workflow <path>` flag partly because "the
  CI preflight check already uses it, per
  `_dispatcher_master_ci_preflight.py`". Measured 2026-09-06:
  `_dispatcher_ci_preflight_lookups.py:92` passes `--workflow` to
  `gh run list`, a GitHub Actions workflow filter, unrelated to Fabro.
  The raw path flag stays for a different reason: it is the ratified
  escape hatch in `SPECIFICATION/contracts.md` §"Self-contained plugin
  dispatch" and the one-off override an operator uses to run an
  uncommitted workflow.
- **Factory selection has no spec clause and no scenario of its own.**
  `grep -n "default_factory\|LIVESPEC_FABRO_FACTORY\|dispatch_factory"
  SPECIFICATION/*.md` returns nothing on 2026-09-06; the only spec
  mention of `dispatcher.factories` is Scenario 106 (reconciliation
  addresses every declared factory). The initial note assumed a factory
  selection scenario existed to mirror. There is none, so the variant
  registry's spec section is authored from the adapter-configuration
  section's shape instead, which IS ratified and IS the closer
  precedent.

## Impl→spec drift found while re-reading

`SPECIFICATION/contracts.md` §"Self-contained plugin dispatch" says an
adopter's target-local workflow is "supplied today via the dispatcher's
explicit `--workflow` override" and that "any future automatic
target-local resolution (the target's `.fabro/workflows/...` taking
precedence over the plugin payload) amends THIS section's plugin-root
resolution rule before it ships." The automatic resolution SHIPPED on
2026-07-20 in commit `c8bde4a5` ("discover the dispatch target's own
committed Fabro workflow", reported as `livespec-console-beads-fabro-8i9`),
with tests in `test_dispatcher_workflow_resolution.py`, and no
proposal in `SPECIFICATION/history/v0*/proposed_changes/` ratifies it
(searched for "dispatch target's own", "target's own committed",
"repo-local override"; the sole hit outside history is the unchanged
prose above). The item the clause cites, `bd-ib-z2ctra`, is `backlog`
and is about a per-tenant Fabro server recipe, not this rule.

This plan's spec proposal MUST therefore do two things in one section:
ratify the three-step precedence that has been running for seven weeks,
and extend it with the named-variant registry. Ratifying the existing
behavior is not optional scope creep; the registry's precedence is
defined RELATIVE to it, and a spec that still says "explicit override
only" cannot host a registry clause coherently.

## Fleet survey: who forks the workflow today, and why

Measured 2026-09-06 over `/data/projects/*/.fabro/workflows/`
(comments and blank lines stripped before diffing against the bundle):

| repo | `workflow.fabro` delta (lines) | `workflow.toml` delta (lines) | prompts differing | graph nodes only in fork |
|---|---|---|---|---|
| `livespec-console-beads-fabro` | 0 | 2 | none | none |
| `homelab` | 35 | 27 | 5 of 6 | `abandon`, `escalate` |
| `openbrain` | 81 | 41 | 6 of 6 | `abandon`, `escalate` |

Readings:

- The console fork's ENTIRE delta is one line: the sandbox image tag
  (`python-rust-agent-v1.46.0` against the bundle's
  `python-agent-v1.47.0`). `dispatcher.fabro_sandbox_image` already
  overrides exactly that value (`_config.py::resolve_fabro_sandbox_image`,
  consumed in `_dispatcher_credentials.py`), and the console repo's
  `.livespec.jsonc` does not set it. That fork is replaceable by one
  config key today and is already one bundle version behind. This is an
  observation for the console repo's owner, not a child of this plan.
- The homelab and openbrain forks still carry the retired `abandon` and
  `escalate` graph nodes that v093's `needs_human` terminal replaced.
  They are drifted copies of an older graph, which is the fork-drift
  problem the homelab plan `fabro-workflow-fork-refresh` filed
  `bd-ib-yqpdrt.1` about. v092's typed inputs remove the toolchain reason
  for those forks; a named-variant registry gives the remaining reason
  (a deliberately different graph) a first-class, seam-checked home
  instead of an unchecked copy.

So the registry has three real consumers in the fleet, all currently
served by the unratified target-local precedence, and none of them
seam-checked.

## The design this plan builds

**Registry.** `dispatcher.workflows.<name>` in the dispatch TARGET's
`.livespec.jsonc` maps a variant name to a directory, relative to the
target repo root, that holds a COMPLETE workflow: `workflow.toml`,
`workflow.fabro` and its `prompts/`. `dispatcher.default_workflow`
names which entry a dispatch uses when nothing more specific chooses.
The reserved name `implement-work-item` is always defined and resolves
through today's target-local-then-bundle rule; a registry entry may not
redefine it. (Mirrors `dispatcher.factories` / `default_factory`,
except the values are directories.)

**Precedence, most specific wins.** (1) explicit `--workflow <path>`,
the raw-path escape hatch, unchanged; (2) explicit `--workflow-name
<name>` on `dispatcher.py dispatch`, `dispatcher.py loop` and `drive
impl:<id>`, a RECORDED per-dispatch argument; (3) the name a prior
dispatch of the same work-item pinned in `dispatch_workflow` item
metadata, so a retry re-runs the same variant; (4)
`dispatcher.default_workflow`; (5) `implement-work-item`. No
environment layer, per the adapter contract's rationale. Every dispatch
writes the resolved name to `dispatch_workflow` metadata beside
`dispatch_factory`, and the dispatch-id journal record carries
`workflow_name` beside the existing `workflow_toml`.

**Refusals, all before any Fabro run exists.** A `--workflow-name` or
`default_workflow` that names no registry entry; a registry entry whose
directory lacks `workflow.toml` or `workflow.fabro`; a registry entry
named `implement-work-item`. Each refusal keeps its own journal stage,
matching how `_dispatcher_loop_materialize.py` reports a node-timeout or
ACP-node typo.

**Seam parity (R4).** `check-seam-equivalence` and
`check-no-fleet-toolchain-literals` iterate the bundle AND every
directory named under this repo's own `dispatcher.workflows`, applying
the discovery control per directory, so a registered variant cannot
carry a fleet literal or an unrendered integration token that the bundle
cannot.

## Amendments from the objective doctor pass (same day)

A scoped objective pass over the first draft of the proposal (an
independent reviewer reading the proposal against §"Self-contained plugin
dispatch", §"Repository integration contract", §"ACP node adapter
configuration", §"ACP node timeouts" and the closed-set disposition)
surfaced seven tensions. Each changed the design as follows, and the
filed proposal carries the amended form:

1. **Not a schema field, by construction.** The "One schema" and "One
   resolver" rules govern integration points the orchestrator REQUIRES of
   a governed repository. The registry is an OPTIONAL target-declared
   capability in the class of `dispatcher.acp_nodes`, so those rules do
   not govern it, and the closed-set members-and-adopters disposition is
   that a repository declaring no registry incurs nothing.
2. **Refusal shape named.** The three refusals take the adapter-layer
   shape (journaled pre-run refusal naming every applicable cause), NOT
   the schema-validation exit-3 `Defective` enumeration, because the keys
   are not schema fields.
3. **A variant declares the same six ACP nodes.** Three sections are
   scoped to `implement-work-item` by name and their per-repository
   layers (`acp_nodes`, `codex_models` expansion, `node_timeouts`) refuse
   on a node the graph does not declare. Rather than exempt variants, the
   proposal makes every such clause apply to a variant as a peer and
   requires the six node names; a variant differs in edges, retry and
   review discipline, prompts, run config and sandbox image.
4. **Same `inputs.*` token set per variant.** Seam equivalence is a
   three-way set identity against ONE Dispatcher-rendered set, so a
   variant that references fewer inputs cannot pass it. The proposal
   makes that a rule: no variant opts out of an integration input. This
   is what the 2026-08-30 R4 rider meant.
5. **The bold lead-in "Target-local workflow." is retained** because two
   other clauses cite it by that name; renaming it would dangle them.
6. **The older adopter-dispatch scenario is aligned** (it still named the
   `--workflow` override as the route to a target-local workflow).
7. **Undefined terms removed or defined.** `dispatch_factory` is no
   longer cited as a defined key; `workflow_toml` and `workflow_name`
   are defined where introduced; the seam check is named as the spec
   names it (the CI seam-equivalence check), the literal scan by the
   gate name `constraints.md` ratifies (`check-no-fleet-toolchain-literals`
   under "Governed-repository integration constraints"), and the journal
   surface by the spec's own term, "dispatch record".

Consequence for the children: B1's refusals are unchanged; the node-name
parity is enforced by the EXISTING adapter-layer and timeout refusals
and needs no new refusal. C gains the per-variant set-identity
requirement explicitly (a variant referencing fewer tokens is a finding).

## Scope cut proposed for the scope event

Requirement carriers (one child each unless noted):

- **A — spec ratification** (spec-change tier, via `propose-change`,
  lands first): amend §"Self-contained plugin dispatch" to ratify the
  shipped three-step precedence and add the registry, precedence,
  refusals, ledger pin, no-environment-layer rule and R4 parity; one
  scenario in `scenarios.md`; `tests/heading-coverage.json` co-edit.
- **B1 — registry and resolution**: parse `dispatcher.workflows` /
  `default_workflow`; `resolve_workflow_variant` in `_config.py`
  mirroring `_factory_target_for`; parameterize `workflow_toml()` by
  variant directory; the three pre-run refusals.
- **B2 — ledger pin and per-dispatch argument**: `--workflow-name`
  threaded through dispatch-common and `drive impl:<id>` exactly as
  `--acp-node` is; `_dispatcher_workflow_ledger.py` mirroring the
  factory ledger; `record_dispatch_workflow` / `dispatch_workflow_for`
  beside the factory pair; `workflow_name` on the dispatch-id record.
- **C — seam parity**: both v092 checks iterate every registered
  variant with the discovery control applied per directory.

Dependency layering: B1 and C depend on A landing as a revision; B2
depends on B1. `bd-ib-yqpdrt.2` (exact adapter package pin) stays an
independent bundle-hygiene child and is not a requirement carrier of
the registry.

Explicit deferrals, each with where it is reconsidered:

- A `LIVESPEC_FABRO_WORKFLOW` environment layer — deferred because the
  adapter contract's no-environment rule is the governing precedent;
  reconsidered only if `revise` rejects that rule for workflows.
- A `list-workflows` enumeration surface and API-configurability of
  `default_workflow` (`api-configurable-keys.json`, the console
  Settings surface) — deferred because no consumer exists; reconsidered
  when `console-control-plane-primitives` enumerates dispatcher keys.
- A second variant shipped INSIDE the plugin bundle — deferred because
  no driver exists (per-node model choice is already `acp_nodes`);
  reconsidered when a graph-shape variant is actually requested.
- Migrating the three fleet forks (console → `fabro_sandbox_image`;
  homelab and openbrain → drop the fork or register it) — deferred to
  those repos' owners; this plan's handoff routes the observation.

## Unrelated prior work

`plan/archive/fabro-on-hp/` remains closed and untouched. The closed
`bd-ib-6pl3in` (Codex ACP worker workflow variant, 2026-06-23)
parameterized the adapter INPUT rather than adding a graph variant; it
is the ancestor of the adapter contract, not of this registry.
