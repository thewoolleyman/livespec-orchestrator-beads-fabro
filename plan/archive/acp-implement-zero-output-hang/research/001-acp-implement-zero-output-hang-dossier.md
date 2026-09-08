# Dossier 001 — ACP implement-agent zero-output hang

Evidence dossier for the plan thread `acp-implement-zero-output-hang` (ledger
epic `bd-ib-b5dg`). Compiled 2026-08-29 from the console repo's live catch and
the orchestrator ledger's prior art. Claims below are labelled **measured**,
**inferred**, or **hypothesis** deliberately; do not strengthen an inferred
claim into a measured one when quoting this document.

## The defect

ACP implement-agent zero-output hang in the Fabro `implement-work-item`
workflow (factory `hp`). An ACP agent stage activates and then produces
nothing at all — zero stdout, zero stderr, zero inference — until the
30-minute ACP turn timeout fires; the in-run retry hangs identically, so a
single occurrence burns roughly 60 minutes of factory wall-clock before
parking on a needs-human interview.

## Measured occurrence (2026-08-29, caught alive)

Caught alive by the test-adequacy-gates worker in the console repo
`livespec-console-beads-fabro`.

- Run `01M16KMWY5Y2DY0X90S1BDXCQX` (remote `hp-xubuntu:32276`), dispatched for
  work item `livespec-console-beads-fabro-txtzn5.14`.
- Event trace: `stage.started` "Implement (Red-Green-Replay)" →
  `agent.acp.started` → `agent.session.activated` → `agent.acp.timed_out`
  `dur=1800044ms` `stderr[0b]` `stdout[0b]` (30 min, ZERO output;
  `active_time_ms=0`, `inference_time_ms=0`, `tool_time_ms=0`) →
  `stage.failed` (`will_retry`) → retry → `agent.acp.timed_out`
  `dur=1800037ms`, zero output again → `stage.failed` (`will_retry=False`) →
  escalate interview ("Needs human: the loop cannot auto-resolve this
  work-item", options R/I/A) → `run.blocked`.
- `fabro_failure_category=transient_infra`. Console dispatch-journal outcome
  record `2026-08-29T12:15:47Z` `status=blocked`.
- The run carried the notice `[github_token_refresh_limited]`: "ACP agent
  stages receive workflow env at PROCESS LAUNCH; stages running beyond token
  expiry may need to be retried."
- The interview was answered [A] Abandon by the console worker; run terminal
  (`failed`/`workflow_error`); the item was released back to `ready` by hand.
- Cost per occurrence: ~60+ min factory wall-clock (two 30-min zero-output
  turns) before a needs-human park.
- Consequence: the console repo's test-adequacy coverage lane (epic
  `livespec-console-beads-fabro-4jb3kl`) has PAUSED factory dispatch of its
  remaining children pending an orchestrator-side fix.

## Counter-evidence and bounds (carry these hedges)

- **NOT universal.** TWO runs produced real output on factory `hp` the same
  day, both dispatched for `livespec-console-beads-fabro-ag0` through the same
  `implement-work-item` workflow: run 1 (dispatched 10:54:53Z) authored the
  actual production fix, PR #873 merged 11:36:07Z commit `9042269`; run 2
  (dispatched 11:20:33Z, an accidental double-dispatch) authored tests-only
  PR #876 merged 12:22:28Z commit `fded418`. So the same workflow on the same
  factory ran to completion twice on the day the zero-output hang parked run
  `01M16KMWY5Y2DY0X90S1BDXCQX`. The hang is real, measured, and intermittent.
- **The env hypothesis is a hypothesis, not a measured cause.** A coherent
  HYPOTHESIS consistent with all observations: env (e.g. auth token) is
  delivered at ACP process launch; a launch with dead/expired env hangs
  silently with zero output, the in-run retry reuses the same launch env so it
  hangs identically, while a fresh dispatch gets fresh env and succeeds.
- **The older console parks are unattributed.** The console-side claim "8
  parks over 7 items since 2026-08-22 are all this hang" is INFERRED, not
  measured: only the `.14` park was caught alive. The console dispatch journal
  categorizes the 08-22/23 parks (`txtzn5.15`, `txtzn5.12`, `txtzn5.17`) as
  `fabro_failure_category=deterministic` with a "404 Not Found on remote
  compact task" cause — a different signature. Treat the older parks as
  unattributed.

## Related, distinct, already filed

- **Plan thread `fabro-token-refresh`** (ledger epic `bd-ib-2nq`) owns
  token-refresh lore; the launch-env hypothesis overlaps it. Its recent epic
  comments (read 2026-08-29) concern the three-credential-carrier findings and
  record no zero-output-hang tracking of its own.
- **`bd-ib-oj71`** (backlog, P2): Codex-mode dispatch has no usability
  preflight and ImplementWorkItem has no dead-implementer circuit breaker — an
  exhausted Codex usage window burned review rounds against an empty diff.
  Same fail-fast shape as this plan's aim 2, different trigger.
- **`livespec-impl-beads-oyg`** (closed): the 2026-06-13 silent-stall
  watchdog — a run wedged 152 minutes with zero events after
  `agent.session.activated`. That watchdog covers a run emitting NO events;
  today's defect emits its timeout events on schedule and still wastes an
  hour, so it slips past that remedy.
- **`bd-ib-tec5sz`** (active): the watchdog fallback reads `updated_at`, a
  field fabro never emits — context for why watchdog-side liveness is thin.
- **`bd-ib-g56f`** / **`bd-ib-jm4efv`**: the swallowed-terminal-cause and
  `transient_infra`-misclassification family; today's park was classified
  `transient_infra` too.
- **Archived plan `plan/archive/dispatch-claim-liveness/`** holds prior art on
  claim liveness and the standing verification rules cited from this repo's
  `CLAUDE.md`.
- History note: an adjacent "stranded claim with no run" filing (`bd-ib-a4e7`)
  was withdrawn as a false alarm the same day — the dispatcher's
  already-claimed refusal and observe-only `active` behaved correctly and
  prevented worse.

Prior-art scan scope, per Verification discipline Rule 1: the full orchestrator
tenant ledger (`bd list --status all -n 0 --json`, 832 records on 2026-08-29),
scanned for zero-output / ACP-timeout / hang / activation / launch-env
signatures. No existing item tracks the zero-output activation hang itself.

## The plan's aim (grooming owns the final cut)

1. Root-cause the zero-output activation hang (launch-env/token delivery into
   the remote sandbox ACP adapter is the leading hypothesis).
2. Fail fast: an ACP agent that activated but has produced zero output and
   zero inference for some floor (minutes, not 30) should be killed and
   retried WITH FRESH LAUNCH ENV, or fail the stage with a typed cause — never
   burn 2×30 min before a human gate.
3. Surface zero-output agent turns as a first-class telemetry signal.
