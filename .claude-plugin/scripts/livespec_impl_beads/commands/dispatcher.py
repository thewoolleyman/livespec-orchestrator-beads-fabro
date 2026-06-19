"""`dispatcher` — the thin Dispatcher of the Beads/Dolt + Fabro orchestrator.

Per livespec spec.md §"Contract + reference implementations architecture"
(orchestrator-internal decomposition: Ledger / Loop / Dispatcher) and the
Dispatcher guidance in livespec non-functional-requirements.md, this CLI
polls the beads Ledger for ready work-items, invokes the Fabro Loop (the
`.fabro/workflows/implement-work-item/` phase graph) once per item —
launched from the target repo's primary checkout; Fabro clones fresh
inside its docker sandbox (Architecture C), so the host owns no git
working state — confirms the PR merge, runs the post-merge janitor hard
gate in a fresh detached worktree of merged master (never the host
primary's working tree, whose environment rot once false-redded a
confirmed-green merge — work-item livespec-impl-beads-cgd), writes
status/PR evidence back to the Ledger, and journals every step. It is
orchestrator-PRIVATE tooling: core's contract sees only the three
`orchestrator.py` CLIs.

  dispatcher.py ledger-check [--project-root <path>] [--json]
  dispatcher.py spec-check [--project-root <path>] [--spec-root <path>] [--json]
  dispatcher.py janitor-check [--repo <path>] [--json]
  dispatcher.py dispatch --repo <path> --item <id> [common flags]
  dispatcher.py loop --repo <path> --budget <n> [--parallel <k>]
                     [--mode shadow|autonomous] [--item <id>]... [common flags]

`spec-check` runs the three re-homed spec-context work-item invariants
(no-stalled-epic / no-stale-gap-tied / unresolved-spec-commitment; see
`_dispatcher_spec_checks.py`) against the tenant rows plus the spec
tree at `--spec-root` (default `<project-root>/SPECIFICATION`).
`janitor-check` runs the three re-homed stale-cleanup checks
(no-stale-merged-branch / no-stale-merged-pr-branch / no-stale-worktree;
see `_dispatcher_janitor_checks.py`) against the repo's git/gh state.
Both are standalone check surfaces — the pre-dispatch hard gate inside
`dispatch`/`loop` stays the pure-Ledger dispatch-safety trio.

Common flags: [--workflow <toml>] [--fabro-bin <path>]
[--janitor <json-argv>] [--journal <path>] [--poll-attempts <n>]
[--poll-interval-seconds <s>] [--no-close-on-merge]
[--skip-ledger-check] [--json]

Credential channel (Architecture C): the per-dispatch UNCOMMITTED
run-config overlay materialized under the temp dir is the RUN-SCOPED
credential projection (per the family-secrets scoped
transient-materialization rule): it appends an
`[environments.<id>.env]` table carrying the CLAUDE_CODE_OAUTH_TOKEN
value read from the Dispatcher's process environment, is written
mode-600, and is deleted when the run returns. The committed workflow
config carries NO secret VALUE and NO `{{ env }}` interpolation —
interpolation can NOT deliver credentials to server-mediated runs (do
not re-attempt it): resolution happens in the WORKER process, which
fabro-server spawns with a fail-closed env allowlist
(fabro-server/src/spawn_env.rs), so the token never reaches the
resolver and the LITERAL `{{ env.X }}` string flows into the sandbox
(proven empirically 2026-06-12: API 401 with the token present in
both the dispatcher's and the server daemon's env). The Dispatcher is
invoked under the with-livespec-env.sh wrapper (the livespec
1Password Environment carries CLAUDE_CODE_OAUTH_TOKEN) and refuses to
dispatch when the variable is absent or empty — there would be
nothing to project. The token value is never logged, echoed, or
journaled.

Sandbox sibling clones: the same overlay appends one depth-1
prepare-step clone per fleet member (from livespec master's
fleet-manifest.jsonc, fetched host-side via `gh api` at run-config
generation; the dispatch target is excluded) and projects the
non-secret LIVESPEC_SIBLING_CLONES_ROOT=/workspace/siblings into the
sandbox env table, so cross-repo checks under `just check` resolve
family siblings inside the sandbox — mirroring livespec CI. An
unreachable or malformed manifest fails the dispatch fast at the
`run-config-overlay` stage.

Connection + consent model: the Ledger connection resolves from the
TARGET repo's `.livespec.jsonc` (cwd-style `--repo` addressing) plus
`BEADS_DOLT_PASSWORD` for that tenant in the environment — one tenant
per process. Modes per the Dispatcher guidance: `shadow` (default)
dispatches ONLY items explicitly named via `--item`; `autonomous` takes
the ready queue. Store writes are machine-path dispositions of
already-filed items (close-on-confirmed-merge with PR/merge-sha
evidence), exempt from the per-operation consent discipline that
governs user-facing capture front-ends (livespec-impl-beads-nip);
`--no-close-on-merge` turns them off entirely. A `blocked` outcome (run
parked at the phase graph's in-loop human gate) closes nothing and
frees the slot: the operator answers via `fabro attach <run-id>`; the
Dispatcher never auto-resumes.

Exit codes: 0 success / all dispatched green; 1 non-skipped findings
present or any dispatch not green (failed OR blocked — both need the
operator's eyes); 2 usage error; 3 precondition error (missing repo /
workflow / item not ready). `skipped`-severity findings (unmet
preconditions) are reported but never flip the exit code.

Cost-observability seam (work-item livespec-impl-beads-5v9, the
prerequisite to y0m's fail-closed spend cap): the 5v9 investigation found
per-run cost FUNDAMENTALLY UNOBSERVABLE in this fabro version (v0.254.0,
ACP backend) — `fabro ps -a --json`'s `total_usd_micros` is null on every
run and no token/usage signal is populated anywhere. The warranted
fail-closed gate lives in `_dispatcher_cost`: `observe_run_cost(ps_json,
run_id)` is the cost SIGNAL (reads `total_usd_micros` from `fabro ps -a
--json`, surfacing a real value the moment fabro populates it),
`cost_gate_decision(mode, observation)` is the fail-closed rule
(autonomous + unobservable cost ⇒ refuse; shadow ⇒ warn), and
`gate_wave(...)` applies it across a completed wave — journaling one
leak-free `cost-gate` record per launched run and returning the work-item
ids that refused.

The gate is LIVE (work-item livespec-impl-beads-y0m): `_cost_gate_after_verdict`
runs `fabro ps -a --json` (via `ShellCommandRunner`, the same seam the
watchdog uses) ONCE after the wave's verdict is computed — alongside
`reflect` / `_alarm_on_terminal_failure`, FAIL-OPEN so a probe error or any
exception is journaled as `cost-gate-error` and the verdict is never
changed — passes the output to `gate_wave` (with `os.environ` so the caps
resolve), and turns each returned refusal into a `spend-cap-breach`-class
`NotifyEvent` through the existing `notify_terminal` seam. y0m extends the
gate from the "unobservable" verdict to the per-run + per-session USD
cap-VALUE comparison (`cap_value_decision`) using the committed
env-overridable defaults `resolve_per_run_cap_usd` /
`resolve_per_session_cap_usd` ($25 / $100, `LIVESPEC_MAX_RUN_USD` /
`LIVESPEC_MAX_SESSION_USD`), accumulating the per-session total across the
wave's observed runs. The cap-VALUE path is DORMANT until fabro reports a
populated cost (`total_usd_micros` null today; tracked as
livespec-impl-beads-efj) but is correct + tested; the
fail-closed-when-unobservable behavior 5v9 built stays the live path.
"""

import argparse
import json
import os
import sys
import tempfile
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from time import sleep as _real_sleep
from typing import cast

from livespec_impl_beads.commands._config import resolve_store_config
from livespec_impl_beads.commands._cross_repo import (
    is_item_ready,
    load_manifest,
    ready_sort_key,
)
from livespec_impl_beads.commands._dispatcher_cost import (
    COST_MODE_REPORT,
    gate_wave,
    resolve_cost_mode,
)
from livespec_impl_beads.commands._dispatcher_cost_pricing import DEFAULT_DISPATCH_COST_MODEL_ENV
from livespec_impl_beads.commands._dispatcher_cost_report import (
    build_cost_report_item,
    emit_cost_report,
)
from livespec_impl_beads.commands._dispatcher_cost_sink import (
    CostReport,
    CostSink,
    cost_lookup_keys,
)
from livespec_impl_beads.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
    PollPolicy,
    run_dispatch,
)
from livespec_impl_beads.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
    WatchedFabroLauncher,
    utc_now_iso,
)
from livespec_impl_beads.commands._dispatcher_janitor_checks import run_janitor_checks
from livespec_impl_beads.commands._dispatcher_ledger_checks import (
    LedgerFinding,
    run_ledger_checks,
)
from livespec_impl_beads.commands._dispatcher_notify import (
    HttpNotifyPoster,
    NotifyEvent,
    NotifyPoster,
    notify_terminal,
    terminal_events,
)
from livespec_impl_beads.commands._dispatcher_plan import (
    SiblingClones,
    build_plan,
    cc_otel_overlay_env,
    host_only_refusal_detail,
    is_host_only_item,
    item_sizing_warnings,
    janitor_checkout_path,
    parse_fleet_members,
    render_goal,
    render_run_config_overlay,
    resolve_sandbox_otel_endpoint,
)
from livespec_impl_beads.commands._dispatcher_reflection import reflect
from livespec_impl_beads.commands._dispatcher_reflector_oob import (
    GitPrLessonsProposer,
    LessonsProposer,
    resolve_mode,
    resolve_reflector_budget_seconds,
    run_reflector_oob,
)
from livespec_impl_beads.commands._dispatcher_self_update import (
    SELF_UPDATE_BREACH_CLASS,
    canary_self_check_argv,
    canary_verdict,
    is_self_merge,
    parse_pr_files,
    pr_files_argv,
    promotion_decision,
)
from livespec_impl_beads.commands._dispatcher_spec_checks import run_spec_checks
from livespec_impl_beads.commands._otel_receive import (
    HeartbeatSink,
    OtelReceiver,
    StartableServer,
    ensure_receiver_started,
    resolve_receiver_config,
)
from livespec_impl_beads.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)
from livespec_impl_beads.store import (
    WorkItemComment,
    append_work_item,
    materialize_work_items,
    read_work_item_comments,
    read_work_items,
)
from livespec_impl_beads.types import AuditRecord, StoreConfig, WorkItem

__all__: list[str] = ["main"]

_EXIT_FAILURE = 1
_EXIT_USAGE_ERROR = 2
_EXIT_PRECONDITION_ERROR = 3

_OAUTH_TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"  # noqa: S105 - env-var NAME, not a secret value

# The ingest-only Honeycomb key (write-only; the management/MCP key never
# touches this egress path, per telemetry-pipeline-architecture.md §3.4).
# An env-var NAME, not a secret value.
_HONEYCOMB_INGEST_KEY_ENV = "HONEYCOMB_INGEST_KEY_LIVESPEC"

# Process-level holder for the single shared live OTLP receiver (29f.7 E1).
# `ensure_receiver_started` keeps ONE receiver per host across concurrent
# dispatches in this dict — NOT one per dispatch (that would collide on the
# bound port). Module-scoped state, started fail-open at dispatch entry.
_OTEL_RECEIVER_HOLDER: dict[str, object] = {}

# Where the canonical fleet member registry lives: fleet-manifest.jsonc
# on livespec master (livespec non-functional-requirements.md §"Fleet
# membership contract"). Fetched HOST-SIDE at run-config generation
# time via `gh api` raw content — the same consume-from-master pattern
# the other family consumers (fleet conformance, release fan-out) use.
# This pins the manifest LOCATION, not the member list: the list itself
# is always read fresh, and an unreachable/malformed manifest fails the
# dispatch fast instead of falling back to a stale hardcoded set.
_FLEET_MANIFEST_API_PATH = "repos/thewoolleyman/livespec/contents/fleet-manifest.jsonc"
_FLEET_MANIFEST_FETCH_TIMEOUT_SECONDS = 60.0

# In-sandbox directory the sibling clones land under; projected into
# the sandbox env as LIVESPEC_SIBLING_CLONES_ROOT. `/workspace` is the
# fabro docker sandbox's workspace root (the target repo's clone sits
# at /workspace/<repo>), so the siblings root never collides with it.
_SIBLING_CLONES_ROOT = "/workspace/siblings"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.subcommand == "ledger-check":
        return _run_ledger_check(args=args)
    if args.subcommand == "spec-check":
        return _run_spec_check(args=args)
    if args.subcommand == "janitor-check":
        return _run_janitor_check(args=args)
    if args.subcommand == "dispatch":
        return _run_dispatch_command(args=args)
    return _run_loop_command(args=args)


def _run_ledger_check(*, args: argparse.Namespace) -> int:
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    findings = run_ledger_checks(items=_load_items(repo=project_root))
    return _emit_check_findings(findings=findings, as_json=args.as_json, label="ledger")


def _run_spec_check(*, args: argparse.Namespace) -> int:
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    spec_root = (
        Path(args.spec_root) if args.spec_root is not None else project_root / "SPECIFICATION"
    )
    findings = run_spec_checks(
        items=_load_items(repo=project_root),
        spec_root=spec_root,
        manifest=load_manifest(project_root=project_root),
    )
    return _emit_check_findings(findings=findings, as_json=args.as_json, label="spec")


def _run_janitor_check(*, args: argparse.Namespace) -> int:
    repo = Path(args.repo) if args.repo is not None else Path.cwd()
    findings = run_janitor_checks(repo=repo, runner=ShellCommandRunner())
    return _emit_check_findings(findings=findings, as_json=args.as_json, label="janitor")


def _emit_check_findings(*, findings: list[LedgerFinding], as_json: bool, label: str) -> int:
    """Emit check findings (JSON array or human lines); exit 1 on non-skipped."""
    if as_json:
        payload = [asdict(finding) for finding in findings]
        _ = sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        for finding in findings:
            severity = finding.severity.upper()
            line = f"{severity}  {finding.check}  {finding.item_id}  {finding.message}\n"
            _ = sys.stdout.write(line)
        if not findings:
            _ = sys.stdout.write(f"(no {label} findings)\n")
    actionable = any(finding.severity != "skipped" for finding in findings)
    return _EXIT_FAILURE if actionable else 0


def _run_dispatch_command(*, args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    janitor, janitor_ok = _parse_janitor(raw=args.janitor)
    if not janitor_ok:
        return _EXIT_USAGE_ERROR
    _ = _ensure_otel_receiver(args=args, repo=repo)
    prepared = _prepare(args=args, repo=repo)
    if prepared is None:
        return _EXIT_PRECONDITION_ERROR
    items, journal = prepared
    if not args.skip_ledger_check and _ledger_blocked(items=items, journal=journal):
        return _EXIT_FAILURE
    ready = _ready_items(items=items, repo=repo)
    target = next((item for item in ready if item.id == args.item), None)
    if target is None:
        _ = sys.stderr.write(f"ERROR: work-item {args.item} is not in the ready set\n")
        return _EXIT_PRECONDITION_ERROR
    outcome = _dispatch_one(args=args, repo=repo, item=target, journal=journal, janitor=janitor)
    _emit_outcomes(outcomes=[outcome], as_json=args.as_json)
    # Verdict computed BEFORE the fail-open reflection + notification
    # stages; immutable by both (loop-reflection-gate best-practices §6 /
    # 0jxs operability gate). The alarm is strictly best-effort.
    exit_code = 0 if outcome.status == "green" else _EXIT_FAILURE
    _alarm_on_terminal_failure(
        outcomes=[outcome],
        include_loop_summary=False,
        journal=journal,
    )
    _cost_gate_after_verdict(
        args=args,
        repo=repo,
        outcomes=[outcome],
        journal=journal,
    )
    _self_update_after_verdict(
        repo=repo,
        outcomes=[outcome],
        journal=journal,
    )
    reflect(
        outcomes=[outcome],
        journal=journal,
        journal_path=_journal_path(args=args, repo=repo),
        spans_path=_spans_path(args=args, repo=repo),
    )
    _reflector_oob_after_verdict(args=args, repo=repo, journal=journal)
    return exit_code


def _run_loop_command(*, args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    janitor, janitor_ok = _parse_janitor(raw=args.janitor)
    if not janitor_ok:
        return _EXIT_USAGE_ERROR
    _ = _ensure_otel_receiver(args=args, repo=repo)
    prepared = _prepare(args=args, repo=repo)
    if prepared is None:
        return _EXIT_PRECONDITION_ERROR
    items, journal = prepared
    if not args.skip_ledger_check and _ledger_blocked(items=items, journal=journal):
        return _EXIT_FAILURE
    picked = _candidates(args=args, items=items, repo=repo)[: args.budget]
    journal.append(
        record={
            "stage": "loop-pick",
            "mode": args.mode,
            "budget": args.budget,
            "picked": [item.id for item in picked],
        }
    )
    if not picked:
        _emit_outcomes(outcomes=[], as_json=args.as_json)
        return 0
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = [
            pool.submit(
                _dispatch_one,
                args=args,
                repo=repo,
                item=item,
                journal=journal,
                janitor=janitor,
            )
            for item in picked
        ]
        outcomes = [future.result() for future in futures]
    _emit_outcomes(outcomes=outcomes, as_json=args.as_json)
    # Verdict is computed BEFORE the mechanical reflection stage and is
    # immutable by it (loop-reflection-gate best-practices §6: reflection
    # never changes a dispatch verdict). reflect() is fail-open and never
    # raises — it cannot alter `exit_code`.
    exit_code = 0 if all(outcome.status == "green" for outcome in outcomes) else _EXIT_FAILURE
    _alarm_on_terminal_failure(
        outcomes=outcomes,
        include_loop_summary=True,
        journal=journal,
    )
    _cost_gate_after_verdict(
        args=args,
        repo=repo,
        outcomes=outcomes,
        journal=journal,
    )
    _self_update_after_verdict(
        repo=repo,
        outcomes=outcomes,
        journal=journal,
    )
    reflect(
        outcomes=outcomes,
        journal=journal,
        journal_path=_journal_path(args=args, repo=repo),
        spans_path=_spans_path(args=args, repo=repo),
    )
    _reflector_oob_after_verdict(args=args, repo=repo, journal=journal)
    return exit_code


def _reflector_oob_after_verdict(
    *,
    args: argparse.Namespace,
    repo: Path,
    journal: JournalFile,
    runner: CommandRunner | None = None,
    lessons_proposer: LessonsProposer | None = None,
    spawn: Callable[[Callable[[], None]], None] | None = None,
) -> None:
    """Fire the out-of-band LLM reflector as the 5th post-verdict stage (29f.4).

    Called AFTER the verdict / exit code is computed (alongside the
    ntfy-alarm, cost-gate, self-update, and mechanical-reflection stages)
    and is the LAST consumer leg of the 29f telemetry pipeline. The reflector
    runs in a daemon thread; `run_reflector_oob` is itself fail-OPEN, time-boxed,
    and default-OFF (the `LIVESPEC_REFLECTOR_OOB` lever), so on a plain dispatch
    this is a no-op that never raises and never touches the verdict.

    Daemon-lifetime reconciliation (29f.8 gap 2). The full cron/timer that is
    the reflector's eventual home is still DEFERRED; the minimal fix here is a
    lever-gated JOIN. A daemon thread dies when the dispatcher process exits, so
    a ~6-min review can never finish in the single-dispatch case — the time-box
    raise (gap 1) is meaningless without this. When the lever is ARMED
    (observe / file), the spawn JOINS the thread up to the stage budget (plus a
    small margin) so the reflector actually completes its review before the
    process exits. When the lever is OFF (the default), the body short-circuits
    inside `run_reflector_oob` immediately, so the fire-and-forget daemon adds
    NO delay — the plain-dispatch path is unchanged.

    `runner` / `lessons_proposer` are injectable for the hermetic test
    tier; production is the real `ShellCommandRunner` (the `claude -p` +
    git/gh subprocess seam) and `GitPrLessonsProposer` (the lessons-via-PR
    seam). `spawn` is injectable so the test tier runs the body
    SYNCHRONOUSLY instead of detaching a thread; production detaches a
    daemon thread. The OOB reflector writes its own verdict spans to a
    journal-sibling file the enrich stage forwards.
    """
    resolved_runner = runner if runner is not None else ShellCommandRunner()
    resolved_proposer = (
        lessons_proposer
        if lessons_proposer is not None
        else GitPrLessonsProposer(runner=resolved_runner)
    )
    spans_path = _reflector_oob_spans_path(args=args, repo=repo)

    def _body() -> None:
        run_reflector_oob(
            repo=repo,
            journal=journal,
            spans_path=spans_path,
            runner=resolved_runner,
            lessons_proposer=resolved_proposer,
        )

    resolved_spawn = spawn if spawn is not None else _default_reflector_spawn()
    resolved_spawn(_body)


def _default_reflector_spawn() -> Callable[[Callable[[], None]], None]:
    """Pick the daemon-thread spawn for the OOB reflector by lever state (29f.8 gap 2).

    OFF (default): the fire-and-forget daemon — the body short-circuits, so it
    adds no delay. ARMED (observe / file): a JOINING daemon bounded by the stage
    budget + margin, so the ~6-min review completes before the process exits
    (a daemon thread would otherwise be killed mid-review on a single dispatch).
    """
    mode = resolve_mode(raw=os.environ.get("LIVESPEC_REFLECTOR_OOB"))
    if mode == "off":
        return _spawn_daemon
    budget = resolve_reflector_budget_seconds(environ=dict(os.environ))
    join_timeout = budget + _REFLECTOR_JOIN_MARGIN
    return lambda body: _spawn_daemon_joining(body, join_timeout=join_timeout)


# Margin added to the stage budget for the lever-armed JOIN, so the join waits
# slightly longer than the reflector's own internal time-box (the reflector
# self-bounds; the join is a backstop, never the primary deadline).
_REFLECTOR_JOIN_MARGIN = 30.0


def _spawn_daemon(body: Callable[[], None]) -> None:
    """Run `body` in a fire-and-forget daemon thread (never blocks the loop)."""
    thread = threading.Thread(target=body, name="reflector-oob", daemon=True)
    thread.start()


def _spawn_daemon_joining(body: Callable[[], None], *, join_timeout: float) -> None:
    """Run `body` in a daemon thread and JOIN it up to `join_timeout` (29f.8 gap 2).

    The thread stays a daemon (a process exit still reaps it), but the JOIN
    holds the process open long enough for the armed reflector to finish its
    review — without it, a ~6-min review dies when the dispatcher exits. The
    join is bounded, so a wedged reflector never hangs the loop: on timeout the
    daemon is abandoned and the process proceeds to exit.
    """
    thread = threading.Thread(target=body, name="reflector-oob", daemon=True)
    thread.start()
    thread.join(timeout=join_timeout)


def _alarm_on_terminal_failure(
    *,
    outcomes: list[DispatchOutcome],
    include_loop_summary: bool,
    journal: JournalFile,
    poster: NotifyPoster | None = None,
) -> None:
    """Fire the fail-open ntfy alarm for any terminal failure (0jxs gate).

    Called AFTER the verdict / exit code is computed, so it can never
    change it. Derives the leak-free alarm events (one per non-green
    outcome — `failed`/`blocked`, covering uvd's `host-only-refused` —
    plus a `non-green-loop` summary for the loop command), then posts them
    fail-open: a missing topic, an unreachable server, or any POST error
    is journaled and swallowed, never raised. A fully-green wave fires
    nothing. `poster` is injectable for the hermetic test tier; production
    is the real `HttpNotifyPoster`.
    """
    events = terminal_events(
        outcomes=tuple(outcomes),
        include_loop_summary=include_loop_summary,
    )
    notify_terminal(
        events=events,
        run_id=_run_id(),
        poster=poster if poster is not None else HttpNotifyPoster(),
        journal=journal,
    )


_FABRO_PS_PROBE_TIMEOUT_SECONDS = 60.0

# The alarm class for a fail-closed cost-gate refusal (the producer h1p's
# `notify_terminal` seam names as y0m's). NOT a `DispatchOutcome.status`,
# so it is built as its own `NotifyEvent` rather than flowing through
# `terminal_events`.
_SPEND_CAP_BREACH_CLASS = "spend-cap-breach"


def _cost_gate_after_verdict(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
    journal: JournalFile,
    runner: ShellCommandRunner | None = None,
    poster: NotifyPoster | None = None,
) -> None:
    """Run the fail-closed cost gate after the verdict is computed (y0m).

    Called AFTER the wave's verdict / exit code is final (alongside the
    reflection + ntfy-alarm stages), and FAIL-OPEN: the whole stage is
    wrapped in a broad supervisor, so a `fabro ps` failure, an unparseable
    payload, or ANY exception is journaled as `cost-gate-error` and
    swallowed — it can never change a computed verdict or crash the
    dispatcher (the load-bearing 0jxs invariant, mirroring the reflection /
    notify stages). It runs `fabro ps -a --json` ONCE, hands the output to
    `gate_wave` (which applies 5v9's unobservable fail-closed gate AND
    y0m's per-run + per-session cap-VALUE comparison, resolving the
    committed env-overridable caps from `os.environ`), and turns each
    returned refusal into a `spend-cap-breach`-class `NotifyEvent` through
    h1p's existing `notify_terminal` seam (strict credential hygiene: only
    the work-item id + outcome class + a non-credential-bearing run id
    reach the alarm body). `runner` / `poster` are injectable for the
    hermetic test tier; production is the real `ShellCommandRunner` /
    `HttpNotifyPoster`.
    """
    try:
        _cost_gate(
            args=args,
            repo=repo,
            outcomes=outcomes,
            journal=journal,
            runner=runner if runner is not None else ShellCommandRunner(),
            poster=poster if poster is not None else HttpNotifyPoster(),
        )
    except Exception as exc:
        # Fail-open supervisor: the verdict is already final, so a broad
        # catch is the whole point — any error is journaled and swallowed,
        # never raised (0jxs operability gate).
        journal.append(
            record={
                "stage": "cost-gate-error",
                "reason": f"{type(exc).__name__}",
            }
        )


def _cost_gate(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
    journal: JournalFile,
    runner: ShellCommandRunner,
    poster: NotifyPoster,
) -> None:
    """The cost-gate / cost-reporter body wrapped fail-open by `_cost_gate_after_verdict`.

    Resolves `LIVESPEC_COST_MODE` (`report` default / `enforce` opt-in) and
    hands it to `gate_wave`. In `report` mode the per-dispatch
    API-equivalent cost is DERIVED + journaled but NEVER refused: the wave
    returns no refusals, and this stage instead EMITS the cost-report
    telemetry span (through the established spans-file → enrich egress) and
    a one-line stderr summary. In `enforce` mode the original fail-closed
    behavior is intact: each refusal becomes a `spend-cap-breach` alarm.
    """
    if not any(outcome.status == "green" for outcome in outcomes):
        # No launched run in the wave -> no cost to gate (host-only refusals
        # and other non-green outcomes never reached a fabro run).
        return
    cost_mode = resolve_cost_mode(environ=dict(os.environ))
    ps = runner.run(
        argv=[args.fabro_bin, "ps", "-a", "--json"],
        cwd=repo,
        timeout_seconds=_FABRO_PS_PROBE_TIMEOUT_SECONDS,
    )
    ps_json = ps.stdout if ps.exit_code == 0 else ""
    refusals = gate_wave(
        mode=getattr(args, "mode", "shadow"),
        outcomes=tuple(outcomes),
        ps_json=ps_json,
        journal=journal,
        environ=dict(os.environ),
        derived_cost_micros_by_work_item=_derived_costs(args=args, repo=repo, outcomes=outcomes),
        cost_mode=cost_mode,
    )
    if cost_mode == COST_MODE_REPORT:
        _emit_cost_report_telemetry(args=args, repo=repo, outcomes=outcomes)
        return
    if not refusals:
        return
    events = tuple(
        NotifyEvent(work_item_id=work_item_id, outcome_class=_SPEND_CAP_BREACH_CLASS)
        for work_item_id in refusals
    )
    notify_terminal(
        events=events,
        run_id=_run_id(),
        poster=poster,
        journal=journal,
    )


def _emit_cost_report_telemetry(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
) -> None:
    """Build + emit the report-mode per-dispatch cost telemetry (report mode).

    Reads each green outcome's full `CostReport` from the per-dispatch cost
    sink, builds the leak-free cost-report items (derived USD + per-category
    token sums + the honest model basis), and emits the `cost.report` OTLP
    span(s) plus the one-line stderr summary. A green run with no accrued
    cost (no CC telemetry arrived) is reported as UNOBSERVABLE — never
    refused. The whole call is inside `_cost_gate_after_verdict`'s fail-open
    supervisor, so a sink-read / emit error degrades to a journaled
    `cost-gate-error` rather than crashing the (already-final) verdict.
    """
    default_model = os.environ.get(DEFAULT_DISPATCH_COST_MODEL_ENV, "").strip() or None
    reports = _derived_reports(args=args, repo=repo, outcomes=outcomes)
    items = tuple(
        build_cost_report_item(
            work_item_id=outcome.work_item_id,
            report=reports.get(outcome.work_item_id),
            default_model=default_model,
        )
        for outcome in outcomes
        if outcome.status == "green"
    )
    emit_cost_report(
        items=items,
        dispatch_id=_dispatch_id_of(outcomes=outcomes),
        spans_path=_cost_report_spans_path(args=args, repo=repo),
    )


def _dispatch_id_of(*, outcomes: list[DispatchOutcome]) -> str | None:
    """The dispatch id correlating the wave's cost-report wave span, if any.

    `DispatchOutcome` does not carry a dispatch id, so the wave span is
    correlated by the per-item `work.item.id` on each child span; the wave
    root carries a dispatch id only when one is later threaded through.
    Returns None today (the child-span work-item ids are the join keys).
    """
    _ = outcomes
    return None


def _derived_costs(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
) -> dict[str, int]:
    """The CC-token-derived per-dispatch cost for each green outcome (efj).

    Reads the per-dispatch cost sink the live receiver wrote
    (`<base>-otel-cost.json`) and, for each green outcome, looks the
    accumulated micro-USD up by the work-item id (the `work.item.id`
    correlation key CC spans carry — the join key per
    `cc-otel-gap-analysis.md` §"Conclusion 9"). A work-item with no accrued
    cost (no CC telemetry arrived) is OMITTED, so `gate_wave` falls back to
    5v9's fabro / fail-closed path for it — the gate is never blinded. The
    read goes through `CostSink`, which is fail-open (a missing / corrupt
    file reads as empty), so a cost-sink error degrades to the fail-closed
    path rather than crashing the (already fail-open) cost gate.
    """
    try:
        return _read_derived_costs(args=args, repo=repo, outcomes=outcomes)
    except Exception:
        # Fail-open: a cost-sink read error degrades to the fail-closed path
        # (gate_wave then sees no derived cost), never crashing the cost gate.
        return {}


def _read_derived_costs(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
) -> dict[str, int]:
    sink = CostSink(path=_cost_sink_path(args=args, repo=repo))
    derived: dict[str, int] = {}
    for outcome in outcomes:
        if outcome.status != "green":
            continue
        for key in cost_lookup_keys(work_item_id=outcome.work_item_id, dispatch_id=None):
            micros = sink.usd_micros(key=key)
            if micros is not None:
                derived[outcome.work_item_id] = micros
                break
    return derived


def _derived_reports(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
) -> dict[str, CostReport]:
    """The full per-dispatch `CostReport` for each green outcome (report mode).

    The richer sibling of `_derived_costs`: reads the per-dispatch cost sink
    and, for each green outcome, looks the full report (token sums +
    model-resolution + summed micro-USD) up by the work-item id. A work-item
    with no accrued cost is OMITTED (the report builder then reports it
    UNOBSERVABLE). Fail-open: a sink-read error yields an empty map, so the
    report degrades to all-unobservable rather than crashing the cost stage.
    """
    try:
        return _read_derived_reports(args=args, repo=repo, outcomes=outcomes)
    except Exception:
        # Fail-open: a cost-sink read error degrades the report to
        # all-unobservable, never crashing the (already fail-open) cost stage.
        return {}


def _read_derived_reports(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcomes: list[DispatchOutcome],
) -> dict[str, CostReport]:
    sink = CostSink(path=_cost_sink_path(args=args, repo=repo))
    reports: dict[str, CostReport] = {}
    for outcome in outcomes:
        if outcome.status != "green":
            continue
        for key in cost_lookup_keys(work_item_id=outcome.work_item_id, dispatch_id=None):
            report = sink.cost_report(key=key)
            if report is not None:
                reports[outcome.work_item_id] = report
                break
    return reports


_CANARY_TIMEOUT_SECONDS = 300.0
_PR_FILES_PROBE_TIMEOUT_SECONDS = 60.0


def _self_update_after_verdict(
    *,
    repo: Path,
    outcomes: list[DispatchOutcome],
    journal: JournalFile,
    runner: ShellCommandRunner | None = None,
    poster: NotifyPoster | None = None,
) -> None:
    """Run the staged-self-update gate after the verdict is final (work-item ddu).

    Called AFTER the wave's verdict / exit code is computed (alongside the
    cost gate / reflection / ntfy-alarm stages) and FAIL-OPEN: the whole
    stage is wrapped in a broad supervisor, so a `gh pr view` failure, an
    unparseable payload, or ANY exception is journaled as
    `self-update-error` and swallowed — it can never change a computed
    verdict or crash the dispatcher (the load-bearing 0jxs invariant).

    For each GREEN outcome carrying a PR number (a confirmed self-merge
    candidate), it reads the merged file list (`gh pr view <branch> --json
    files`) and runs `_self_update_after_merge`: a merge that touched the
    dispatcher's OWN scripts CANARIES the just-pulled candidate and only
    PROMOTES it on a passing canary, else keeps the last-known-good copy
    and alarms. The candidate is the just-pulled primary's own
    `bin/dispatcher.py`; the canary scratch root is a throwaway temp dir.
    `runner` / `poster` are injectable for the hermetic test tier.
    """
    resolved_runner = runner if runner is not None else ShellCommandRunner()
    resolved_poster = poster if poster is not None else HttpNotifyPoster()
    for outcome in outcomes:
        if outcome.status != "green" or outcome.pr_number is None:
            continue
        merged_paths = _resolve_merged_paths(repo=repo, runner=resolved_runner)
        _self_update_after_merge(
            work_item_id=outcome.work_item_id,
            merged_paths=merged_paths,
            candidate_bin=str(_candidate_dispatcher_bin()),
            scratch_root=tempfile.mkdtemp(prefix=f"self-update-canary-{outcome.work_item_id}-"),
            repo=repo,
            journal=journal,
            runner=resolved_runner,
            poster=resolved_poster,
        )


def _resolve_merged_paths(*, repo: Path, runner: ShellCommandRunner) -> tuple[str, ...]:
    """Read the merged PR's changed paths; () on any unobservable signal.

    The publish branch is `feat/<work-item-id>` but the merge is already
    confirmed, so the simplest authoritative source is the repo's most
    recent merge to master — read via `gh pr view <branch> --json files`.
    A `gh` failure / empty payload yields () (no signal), which
    `is_self_merge` treats as "not a self-merge" (the safe default).
    """
    head = runner.run(
        argv=["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        timeout_seconds=_PR_FILES_PROBE_TIMEOUT_SECONDS,
    )
    branch = head.stdout.strip() if head.exit_code == 0 else "master"
    files = runner.run(
        argv=pr_files_argv(branch=branch),
        cwd=repo,
        timeout_seconds=_PR_FILES_PROBE_TIMEOUT_SECONDS,
    )
    return parse_pr_files(stdout=files.stdout) if files.exit_code == 0 else ()


def _candidate_dispatcher_bin() -> Path:
    """The just-pulled primary's own `bin/dispatcher.py` (the canary target).

    Resolved off this module's location (the same package-root walk
    `_workflow_toml` uses): after `_post_merge` pulls the primary, this
    path holds the STAGED new dispatcher code, which the canary
    self-checks before it can take over the loop.
    """
    package_root = Path(__file__).resolve().parents[4]
    return package_root / ".claude-plugin" / "scripts" / "bin" / "dispatcher.py"


def _self_update_after_merge(  # noqa: PLR0913 — kw-only fail-open stage; each field is an independent caller input.
    *,
    work_item_id: str,
    merged_paths: tuple[str, ...],
    candidate_bin: str,
    scratch_root: str,
    repo: Path,
    journal: JournalFile,
    runner: ShellCommandRunner | None = None,
    poster: NotifyPoster | None = None,
) -> None:
    """Stage + canary a self-merge before it can take over (work-item ddu).

    The dispatcher-self-update hazard: `_post_merge` pulls the target
    repo's primary, and when the target IS impl-beads itself that pull
    swaps the running dispatcher's code. This stage, run AFTER a confirmed
    merge, gates the swap: when the merge touched the dispatcher's OWN
    scripts (`is_self_merge`), it CANARIES the staged candidate (the
    candidate's own cheap, side-effect-free `ledger-check` self-check —
    NEVER a real fabro run, per the self-machinery hang-guard) and only
    PROMOTES it to the active pinned copy on a passing canary; a failing
    canary keeps the last-known-good pinned copy and ALARMS through h1p's
    `notify_terminal` seam (`self-update-canary-failed` class).

    FAIL-OPEN, mirroring `_cost_gate_after_verdict`: the whole body is
    wrapped in a broad supervisor, so a canary subprocess failure, an
    unexpected payload, or ANY exception is journaled as
    `self-update-error` and swallowed — it can never crash the dispatcher
    or masquerade as a promotion (the load-bearing 0jxs invariant).
    `runner` / `poster` are injectable for the hermetic test tier;
    production is the real `ShellCommandRunner` / `HttpNotifyPoster`.
    """
    try:
        _self_update(
            work_item_id=work_item_id,
            merged_paths=merged_paths,
            candidate_bin=candidate_bin,
            scratch_root=scratch_root,
            repo=repo,
            journal=journal,
            runner=runner if runner is not None else ShellCommandRunner(),
            poster=poster if poster is not None else HttpNotifyPoster(),
        )
    except Exception as exc:
        # Fail-open supervisor: the verdict is already final, so a broad
        # catch is the whole point — any error is journaled and swallowed,
        # never raised (0jxs operability gate, mirroring the cost-gate /
        # notify stages).
        journal.append(
            record={
                "stage": "self-update-error",
                "reason": f"{type(exc).__name__}",
            }
        )


def _self_update(  # noqa: PLR0913 — kw-only fail-open stage body; each field is an independent caller input.
    *,
    work_item_id: str,
    merged_paths: tuple[str, ...],
    candidate_bin: str,
    scratch_root: str,
    repo: Path,
    journal: JournalFile,
    runner: ShellCommandRunner,
    poster: NotifyPoster,
) -> None:
    """The self-update body wrapped fail-open by `_self_update_after_merge`."""
    if not is_self_merge(merged_paths=merged_paths):
        journal.append(
            record={
                "stage": "self-update-skipped",
                "work_item_id": work_item_id,
                "reason": "merge did not touch the dispatcher's own scripts",
            }
        )
        return
    canary = runner.run(
        argv=canary_self_check_argv(candidate_bin=candidate_bin, scratch_root=scratch_root),
        cwd=repo,
        timeout_seconds=_CANARY_TIMEOUT_SECONDS,
    )
    decision = promotion_decision(verdict=canary_verdict(exit_code=canary.exit_code))
    stage = "self-update-promoted" if decision.promote else "self-update-kept-last-known-good"
    journal.append(
        record={
            "stage": stage,
            "work_item_id": work_item_id,
            "reason": decision.reason,
        }
    )
    if not decision.alarm:
        return
    notify_terminal(
        events=(NotifyEvent(work_item_id=work_item_id, outcome_class=SELF_UPDATE_BREACH_CLASS),),
        run_id=_run_id(),
        poster=poster,
        journal=journal,
    )


def _run_id() -> str:
    """A non-credential-bearing correlation id for one dispatch run.

    Generated per invocation (a random uuid4 hex): it carries no env / goal
    / secret material by construction, so it is always safe to ship in the
    alarm body and to correlate against the journal.
    """
    return uuid.uuid4().hex


def _prepare(
    *,
    args: argparse.Namespace,
    repo: Path,
) -> tuple[list[WorkItem], JournalFile] | None:
    if not repo.is_dir() or not _workflow_toml(args=args).is_file():
        _ = sys.stderr.write("ERROR: --repo or workflow config does not exist\n")
        return None
    journal = JournalFile(path=_journal_path(args=args, repo=repo))
    return _load_items(repo=repo), journal


def _candidates(
    *,
    args: argparse.Namespace,
    items: list[WorkItem],
    repo: Path,
) -> list[WorkItem]:
    ranked = _ready_items(items=items, repo=repo)
    if args.mode == "autonomous":
        return ranked
    requested = set(args.items or [])
    return [item for item in ranked if item.id in requested]


def _ready_items(*, items: list[WorkItem], repo: Path) -> list[WorkItem]:
    index = {item.id: item for item in items}
    manifest = load_manifest(project_root=repo)
    ready = [item for item in items if is_item_ready(item=item, index=index, manifest=manifest)]
    # Compose the single canonical ranking authority so the Dispatcher's
    # drain order never diverges from what `next` advertises (i3jiny):
    # (priority, gap-tied-before-freeform, FIFO captured_at, id).
    return sorted(ready, key=ready_sort_key)


def _dispatch_one(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
) -> DispatchOutcome:
    host_only_refusal = _host_only_refusal(item=item, journal=journal)
    if host_only_refusal is not None:
        return host_only_refusal
    goal_file = Path(tempfile.gettempdir()) / f"fabro-goal-{item.id}.md"
    overlay_file = Path(tempfile.gettempdir()) / f"fabro-run-config-{item.id}.toml"
    janitor_checkout = janitor_checkout_path(repo=repo, work_item_id=item.id)
    plan = build_plan(
        repo=repo,
        work_item_id=item.id,
        workflow_toml=overlay_file,
        goal_file=goal_file,
        fabro_bin=args.fabro_bin,
        janitor=janitor,
        janitor_checkout=janitor_checkout,
    )
    _warn_item_sizing(item=item, journal=journal)
    comments = _read_dispatch_comments(repo=repo, item=item)
    if isinstance(comments, str):
        outcome = DispatchOutcome(
            work_item_id=item.id,
            status="failed",
            stage="ledger-comments",
            pr_number=None,
            merge_sha=None,
            detail=comments,
        )
        journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
        return outcome
    dispatch_id = _run_id()
    journal.append(
        record={"stage": "dispatch-id", "work_item_id": item.id, "dispatch_id": dispatch_id}
    )
    overlay_error = _materialize_overlay(
        committed=_workflow_toml(args=args),
        overlay=overlay_file,
        repo=repo,
        work_item_id=item.id,
        dispatch_id=dispatch_id,
    )
    if overlay_error is not None:
        outcome = DispatchOutcome(
            work_item_id=item.id,
            status="failed",
            stage="run-config-overlay",
            pr_number=None,
            merge_sha=None,
            detail=overlay_error,
        )
        journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
        return outcome
    _ = goal_file.write_text(
        render_goal(item=item, repo=repo, branch=plan.branch, comments=comments),
        encoding="utf-8",
    )
    try:
        outcome = run_dispatch(
            plan=plan,
            runner=ShellCommandRunner(),
            journal=journal,
            sleep=_real_sleep,
            poll=PollPolicy(
                attempts=args.poll_attempts,
                interval_seconds=args.poll_interval_seconds,
            ),
            # The progress watchdog (work-item livespec-impl-beads-oyg):
            # runs `fabro run` while watching liveness and `fabro rm -f`-es
            # a sustained-no-progress stall (the 7us.6 silent-deadlock
            # backstop) — a distinct `stalled-no-progress` outcome that
            # h1p's `notify_terminal` alarms on. 29f.6 layers the
            # metrics-HEARTBEAT (the journal-sibling file the live receiver
            # writes) as the deferred-PRIMARY liveness signal over the
            # coarse wall-clock backstop; an absent/stale/malformed
            # heartbeat degrades to the wall-clock layer, never to NO
            # detection.
            fabro_launcher=WatchedFabroLauncher(
                heartbeat_path=_heartbeat_path(args=args, repo=repo),
            ),
        )
    finally:
        overlay_file.unlink(missing_ok=True)
    if outcome.status == "green" and args.close_on_merge:
        _close_item(repo=repo, item=item, outcome=outcome)
        journal.append(record={"stage": "ledger-close", "work_item_id": item.id})
    journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
    return outcome


def _host_only_refusal(*, item: WorkItem, journal: JournalFile) -> DispatchOutcome | None:
    """Refuse to sandbox a host-only self-machinery item (uvd hang-guard).

    Returns the `host-only-refused` outcome (routed BEFORE any fabro
    launch, so the in-sandbox/in-hook git commit can never deadlock — the
    7us.6 hang class) when the item carries the explicit host-only
    marker, or None to let the dispatch proceed. The refusal is a
    `failed` outcome so the dispatch exit code flips to 1 and the
    orchestrator host-routes the item; the detail carries the actionable
    host-route instruction. Nothing is closed — the item stays open.
    """
    if not is_host_only_item(item=item):
        return None
    outcome = DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage="host-only-refused",
        pr_number=None,
        merge_sha=None,
        detail=host_only_refusal_detail(item_id=item.id),
    )
    journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
    return outcome


def _warn_item_sizing(*, item: WorkItem, journal: JournalFile) -> None:
    """Emit the warn-only item-sizing heuristics at dispatch/loop-feed time.

    Heavy multi-part items have exceeded one unattended ACP turn (bn4
    shakedown evidence), so the Dispatcher flags suspicious sizes — one
    journal record plus one stderr WARN line per heuristic hit. Never
    blocking: the dispatch proceeds regardless.
    """
    warnings = item_sizing_warnings(item=item)
    if not warnings:
        return
    journal.append(
        record={
            "stage": "sizing-warn",
            "work_item_id": item.id,
            "warnings": list(warnings),
        }
    )
    for warning in warnings:
        _ = sys.stderr.write(f"WARN: item-sizing {item.id}: {warning}\n")


def _read_dispatch_comments(
    *,
    repo: Path,
    item: WorkItem,
) -> tuple[WorkItemComment, ...] | str:
    """Read the item's ledger comments for the goal; error string on failure.

    Comments are operator riders appended after filing (e.g.
    pre-authorizations); a brief without them silently re-creates bn4
    finding (c), so a failed read REFUSES the dispatch (error-as-data,
    routed at the `ledger-comments` stage) instead of proceeding
    comment-blind.
    """
    try:
        return read_work_item_comments(path=_store_config(repo=repo), work_item_id=item.id)
    except (
        BeadsCommandError,
        BeadsConnectionError,
        BeadsMappingError,
        BeadsTenantMissingError,
    ) as exc:
        return f"ledger comments read failed for {item.id} ({type(exc).__name__}: {exc})"


def _materialize_overlay(
    *,
    committed: Path,
    overlay: Path,
    repo: Path,
    work_item_id: str,
    dispatch_id: str,
) -> str | None:
    """Write the uncommitted mode-600 run-config overlay.

    Returns None on success, or an actionable error message (an expected
    failure routed as data — the dispatch reports it at the
    `run-config-overlay` stage). The overlay is the RUN-SCOPED
    credential projection: the committed config (graph path absolutized)
    plus an appended env table carrying the CLAUDE_CODE_OAUTH_TOKEN
    value read from this process's environment. Fabro `{{ env }}`
    interpolation is NOT usable here (see the module docstring), so the
    value MUST be materialized. The token never reaches a log, journal,
    or argv; the overlay file is deleted when the run returns.

    The overlay ALSO provisions the sandbox sibling clones: one depth-1
    prepare-step clone per fleet member (minus the dispatch target,
    keyed by the `--repo` basename) plus the non-secret
    `LIVESPEC_SIBLING_CLONES_ROOT` env key, so cross-repo checks under
    `just check` resolve family siblings inside the sandbox the same
    way livespec CI provisions them.

    Finally it projects the in-sandbox Claude-Code OTel env (29f.3): the
    `cc_otel_overlay_env` dict carrying the correlation triple
    (`work_item_id` + `dispatch_id`) and the host-local E1 receiver
    endpoint, so CC native telemetry exports from inside the sandbox to
    the host-local enrich/receive stage. All NON-secret values — the
    Honeycomb ingest key is NOT among them (the sandbox ships plaintext;
    the host egress stage holds the key).
    """
    env_error = _check_credential_env()
    if env_error is not None:
        return env_error
    siblings = _resolve_sibling_clones(repo=repo)
    if isinstance(siblings, str):
        return siblings
    otel_env = cc_otel_overlay_env(
        work_item_id=work_item_id,
        dispatch_id=dispatch_id,
        endpoint=resolve_sandbox_otel_endpoint(environ=dict(os.environ)),
    )
    rendered = render_run_config_overlay(
        committed_text=committed.read_text(encoding="utf-8"),
        workflow_dir=committed.parent.resolve(),
        token=os.environ[_OAUTH_TOKEN_ENV],
        siblings=siblings,
        otel_env=otel_env,
    )
    if rendered is None:
        return (
            f"workflow config {committed} is not materializable: it must carry "
            '[workflow] graph = "..." and [run.environment] id = "..."'
        )
    overlay.unlink(missing_ok=True)
    descriptor = os.open(str(overlay), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        _ = handle.write(rendered)
    return None


def _fetch_fleet_manifest_text() -> str | None:
    """Fetch fleet-manifest.jsonc raw text from livespec master via `gh api`.

    HOST-SIDE read at run-config generation time (the Dispatcher's own
    environment has an authenticated `gh`; the sandbox does not).
    Returns the raw JSONC text, or None on any failure — the caller
    renders the actionable refusal.
    """
    result = ShellCommandRunner().run(
        argv=[
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github.raw",
            _FLEET_MANIFEST_API_PATH,
        ],
        cwd=Path.cwd(),
        timeout_seconds=_FLEET_MANIFEST_FETCH_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0 or result.stdout.strip() == "":
        return None
    return result.stdout


def _resolve_sibling_clones(*, repo: Path) -> SiblingClones | str:
    """Resolve the sandbox sibling-clone plan from the fleet manifest.

    Returns the plan (fleet members minus the dispatch target, keyed by
    the `--repo` basename — primary checkouts are named after their
    repo), or an actionable error string routed as data (the dispatch
    fails at the `run-config-overlay` stage). Failing fast beats
    silently dispatching without sibling clones: that would reintroduce
    the in-sandbox `:no-justfile-resolved` aggregate failure for every
    cross-repo check, and a hardcoded fallback list would rot as the
    fleet changes.
    """
    manifest_text = _fetch_fleet_manifest_text()
    if manifest_text is None:
        return (
            "sibling-clone provisioning refused: could not fetch "
            f"fleet-manifest.jsonc from livespec master (`gh api "
            f"{_FLEET_MANIFEST_API_PATH}`). The sandbox provisions one "
            "depth-1 clone per fleet member so cross-repo checks resolve "
            f"siblings under {_SIBLING_CLONES_ROOT}; check `gh auth "
            "status` and network reachability, then retry the dispatch."
        )
    members = parse_fleet_members(manifest_text=manifest_text)
    if members is None:
        return (
            "sibling-clone provisioning refused: fleet-manifest.jsonc "
            "fetched from livespec master did not parse into an owner "
            "plus a non-empty members list of GitHub-slug-shaped repo "
            "names. Fix the manifest on livespec master (it is the "
            "canonical fleet member registry), then retry the dispatch."
        )
    return SiblingClones(
        owner=members.owner,
        repos=tuple(name for name in members.repos if name != repo.name),
        clones_root=_SIBLING_CLONES_ROOT,
    )


def _check_credential_env() -> str | None:
    """Fail fast when CLAUDE_CODE_OAUTH_TOKEN is absent from the process env.

    Returns None when the credential is present, or an actionable error
    naming the wrapper that provides it. The Dispatcher's process env is
    the SOURCE of the run-scoped overlay projection, so an absent or
    empty variable means there is nothing to project. The value is never
    logged.
    """
    if os.environ.get(_OAUTH_TOKEN_ENV, "") != "":
        return None
    return (
        f"C-mode dispatch refused: {_OAUTH_TOKEN_ENV} is not set in the "
        f"Dispatcher's process environment. The run-config overlay "
        f"projects this variable into the sandbox env table (fabro "
        f"'{{{{ env.{_OAUTH_TOKEN_ENV} }}}}' interpolation cannot deliver "
        f"it — the server-spawned worker env is allowlist-scrubbed), so "
        f"an absent variable leaves nothing to project. Invoke the "
        f"Dispatcher under the with-livespec-env.sh wrapper (the livespec "
        f"1Password Environment carries the token)."
    )


def _close_item(*, repo: Path, item: WorkItem, outcome: DispatchOutcome) -> None:
    merge_sha = outcome.merge_sha
    audit = (
        AuditRecord(
            verification_timestamp=utc_now_iso(),
            commits=(),
            files_changed=(),
            merge_sha=merge_sha,
            pr_number=outcome.pr_number,
        )
        if merge_sha is not None
        else None
    )
    closed = replace(
        item,
        status="closed",
        resolution="completed",
        reason=f"Fabro dispatch landed PR #{outcome.pr_number} ({outcome.detail})",
        audit=audit,
    )
    append_work_item(path=_store_config(repo=repo), item=closed)


def _ledger_blocked(*, items: list[WorkItem], journal: JournalFile) -> bool:
    findings = run_ledger_checks(items=items)
    if not findings:
        return False
    journal.append(
        record={
            "stage": "ledger-check",
            "findings": [asdict(finding) for finding in findings],
        }
    )
    _write_findings(findings=findings)
    return True


def _write_findings(*, findings: list[LedgerFinding]) -> None:
    for finding in findings:
        _ = sys.stderr.write(
            f"LEDGER: {finding.check}  {finding.item_id}  {finding.message}\n",
        )
    _ = sys.stderr.write("ERROR: pre-dispatch ledger checks failed; dispatch blocked\n")


def _load_items(*, repo: Path) -> list[WorkItem]:
    return list(materialize_work_items(read_work_items(path=_store_config(repo=repo))).values())


def _store_config(*, repo: Path) -> StoreConfig:
    return resolve_store_config(cwd=repo, work_items_arg=None, memos_arg=None)


def _emit_outcomes(*, outcomes: list[DispatchOutcome], as_json: bool) -> None:
    if as_json:
        payload = [asdict(outcome) for outcome in outcomes]
        _ = sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return
    if not outcomes:
        _ = sys.stdout.write("(nothing dispatched)\n")
        return
    for outcome in outcomes:
        pr_part = f" PR#{outcome.pr_number}" if outcome.pr_number is not None else ""
        line = f"{outcome.work_item_id}  {outcome.status} at {outcome.stage}{pr_part}"
        _ = sys.stdout.write(f"{line}  {outcome.detail}\n")


def _workflow_toml(*, args: argparse.Namespace) -> Path:
    if args.workflow is not None:
        return Path(args.workflow)
    package_root = Path(__file__).resolve().parents[4]
    return package_root / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"


def _journal_path(*, args: argparse.Namespace, repo: Path) -> Path:
    if args.journal is not None:
        return Path(args.journal)
    return repo / "tmp" / "fabro-dispatch-journal.jsonl"


def _spans_path(*, args: argparse.Namespace, repo: Path) -> Path:
    """Where the mechanical reflection stage appends its OTLP/JSON spans.

    Co-located with the journal (one `<base>-reflection-spans.jsonl`
    sibling) so a future one-shot replay finds both in the same place;
    one `ExportTraceServiceRequest` per line (the family capture format).
    """
    journal = _journal_path(args=args, repo=repo)
    return journal.with_name(f"{journal.stem}-reflection-spans.jsonl")


def _reflector_oob_spans_path(*, args: argparse.Namespace, repo: Path) -> Path:
    """Where the out-of-band reflector appends its `gen_ai.evaluation.result` spans.

    Co-located with the journal (a `<base>-reflector-oob-spans.jsonl`
    sibling next to the mechanical-reflection spans file) so the verdict
    spans ride the SAME established local-span-file → enrich egress path;
    one `ExportTraceServiceRequest` per line (the family capture format).
    """
    journal = _journal_path(args=args, repo=repo)
    return journal.with_name(f"{journal.stem}-reflector-oob-spans.jsonl")


def _heartbeat_path(*, args: argparse.Namespace, repo: Path) -> Path:
    """Where the live receiver writes the per-run metrics heartbeat (§4.4).

    Co-located with the journal (a `<base>-otel-heartbeat.json` sibling) so
    29f.6's oyg `LivenessProbe` reads it OUT OF PROCESS next to the rest of
    the dispatch's tmp artifacts.
    """
    journal = _journal_path(args=args, repo=repo)
    return journal.with_name(f"{journal.stem}-otel-heartbeat.json")


def _cost_sink_path(*, args: argparse.Namespace, repo: Path) -> Path:
    """Where the live receiver writes the per-dispatch CC-token cost (efj).

    Co-located with the journal (a `<base>-otel-cost.json` sibling next to
    the heartbeat file) so the cost gate reads the DERIVED per-dispatch
    cost OUT OF PROCESS, exactly as 29f.6's probe reads the heartbeat. The
    receiver accrues each per-API-call token vector here keyed by
    `work.item.id` / `livespec.dispatch.id`.
    """
    journal = _journal_path(args=args, repo=repo)
    return journal.with_name(f"{journal.stem}-otel-cost.json")


def _cost_report_spans_path(*, args: argparse.Namespace, repo: Path) -> Path:
    """Where report mode appends its `cost.report` OTLP spans (LIVESPEC_COST_MODE=report).

    Co-located with the journal (a `<base>-cost-report-spans.jsonl` sibling
    next to the reflection / reflector-oob spans files) so the report-mode
    cost telemetry rides the SAME established local-span-file → enrich
    egress path; one `ExportTraceServiceRequest` per line (the family
    capture format).
    """
    journal = _journal_path(args=args, repo=repo)
    return journal.with_name(f"{journal.stem}-cost-report-spans.jsonl")


def _build_otel_receiver(*, args: argparse.Namespace, repo: Path) -> StartableServer:
    """Build (but do NOT start) the single host-local live OTLP receiver.

    Resolves the bound loopback addr/port from the `LIVESPEC_OTEL_RECEIVER_*`
    levers, wires the SHARED 29f.5 Honeycomb egress exporter (ingest-only
    key from env), points the metrics heartbeat at the journal-sibling
    file, and points the efj CC-token cost sink at its sibling
    `<base>-otel-cost.json` (the derived-cost seam the y0m spend cap
    reads), with the fallback pricing model resolved from
    `LIVESPEC_DISPATCH_COST_MODEL`. Imported lazily so the egress transport
    is only pulled in when a dispatch actually arms the receiver.
    """
    from livespec_impl_beads.commands._otel_enrich import HoneycombHttpExporter

    config = resolve_receiver_config(environ=dict(os.environ))
    exporter = HoneycombHttpExporter(ingest_key=os.environ.get(_HONEYCOMB_INGEST_KEY_ENV, ""))
    heartbeat = HeartbeatSink(path=_heartbeat_path(args=args, repo=repo))
    cost = CostSink(path=_cost_sink_path(args=args, repo=repo))
    default_model = os.environ.get(DEFAULT_DISPATCH_COST_MODEL_ENV, "").strip() or None
    return OtelReceiver(
        config=config,
        exporter=exporter,
        heartbeat=heartbeat,
        cost=cost,
        default_model=default_model,
    )


def _ensure_otel_receiver(
    *,
    args: argparse.Namespace,
    repo: Path,
    holder: dict[str, object] | None = None,
    factory: Callable[[], StartableServer] | None = None,
) -> StartableServer | None:
    """Idempotently start the single shared live OTLP receiver (29f.7 E1).

    Called at dispatch entry. Fail-OPEN: a receiver start failure NEVER
    blocks or fails a dispatch (the dispatcher already wrote the
    authoritative journal; egress is best-effort). `holder` + `factory` are
    injectable for the hermetic test tier (so no real socket binds in a
    test); production uses the module-level holder + the real factory.
    """
    target_holder = _OTEL_RECEIVER_HOLDER if holder is None else holder
    resolved_factory = (
        (lambda: _build_otel_receiver(args=args, repo=repo)) if factory is None else factory
    )
    return ensure_receiver_started(holder=target_holder, factory=resolved_factory)


def _parse_janitor(*, raw: str | None) -> tuple[tuple[str, ...] | None, bool]:
    """Parse the --janitor JSON-argv flag; (argv-or-None, parse-ok)."""
    if raw is None:
        return None, True
    try:
        parsed_raw: object = json.loads(raw)
    except json.JSONDecodeError:
        parsed_raw = None
    if not isinstance(parsed_raw, list):
        _ = sys.stderr.write("ERROR: --janitor must be a JSON array of strings\n")
        return None, False
    parts: list[str] = []
    for part in cast("list[object]", parsed_raw):
        if not isinstance(part, str):
            _ = sys.stderr.write("ERROR: --janitor must be a JSON array of strings\n")
            return None, False
        parts.append(part)
    return tuple(parts), True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dispatcher")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    ledger = subparsers.add_parser("ledger-check")
    _ = ledger.add_argument("--project-root", dest="project_root", default=None)
    _ = ledger.add_argument("--json", dest="as_json", action="store_true")
    spec = subparsers.add_parser("spec-check")
    _ = spec.add_argument("--project-root", dest="project_root", default=None)
    _ = spec.add_argument("--spec-root", dest="spec_root", default=None)
    _ = spec.add_argument("--json", dest="as_json", action="store_true")
    janitor = subparsers.add_parser("janitor-check")
    _ = janitor.add_argument("--repo", dest="repo", default=None)
    _ = janitor.add_argument("--json", dest="as_json", action="store_true")
    dispatch = subparsers.add_parser("dispatch")
    _add_dispatch_common(parser=dispatch)
    _ = dispatch.add_argument("--item", dest="item", required=True)
    loop = subparsers.add_parser("loop")
    _add_dispatch_common(parser=loop)
    _ = loop.add_argument("--budget", dest="budget", type=int, required=True)
    _ = loop.add_argument("--parallel", dest="parallel", type=int, default=1)
    _ = loop.add_argument("--mode", dest="mode", choices=["shadow", "autonomous"], default="shadow")
    _ = loop.add_argument("--item", dest="items", action="append", default=None)
    return parser


def _add_dispatch_common(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--repo", dest="repo", required=True)
    _ = parser.add_argument("--workflow", dest="workflow", default=None)
    _ = parser.add_argument("--fabro-bin", dest="fabro_bin", default="fabro")
    _ = parser.add_argument("--janitor", dest="janitor", default=None)
    _ = parser.add_argument("--journal", dest="journal", default=None)
    _ = parser.add_argument("--poll-attempts", dest="poll_attempts", type=int, default=80)
    _ = parser.add_argument(
        "--poll-interval-seconds",
        dest="poll_interval_seconds",
        type=float,
        default=30.0,
    )
    _ = parser.add_argument(
        "--no-close-on-merge",
        dest="close_on_merge",
        action="store_false",
    )
    _ = parser.add_argument(
        "--skip-ledger-check",
        dest="skip_ledger_check",
        action="store_true",
    )
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
