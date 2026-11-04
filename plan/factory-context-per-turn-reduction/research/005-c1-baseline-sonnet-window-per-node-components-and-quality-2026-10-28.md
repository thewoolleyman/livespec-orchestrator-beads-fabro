# 005 - C1 baseline: per-node context on the Sonnet 5.5 routing over a named window, the per-request component split, and the quality baseline

Written 2026-10-28 ~15:40Z by the session driving this plan. This note is the graded deliverable for child C1
(`bd-ib-iljsyl`). It covers all three of that child's Definition-of-Done assertions in one place. Notes 003 and 004 are
its inputs and remain the detailed record. This is the BEFORE baseline: `bd-ib-coxsfu` (prepare-step scripts out of
the agent preamble) had not dispatched when this window closed.

## 1. Per-node input tokens per model response (assertion 1)

**Window:** responses sent from 2026-10-27T23:20Z to 2026-10-28T14:30Z. Every factory agent node in it ran
`claude-sonnet-5-5`. Twelve work-items and sixteen dispatches contributed.

**Instrument:** Honeycomb `llm-spend` in the `livespec` environment. Per row,
`ctx_in = input_tokens + cache_read_tokens + cache_creation_tokens`, which is one response's whole input.

**Filters:**

- `spend.model = sonnet-5.5`;
- `kind = factory-claude-response`;
- `node` is one of the eight Fabro agent nodes;
- `spend.correction != retract`.

Query: https://ui.honeycomb.io/thewoolleyweb/environments/livespec/datasets/llm-spend/result/wu3NFpv84A8

| Node | Responses | Work items | Median `ctx_in` | P90 `ctx_in` | Max |
|---|---:|---:|---:|---:|---:|
| implement | 703 | 11 | 459,936 | 631,492 | 830,365 |
| proof_capture | 373 | 10 | 381,970 | 409,631 | 430,823 |
| fix | 234 | 3 | 402,717 | 515,233 | 531,328 |
| review | 199 | 10 | 383,067 | 415,118 | 493,546 |
| proof_verify | 117 | 9 | 365,482 | 386,414 | 392,345 |
| dod_gate | 78 | 12 | 344,773 | 353,894 | 358,847 |
| review_fix | 74 | 4 | 398,802 | 454,932 | 456,964 |
| disposition | 16 | 6 | 107,814 | 357,148 | 359,461 |
| **All nodes** | **1,794** | **12** | **388,571** | **574,041** | **830,365** |

`disposition`'s p90 comes from a few responses that ran before `bd-ib-7zxqyl` put that node at `summary:medium`
fidelity. Its median is the post-change value.

**Cross-check against a different instrument.** Note 004 read ACP `usage_update` events from `fabro dump` exports of
six runs in the same window. The two instruments agree within 5% on every node they share:

- `dod_gate`: 343,550 in note 004, 344,773 here;
- `implement`: 445,815 in note 004, 459,936 here;
- `review`: 381,278 in note 004, 383,067 here;
- `disposition`: 100,429 in note 004, 107,814 here.

**Method notes**, because each of these silently produced a wrong answer before it was fixed:

1. **The model value is `sonnet-5.5`, not `claude-sonnet-5-5`.** Filtering on the API model id returned zero rows
   with no error. A control query broken down by `spend.model` and `node` gave the real value.
2. **`kind = factory-claude-response` is required.** The `llm-spend` dataset also holds `factory-node-tokens` rows from
   `source = node_join`. Each of those is a whole node visit's total, up to 53.7M tokens. Without this filter they put
   the p90 for `proof_verify` at 2.14M and for `dod_gate` at 1.36M.
3. **Duplicates are handled by marker, not by message id.** `llm-spend` has no message-id column. A `retract` row
   withdraws an earlier row, and a `restate` row re-issues it with the real model and node. Excluding `retract` is the
   method note 002 used. So "deduplicated by message id" in the original Definition of Done is carried out by this
   marker rule.

## 2. What one request carries, per component (assertion 2)

**The request:** the first request of each agent node's session, before the node has done any work. Its transcript is
therefore empty. Observed values, from note 003 (ACP `usage_update`, three runs):

| Node | First request |
|---|---|
| dod_gate | 337,843 - 338,078 |
| implement | 341,518 - 341,754 |
| review | 349,841 - 359,626 |
| proof_capture | 357,297 - 370,586 |
| proof_verify | 351,211 - 360,984 |
| disposition | 100,203 |

| Component | Tokens | How measured |
|---|---:|---|
| System prompt (harness base) | 3,890 | `claude -p --model sonnet --output-format json` in an empty git repository, with `--strict-mcp-config` and an empty MCP config, `--tools ""` and `--disable-slash-commands`. Probe run 2026-10-28 ~15:30Z. |
| Tool definitions | ~21,160 | The same probe with the default tool set: 25,053 total. Subtract the 3,890 system-prompt probe. |
| Skills | 0 | The same probe with skills enabled and tools off read 3,890, the same as with skills disabled. The sandbox ACP session lists 23 built-in commands and no plugin skills (note 003). |
| Plugins | 0 | No plugin is installed in the sandbox session (note 003). |
| MCP tools | 0 | The sandbox ACP session has no MCP server (note 003). |
| Instruction files (`CLAUDE.md` -> `AGENTS.md`) | ~54,650 | Note 002, section 3: the probe in a repository holding this `AGENTS.md`, minus the empty-repository probe. |
| Goal and node prompt | ~10,000 - 20,000 | Goal text 11,534 characters; node prompts 7 - 40 KB (note 003). |
| Fabro `compact` preamble (the 46 Dispatcher prepare-step scripts) | ~241,400 | Rebuilt from `run.json` and measured with one `claude -p` probe (note 003, section 3). This is the component `bd-ib-coxsfu` removes. |
| Transcript | 0 on the first request | Grows within a session. The `implement` median of ~460k minus its ~342k floor is ~118k of transcript. Its p90 of ~631k is ~290k. |

The first-request components sum to about 331k - 341k. That brackets the observed `dod_gate` and `implement`
first requests. `disposition` lacks only the preamble, and its 100,203 is about what the remaining components add up to.

## 3. Quality baseline for the window (assertion 3)

**Instrument:** the per-response rows of section 1, grouped two ways.

- By `work.item.id`, with
  `tok_all = input_tokens + cache_read_tokens + cache_creation_tokens + output_tokens` summed and
  `livespec.dispatch.id` counted distinct. Query: https://ui.honeycomb.io/thewoolleyweb/environments/livespec/datasets/llm-spend/result/aKS7JgJrQfA
- By `node`, with `session.id` counted distinct. Query: https://ui.honeycomb.io/thewoolleyweb/environments/livespec/datasets/llm-spend/result/Gi3dFUQrH4d

Outcomes were read from the ledger at ~15:35Z with `bd list --status all`. `run_id` is empty on these rows, so the
dispatch id stands in for the run.

| Work item | Dispatches | Tokens (all) | Ledger outcome at 15:35Z |
|---|---:|---:|---|
| bd-ib-weje2m | 1 | 157,995,186 | closed, PR #3853 merged |
| bd-ib-jp2qr2 | 2 | 113,471,517 | active |
| bd-ib-57ss2n | 1 | 109,715,271 | active |
| bd-ib-4jdgcw | 2 | 92,387,406 | closed, PR #3849 merged |
| bd-ib-onrjh3 | 1 | 67,309,784 | closed, PR #3857 merged |
| bd-ib-tfu2gj | 1 | 54,527,445 | active |
| bd-ib-j5cwkj | 2 | 51,891,243 | acceptance |
| bd-ib-6sugaf | 2 | 50,788,406 | closed, PR #3854 merged |
| bd-ib-egzipe | 1 | 31,177,463 | closed, PR #3863 merged |
| bd-ib-3kqdln | 1 | 15,285,819 | closed, PR #3864 merged |
| bd-ib-qqtqoh | 1 | 15,090,160 | closed, PR #3847 merged |
| bd-ib-n4twqd | 1 | 1,734,502 | active |
| **Total** | **16** | **761,374,202** | |

- **Accepted first pass: 5 of 7 accepted items (71%).** Seven items reached `closed` with their pull request merged.
  Five of them did so on their only dispatch in the window: `weje2m`, `onrjh3`, `egzipe`, `3kqdln` and `qqtqoh`. Two
  took a second dispatch: `4jdgcw` and `6sugaf`. Counted over all twelve items, five of twelve were accepted first pass.
  The other five items were unresolved when the window closed.
- **Fleet-total tokens per accepted item: 108.8M.** That is the window total of 761,374,202 divided by seven accepted
  items. Spend on the five unresolved items is included, because the fleet paid it. Counting only the accepted items'
  own spend (430,034,224) gives 61.4M per accepted item.
- **Fix-loop count per node.** This counts distinct ACP sessions per node against the items that reached that node.
  A count above the item count is a repeat visit: a review loop, a retry, or a provider fallback.

| Node | Sessions | Work items | Sessions above one per item |
|---|---:|---:|---:|
| implement | 17 | 11 | 6 |
| fix | 8 | 3 | 5 |
| review | 19 | 10 | 9 |
| review_fix | 4 | 4 | 0 |
| proof_capture | 27 | 10 | 17 |
| proof_verify | 14 | 9 | 5 |
| dod_gate | 26 | 12 | 14 |
| disposition | 10 | 6 | 4 |

The `fix` loop ran 8 times on 3 items. `review_fix` ran once on each of 4 items. The largest repeat counts are on
`proof_capture` and `dod_gate`, which is where a re-entered loop re-pays the whole ~340k floor on every visit.

**Caveat:** the dispatch count includes only dispatches that produced Sonnet 5.5 responses in the window. An item
whose earlier dispatch ran on another model, or before 23:20Z, shows as fewer dispatches than it had.

## 4. What this baseline is for

This is the "before" column of the plan's before/after table. The after window opens when `bd-ib-coxsfu` ships. Note
003 predicts the first-request floor drops from ~340k to ~100k on every node except `disposition`. To compare, re-run
the three queries above with the same filters over a window that starts after that release.
