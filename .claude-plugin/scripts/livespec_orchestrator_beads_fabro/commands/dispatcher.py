"""`dispatcher` — the thin Dispatcher of the Beads/Dolt + Fabro orchestrator.

Per livespec spec.md
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
value read from the Dispatcher's process environment plus a GITHUB_TOKEN
freshly minted from the GitHub App installation-token provider (the FULL
name, not the short GH_TOKEN — see render_run_config_overlay: gh prefers
GH_TOKEN, and fabro re-projects its own re-minted token per exec under
GITHUB_TOKEN, so a projected GH_TOKEN would shadow fabro's fresh value
and expire past the ~60-min TTL at a long run's publish node), is
written mode-600, and is deleted when the run returns. The committed workflow
config carries NO secret VALUE and NO `{{ env }}` interpolation —
interpolation can NOT deliver credentials to server-mediated runs (do
not re-attempt it): resolution happens in the WORKER process, which
fabro-server spawns with a fail-closed env allowlist
(fabro-server/src/spawn_env.rs), so the token never reaches the
resolver and the LITERAL `{{ env.X }}` string flows into the sandbox
(proven empirically 2026-06-12: API 401 with the token present in
both the dispatcher's and the server daemon's env). The Dispatcher is
invoked under the dispatch TARGET's configured credential_wrapper, which
must inject the full per-wrapper set: GITHUB_APP_ID, GITHUB_PRIVATE_KEY,
BEADS_DOLT_PASSWORD, and CLAUDE_CODE_OAUTH_TOKEN. Per the
github-app-auth design there is NO fleet-PAT fallback, and the
Dispatcher refuses to dispatch when a credential is absent — there
would be nothing to project. The engine's
subprocess runner re-resolves GH_TOKEN from the caching provider
before EVERY command, so the ~76-minute merge-poll and any >1-hour
operation re-mint transparently instead of dying on a once-at-start
export. Token values are never logged, echoed, or journaled.

Sandbox sibling clones: the same overlay appends one depth-1
prepare-step clone per fleet member (from livespec master's
.livespec-fleet-manifest.jsonc, fetched host-side via `gh api` at run-config
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
the ready queue. The Dispatcher is the sole enforcer of the two
human-delegable policy valves bracketing the WIP-limited autonomous
middle: ADMISSION (admit the highest-`rank` admission-eligible `ready`
items up to the per-repo `dispatcher.wip_cap`, set the assignee,
transition `ready → active`; a manual / unresolvable-assignee item is
held + surfaced) and POST-MERGE ACCEPTANCE (`complete` merges on green
into `acceptance`, then `accept` confirms per the effective
`acceptance_policy` — `ai-only` → `done`, else park in `acceptance` for a
human; `reject` routes `rework → active` / `re-groom → backlog`). Store
writes (admit / complete / accept / reject / close-on-confirmed-merge
with PR/merge-sha evidence) are machine-path dispositions of already-filed
items, exempt from the per-operation consent discipline that governs
user-facing capture front-ends (livespec-impl-beads-nip);
`--no-close-on-merge` turns the post-merge acceptance writes off entirely.
A `blocked` outcome (run parked at the phase graph's in-loop human gate)
closes nothing and frees the slot: the operator answers via `fabro attach
<run-id>`; the Dispatcher never auto-resumes.

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
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from time import sleep as _real_sleep
from typing import Protocol, cast

from livespec_runtime.cross_repo.types import CrossRepoManifest
from livespec_runtime.github_auth.errors import GithubAppAuthError
from livespec_runtime.work_items.lifecycle import is_item_ready, ready_sort_key

from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_bin
from livespec_orchestrator_beads_fabro.commands._cross_repo import load_manifest
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import (
    admit_and_select,
    autonomous_armed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_autonomous import (
    arm_autonomous_for_loop,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration import (
    build_calibration_record,
    calibration_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    bounce_blocked,
    bounce_non_convergence_to_backlog,
    complete_and_accept,
    host_only_refusal,
    warn_item_sizing,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_gate import (
    cost_gate_after_verdict,
    derived_costs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import (
    DEFAULT_DISPATCH_COST_MODEL_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink import (
    CostSink,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
    read_dispatch_comments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    GithubTokenEnvRunner,
    JournalFile,
    ShellCommandRunner,
    WatchedFabroLauncher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_checks import run_janitor_checks
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_checks import (
    LedgerFinding,
    run_ledger_checks,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_lessons import (
    read_ratified_lessons,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human import (
    resolve_or_bounce_needs_human,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_notify import (
    HttpNotifyPoster,
    NotifyPoster,
    notify_terminal,
    terminal_events,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    cost_sink_path,
    heartbeat_path,
    journal_path,
    reflector_oob_spans_path,
    spans_path,
    store_config,
    workflow_toml,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    build_plan,
    janitor_checkout_path,
    janitor_core_ref_from_config,
    render_goal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection import reflect
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflector_oob import (
    GitPrLessonsProposer,
    LessonsProposer,
    resolve_mode,
    resolve_reflector_budget_seconds,
    run_reflector_oob,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    github_token_supplier,
    run_id,
    self_update_after_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_spec_checks import run_spec_checks
from livespec_orchestrator_beads_fabro.commands._otel_receive import (
    HeartbeatSink,
    OtelReceiver,
    StartableServer,
    ensure_receiver_started,
    resolve_receiver_config,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout
from livespec_orchestrator_beads_fabro.store import (
    materialize_work_items,
    read_work_items,
    update_work_item_status,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

# Compatibility alias for existing dispatcher tests and dispatch-path monkeypatches.
_github_token_supplier = github_token_supplier


__all__: list[str] = [
    "bounce_blocked",
    "bounce_non_convergence_to_backlog",
    "complete_and_accept",
    "host_only_refusal",
    "main",
    "warn_item_sizing",
]

_EXIT_FAILURE = 1
_EXIT_USAGE_ERROR = 2
_EXIT_PRECONDITION_ERROR = 3

# The active platform's path separators (os.altsep is None on POSIX). Built as
# a tuple of the truthy separators so the "does this string carry a directory
# component" test is a single `any(...)` with no unreachable `os.altsep` arc.
_PATH_SEPARATORS: tuple[str, ...] = tuple(sep for sep in (os.sep, os.altsep) if sep)

# The ingest-only Honeycomb key (write-only; the management/MCP key never
# touches this egress path, per telemetry-pipeline-architecture.md §3.4).
# An env-var NAME, not a secret value.
_HONEYCOMB_INGEST_KEY_ENV = "HONEYCOMB_INGEST_KEY_LIVESPEC"

# Process-level holder for the single shared live OTLP receiver (29f.7 E1).
# `ensure_receiver_started` keeps ONE receiver per host across concurrent
# dispatches in this dict — NOT one per dispatch (that would collide on the
# bound port). Module-scoped state, started fail-open at dispatch entry.
_OTEL_RECEIVER_HOLDER: dict[str, object] = {}


def main(*, argv: list[str] | None = None) -> int:
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
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        for finding in findings:
            severity = finding.severity.upper()
            line = f"{severity}  {finding.check}  {finding.item_id}  {finding.message}\n"
            _ = write_stdout(text=line)
        if not findings:
            _ = write_stdout(text=f"(no {label} findings)\n")
    actionable = any(finding.severity != "skipped" for finding in findings)
    return _EXIT_FAILURE if actionable else 0


def _resolve_fabro_bin_for(*, args: argparse.Namespace, repo: Path) -> str:
    """The effective `fabro` binary for this run: explicit flag wins, else resolve.

    An explicit `--fabro-bin <path>` (non-None) is an operator override and is
    returned verbatim; None (the flag's default) defers to
    `resolve_fabro_bin`'s env > config > absolute-default precedence.
    """
    if args.fabro_bin is not None:
        return cast("str", args.fabro_bin)
    return resolve_fabro_bin(cwd=repo)


def _fabro_preflight_error(*, fabro_bin: str) -> str | None:
    """Return an operator-facing ERROR string when `fabro_bin` is unresolvable, else None.

    A value carrying a directory component (a path separator) is resolvable
    only if it names an existing executable file; a bare name is resolvable
    only if it is found on `PATH` (`shutil.which`). The error names every
    corrective knob so the operator can fix the misconfiguration in place.
    """
    if any(sep in fabro_bin for sep in _PATH_SEPARATORS):
        resolvable = Path(fabro_bin).is_file() and os.access(fabro_bin, os.X_OK)
    else:
        resolvable = shutil.which(fabro_bin) is not None
    if resolvable:
        return None
    return (
        f"ERROR: fabro engine binary not resolvable: {fabro_bin!r}; set --fabro-bin,"
        " the LIVESPEC_FABRO_BIN env var, or the .livespec.jsonc"
        " dispatcher.fabro_bin key to an absolute path"
        " (default: $HOME/.fabro/bin/fabro)\n"
    )


def _dispatch_preamble(
    *, args: argparse.Namespace, repo: Path
) -> tuple[tuple[str, ...] | None, int | None]:
    """Shared dispatch/loop entry validation: janitor spec + fabro engine binary.

    Returns `(janitor, None)` to proceed (the parsed janitor override to thread
    downstream), or `(None, exit_code)` to short-circuit the command:
    `_EXIT_USAGE_ERROR` for a malformed `--janitor`, `_EXIT_PRECONDITION_ERROR`
    for an unresolvable fabro engine binary. The fabro check runs BEFORE the
    caller arms the receiver, prepares the store, or admits anything, so a
    misconfigured engine binary refuses with ZERO side effects and provably
    before admission (ready -> active) rather than stranding an item at active.
    Sets `args.fabro_bin` to the resolved path as a side effect.
    """
    janitor, janitor_ok = _parse_janitor(raw=args.janitor)
    if not janitor_ok:
        return None, _EXIT_USAGE_ERROR
    args.fabro_bin = _resolve_fabro_bin_for(args=args, repo=repo)
    fabro_error = _fabro_preflight_error(fabro_bin=args.fabro_bin)
    if fabro_error is not None:
        _ = write_stderr(text=fabro_error)
        return None, _EXIT_PRECONDITION_ERROR
    return janitor, None


def _run_dispatch_command(*, args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    janitor, preamble_exit = _dispatch_preamble(args=args, repo=repo)
    if preamble_exit is not None:
        return preamble_exit
    _ = _ensure_otel_receiver(args=args, repo=repo)
    prepared = _prepare(args=args, repo=repo)
    if prepared is None:
        return _EXIT_PRECONDITION_ERROR
    items, journal = prepared
    if not args.skip_ledger_check and _ledger_blocked_after_normalization(
        items=items,
        config=store_config(repo=repo),
        journal=journal,
    ):
        return _EXIT_FAILURE
    ready = _ready_items(items=items, repo=repo)
    target = next((item for item in ready if item.id == args.item), None)
    if target is None:
        all_ids = {item.id for item in items}
        if args.item not in all_ids:
            msg = (
                f"ERROR: work-item {args.item} not found in the target-tenant"
                f" ({repo.name}); --target-repo and --item must reference the same tenant\n"
            )
            _ = write_stderr(text=msg)
        else:
            _ = write_stderr(text=f"ERROR: work-item {args.item} is not in the ready set\n")
        return _EXIT_PRECONDITION_ERROR
    # The admission valve runs BEFORE the Fabro launch: a host-only item is
    # routed away, a manual / unresolvable-assignee item is held + surfaced,
    # and an admission-eligible item is admitted (ready -> active, assignee
    # set) and dispatched. A targeted dispatch is an operator override, so it
    # does NOT enforce the per-repo WIP cap (the queue-draining `loop` does).
    # The targeted `dispatch --item` path NEVER arms full autonomous mode — the
    # `--mode autonomous` opt-in rides the queue-draining `loop`, not `dispatch`
    # (SPECIFICATION/contracts.md) — so the admission valve runs with the mode
    # collapse OFF (armed=False), exactly the pre-mode behavior.
    admission = admit_and_select(
        repo=repo,
        items=items,
        candidates=[target],
        journal=journal,
        enforce_cap=False,
        armed=False,
    )
    dispatched = [
        _dispatch_one(args=args, repo=repo, item=item, journal=journal, janitor=janitor)
        for item in admission.admitted
    ]
    outcome = (admission.refused + dispatched)[0]
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
    cost_gate_after_verdict(
        args=args,
        repo=repo,
        outcomes=[outcome],
        journal=journal,
        runner=_post_verdict_runner(runner=None),
    )
    self_update_after_verdict(
        repo=repo,
        outcomes=[outcome],
        journal=journal,
        runner=_post_verdict_runner(runner=None),
    )
    reflect(
        outcomes=[outcome],
        journal=journal,
        journal_path=journal_path(args=args, repo=repo),
        spans_path=spans_path(args=args, repo=repo),
    )
    _reflector_oob_after_verdict(args=args, repo=repo, journal=journal)
    return exit_code


def _requested_items_preflight_error(
    *,
    requested_ids: set[str],
    items: list[WorkItem],
    repo: Path,
) -> str | None:
    """Return an operator-facing error string if a requested item fails preflight, else None.

    Validates in order: (1) items absent from the target-tenant entirely →
    target-tenant mismatch error; (2) items present in the tenant but not yet
    ready → not-in-ready-set error. Returns None when every requested id is
    ready and no preflight error applies.
    """
    all_ids = {item.id for item in items}
    missing_from_tenant = requested_ids - all_ids
    if missing_from_tenant:
        missing_text = ", ".join(sorted(missing_from_tenant))
        return (
            f"ERROR: work-item(s) {missing_text} not found in the target-tenant "
            f"({repo.name}); --target-repo and --item must reference the same tenant\n"
        )
    ready_ids = {item.id for item in _ready_items(items=items, repo=repo)}
    not_ready = requested_ids - ready_ids
    if not_ready:
        missing = ", ".join(sorted(not_ready))
        return f"ERROR: requested work-item(s) not in the ready set: {missing}\n"
    return None


def _run_loop_command(*, args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    janitor, preamble_exit = _dispatch_preamble(args=args, repo=repo)
    if preamble_exit is not None:
        return preamble_exit
    _ = _ensure_otel_receiver(args=args, repo=repo)
    prepared = _prepare(args=args, repo=repo)
    if prepared is None:
        return _EXIT_PRECONDITION_ERROR
    items, journal = prepared
    if not args.skip_ledger_check and _ledger_blocked_after_normalization(
        items=items,
        config=store_config(repo=repo),
        journal=journal,
    ):
        return _EXIT_FAILURE
    # Full autonomous mode two-factor arming: surface + journal the dangerous
    # acknowledgement when this run is armed (persistent permission + explicit
    # --mode autonomous). The armed bool is threaded onto `args` so the three
    # in-band consumers — the admission approve-gate collapse, the post-merge
    # acceptance collapse, and the post-run needs-human resolve-or-escalate
    # stage — read it and collapse/resolve to their autonomous leg; a non-armed
    # run is transparent (every gate keeps its normal policy).
    args.autonomous_armed = arm_autonomous_for_loop(
        mode=args.mode, repo=repo, journal=journal
    ).armed
    requested_ids = set(args.items or [])
    if requested_ids:
        preflight_error = _requested_items_preflight_error(
            requested_ids=requested_ids, items=items, repo=repo
        )
        if preflight_error is not None:
            _ = write_stderr(text=preflight_error)
            return _EXIT_PRECONDITION_ERROR
    candidates = _candidates(args=args, items=items, repo=repo)[: args.budget]
    # The admission valve drains the candidate set up to the per-repo WIP cap:
    # host-only items are routed away, manual / unresolvable items are held +
    # surfaced, and the highest-rank admission-eligible items fill the free
    # slots (ready -> active, assignee set). Capacity-deferred items simply
    # wait for the next pass.
    admission = admit_and_select(
        repo=repo,
        items=items,
        candidates=candidates,
        journal=journal,
        enforce_cap=True,
        armed=autonomous_armed(args=args),
    )
    journal.append(
        record={
            "stage": "loop-pick",
            "mode": args.mode,
            "budget": args.budget,
            "picked": [item.id for item in admission.admitted],
        }
    )
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
            for item in admission.admitted
        ]
        dispatched = [future.result() for future in futures]
    # Held / host-only-refused items ride in the outcomes (so the verdict and
    # the post-verdict alarm see them); capacity-deferred items do not.
    outcomes = admission.refused + dispatched
    if not outcomes:
        _emit_outcomes(outcomes=[], as_json=args.as_json)
        return 0
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
    cost_gate_after_verdict(
        args=args,
        repo=repo,
        outcomes=outcomes,
        journal=journal,
        runner=_post_verdict_runner(runner=None),
    )
    self_update_after_verdict(
        repo=repo,
        outcomes=outcomes,
        journal=journal,
        runner=_post_verdict_runner(runner=None),
    )
    reflect(
        outcomes=outcomes,
        journal=journal,
        journal_path=journal_path(args=args, repo=repo),
        spans_path=spans_path(args=args, repo=repo),
    )
    _reflector_oob_after_verdict(args=args, repo=repo, journal=journal)
    return exit_code


class _ReflectorSpawn(Protocol):
    def __call__(self, *, body: Callable[[], None]) -> None: ...


def _reflector_oob_after_verdict(  # noqa: PLR0913 — kw-only fail-open stage; seams are independently injectable.
    *,
    args: argparse.Namespace,
    repo: Path,
    journal: JournalFile,
    runner: CommandRunner | None = None,
    token_supplier: Callable[[], str] | None = None,
    lessons_proposer: LessonsProposer | None = None,
    spawn: _ReflectorSpawn | None = None,
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
    resolved_runner = _post_verdict_runner(runner=runner, token_supplier=token_supplier)
    resolved_proposer = (
        lessons_proposer
        if lessons_proposer is not None
        else GitPrLessonsProposer(runner=resolved_runner)
    )
    spans_path = reflector_oob_spans_path(args=args, repo=repo)

    def _body() -> None:
        run_reflector_oob(
            repo=repo,
            journal=journal,
            spans_path=spans_path,
            runner=resolved_runner,
            lessons_proposer=resolved_proposer,
        )

    resolved_spawn = spawn if spawn is not None else _default_reflector_spawn()
    resolved_spawn(body=_body)


def _default_reflector_spawn() -> _ReflectorSpawn:
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
    return lambda body: _spawn_daemon_joining(body=body, join_timeout=join_timeout)


# Margin added to the stage budget for the lever-armed JOIN, so the join waits
# slightly longer than the reflector's own internal time-box (the reflector
# self-bounds; the join is a backstop, never the primary deadline).
_REFLECTOR_JOIN_MARGIN = 30.0


def _spawn_daemon(*, body: Callable[[], None]) -> None:
    """Run `body` in a fire-and-forget daemon thread (never blocks the loop)."""
    thread = threading.Thread(target=body, name="reflector-oob", daemon=True)
    thread.start()


def _spawn_daemon_joining(*, body: Callable[[], None], join_timeout: float) -> None:
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


def _github_token_error_supplier(*, detail: str) -> Callable[[], str]:
    def _raise_github_token_error() -> str:
        raise GithubAppAuthError(detail=detail)

    return _raise_github_token_error


def _post_verdict_runner(
    *,
    runner: CommandRunner | None,
    token_supplier: Callable[[], str] | None = None,
) -> CommandRunner:
    resolved_runner: CommandRunner = runner if runner is not None else ShellCommandRunner()
    resolved_supplier = token_supplier
    if resolved_supplier is None and runner is None:
        supplier_or_error = _github_token_supplier()
        resolved_supplier = (
            _github_token_error_supplier(detail=supplier_or_error)
            if isinstance(supplier_or_error, str)
            else supplier_or_error
        )
    if resolved_supplier is None:
        return resolved_runner
    return GithubTokenEnvRunner(inner=resolved_runner, token=resolved_supplier)


def _run_id() -> str:
    """A non-credential-bearing correlation id for one dispatch run.

    Generated per invocation (a random uuid4 hex): it carries no env / goal
    / secret material by construction, so it is always safe to ship in the
    alarm body and to correlate against the journal.
    """
    return run_id()


def _prepare(
    *,
    args: argparse.Namespace,
    repo: Path,
) -> tuple[list[WorkItem], JournalFile] | None:
    if not repo.is_dir() or not workflow_toml(args=args).is_file():
        _ = write_stderr(text="ERROR: --repo or workflow config does not exist\n")
        return None
    journal = JournalFile(path=journal_path(args=args, repo=repo))
    return _load_items(repo=repo), journal


def _candidates(
    *,
    args: argparse.Namespace,
    items: list[WorkItem],
    repo: Path,
) -> list[WorkItem]:
    ranked = _ready_items(items=items, repo=repo)
    requested = set(args.items or [])
    if requested:
        return [item for item in ranked if item.id in requested]
    if args.mode == "autonomous":
        return ranked
    return []


def _janitor_core_ref(*, repo: Path) -> str:
    config = repo / ".livespec.jsonc"
    if not config.exists():
        return janitor_core_ref_from_config(config_text="{}")
    return janitor_core_ref_from_config(config_text=config.read_text(encoding="utf-8"))


def _ready_items(*, items: list[WorkItem], repo: Path) -> list[WorkItem]:
    index = {item.id: item for item in items}
    manifest = load_manifest(project_root=repo)
    ready = [
        item for item in items if _is_dispatch_candidate(item=item, index=index, manifest=manifest)
    ]
    # Compose the single canonical ranking authority so the Dispatcher's
    # drain order never diverges from what `next` advertises (i3jiny):
    # (rank, id) — the fractional rank is the sole ordering key.
    return sorted(ready, key=ready_sort_key)


def _is_dispatch_candidate(
    *,
    item: WorkItem,
    index: dict[str, WorkItem],
    manifest: CrossRepoManifest,
) -> bool:
    if is_item_ready(item=item, index=index, manifest=manifest):
        return True
    if item.status != "pending-approval":
        return False
    ready_projection = replace(item, status="ready")
    return is_item_ready(item=ready_projection, index=index, manifest=manifest)


def _dispatch_one(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
) -> DispatchOutcome:
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
        janitor_core_ref=_janitor_core_ref(repo=repo),
    )
    warn_item_sizing(item=item, journal=journal)
    comments = read_dispatch_comments(repo=repo, item=item)
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
    token_supplier = _github_token_supplier()
    if isinstance(token_supplier, str):
        outcome = DispatchOutcome(
            work_item_id=item.id,
            status="failed",
            stage="github-app-auth",
            pr_number=None,
            merge_sha=None,
            detail=token_supplier,
        )
        journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
        return outcome
    overlay_error = materialize_overlay(
        committed=workflow_toml(args=args),
        overlay=overlay_file,
        repo=repo,
        work_item_id=item.id,
        dispatch_id=dispatch_id,
        token=token_supplier,
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
    # Lessons are read host-side from `repo` (the dispatcher's operative
    # checkout, where the reflector maintains loop-reflection-gate/lessons.md),
    # exactly like `comments` above; only committed content is read, so an
    # unmerged reflector proposal never influences a brief.
    lessons = read_ratified_lessons(lessons_root=repo)
    goal_text = render_goal(
        item=item, repo=repo, branch=plan.branch, comments=comments, lessons=lessons
    )
    _ = goal_file.write_text(goal_text, encoding="utf-8")
    started_at = time.monotonic()
    try:
        outcome = run_dispatch(
            plan=plan,
            # Pillar 1 (first-class remint): the decorator re-resolves
            # GH_TOKEN from the caching provider before EVERY engine
            # subprocess, so the ~76-min merge-poll and the post-merge
            # git/janitor legs never ride an expired once-at-start token.
            runner=GithubTokenEnvRunner(inner=ShellCommandRunner(), token=token_supplier),
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
                heartbeat_path=heartbeat_path(args=args, repo=repo),
            ),
        )
    finally:
        overlay_file.unlink(missing_ok=True)
    _post_run_dispositions(
        args=args,
        repo=repo,
        item=item,
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=time.monotonic() - started_at,
        dispatch_context_size=len(goal_text),
        token_supplier=token_supplier,
    )
    return outcome


def _post_run_dispositions(  # noqa: PLR0913 — kw-only post-run stage; each field is an independent caller input.
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
    wall_clock_seconds: float,
    dispatch_context_size: int,
    token_supplier: Callable[[], str],
) -> None:
    """Run the machine-path dispositions after a dispatch reaches its terminal.

    The sequence the Dispatcher runs once a `run_dispatch` returns: on a
    confirmed merge (when armed) run the post-merge acceptance valve
    (`complete` -> `acceptance`, then `accept` per `acceptance_policy`),
    journal the terminal outcome, bounce a non-converging slice to `backlog`
    (n5kina), and emit the calibration telemetry (yfsv4j). Aggregated here so
    `_dispatch_one` stays a single readable sequence; every step is keyed off
    the terminal `outcome` and is independently fail-soft where it touches IO.
    """
    if outcome.status == "green" and args.close_on_merge:
        complete_and_accept(
            repo=repo,
            item=item,
            outcome=outcome,
            journal=journal,
            armed=autonomous_armed(args=args),
        )
    journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
    bounce_non_convergence_to_backlog(repo=repo, item=item, outcome=outcome, journal=journal)
    resolve_or_bounce_needs_human(args=args, repo=repo, item=item, outcome=outcome, journal=journal)
    _emit_calibration(
        args=args,
        repo=repo,
        item=item,
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=wall_clock_seconds,
        dispatch_context_size=dispatch_context_size,
        token_supplier=token_supplier,
    )


# The merged-PR diff-size probe budget: fail-soft to None.
_PR_DIFF_PROBE_TIMEOUT_SECONDS = 60.0


def _emit_calibration(  # noqa: PLR0913 — kw-only fail-open stage; each field is an independent caller input.
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
    wall_clock_seconds: float,
    dispatch_context_size: int,
    runner: CommandRunner | None = None,
    token_supplier: Callable[[], str] | None = None,
) -> None:
    """Journal this dispatch's calibration telemetry on the existing journal (yfsv4j).

    Per livespec-orchestrator-beads-fabro SPECIFICATION/contracts.md, the
    Dispatcher MUST emit calibration telemetry — an outcome
    signal plus mechanical size proxies — recorded on the EXISTING journal
    so it rides the journal → Honeycomb leg, with NO new always-on service.
    This stage runs AFTER the `outcome` record, gathers the already-observed
    inputs (the per-item journal records for the fix-loop count, the derived
    CC-token cost, and the merged-PR diff size), builds the pure
    `CalibrationRecord`, and appends ONE `calibration` record.

    FAIL-OPEN, mirroring the cost-gate / reflection stages: the merged-PR
    diff-size probe is the only IO and is itself fail-soft (a `gh` failure
    yields `None`), and the whole body is wrapped in a broad supervisor so
    a probe error or ANY exception is journaled as `calibration-error` and
    swallowed — it never crashes the (already-final) dispatch verdict.
    `runner` is injectable for the hermetic test tier.
    """
    resolved_runner = _post_verdict_runner(runner=runner, token_supplier=token_supplier)
    try:
        record = build_calibration_record(
            item=item,
            outcome=outcome,
            repo_name=repo.name,
            journal_records=_read_journal_records_for(args=args, repo=repo),
            wall_clock_seconds=wall_clock_seconds,
            token_cost_micros=_calibration_token_cost(args=args, repo=repo, outcome=outcome),
            dispatch_context_size=dispatch_context_size,
            merged_pr_diff_size=_merged_pr_diff_size(
                repo=repo,
                outcome=outcome,
                runner=resolved_runner,
            ),
        )
        journal.append(record=calibration_journal_record(record=record))
    except Exception as exc:
        # Fail-open supervisor: the verdict is already final, so a broad
        # catch is the whole point — any error is journaled and swallowed,
        # never raised (the load-bearing 0jxs invariant, mirroring the
        # cost-gate / reflection stages).
        journal.append(
            record={
                "stage": "calibration-error",
                "work_item_id": item.id,
                "reason": f"{type(exc).__name__}",
            }
        )


def _read_journal_records_for(
    *,
    args: argparse.Namespace,
    repo: Path,
) -> tuple[dict[str, object], ...]:
    """Read back the flushed journal records (the fix-loop-count read surface).

    The engine has already flushed each `pr-view` / `pr-update-branch`
    record to the on-disk journal by the time calibration runs, so the
    fix-loop count derives from the same authoritative surface the
    mechanical reflection scan reads. A missing or unreadable file yields
    an empty tuple (fail-soft), and malformed lines are skipped.
    """
    resolved_journal_path = journal_path(args=args, repo=repo)
    if not resolved_journal_path.is_file():
        return ()
    records: list[dict[str, object]] = []
    for line in resolved_journal_path.read_text(encoding="utf-8").splitlines():
        try:
            parsed: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            mapping = cast("dict[object, object]", parsed)
            records.append({str(key): value for key, value in mapping.items()})
    return tuple(records)


def _calibration_token_cost(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcome: DispatchOutcome,
) -> int | None:
    """The derived CC-token micro-USD for this dispatch, or None when unobservable.

    Reuses the per-dispatch cost sink the live receiver wrote (the efj
    derived-cost seam the cost gate reads): looks the accrued micro-USD up
    by the work-item id. A dispatch with no accrued cost (no CC telemetry
    arrived, or a non-green outcome that never launched a run) reads as
    `None` — the calibration analysis pass treats absence as missing data,
    never as zero. Fail-soft: the underlying `_derived_costs` already
    swallows a cost-sink read error to an empty map.
    """
    derived = derived_costs(args=args, repo=repo, outcomes=[outcome])
    return derived.get(outcome.work_item_id)


def _merged_pr_diff_size(
    *,
    repo: Path,
    outcome: DispatchOutcome,
    runner: CommandRunner,
) -> int | None:
    """The merged-PR diff size (additions + deletions), or None when unobservable.

    The merged-PR diff-size size proxy: a `gh pr view <pr> --json
    additions,deletions` probe summed into one churn number, read only for
    a green outcome carrying a PR number. A non-merged outcome, a missing
    PR number, or a `gh` failure / unparseable payload yields `None` (the
    proxy is absent, never falsely zero). The probe is fail-soft on its own
    and the whole calibration stage is fail-open around it.
    """
    if outcome.status != "green" or outcome.pr_number is None:
        return None
    result = runner.run(
        argv=[
            "gh",
            "pr",
            "view",
            str(outcome.pr_number),
            "--json",
            "additions,deletions",
        ],
        cwd=repo,
        timeout_seconds=_PR_DIFF_PROBE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return None
    return _parse_pr_diff_size(stdout=result.stdout)


def _parse_pr_diff_size(*, stdout: str) -> int | None:
    """Sum additions + deletions from a `gh pr view --json` payload; None if absent.

    Pure parse: returns the churn total when both integer fields are
    present, else `None` (an unparseable or partial payload is unobservable,
    never a false zero).
    """
    try:
        parsed: object = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    payload = cast("dict[str, object]", parsed)
    additions = payload.get("additions")
    deletions = payload.get("deletions")
    if not isinstance(additions, int) or not isinstance(deletions, int):
        return None
    return additions + deletions


_BEADS_NATIVE_OPEN = "open"
_LIVESPEC_BACKLOG = "backlog"


def _normalize_native_open_statuses(
    *,
    items: list[WorkItem],
    config: StoreConfig,
    journal: JournalFile,
) -> list[WorkItem]:
    normalized: list[dict[str, str]] = []
    result: list[WorkItem] = []
    for item in items:
        stored_status = str(item.status)
        if stored_status != _BEADS_NATIVE_OPEN:
            result.append(item)
            continue
        update_work_item_status(path=config, item_id=item.id, status=_LIVESPEC_BACKLOG)
        result.append(replace(item, status=_LIVESPEC_BACKLOG))
        normalized.append(
            {
                "item_id": item.id,
                "from": _BEADS_NATIVE_OPEN,
                "to": _LIVESPEC_BACKLOG,
                "reason": "beads-native intake default",
            }
        )
    if normalized:
        _append_normalization_note(journal=journal, normalized=normalized)
    return result


def _append_normalization_note(
    *,
    journal: JournalFile,
    normalized: list[dict[str, str]],
) -> None:
    line = json.dumps(
        {"stage": "status-normalization", "normalized": normalized},
        sort_keys=True,
    )
    journal.path.parent.mkdir(parents=True, exist_ok=True)
    with journal.path.open("a", encoding="utf-8") as handle:
        _ = handle.write(f"{line}\n")


def _ledger_blocked_after_normalization(
    *,
    items: list[WorkItem],
    config: StoreConfig,
    journal: JournalFile,
) -> bool:
    items[:] = _normalize_native_open_statuses(items=items, config=config, journal=journal)
    return _ledger_blocked(items=items, journal=journal)


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
        _ = write_stderr(
            text=f"LEDGER: {finding.check}  {finding.item_id}  {finding.message}\n",
        )
    _ = write_stderr(text="ERROR: pre-dispatch ledger checks failed; dispatch blocked\n")


def _load_items(*, repo: Path) -> list[WorkItem]:
    records = read_work_items(path=store_config(repo=repo))
    return list(materialize_work_items(records=records).values())


def _emit_outcomes(*, outcomes: list[DispatchOutcome], as_json: bool) -> None:
    if as_json:
        payload = [asdict(outcome) for outcome in outcomes]
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return
    if not outcomes:
        _ = write_stdout(text="(nothing dispatched)\n")
        return
    for outcome in outcomes:
        pr_part = f" PR#{outcome.pr_number}" if outcome.pr_number is not None else ""
        line = f"{outcome.work_item_id}  {outcome.status} at {outcome.stage}{pr_part}"
        _ = write_stdout(text=f"{line}  {outcome.detail}\n")


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
    from livespec_orchestrator_beads_fabro.commands._otel_enrich import HoneycombHttpExporter

    config = resolve_receiver_config(environ=dict(os.environ))
    exporter = HoneycombHttpExporter(ingest_key=os.environ.get(_HONEYCOMB_INGEST_KEY_ENV, ""))
    heartbeat = HeartbeatSink(path=heartbeat_path(args=args, repo=repo))
    cost = CostSink(path=cost_sink_path(args=args, repo=repo))
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
        _ = write_stderr(text="ERROR: --janitor must be a JSON array of strings\n")
        return None, False
    parts: list[str] = []
    for part in cast("list[object]", parsed_raw):
        if not isinstance(part, str):
            _ = write_stderr(text="ERROR: --janitor must be a JSON array of strings\n")
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
    # Default None (NOT the bare name "fabro"): a None sentinel means "not
    # explicitly passed -> resolve from LIVESPEC_FABRO_BIN / the .livespec.jsonc
    # dispatcher.fabro_bin key / the absolute default at command entry". An
    # explicit `--fabro-bin <path>` still wins over resolution.
    _ = parser.add_argument("--fabro-bin", dest="fabro_bin", default=None)
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
