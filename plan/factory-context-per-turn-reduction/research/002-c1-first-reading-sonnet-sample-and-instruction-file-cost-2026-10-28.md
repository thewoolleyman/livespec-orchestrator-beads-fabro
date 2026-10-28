# 002 - C1 first reading: the Sonnet 5.5 sample is too thin, the Anthropic floor is higher, and the instruction file costs 54.6k tokens

Written 2026-10-28 ~05:20Z by the session driving this plan (`factory-context-per-turn-reduction`) for child C1
(`bd-ib-iljsyl`). This is a partial reading. It does not discharge C1: the per-node Sonnet 5.5 baseline cannot be
taken yet, for the reason in section 1.

## 1. Factory traffic since the routing switch is mostly not Sonnet 5.5

The routing commit is `182415ed7`, "route every factory node and the ratification reviewer to Claude Sonnet 5.5". It
landed 2026-10-28T00:09Z. That is about 50 minutes after the 23:20Z the commissioning brief gave.

The query below counts Honeycomb `llm-spend` rows with `node` set, from 2026-10-27T23:00Z to 05:10Z, broken down by
model and by `spend.correction`. Query: https://ui.honeycomb.io/thewoolleyweb/environments/livespec/datasets/llm-spend/result/3RDvYNEgLFs

| Model | Source | Rows (no correction) | Work items | Last response |
|---|---|---:|---:|---|
| gpt-5.6-terra (plus `pending` rows later restated as terra) | codex-app-server | 1,476 + 99 | 7 | 02:55Z |
| opus-5 | claude-code | 251 | 2 | 02:22Z |
| sonnet-5.5 | claude-code | 18 | 1 | 01:55Z |

So in the window the plan was told to measure, the factory served Sonnet 5.5 on 18 responses, for one item, all on
`proof_capture`. Codex Terra and Opus 5 kept serving runs that were already in flight. Factory traffic stopped at
about 02:55Z, when dispatch was held for the E2BIG launch bug. **No per-node Sonnet 5.5 baseline can be measured
until the factory resumes on that routing.** C1 waits for that, and for a window long enough to cover every node.

## 2. Anthropic responses carry much more context than Codex responses

These medians and p90s are for the same window. They count input + cache read + cache creation per row, and exclude
rows marked `spend.correction = retract`. Query: https://ui.honeycomb.io/thewoolleyweb/environments/livespec/datasets/llm-spend/result/qgF1oak3Hwh

| Node | Model | Responses | Median input | P90 input |
|---|---|---:|---:|---:|
| implement | opus-5 | 95 | 755,346 | 794,671 |
| review | opus-5 | 45 | 497,013 | 527,760 |
| review_fix | opus-5 | 81 | 406,219 | 543,464 |
| fix | opus-5 | 14 | 364,603 | 377,072 |
| proof_capture | sonnet-5.5 | 17 | 381,523 | 401,575 |
| implement | gpt-5.6-terra | 509 | 202,750 | 238,549 |
| fix | gpt-5.6-terra | 362 | 164,497 | 219,332 |
| proof_capture | gpt-5.6-terra | 164 | 220,113 | 240,780 |

On Codex, the p90 bunched near 235k. That bunching was the signature of a compaction threshold (note 001, caveat 2).
The Anthropic nodes show no such ceiling. Their medians are 2-4 times the Codex medians, and Opus `implement` sits
near 755k. The likely reason is that Claude nodes run with a much larger context window and compact later, so a
long tool loop keeps its whole transcript. If Sonnet 5.5 behaves like Opus 5 here, the per-turn problem is worse
than the Codex figures suggest, and the transcript component (note 001, item 6) is a bigger share than assumed.
Section 1 says why this is not yet measured on Sonnet.

Method caveat: `llm-spend` has no message-id column. Duplicate rows are handled with the `spend.correction`
markers: a `retract` row withdraws an earlier row, and a `restate` row re-issues it with the real model. Without a
message id, a retracted row cannot be paired with the row it withdraws, so a few duplicate rows remain in these
medians. A median moves very little from a few duplicates, but a total would not be reliable. The DoD says
"deduplicated by message id", and C1 has to either add that id or restate the method as this marker rule.

## 3. Instruction-file cost, measured: this repository's AGENTS.md costs about 54,600 tokens per request

The probe ran `claude -p "Reply with the single word ok." --model sonnet --output-format json`, with an empty
strict MCP config, in three scratch git repositories on this host:

| Probe | Repository contents | input + cache read + cache creation |
|---|---|---:|
| a | empty | 26,250 |
| b | `AGENTS.md` (147,088 bytes) + `CLAUDE.md -> AGENTS.md` | 80,900 |
| c | b + `.claude/CLAUDE.md -> ../AGENTS.md` | 80,907 |

- One copy of this repository's instruction file adds **54,650 tokens** to every request on the Claude tokenizer.
  That is about 2.7 bytes per token, not the 4 assumed in note 001, so the 37k figure understated it by about half.
- This repository links both `CLAUDE.md` and `.claude/CLAUDE.md` to the same file, and Claude Code loads that file
  **once** (b and c are equal). There is no double load to fix.
- Probe a's 26,250 tokens is this host's interactive setup: the system prompt, tool definitions, user-level skills
  and plugins, and the global `~/.claude/CLAUDE.md`. It is not a sandbox measurement. A sandbox's equivalent has to
  be read from a factory run (C1, assertion 2).

What this means for C3: a factory node whose sandbox loads the governed repository's `CLAUDE.md` pays 54.6k tokens
per response for this repository's file alone. Against a 100k bound per response, that is more than half the
budget before the goal, tools or transcript are counted. This holds whether or not the node's sandbox loads
anything else. Whether factory sandboxes actually load it, and on which nodes, is the next measurement: it needs a
factory run dump on the Sonnet routing, which section 1 says does not exist yet.

## Next

1. Wait for the factory to resume on the Sonnet 5.5 routing. petri-factory-on-gmktec owns that. Then measure
   per-node medians over a named window that covers every node, and take one run dump per node for the component
   breakdown.
2. C3 quick win: ask the maintainer in the plan's pane whether to rewrite AGENTS.md. Section 3 is the evidence.
