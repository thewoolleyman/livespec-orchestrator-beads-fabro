## The maintainer's statement of what done means

Okay the mitigations to this bind need to be written as a new plan. Use the orchestrator plan skill to create the plan with a clear definition of done populated and then let me know so I can start working it.

## Definition of Done assertions derived from that statement

- Over a 24-hour window after this plan's children land, total Anthropic spend in the livespec llm-spend Honeycomb dataset is at most 40% of the 2026-10-26 baseline of $1,224 per 24 hours.
- Over that same window, llm-spend shows no claude -p response on claude-opus-4-8 launched from any livespec fleet repository.
- Each spec-stated behaviour judgement sends at most 100,000 input tokens to its model, whichever provider serves it, against a 2026-10-26 median of 875,054.
- Each Definition-of-Done brief grading sends at most 100,000 input tokens to its model, whichever provider serves it.
- A statement and governing heading whose texts are unchanged since their last judgement are not sent to a model again.
- Every interactive fleet seat runs with the model and effort named in one committed fleet configuration, and llm-spend shows that model and effort on the seat's responses.
- Over a 24-hour window, the average USD per interactive main-thread response in llm-spend is at most 60% of the 2026-10-26 baseline of $0.112.
- Over a 24-hour window, subagent responses are at most 5% of local Anthropic spend in llm-spend, read from a consumer kind that marks subagent responses.

# 001 — Charter: Anthropic token burn mitigation (2026-10-26)

## Maintainer statement (verbatim)

> Okay the mitigations to this bind need to be written as a new plan. Use the orchestrator plan skill to create the plan with a clear definition of done populated and then let me know so I can start working it.

The Definition of Done assertions below were derived by the creating session (livespec-dev-tooling plan `token-spend-analysis`, session 53b20143) from the measurements in this note; the maintainer directed that they be populated without a confirmation round, and may re-word them on first resume.

## The bind, as measured 2026-10-26 between 20:19Z and 20:35Z

Source: livespec Honeycomb dataset `llm-spend` (schema 2/6, original response events) and the local Claude transcripts under `~/.claude/projects` on the vps. USD is API list price — a relative weight, since billing is subscription quota.

- Anthropic spend, last 24 h: about **$1,224** (by account: anthropic-6 $1,172, anthropic-0 $52). This is the quota-constrained budget the caam rotation is draining.
- Local Anthropic spend by kind, last 24 h, from transcripts ($1,240.58):
  - headless `claude -p` / sdk: **$753.71 (60.8%)**, of which `claude-opus-4-8` $705.98 over 561 responses;
  - interactive main threads: **$463.35 (37.3%)**, mostly `claude-opus-5-5` ($406.81 over 3,827 responses; $0.112 per main-thread response overall);
  - subagents: **$23.52 (1.9%)**, mostly `claude-sonnet-5-5`.
- The `claude -p` spend by caller (opening prompt), sessions active in the last day ($1,669.79):
  - the spec-stated behaviour judge ("You are judging ONE behaviour statement against a RATIFIED specification"): **$1,268.95 (76%)** across this repo ($982.61, 190 sessions), livespec-overseer ($232.58, 72) and livespec-dev-tooling ($53.76, 19);
  - the Definition-of-Done brief grader ("# Definition-of-Done gate — grade the brief before anything is built"): **$315.39 (19%)**;
  - two one-off fable briefs: $85.46.
- Why the spec-stated judge is expensive: each session sends a median **875,054 input tokens** (mean 761,660) and a median first prompt of **1,040,296 characters** — effectively the whole ratified spec tree per single-statement judgement — over a median of 2 responses and 5,300 output tokens. On `claude-opus-4-8[1m]` almost all of that is a 1-hour prompt-cache write ($10/MTok) that the next one-shot session never reads. Output is under 5% of the cost, so effort level is not the lever.
- The burn continues: `claude -p` on opus-4.8 was $85 in the 3 hours to ~20:29Z (~$28/h).

## What is already being worked, and is NOT duplicated here

- `bd-ib-mfzvdl` (active): routes the drift judge and the Definition-of-Done judges through the configured Codex-first `dod_gate` chain.
- `bd-ib-c6va2d` (ready): moves the out-of-band reflector off `claude -p` onto the same chain.
- Coordinator rulings R47/R48 (gitops-fleet-capacity-monitoring): factory judges cut to Haiku/Sonnet, Claude screen leg off.

Those move WHICH provider pays. They do not shrink the prompt: a ~875k-token judgement routed to Codex spends the ChatGPT budget instead, and may not fit a non-1M context. This plan proves their outcome on the Anthropic side (assertion 2) and owns what they leave: prompt size per judgement, interactive-seat cost, and subagent cost.

## Mitigation directions (for the plan's children)

1. Spec-stated judge and DoD brief grader: send only the governing heading and its cited sections (`_spec_tree_condensation.py` exists), not the tree; batch statements that share a heading into one judgement; cache verdicts by (statement, heading-text hash) so an unchanged pair is never re-judged.
2. One-shot calls that must stay on Anthropic: no 1-hour cache write for a prompt no later call reads.
3. Interactive seats: one committed fleet configuration for seat model and effort (Opus 5.5 at medium is the measured default today), with a cheaper default for monitoring/coordination seats whose work is mostly reading.
4. Subagents: default subagent model no costlier than Sonnet 5.5 unless an agent definition names one; measurable once `llm-spend` marks subagent responses (livespec-dev-tooling plan `token-spend-analysis` owns that telemetry).

## Measurement

Every assertion is proved from the `llm-spend` dataset and the board https://ui.honeycomb.io/thewoolleyweb/environments/livespec/board/abHcUYvjaYf, queried headless through `~/token-spend-report/scripts/hcq.py` with `HONEYCOMB_MCP_API_KEY_LIVESPEC` (see livespec-dev-tooling `.ai/honeycomb-query-credential.md`). Per-consumer USD currently double-counts restated spend (livespec-dev-tooling-2saqsm); until that lands, measure from original response events (`spend.correction` does-not-exist).
