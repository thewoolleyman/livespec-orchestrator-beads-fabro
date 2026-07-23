# Synthesis — factory success-rate investigation (2026-07-23)

Four parallel research tracks were run on 2026-07-23 to answer: (1) why
does the `review_fix` node conflate finding-disposition with fixing,
and is that shape sound; (2) where do factory runs actually fail, and
would more/parallel/better-model reviewers raise the merge rate; (3) is
a real-time "supervisor" (watch-and-steer) pattern feasible. Each track
has its own note in this directory; this file is the cross-track
conclusion.

## The one-paragraph answer

Improving the review stage is pointed at the wrong stage. The factory's
losses are overwhelmingly mechanical — PR-publish credentials
(GitHub App `workflows` permission, token TTL), git-checkpoint infra,
and runs dying unanswered at the `escalate` human gate (40% of all
failures end as a 2h stall there) — while the review gate is cheap
(~2 min/visit), approves 83% first-pass, terminally blocks ~2%, and has
zero detected misses. Reviewer scaling (parallel reviewers, stronger
models) would optimize the healthiest stage in the pipeline; the
platform could express it (with ACP/OAuth caveats), but the data says
don't.

## Where the leverage actually is (in priority order)

1. Workflow-editing items doomed at push (31% of failures) —
   `bd-ib-nga9` / `bd-ib-lgv` (refuse pre-dispatch), plus `bd-ib-2nq`
   (token TTL rollout).
2. Git checkpoint-commit failures (29%) — `bd-ib-6ka` (30s checkpoint
   budget vs gate-running pre-commit hooks).
3. The unanswered human gate (40% of failures by terminal mechanism) —
   `bd-ib-18r` / `bd-ib-6vu` (blocked as first-class outcome;
   credential re-projection on resume), i.e. notification + answer
   loop, salvaging runs that already survived implementation.
4. openbrain factory-readiness (13%, sandbox-init) and dispatch
   contention (`bd-ib-sd8o`), PR-node token projection (`bd-ib-4sy`,
   `bd-ib-qq7f`).

Epic anchor tracking this: `bd-ib-cvgjop`.

## The review_fix conflation (hygiene, not merge-rate)

The disposition+fix coupling was never argued anywhere, contradicts the
entire fabro ecosystem norm (reviewer- or human-owned structured
disposition, separate fix node), and the precedent the epic cited
(spec-dod) actually separates the two. Per the spec's own
intent-preservation rule the missing design record is itself a
surfaceable finding → filed as `bd-ib-o35rcx` (blocked, needs-human:
maintainer decides status-quo-with-rationale vs restructure). Detail:
review-fix-conflation.md.

## Supervisor pattern (feasible; unproven value)

Mid-turn injection exists today (`fabro steer --interrupt`, pair API);
the limiter is watching granularity (turn-level over ACP). The
practical fine-grained channel is an in-sandbox PreToolUse HTTP hook —
the dominant prior-art pattern — pending one cheap verification (does
the ACP adapter run project hooks?). No published evidence that
concurrent oversight improves code quality; the failure buckets it
would target are small here. Detail: supervisor-pattern-feasibility.md.

## Also captured

- Honeycomb access path quirk (management key vs hosted MCP endpoint)
  → durable-doc chore `bd-ib-elvxv2` (targets the livespec repo, with
  an optional vps-info pointer).
- Raw evidence corpus: `data/` (see `data/README.md`).
