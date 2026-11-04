# 004 - "Before" reference: six Sonnet 5.5 runs on petri, per node, taken before bd-ib-coxsfu lands

Written 2026-10-28 ~12:30Z by the session driving this plan, for child C1 (`bd-ib-iljsyl`). This is a provisional
reference. Its purpose is that the pre-fix state stays on record once `bd-ib-coxsfu` (prepare-step scripts out of
the agent preamble) ships and the "before" window can no longer be re-taken. It does NOT replace the DoD's
Honeycomb `llm-spend` baseline: that is still owed, and it waits on the Honeycomb MCP being re-authenticated.

## Population and instrument

- Population: every run on petri (`https://gmktec-xubuntu.perch-rudd.ts.net:32276`) that had reached a terminal
  state by ~12:20Z among those started after the 05:46Z resume. Every agent node in them ran `claude-sonnet-5-5`
  through `claude-agent-acp`. That is six runs:
  `01M60GNFKGDEWA90ZT134J3X1P`, `01M60GRDDDTSJ569G21Q6JJ7RJ`, `01M60GTSRMY3Z2AH5XJAC2T7NS`,
  `01M60GX1RM6CSVW5VWKV8VXN5J`, `01M60NKG42TS1K2PGMAE3NEA31` and `01M60VT8SB6TC0VDE5H3DZQ2CR`.
  Four runs were still in flight and are excluded.
- Instrument: the ACP `usage_update.used` value (input + output + cache read + cache creation of the latest
  request; see note 003, section 1), read from `fabro dump` exports. Each update is one request's whole context.

## Per-node context per request

| Node | Updates | Median | P90 | Min | Max |
|---|---:|---:|---:|---:|---:|
| dod_gate | 64 | 343,550 | 348,879 | 336,660 | 351,655 |
| implement | 619 | 445,815 | 636,692 | 340,337 | 659,489 |
| review | 181 | 381,278 | 415,478 | 349,841 | 495,907 |
| review_fix | 30 | 455,064 | 456,898 | 357,153 | 457,282 |
| proof_capture | 220 | 377,528 | 412,818 | 357,297 | 431,428 |
| proof_verify | 116 | 361,367 | 372,779 | 351,211 | 387,195 |
| disposition | 5 | 100,429 | 101,008 | 100,203 | 101,008 |

`fix` did not run in any of the six.

## Disposition independently corroborates the note 003 decomposition

`disposition` is the one agent node at an explicit `fidelity="summary:medium"` (`bd-ib-7zxqyl`). That fidelity
windows the preamble to the last five stages, so no prepare-step script reaches it. Its first request is
100,203 tokens. That matches note 003's non-preamble components exactly: `AGENTS.md` ~54,650 + harness ~26,000 +
goal and node prompt ~19,500. So the ~241k gap between `disposition` and every other node is the prepare-script
preamble, measured from a second direction. It also shows the floor `bd-ib-coxsfu` should reach: about 100k with
`AGENTS.md` as it is today, and about 55k once the `AGENTS.md` split (C3) lands.

## Quality reference: stage visits per run

| Run | Item | Outcome | dod_gate | implement | janitor | fix | review | review_fix | proof_capture | proof_verify | disposition |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 01M60GNFKGDE | bd-ib-j5cwkj | failed | 1 | 1 | 2 | 0 | 2 | 1 | 2 | 1 | 1 |
| 01M60GRDDDTS | bd-ib-qqtqoh | succeeded | 1 | 1 | 1 | 0 | 1 | 0 | 1 | 1 | 0 |
| 01M60GTSRMY3 | bd-ib-4jdgcw | succeeded | 1 | 1 | 1 | 0 | 3 | 0 | 3 | 3 | 0 |
| 01M60GX1RM6C | bd-ib-6sugaf | failed | 1 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 01M60NKG42TS | bd-ib-6sugaf | succeeded | 1 | 1 | 1 | 0 | 1 | 0 | 1 | 1 | 0 |
| 01M60VT8SB6T | bd-ib-onrjh3 | succeeded | 1 | 2 | 1 | 0 | 1 | 0 | 1 | 1 | 0 |

Four of six succeeded. Over those six runs, `fix` ran 0 times and `review_fix` ran once. This is a reference for
DoD assertion 4 (no quality regression), not the graded baseline. Six runs are too few to grade a rate, and the
graded comparison needs the named window C1 still owes.
