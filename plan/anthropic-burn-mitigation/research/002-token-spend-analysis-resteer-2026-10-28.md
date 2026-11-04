<!-- Recorded verbatim from plan token-spend-analysis (livespec-dev-tooling, epic livespec-dev-tooling-6lv7ze), report /home/ubuntu/token-spend-report/reports/2026-10-28-anthropic-burn-mitigation-resteer.md, at the maintainer's direction. This plan's dispositions of each suggestion are in the scope event on bd-ib-b2jzxw that cites this note. -->

# Research report: re-steering anthropic-burn-mitigation from measured spend

- **For:** plan `anthropic-burn-mitigation` (livespec-orchestrator-beads-fabro, epic `bd-ib-b2jzxw`), to be recorded as a research note in that plan and folded into its goals and Definition of Done where the plan's owner judges it fits.
- **From:** plan `token-spend-analysis` (livespec-dev-tooling, epic `livespec-dev-tooling-6lv7ze`), session 54dcfe2a, at the maintainer's request.
- **Written:** 2026-10-28 ~00:45Z.
- **Evidence base:** the livespec Honeycomb `llm-spend` dataset (board `abHcUYvjaYf`). Every figure below links to the query that produced it. USD figures are API list-price equivalents; billing is subscription quota.

## Summary

1. The plan has removed the judge's worst case. The 90th-percentile context per spec-stated judge response fell from about 440k to about 152k tokens. The **median did not move** (about 140–150k), so the plan's own "at most 100,000 input tokens per judgement" assertion is not yet met.
2. The plan's baseline figure (median 875,054) is a counting artefact and should be restated from Honeycomb.
3. Judge spend per hour fell about 85–90%. That figure mixes three causes: smaller prompts, fewer calls, and a model switch made outside the plan. As written, the headline assertion could pass without any context reduction.
4. The largest token lever in the fleet, factory Codex context per turn (about 195k on every node), is outside this plan's scope and has no owner. It burned the week's Codex allowance in 27 hours and most of the paid credits in the next 13.

## 1. What the plan has achieved so far

Context per response for headless `claude -p` in the orchestrator checkout (`spend.consumer = "claude -p: -data-projects-livespec-orchestrator-beads-fabro"`; context = input + cache read + cache creation; corrections excluded):

| Period | Sessions | Responses | Median context | P90 context | USD | USD per hour |
|---|---:|---:|---:|---:|---:|---:|
| Before `bd-ib-qksrl6` (2026-10-25 15:37Z to 10-27 02:43Z, 35.1 h) | 396 | 757 | 140,766 | 439,610 | $856.89 | ≈ $24.40 |
| `qksrl6` to `bd-ib-k5qp5z` (to 10-27 22:15Z, 19.5 h) | 78 | 86 | 148,756 | 152,449 | $66.02 | ≈ $3.40 |
| After `k5qp5z` (to ~10-28 00:30Z, ~2.3 h, thin sample) | 11 | 20 | 138,866 | 151,275 | $4.80 | ≈ $2.10 |

Query: https://ui.honeycomb.io/thewoolleyweb/environments/livespec/datasets/llm-spend/result/pcwy795Pci1

- **The ~440k mega-prompt is gone.** Bounding each judgement to the clauses it needs (`qksrl6`) removed the tail where the judge re-read the whole spec. One residual spike remains around 05:30Z on 10-27; it is worth identifying.
- **The median, about 140–150k, is untouched.** It looks like fixed overhead per call, not spec text (see §3).
- **Assertion status:** "Each spec-stated behaviour judgement sends at most 100,000 input tokens" is **not met**. It is about 40–50% over per response, and a session can carry more than one response.

## 2. Restate the baseline

The plan's DoD cites a 2026-10-26 median of **875,054** input tokens per judgement. That figure came from a transcript scan that was not deduplicated: Claude Code writes one response as several records repeating the same `usage` (livespec-dev-tooling `.ai/claude-transcript-usage-dedupe.md`). Deduplicated by `message.id`, the median was about **438k**, which matches Honeycomb's pre-`qksrl6` P90 of 439,610.

**Suggested change:** restate the baseline from Honeycomb, and say what unit the assertion grades. The DoD promises a bound **per judgement**. A judgement can span more than one model response, so measure it as the sum per `session.id`, not per response row.

## 3. Prioritise judge isolation (`bd-ib-a3aqie`) over more clause trimming

The ~140k floor is the remaining cost of every judgement. It most plausibly comes from what a headless `claude -p` loads before the prompt: the checkout's CLAUDE.md, enabled plugins and skills, and MCP tool definitions. This is an inference I have not verified. `bd-ib-a3aqie` ("re-land host judge isolation so each candidate runs without the interactive agent setup") is the item aimed at exactly that.

**Suggestions:**
- Land `a3aqie` before `bd-ib-jp2qr2` (DoD-grading total bound) and before any further clause work. Its effect should show directly as the median dropping.
- Before landing it, record one judge invocation's request size broken down by component (system prompt, tool definitions, project memory, prompt). The plan then knows what the floor is made of rather than inferring it.
- Add a DoD assertion of the form: "With its spec clauses removed, a spec-stated judgement's request carries at most N tokens of fixed overhead." That keeps isolation from regressing silently.

## 4. Separate the causes of the spend drop

Judge spend fell from about $24.40 to about $2–3 per hour. Three things changed in the same window:

1. **Smaller prompts** (`qksrl6`): visible only in the P90.
2. **Fewer calls:** sessions fell from about 11 to about 4 per hour. Some of that is verdict reuse (`k5qp5z`, and `bd-ib-onrjh3` once it lands) and some is fleet activity.
3. **A model switch:** coordinator rulings R47/R66 moved host judges from claude-opus-4-8 to sonnet-5.5 and haiku-5.5 through environment variables, independently of this plan.

The DoD's headline, "total Anthropic spend at most 40% of the 2026-10-26 baseline", could be met by cause 3 alone while context per judgement barely moved.

**Suggestions:**
- Keep the spend assertion, but make the context and volume assertions independently gradeable. Report each with its own measured value at proof time.
- Per-caller attribution is needed to read any of this per judge type. Four orchestrator modules share the spec-stated prompt (`_drift_run_judge`, `_dod_governing_heading_judge`, `_spec_stated_citation`, `_ledger_intent_scan`). Their producer half is `livespec.caller` via `OTEL_RESOURCE_ATTRIBUTES` on every `claude -p` spawn. The consumer half is livespec-dev-tooling `livespec-dev-tooling-iznup7` (`spend.caller`, plus a board panel). This plan is the natural owner of the producer half.

## 5. Model choice where factory Claude runs

- Factory Claude currently runs **opus-5**, at $5 input / $0.50 cached / $25 output per million tokens. Since 2026-10-27 09:00Z: 1,373 responses, about 302M tokens, $191.20, all billed to anthropic-4.
- Claude Sonnet 5.5 is $2 / $0.20 / $10. Third-party comparisons put it ahead of GPT-5.6 Terra on most shared benchmarks (Vals AI: 17 of 19). There is no vendor-published Sonnet 5.5 figure, so treat that as directional.

**Suggestion:** default factory Claude nodes, and any judge that stays on Claude, to Sonnet 5.5 unless a node shows a measured quality need for Opus. Grade it on accepted-first-pass and fix-loop counts per item.

## 6. Coordinate with `bd-ib-qy6v2h`

`bd-ib-qy6v2h` (filed 2026-10-27; ready) stops projecting `CLAUDE_CODE_OAUTH_TOKEN` into sandboxes whose graph routes no node to Claude. It is the sandbox analogue of `a3aqie`'s isolation, and it closes an unattributed spend path. On 2026-10-27 15:00–18:00Z, anthropic-4 dropped 36 points of 5-hour quota, about $215 at its measured $5.96 per point. Honeycomb shows only $72.05 of Claude Code cost across all accounts in that window. All 44 factory dispatches then were Codex-only, yet each held a live anthropic-4 token. The maintainer reports no Anthropic use outside the fleet, so that consumer is still unidentified. It fits this plan's goal and deserves a carrier or an explicit link.

## 7. Out of this plan's scope, but where most tokens go: factory Codex context per turn

Median input tokens per factory Codex response by Fabro node, last 24 h to ~10-28 00:30Z (medians are valid; totals in this query double-count re-attributed responses and are not quoted):

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

Query: https://ui.honeycomb.io/thewoolleyweb/environments/livespec/datasets/llm-spend/result/5muNH47Qfh1

What it cost:
- **Share of Codex:** factory Codex was 97% of Codex tokens from 2026-10-26 22:00Z (5.26B of 5.42B; $2,036 list).
- **Mix:** gpt-5.6-terra at high effort is 86% of factory tokens. Output is under 5% of cost: about 195k input against about 270 output tokens per response.
- **Weekly allowance:** the allowance (1% to 100%) went in **27 hours**, 06:55Z on 10-26 to 09:55Z on 10-27, on $1,849 of API-equivalent usage. The factory was 90.7% of that.
- **Credits:** paid credits then fell from 26,026 to 212 between 10:02Z and 23:13Z (about 1,980 per hour).
- **Concurrency:** it rose from about 5 to 15–20 dispatches on the evening of 10-26.

Every node except `disposition` re-reads about 156–220k tokens per turn. That suggests a large fixed load per turn, not task-specific context. The Codex spans show `render_available_skills`, `plugins_for_config`, `append_mcp_tools` and `agents_md.refresh` on every turn, which is consistent with full skill, plugin and tool catalogues entering every node. This is unverified.

**Suggestion:** this plan's isolation method (measure the fixed floor, strip what a caller does not need, re-measure) applies directly. Either widen this plan's scope to include factory Codex context per node, or open a sibling plan and link it. Candidate assertions:
- Median input per factory Codex response is at most a stated bound per node, for example 100k.
- A node's sandbox loads only the skills, plugins and MCP tools that node declares.

## 8. Cheaper models for low-risk factory nodes

Published benchmarks put GPT-5.6 Luna 1–3 points behind Terra on coding: SWE-bench Pro 62.7% vs 63.4%; Artificial Analysis coding-agent index 74.6 vs 77.4. Luna is exactly one tenth of Terra's price on every token class: $0.20 / $0.02 / $1.20 against $2 / $0.20 / $12. A trial on `dod_gate`, `proof_capture` and `disposition`, compared against Terra on pass rate and tokens per merged item, would show whether that gap shows up as rework in this fleet. Effort level barely matters for cost here, because output is under 5% of it.

## 9. Concurrency as a budget control

Codex usage scaled with concurrency, not with per-run cost. Setting the factory cap belongs to the coordinator (gitops-fleet-capacity-monitoring). It now has a live signal for it:
- **Panel:** "Codex allowance and paid credits" on board `abHcUYvjaYf`, from `kind = codex-allowance` events in `llm-spend`, every 5 minutes.
- **Trigger:** "token-spend Codex credits low" (below 4,000 credits).
- **Tracking:** livespec-dev-tooling `livespec-dev-tooling-pjdpwb`.

## Suggested changes to the plan, in one list

1. Restate the 875,054 baseline as the deduplicated ~438k (Honeycomb P90 439,610), and grade per judgement session (§2).
2. Order `bd-ib-a3aqie` before `bd-ib-jp2qr2`, and add a fixed-overhead assertion (§3).
3. Make context, call volume and model choice separately gradeable, so the spend headline cannot pass on the model switch alone. Own the `livespec.caller` producer half (§4).
4. Default remaining Claude judges and factory Claude nodes to Sonnet 5.5, with a measured exception path (§5).
5. Link or carry `bd-ib-qy6v2h` (§6).
6. Widen the scope to factory Codex context per node, or open a linked sibling plan (§7).
7. Optional: a Luna trial on low-risk nodes (§8).
