# Dark-factory failure telemetry (investigation of 2026-07-23)

Question investigated: where do factory runs (the `implement-work-item`
Fabro workflow) stop being green, and why — specifically, would adding
more / parallel / better-model REVIEW nodes improve the merge success
rate?

Bottom line: **review is not the bottleneck.** Across ~6 weeks of
factory runs, non-merges are dominated by the PR/publish stage (a
GitHub-App `workflows`-permission gap), git-checkpoint/infra failures,
and runs orphaning unanswered at the human-escalation gate. The review
gate approves ~83% first-pass, terminally blocks ~2%, and shows zero
detected quality-misses.

Raw evidence for every table below is in `data/` (see `data/README.md`
for what each file is and how to regenerate it).

## How the data was obtained (access notes)

- Honeycomb: the `HONEYCOMB_MCP_API_KEY_LIVESPEC` key is a
  **management key (`hcamk_`)** scoped `environments:read` + `mcp:read`
  — it does NOT work with the v1 Query Data API (401). Queries were
  driven against Honeycomb's **hosted MCP endpoint**
  `https://mcp.honeycomb.io/mcp` over raw JSON-RPC (Streamable-HTTP,
  `Authorization: Bearer <key>`); helper preserved as `data/hctool.sh`.
  Team `thewoolleyweb`, environment `livespec`, dataset `fabro`
  (plus `livespec-dispatcher`, `fabro-sandbox`, `claude-code`).
  Durable capture of this quirk is ledger item `bd-ib-elvxv2`.
- fabro CLI: `FABRO_SERVER=http://127.0.0.1:32276 ~/.fabro/bin/fabro
  --json ps -a` → full durable run history (265 runs) =
  `data/raw-archive.tar.gz:fabro_all_runs.json`; per-failure
  `fabro --json inspect <run_id>` = `...:insp/`.
- Beads: `with-livespec-env.sh bd list/stats` from the repo root.

## Denominator (authoritative = fabro server durable state)

- **265 total runs; 252 are `implement-work-item`** (the factory),
  **2026-06-11 → 2026-07-23** (~6 weeks). The remaining 13 are
  test/probe workflows.
- This repo (`livespec-orchestrator-beads-fabro`): **104** factory
  runs. Others: livespec-core 40, dev-tooling 34, console 23,
  runtime 12, git-jsonl 11, drivers 14, openbrain 7.
- Beads ledger at the time of the census: 314 work-items — 244 closed,
  53 backlog, 10 blocked, 6 acceptance, 1 active. ≥74 closed items
  carry a merge/PR reference (factory-merged; a lower bound).
- **Honeycomb coverage caveat:** the `fabro` OTLP dataset only goes
  live ~**2026-07-17** (enrich export) and `run_turn`/O4 attributes
  from ~07-19. In the 07-17→07-23 window Honeycomb shows **62 root run
  spans vs 84 CLI runs (~74% coverage)** — it drops early-fail runs and
  `FABRO_LOG`-gated ones (`bd-ib-98c.12`). So Honeycomb alone cannot
  give the 6-week distribution; it supplied the recent per-node/turn
  detail while the CLI supplied the full census.

## Outcome distribution — 252 factory runs (full history)

| Outcome | Count | % |
|---|---|---|
| succeeded/completed (reached exit = PR opened + auto-merge armed) | 197 | 78.2% |
| failed/workflow_error | 49 | 19.4% |
| failed/terminated | 2 | 0.8% |
| failed/cancelled | 2 | 0.8% |
| blocked (parked, active at census time) | 2 | 0.8% |

**Success rate is repo-dependent:** this repo **98/104 = 94%**;
fleet-wide 78%. Failures concentrate off-repo: dev-tooling 17,
livespec-core 14, openbrain 7-of-7, this repo 6, console 6, drivers 4,
git-jsonl 1.

Caveat: fabro "succeeded" = PR opened + auto-merge armed, **not
confirmed-merged**. Post-PR CI/merge outcomes are outside fabro
telemetry.

## Failure distribution by ROOT CAUSE (55 non-successes)

Derived from `inspect.checkpoint.context_values.failure_signature`
(`node|category|message`) + `conclusion.failure.detail` (per-run JSON in
`data/raw-archive.tar.gz:insp/`).

| Root cause | Runs | % | Detail |
|---|---|---|---|
| **PR-stage credential/permission** | 17 | 31% | 15× GitHub App token **lacks `workflows` permission** → push of items touching `.github/workflows/*.yml` rejected: *"refusing to allow a GitHub App to create/update workflow without workflows permission."* Plus 2× expired/invalid App token (TTL). Includes the 2 blocked-at-census runs. |
| **git-checkpoint-commit failure** | 16 | 29% | Checkpoint commit `git commit timed out after ~30000ms` (hooks run on checkpoint commits; `skip_git_hooks=false`), or `git commit failed (exit 1)` (hook rejection), or `git add failed`. Nodes: implement 12, review_fix 2, pr 1, fix 1. |
| **Sandbox-init failure (repo not factory-ready)** | 7 | 13% | *"Failed to initialize sandbox"*, died in 0–1 min, **all 7 = openbrain**. Never started. |
| **implement genuine self-escalation** | 6–7 | ~12% | The agent did the work, ran checks, and honestly reported it could not meet an acceptance criterion (spec/tooling conflicts). Correct escalations, not pipeline defects. Plus 1 transient "acp turn failed". |
| Human abandon [A] | 2 | 4% | Operator chose Abandon at the gate. |
| Pipeline cancelled (manual) | 2 | 4% | |
| Server-shutdown mid-run | 2 | 4% | Server restart killed the run. |
| non_converged → regroom (fix-loop cap) | 1 | 2% | Scenario-14 bounce back to the Dispatcher. |
| Deterministic failure cycle (janitor/fix) | 1 | 2% | |
| **Review-quality terminal** | ~0 | ~0% | See the review-gate section. |

### Same data by TERMINAL MECHANISM (how the run actually ended)

- **`stall watchdog: node "escalate" 7200s` — 22 runs (40% of
  failures).** The dominant terminal path: a node fails → routes to the
  human gate (`escalate`, fabro `blocked`) → **no human answers → 2h
  stall-cancel.** Originating stage: **pr 15, implement 6, review 1.**
  These are also the "240-minute" wall-time cluster (≈2h to reach pr +
  2h stall), *not* ACP-turn timeouts.
- git-checkpoint-commit terminal 16; sandbox-init 7; abandon 2;
  pipeline-cancel 2; server-shutdown 2; non_converged 1;
  deterministic-cycle 1; +2 active-blocked.

Genuine ACP-turn timeouts are **rare now**: 1 `stop_reason=timed_out`
(a pr turn at its 1800s ceiling) in the recent window; the 2 historical
implement 4h timeouts were 2026-06-12, before the 7200→14400s bump.

## Review-gate specifics (recent window, ~35 reviewed runs, Honeycomb `run_turn`)

- **First-pass: ~29/35 (83%) approve; 6/35 (17%) require ≥1
  review_fix round.** (Distinct traces: review node 35, review_fix 6.)
- review_fix rounds per fixed run: mostly 1, a few 2–3; **none hit the
  cap-of-3 escalation.** Review-node visit counts: visit1=34, visit2=9,
  visit3=2, visit4=1.
- **Review is the terminal cause of a non-merge in ~1 of 55 (≈2%)**
  (one review→escalate→stall; plus 3 git-checkpoint failures that
  happened to land during review_fix — infra, not review quality).
- **Review misses (approved-then-reverted for quality): none found.**
  The 6 "revert" commits on this repo's master since June are all
  infra/process reversals, not "factory merged bad code". Fleet
  quick-scan (livespec 4, dev-tooling 1) — same character.

## Latency per node (recent window, `run_turn` duration)

| node | P50 | P95 | MAX | note |
|---|---|---|---|---|
| implement | 18.3 min | 37.6 min | 54.4 min | heaviest; well under the 240-min ceiling |
| review_fix | 12.8 min | 25 min | 25 min | real fix work |
| fix | 2.0 min | — | 12 min | |
| review | 1.9 min | 4.8 min | 5.0 min | cheap and fast |
| pr | 0.85 min | 4.2 min | 30 min | MAX = the one 1800s timeout |

Successful-run wall time: **P50 24.6 min, P90 52 min, MAX 100 min.**

## Reading of the data

- **Dominant non-success stage = PR/publish + the git-checkpoint/infra
  layer, funneling into an unanswered human gate.** The single biggest
  fixable root cause is the GitHub App `workflows`-permission gap
  (17 runs / 31%): any item editing `.github/workflows/*.yml` is doomed
  at push regardless of implementation or review quality.
- **Reviewer capacity/quality is NOT the bottleneck.** Review approves
  83% first-pass, costs ~2 min/visit, terminally blocks ~2%, misses ~0.
- The ledger already corroborates every bucket — see the epic
  `bd-ib-cvgjop` for the prioritized item list (`bd-ib-nga9`,
  `bd-ib-lgv`, `bd-ib-2nq`, `bd-ib-6ka`, `bd-ib-18r`, `bd-ib-6vu`,
  `bd-ib-4sy`, `bd-ib-qq7f`, `bd-ib-sd8o`).

## Data that could NOT be obtained

- **Cost:** `total_usd_micros` is null on every run (O5 token/cost
  telemetry deferred, `bd-ib-98c.8`).
- **Confirmed-merge outcomes:** fabro "succeeded" = PR-armed, not
  merged. Closest proxy: ≥74 closed items with a merge/PR reference
  (lower bound; includes hand-merges).
- **Review verdict as a direct span attribute:** not emitted;
  approve/fix rates inferred from review_fix turn/trace counts.
- **Honeycomb history before 2026-07-17:** absent (export not yet
  live); the 6-week distribution relies on fabro CLI durable state.
- 29 `run_turn` spans with blank node_id/stop_reason are codex-acp
  turns whose O4 attributes were dropped pre-allowlist-fix — a known
  data-quality gap, not additional failures.
