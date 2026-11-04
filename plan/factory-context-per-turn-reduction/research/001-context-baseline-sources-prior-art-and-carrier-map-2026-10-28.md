## The maintainer's statement of what done means

The maintainer wants factory spend under control. Factory context per turn is a median of about 156-220k input tokens on every node except disposition; it was 97% of Codex tokens, the Codex weekly allowance was gone in 27 hours and paid credits fell from 26,026 to 212 in 13 hours, and on Claude Sonnet 5.5 the same context drains the Anthropic weekly limits and holds the factory to 4 concurrent runs. Reduce the context each factory node carries per turn, whichever provider serves it. (Commissioning brief from plan token-spend-analysis, 2026-10-28; the derived assertions below were not confirmed in a dialogue.)

## Definition of Done assertions derived from that statement

- A per-node baseline exists of the median input tokens per factory model response, for each Fabro node (implement, fix, review, review_fix, proof_capture, proof_verify, dod_gate, disposition), measured by one stated method (Honeycomb llm-spend, input plus cache read plus cache creation per response, deduplicated by message id, grouped by Fabro node, over a named window) on the factory's current model routing, and a per-component breakdown of one request per node (system prompt, tool definitions, skills, plugins, MCP tools, instruction files, goal, transcript) is recorded beside it.
- After the change, over a window of the same length and measured by the same method, the median input tokens per factory model response is at most 100,000 on every node.
- A factory node's sandbox loads only the skills, plugins, MCP tools and instruction files that node declares: a run's per-node request breakdown lists no skill, plugin, MCP tool or instruction file the node's declaration omits, and a node that declares none loads none.
- Against the baseline window, no factory node's accepted-first-pass rate falls and no node's fix-loop count rises, per node.
- One table is published for the plan, with a row per node and the columns node, median before, median after, delta, p90 before, p90 after, and beneath it the fleet-total tokens per accepted item before and after.

# 001 - Factory context per turn: measured baseline, context sources, prior art, carrier map

Written 2026-10-28 by a session commissioned from livespec-dev-tooling plan `token-spend-analysis`
(epic `livespec-dev-tooling-6lv7ze`). Commissioning only: no child is filed and nothing is dispatched.

## Why this plan exists

Factory spend has to come under control. Token-spend-analysis measured on 2026-10-28
(`/home/ubuntu/token-spend-report/reports/2026-10-28-anthropic-burn-mitigation-resteer.md`, recorded here as
`plan/anthropic-burn-mitigation/research/002-token-spend-analysis-resteer-2026-10-28.md`):

- Every factory node except `disposition` re-reads a median 156k-220k input tokens per model response. Output is
  under 5% of cost (about 270 output tokens per response). Factory Codex was 97% of Codex tokens from
  2026-10-26 22:00Z.
- The Codex weekly allowance went from 1% to 100% in 27 h; paid credits fell from 26,026 to 212 in 13 h.
- The factory now runs Claude Sonnet 5.5 on the Anthropic subscription (commit 98687ff1 in livespec-dev-tooling),
  and the same per-turn context now drains the Anthropic weekly limits; the factory is throttled to 4 concurrent
  runs because of it.

The lever is therefore PROVIDER-AGNOSTIC: cut the context each turn carries, whichever model serves it. It
has no owner today. `anthropic-burn-mitigation` (epic `bd-ib-b2jzxw`) owns judge-side isolation and a few
interactive-seat items; this plan owns the factory node side and links to it. Neither plan's assertions are
rewritten by the other.

## Measured baseline (Codex routing, last 24 h to 2026-10-28 ~00:30Z)

Source: Honeycomb `llm-spend`, query https://ui.honeycomb.io/thewoolleyweb/environments/livespec/datasets/llm-spend/result/5muNH47Qfh1
(medians valid; the totals in that query double-count re-attributed responses and are not quoted).
Unit: input tokens per model response (input + cache read + cache creation), grouped by Fabro node.

| Node | Responses | Median input | P90 input |
|---|---:|---:|---:|
| implement | 14,040 | 192,519 | 235,783 |
| proof_capture | 2,372 | 219,665 | 239,873 |
| review_fix | 1,993 | 182,268 | 234,556 |
| fix | 1,915 | 156,402 | 233,798 |
| review | 1,461 | 213,503 | 235,390 |
| proof_verify | 694 | 215,910 | 225,949 |
| dod_gate | 340 | 206,432 | 220,011 |
| disposition | 13 | 30,842 | 34,878 |

Caveats the plan's first child must close, because the DoD cannot be graded against them as they stand:

1. This baseline is on the CODEX routing (gpt-5.6-terra at high effort, 86% of factory tokens). The factory is now on
   Claude Sonnet 5.5. Tokenizer, caching accounting and the harness's own prelude differ per provider, so the Codex
   figures are a prior, not the baseline. DoD assertion (a) re-measures per node on the CURRENT routing.
2. The P90 is bunched against about 235k on every node, which is the signature of a ceiling (a context window or a
   compaction threshold), not of task-specific variation. The median sits only 20-45k under it. Treat the floor
   as the problem, not the tail.
3. `disposition` (median 30.8k) is the control: it is the only node whose context is small, and it is the node whose
   prompt was bounded explicitly (`bd-ib-7zxqyl`, Petri). Whatever it omits that the others carry is the first
   suspect set.

Judge-side reference (`claude -p` in this checkout, same report section 1): median about 140k-150k, unchanged by
`bd-ib-qksrl6`; P90 fell 440k to 152k. That the judge's FLOOR is also about 140k is evidence the floor is harness
overhead, not task text.

## What feeds a node's context (survey, 2026-10-28; read-only, not yet measured per component)

Sizes are on-disk bytes; at roughly 4 bytes per token.

1. Node prompt, per node: `.claude-plugin/.fabro/workflows/implement-work-item/prompts/*.md` -
   implement 27.5 KB, fix 16.8 KB, review 25.9 KB, review-fix 8.9 KB, dod-gate 20.4 KB, proof-capture 39.4 KB,
   proof-verify 29.5 KB, disposition 6.8 KB. That is 2k-10k tokens: about 3-5% of the floor. Not the floor; but
   proof-capture and proof-verify are the largest and are worth trimming for their own sake.
2. The rendered goal/brief, `commands/_dispatcher_goal.py::render_goal` (item description, comments, lessons). Per run,
   variable, and already carries size advisories (spec v192, "rendered-goal-reach-and-size-advisories"). Its size is
   not in the telemetry today, so its share is unknown.
3. The governed repository's instruction file, loaded by the agent harness from the sandbox checkout. This
   repository's own `AGENTS.md`/`CLAUDE.md` is 147,088 bytes (about 37k tokens) in one file; fleet siblings range
   from 41 KB to 166 KB (vps-info 166 KB, livespec 93 KB, console 52 KB). On a factory node whose target repo is
   this one, that single file is a large part of the per-turn floor, on every turn, and only the nodes that need
   a given section need it. Not yet measured.
4. Skills, plugins and MCP tools the sandbox's agent loads. The Codex spans carry `render_available_skills`,
   `plugins_for_config`, `append_mcp_tools` and `agents_md.refresh` on every turn (report section 7), consistent with
   the full catalogues entering every node. The sandbox plugin cache is populated by the plugin-cache prepare gate
   (`commands/_dispatcher_plugin_cache_gate.py`) and `harness_settings_prepare_steps_block`; neither declares a
   per-node subset, and `workflow.toml` / `workflow.fabro` have no per-node skills/plugins/MCP/instruction-file
   declaration at all (grep for skill, mcp, AGENTS, project_doc found only comments). Unverified: the overlay is
   assembled by `commands/_dispatcher_overlay.py` (460 lines) from about 25 `*_prepare_steps_block` helpers.
5. The review-context assembly for `review`, `review_fix`, `proof_verify` and `dod_gate`: diff, PR state, item
   record, spec clauses. Not surveyed beyond the prompts; child C3 owns its measurement.
6. Conversation accumulation within a run: a node that takes many turns re-reads its own transcript. Largely
   cached, but it counts as input. The 14,040 `implement` responses suggest long tool loops; reducing turns is
   a legitimate lever but a separate one from the floor.

The honest status: items 3 and 4 are the leading suspects by size and by the span evidence; none of the six has
been measured per component for a factory node. The plan's first child (C1) produces that decomposition, exactly as
the token-spend report recommended for the judge ("record one invocation's request size broken down by component").

## Prior art in the ledger (queried with `bd list --status all --limit 0 --json`, 1,720 items)

| Item | Status | Relevance |
|---|---|---|
| `bd-ib-qksrl6` | closed | Bounded each spec-stated judgement prompt to the clauses it needs (the earlier 200k/1 MB prompt cap). Removed the 440k tail, left the ~140k floor. Judge side only. |
| `bd-ib-k5qp5z` | closed | Reuses a governing-heading verdict across a spec revision that leaves its clauses unchanged. Call-volume lever, judge side. |
| `bd-ib-w4hqe2` | acceptance | Host judgements launch without the interactive agent setup (hooks, plugins, MCP, instruction files). The isolation METHOD this plan generalises to factory nodes; its DoD wording is the template for assertion (c). |
| `bd-ib-a3aqie` | active | Re-lands that isolation (Codex: zero project-instruction byte budget, skills and multi-agent disabled; Claude: no setting sources, empty strict MCP, no slash commands, no session persistence). Directly reusable flags for factory nodes. |
| `bd-ib-jp2qr2` | ready | Bounds a host DoD judgement's TOTAL input at 100,000 across requests. Judge side; same 100k figure this plan adopts per factory response. |
| `bd-ib-qy6v2h` | ready | Stops projecting `CLAUDE_CODE_OAUTH_TOKEN` into sandboxes whose graph routes no node to Claude. Sandbox analogue of isolation; closes an unattributed spend path. Overlaps the overlay code this plan edits. |
| `bd-ib-7zxqyl` | closed | Bounded the disposition stage's prompt to its adapter's window on Petri. Explains why `disposition` is the small node; read it for the technique. |
| `bd-ib-b2jzxw` | backlog | Epic of `anthropic-burn-mitigation`. Link, not parent. |
| `bd-ib-dbqb`, `bd-ib-bb41.9`, `bd-ib-cewr.3` | closed | Sandbox plugin cache / registry faults. Read before touching plugin materialization: a per-node plugin subset must not reintroduce a registry-mid-run drift. |
| `livespec-dev-tooling-pjdpwb` | (other tenant) | Concurrency as budget control (Codex allowance panel and trigger). Complementary: it bounds how many turns run at once; this plan bounds what each costs. |

No item in the ledger owns factory per-node context. A search of titles for "context per", "input tokens",
"skill/plugin/MCP loaded in sandbox" returns only the items above.

## Design stance (defaults recorded, none yet ruled on by the maintainer)

- Measure first, cut second, per component, per node. No reduction is claimed from an inference.
- Cut by declaration: a node declares the skills, plugins, MCP tools and instruction files it needs; everything
  else is absent from its sandbox. Absence, not instruction ("do not read X") - an item the harness lists still
  costs its catalogue entry.
- Instruction files are the likeliest big win and the riskiest: a node that needs a repo rule today may be reading
  it from AGENTS.md. The mechanism is a per-node instruction EXCERPT, reached only after C1 shows which sections
  each node actually reads.
- Quality is a gate, not an afterthought: assertion (d) compares accepted-first-pass rate and fix-loop count per
  node against a baseline window, so a cheaper-but-worse node fails the plan.
- Provider-agnostic: the 100k bound is graded on whichever provider currently serves the node.
- The bound of 100k per response is the maintainer's figure, matching the judge bound in `bd-ib-jp2qr2`.

## Proposed carrier map (children NOT yet filed; ids assigned when filed under the scoping event)

Assertions are those in the epic's `## Definition of Done`, in order: (a) per-node baseline, (b) median at most 100k,
(c) declared-only sandbox loading, (d) no quality regression, (e) before/after table and tokens per accepted item.

| Proposed child | Scope | Carries |
|---|---|---|
| C1 | Baseline harness: one stated method (Honeycomb `llm-spend`, grouped by Fabro node, dedupe by message id, per-node median and p90 over a named window) on the current Sonnet 5.5 routing, plus a one-run per-component breakdown of a request (system prompt, tool defs, skills catalogue, plugins, MCP, instruction files, goal, transcript) for every node. Also records the accepted-first-pass rate, fix-loop count and tokens-per-accepted-item for the baseline window. Makes the fixed method reproducible by a script in the repo. | (a), baseline half of (d), (e) |
| C2 | Per-node declaration in the workflow (skills, plugins, MCP tools, instruction files) and the dispatcher overlay that materialises ONLY that set into the node's sandbox; reuse the `a3aqie` isolation flags for both agents. Includes the plugin-cache interaction with `bb41.9`/`cewr.3`. | (c) |
| C3 | Instruction-file reduction for factory nodes (per-node excerpt or trimmed delivery of the governed repo's AGENTS.md/CLAUDE.md), and trimming of the two largest node prompts (proof-capture, proof-verify) and the review-context assembly. | (b) |
| C4 | Goal/brief size: put the rendered goal's size per node into the run telemetry, then bound it. | (b), (a) |
| C5 | Per-node regression guard: a node-level check that fails the dispatcher's release when a node's declared set grows past a stated token budget (keeps (b) from regressing silently), plus the accepted-first-pass / fix-loop comparison. | (d), (b) |
| C6 | Coordination with `bd-ib-qy6v2h`, `bd-ib-a3aqie`, `bd-ib-w4hqe2`: an explicit link or carrier so the three isolation items and C2 do not edit the overlay in conflicting ways. | (c) |
| plan-level proof | After-window measurement, the (e) table and tokens per accepted item before/after, attested by a separate replaying session. | (b), (d), (e) |

Ordering: C1 first (nothing is cut before the floor is decomposed), then C2 and C4 in parallel, C3 informed by C1,
C5 last. Deferred explicitly: (i) cheaper-model trials per node (report section 8) - a model lever, owned elsewhere
(`anthropic-burn-mitigation`), reconsidered after C1 so effects are not confounded; (ii) concurrency caps -
`livespec-dev-tooling-pjdpwb`; (iii) reducing turns per run - reconsidered after the floor is known.

## Defaults the commissioning session chose (maintainer may re-word on first resume)

- The slug `factory-context-per-turn-reduction`, a sibling of `anthropic-burn-mitigation` and not a widening of it.
- The five DoD assertions are session-derived from the commissioning brief, not confirmed in a dialogue.
- Every assertion is `host_captured` (the plan default); none is `human_attested`.
- The median (not p90) is the graded statistic for the bound, per the brief; p90 is reported in the table.
- The baseline window is to be named by C1 and is NOT the 24 h Codex window above.
