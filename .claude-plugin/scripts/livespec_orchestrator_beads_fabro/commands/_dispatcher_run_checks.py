"""Dispatcher check runners and dispatch preflight helpers."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_bin
from livespec_orchestrator_beads_fabro.commands._cross_repo import load_manifest
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_checks import run_janitor_checks
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_checks import (
    LedgerFinding,
    run_ledger_checks,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import ready_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_otel_wiring import parse_janitor
from livespec_orchestrator_beads_fabro.commands._dispatcher_spec_checks import run_spec_checks
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "dispatch_preamble",
    "requested_items_preflight_error",
    "run_janitor_check",
    "run_ledger_check",
    "run_spec_check",
]

_EXIT_FAILURE = 1
_EXIT_USAGE_ERROR = 2
_EXIT_PRECONDITION_ERROR = 3

# The active platform's path separators (os.altsep is None on POSIX). Built as
# a tuple of the truthy separators so the "does this string carry a directory
# component" test is a single `any(...)` with no unreachable `os.altsep` arc.
_PATH_SEPARATORS: tuple[str, ...] = tuple(sep for sep in (os.sep, os.altsep) if sep)


def run_ledger_check(*, args: argparse.Namespace) -> int:
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    findings = run_ledger_checks(items=load_items(repo=project_root))
    return _emit_check_findings(findings=findings, as_json=args.as_json, label="ledger")


def run_spec_check(*, args: argparse.Namespace) -> int:
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    spec_root = (
        Path(args.spec_root) if args.spec_root is not None else project_root / "SPECIFICATION"
    )
    findings = run_spec_checks(
        items=load_items(repo=project_root),
        spec_root=spec_root,
        manifest=load_manifest(project_root=project_root),
    )
    return _emit_check_findings(findings=findings, as_json=args.as_json, label="spec")


def run_janitor_check(*, args: argparse.Namespace) -> int:
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


def dispatch_preamble(
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
    janitor, janitor_ok = parse_janitor(raw=args.janitor)
    if not janitor_ok:
        return None, _EXIT_USAGE_ERROR
    args.fabro_bin = _resolve_fabro_bin_for(args=args, repo=repo)
    fabro_error = _fabro_preflight_error(fabro_bin=args.fabro_bin)
    if fabro_error is not None:
        _ = write_stderr(text=fabro_error)
        return None, _EXIT_PRECONDITION_ERROR
    return janitor, None


def requested_items_preflight_error(
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
    ready_ids = {item.id for item in ready_items(items=items, repo=repo)}
    not_ready = requested_ids - ready_ids
    if not_ready:
        missing = ", ".join(sorted(not_ready))
        return f"ERROR: requested work-item(s) not in the ready set: {missing}\n"
    return None
