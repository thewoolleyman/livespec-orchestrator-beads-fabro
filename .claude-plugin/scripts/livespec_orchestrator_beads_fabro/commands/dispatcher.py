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
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from livespec_runtime.github_auth.errors import GithubAppAuthError

from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import (
    admit_and_select,
    autonomous_armed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_autonomous import (
    arm_autonomous_for_loop,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration_emit import (
    emit_calibration,
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
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    GithubTokenEnvRunner,
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    emit_outcomes,
    ledger_blocked_after_normalization,
    load_items,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop import dispatch_one
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    candidates,
    is_dispatch_candidate,
    janitor_core_ref,
    post_run_dispositions,
    prepare,
    ready_items,
    run_id,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_notify import (
    HttpNotifyPoster,
    NotifyPoster,
    notify_terminal,
    terminal_events,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_otel_wiring import (
    ensure_otel_receiver,
    parse_janitor,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    journal_path,
    spans_path,
    store_config,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_post_verdict import (
    reflector_oob_after_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection import reflect
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_checks import (
    dispatch_preamble,
    requested_items_preflight_error,
    run_janitor_check,
    run_ledger_check,
    run_spec_check,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    github_token_supplier,
    self_update_after_verdict,
)
from livespec_orchestrator_beads_fabro.io import write_stderr

# Compatibility alias for existing dispatcher tests and dispatch-path monkeypatches.
_github_token_supplier = github_token_supplier


__all__: list[str] = [
    "bounce_blocked",
    "bounce_non_convergence_to_backlog",
    "candidates",
    "complete_and_accept",
    "dispatch_one",
    "dispatch_preamble",
    "emit_calibration",
    "host_only_refusal",
    "is_dispatch_candidate",
    "janitor_core_ref",
    "load_items",
    "main",
    "parse_janitor",
    "post_run_dispositions",
    "prepare",
    "ready_items",
    "reflector_oob_after_verdict",
    "requested_items_preflight_error",
    "run_id",
    "run_janitor_check",
    "run_ledger_check",
    "run_spec_check",
    "warn_item_sizing",
]
_EXIT_FAILURE = 1
_EXIT_USAGE_ERROR = 2
_EXIT_PRECONDITION_ERROR = 3


def main(*, argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.subcommand == "ledger-check":
        return run_ledger_check(args=args)
    if args.subcommand == "spec-check":
        return run_spec_check(args=args)
    if args.subcommand == "janitor-check":
        return run_janitor_check(args=args)
    if args.subcommand == "dispatch":
        return _run_dispatch_command(args=args)
    return _run_loop_command(args=args)


def _run_dispatch_command(*, args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    janitor, preamble_exit = dispatch_preamble(args=args, repo=repo)
    if preamble_exit is not None:
        return preamble_exit
    _ = ensure_otel_receiver(args=args, repo=repo)
    prepared = prepare(args=args, repo=repo)
    if prepared is None:
        return _EXIT_PRECONDITION_ERROR
    items, journal = prepared
    if not args.skip_ledger_check and ledger_blocked_after_normalization(
        items=items,
        config=store_config(repo=repo),
        journal=journal,
    ):
        return _EXIT_FAILURE
    ready = ready_items(items=items, repo=repo)
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
        dispatch_one(args=args, repo=repo, item=item, journal=journal, janitor=janitor)
        for item in admission.admitted
    ]
    outcome = (admission.refused + dispatched)[0]
    emit_outcomes(outcomes=[outcome], as_json=args.as_json)
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
    reflector_oob_after_verdict(args=args, repo=repo, journal=journal)
    return exit_code


def _run_loop_command(*, args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    janitor, preamble_exit = dispatch_preamble(args=args, repo=repo)
    if preamble_exit is not None:
        return preamble_exit
    _ = ensure_otel_receiver(args=args, repo=repo)
    prepared = prepare(args=args, repo=repo)
    if prepared is None:
        return _EXIT_PRECONDITION_ERROR
    items, journal = prepared
    if not args.skip_ledger_check and ledger_blocked_after_normalization(
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
        preflight_error = requested_items_preflight_error(
            requested_ids=requested_ids, items=items, repo=repo
        )
        if preflight_error is not None:
            _ = write_stderr(text=preflight_error)
            return _EXIT_PRECONDITION_ERROR
    selected_candidates = candidates(args=args, items=items, repo=repo)[: args.budget]
    # The admission valve drains the candidate set up to the per-repo WIP cap:
    # host-only items are routed away, manual / unresolvable items are held +
    # surfaced, and the highest-rank admission-eligible items fill the free
    # slots (ready -> active, assignee set). Capacity-deferred items simply
    # wait for the next pass.
    admission = admit_and_select(
        repo=repo,
        items=items,
        candidates=selected_candidates,
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
                dispatch_one,
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
        emit_outcomes(outcomes=[], as_json=args.as_json)
        return 0
    emit_outcomes(outcomes=outcomes, as_json=args.as_json)
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
    reflector_oob_after_verdict(args=args, repo=repo, journal=journal)
    return exit_code


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
        run_id=run_id(),
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
