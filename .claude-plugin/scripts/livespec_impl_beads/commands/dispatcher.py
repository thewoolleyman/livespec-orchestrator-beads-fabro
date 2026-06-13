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
"""

import argparse
import json
import os
import sys
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from time import sleep as _real_sleep
from typing import cast

from livespec_impl_beads.commands._config import resolve_store_config
from livespec_impl_beads.commands._cross_repo import is_item_ready, load_manifest
from livespec_impl_beads.commands._dispatcher_engine import (
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
    NotifyPoster,
    notify_terminal,
    terminal_events,
)
from livespec_impl_beads.commands._dispatcher_plan import (
    SiblingClones,
    build_plan,
    host_only_refusal_detail,
    is_host_only_item,
    item_sizing_warnings,
    janitor_checkout_path,
    parse_fleet_members,
    render_goal,
    render_run_config_overlay,
)
from livespec_impl_beads.commands._dispatcher_reflection import reflect
from livespec_impl_beads.commands._dispatcher_spec_checks import run_spec_checks
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
    reflect(
        outcomes=[outcome],
        journal=journal,
        journal_path=_journal_path(args=args, repo=repo),
        spans_path=_spans_path(args=args, repo=repo),
    )
    return exit_code


def _run_loop_command(*, args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    janitor, janitor_ok = _parse_janitor(raw=args.janitor)
    if not janitor_ok:
        return _EXIT_USAGE_ERROR
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
    reflect(
        outcomes=outcomes,
        journal=journal,
        journal_path=_journal_path(args=args, repo=repo),
        spans_path=_spans_path(args=args, repo=repo),
    )
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
        run_id=_run_id(),
        poster=poster if poster is not None else HttpNotifyPoster(),
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
    return sorted(ready, key=lambda item: (item.priority, item.id))


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
    overlay_error = _materialize_overlay(
        committed=_workflow_toml(args=args),
        overlay=overlay_file,
        repo=repo,
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
            # The coarse wall-clock progress watchdog (work-item
            # livespec-impl-beads-oyg): runs `fabro run` while watching the
            # event stream and `fabro rm -f`-es a sustained-no-progress
            # stall (the 7us.6 silent-deadlock backstop). A stall yields a
            # distinct `stalled-no-progress` outcome that h1p's
            # `notify_terminal` alarms on.
            fabro_launcher=WatchedFabroLauncher(),
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


def _materialize_overlay(*, committed: Path, overlay: Path, repo: Path) -> str | None:
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
    """
    env_error = _check_credential_env()
    if env_error is not None:
        return env_error
    siblings = _resolve_sibling_clones(repo=repo)
    if isinstance(siblings, str):
        return siblings
    rendered = render_run_config_overlay(
        committed_text=committed.read_text(encoding="utf-8"),
        workflow_dir=committed.parent.resolve(),
        token=os.environ[_OAUTH_TOKEN_ENV],
        siblings=siblings,
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
