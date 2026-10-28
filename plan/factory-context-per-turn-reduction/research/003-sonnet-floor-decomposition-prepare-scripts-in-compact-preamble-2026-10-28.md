# 003 - The Sonnet 5.5 per-turn floor is 338k tokens, and 71% of it is the dispatcher's prepare-step scripts echoed in Fabro's compact preamble

Written 2026-10-28 ~11:20Z by the session driving this plan, for child C1 (`bd-ib-iljsyl`). This note covers the
per-component breakdown (C1 assertion 2) and a first per-node reading on the Sonnet 5.5 routing. It does NOT yet
close C1. The fleet medians over a named window (assertion 1) need the Honeycomb `llm-spend` query, which waits on
the Honeycomb MCP being re-authenticated, and the quality baseline (assertion 3) is not taken yet.

## 1. Source and instrument

- Runs: three succeeded runs dispatched on petri (`https://gmktec-xubuntu.perch-rudd.ts.net:32276`) after the factory
  resumed at 05:46Z on the Sonnet 5.5 routing. Every agent node runs `ANTHROPIC_MODEL=claude-sonnet-5-5 ...
  claude-agent-acp`: `01M60GTSRMY3Z2AH5XJAC2T7NS` (bd-ib-4jdgcw), `01M60GRDDDTSJ569G21Q6JJ7RJ` (bd-ib-qqtqoh), and
  `01M60NKG42TS1K2PGMAE3NEA31` (bd-ib-6sugaf). Exported with the petri carrier client
  `/home/ubuntu/.local/state/fabro-currency/carrier-petri-v0.382-adeefec4c/fabro dump <run> --server <url> -o <dir>`.
- Instrument: the ACP `usage_update` events in each dump's `events.jsonl`, at
  `item.record.body.ev.custom.event.update`, keyed by `custom.node`. In `@agentclientprotocol/claude-agent-acp`
  (`dist/acp-agent.js`), `used = totalTokens(lastAssistantUsage)`. That is the latest assistant message's input +
  output + cache read + cache creation, i.e. the whole context of that one request. `size` (always 200,000 here) is
  the adapter's inferred window default, not a limit that was enforced: `used` exceeds it on every request.

## 2. Per-node reading (3 runs, 690 usage updates)

| Node | Updates | Median used | P90 used | First update of each session |
|---|---:|---:|---:|---|
| dod_gate | 34 | 342,160 | 348,879 | 337,843 - 338,078 |
| implement | 344 | 461,834 | 639,574 | 341,518 - 341,754 |
| review | 108 | 376,164 | 419,281 | 349,841 - 359,626 |
| proof_capture | 119 | 375,203 | 395,116 | 357,297 - 370,586 |
| proof_verify | 85 | 361,458 | 372,202 | 351,211 - 360,984 |

The first request of EVERY session, before the node has done any work, already carries 338k-371k tokens. The floor is
the problem; only `implement` grows much beyond it (its transcript reaches 660k). These are three runs, not a window,
so they are not the DoD baseline. But the floor is consistent to within 1% across runs, which says it is structural.

## 3. Where the 338k comes from

| Component | Tokens | How measured |
|---|---:|---|
| Fabro `compact` fidelity preamble: the 46 dispatcher prepare-step scripts | ~241,400 | Rebuilt from `run.json` `spec.settings.run.prepare.steps` in the engine's compact format (358,046 chars); measured with one `claude -p --model sonnet` probe (267,661 total) minus the empty-repository baseline (26,250) |
| Governed repository `CLAUDE.md` -> `AGENTS.md` (this repository) | ~54,650 | Note 002, section 3 |
| Harness base: system prompt, tool definitions, built-in commands | ~20,000-26,000 | Note 002 probe a (26,250 on this host, which includes host-only skills; the sandbox exposes only 23 built-in commands and no plugin skills) |
| Goal (11,534 chars) + node prompt (7-40 KB) | ~10,000-20,000 | File sizes |
| **Sum** | **~326k-342k** | Against the observed 337,843-341,754 for `dod_gate`/`implement` first requests |

The mechanism is in the Petri engine, `crates/attractor/steps/src/fidelity.rs` (read at petri `b99987b`):
`Detail::Compact` renders each completed `command` stage as `- Script: \`<full script>\`` plus at most 25 lines of
output. The script is NOT truncated. Every agent node runs at the default `compact` fidelity unless the graph says
otherwise (`fidelity_source: default`, thread `run_prepare_46` on `dod_gate`). So every agent request carries the
full text of every prepare step the Dispatcher materialised, on every turn of every node.

Why those scripts are so expensive:

- Steps 29-32 write the gh-refresh helper as a base64 tarball split into four `printf` chunks: 184,856 base64
  characters. Base64 tokenizes at about one token per 1-1.5 characters.
- Steps 35-42 write Python helpers into the sandbox plugin root as heredocs (`livespec-proof-record-reader`,
  `livespec-hook-limit.py`, `livespec-record-file-resolution.py` and others), about 170 KB.

None of that text is useful to an agent turn. It is plumbing, and the node prompts never reference it.

## 4. Consequence for the plan

- The single largest lever is not instruction files or skills. It is the ~241k tokens of prepare-script text in the
  engine preamble, about 71% of the floor, on every node and every turn, whichever provider serves it. Removing it
  alone takes the first-request floor from ~338k to ~97k, under the plan's 100k bound before anything else changes.
- The skills/plugins/MCP suspicion of note 001 is not borne out on the Sonnet routing: the sandbox's ACP session
  lists only 23 built-in commands and no plugin skills. C2's declaration work still matters for assertion 3, but it
  is not where the tokens are.
- `AGENTS.md` at ~54.6k is the second component, so the C3 split (held for the maintainer) remains worth doing.

## 5. Routed

Filed as `bd-ib-coxsfu`, a child of this epic: stop echoing prepare-step script bodies into agent prompts. The candidate
mechanisms, for the implementer to choose between with evidence, are: (a) make each prepare step's script a short
command that runs a payload delivered another way, so the preamble's `Script:` line is short; (b) give every agent
node an explicit fidelity that excludes command scripts while still carrying the goal and the context the node's
prompt relies on (`bd-ib-7zxqyl` set `summary:medium` on disposition for the same class of reason); (c) an engine
change so `compact` does not render prepare-stage scripts. Per the maintainer's standing direction, (c) is the
upstream last resort.
