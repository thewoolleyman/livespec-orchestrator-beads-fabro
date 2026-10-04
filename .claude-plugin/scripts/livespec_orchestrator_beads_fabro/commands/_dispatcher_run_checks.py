"""Dispatcher check runners and dispatch preflight helpers."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._config import (
    FactoryTarget,
    resolve_fabro_bin,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._cross_repo import load_manifest
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_validation import (
    schema_validation_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    invoker_from_args,
    require_invoker_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_checks import run_janitor_checks
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_checks import (
    LedgerFinding,
    run_ledger_checks,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    apply_native_status_remaps,
    load_items,
    plan_native_status_remaps,
    project_native_status_remaps,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_gate import run_ledger_gate
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import ready_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_orphaned_run_check import (
    orphaned_factory_run_findings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_otel_wiring import parse_janitor
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_readiness_diagnostics import (
    not_ready_requested_items_error,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_pass import (
    reconcile_runs_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import (
    rework_redispatch_eligible_ids,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_capabilities import (
    sandbox_capabilities_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_spec_checks import run_spec_checks
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_gate import (
    step_discipline_refusal,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout
from livespec_orchestrator_beads_fabro.store import WorkItemComment, read_work_item_comments
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "dispatch_preamble",
    "requested_items_preflight_error",
    "run_janitor_check",
    "run_ledger_check",
    "run_ledger_normalize",
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
    """Run the pure Ledger invariants, then the factory-inventory one.

    `orphaned-factory-run` is appended here rather than inside
    `run_ledger_checks` because that function is a PURE function of the rows,
    and three other surfaces — the pre-dispatch gate, the pre-push conformance
    gate, and the `status_conformance` dev-tooling check — call it precisely
    for that. Surveying a factory from inside it would put a network round trip
    on all three. This is the surface that owns the survey; a repo declaring no
    factory still performs no I/O.
    """
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    items = load_items(repo=project_root)
    config = store_config(repo=project_root)
    comments_by_item = _load_comments_by_item(config=config, items=items)
    findings = run_ledger_checks(items=items, comments_by_item=comments_by_item)
    findings.extend(orphaned_factory_run_findings(repo=project_root))
    return _emit_check_findings(findings=findings, as_json=args.as_json, label="ledger")


def run_ledger_normalize(*, args: argparse.Namespace) -> int:
    """Self-heal a tenant's beads-native statuses to their livespec lifecycle.

    Reuses the dispatch-path primitive `plan_native_status_remaps`: `open` →
    `backlog` and `in_progress` → `active` (every other status is left
    untouched). With `--dry-run` the remaps are planned and projected in
    memory but NOT written; otherwise each remap is applied via the store's
    `update_work_item_status` seam and the tenant is reloaded. Residual
    non-conformant findings (statuses no remap can map) are then computed
    over the resulting rows and reported alongside the remaps. Exit 1 when a
    non-skipped residual finding remains after normalization, else 0 — the
    same signal `run_ledger_check` uses. `--gate` short-circuits to the
    always-run pre-push gate (`run_ledger_gate`): a fail-soft, auto-heal-loud
    conformance gate that heals the two safe transient remaps IN PLACE, prints
    each, and blocks only on residual drift (exit 0 clean/healed, 1 residual,
    2 could-not-check).
    """
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    if args.gate:
        return run_ledger_gate(project_root=project_root)
    items = load_items(repo=project_root)
    remaps = plan_native_status_remaps(items=items)
    if args.dry_run:
        resulting = project_native_status_remaps(items=items, remaps=remaps)
    else:
        apply_native_status_remaps(remaps=remaps, config=store_config(repo=project_root))
        resulting = load_items(repo=project_root)
    residual = run_ledger_checks(items=resulting)
    return _emit_normalize_summary(
        remaps=remaps,
        residual=residual,
        dry_run=args.dry_run,
        as_json=args.as_json,
    )


def _emit_normalize_summary(
    *,
    remaps: list[dict[str, str]],
    residual: list[LedgerFinding],
    dry_run: bool,
    as_json: bool,
) -> int:
    """Emit the normalize summary (JSON object or human lines); exit 1 on residual."""
    if as_json:
        payload = {
            "dry_run": dry_run,
            "remapped": remaps,
            "residual": [asdict(finding) for finding in residual],
        }
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        _emit_normalize_text(remaps=remaps, residual=residual, dry_run=dry_run)
    actionable = any(finding.severity != "skipped" for finding in residual)
    return _EXIT_FAILURE if actionable else 0


def _load_comments_by_item(
    *,
    config: StoreConfig,
    items: list[WorkItem],
) -> dict[str, tuple[WorkItemComment, ...]]:
    return {
        item.id: read_work_item_comments(path=config, work_item_id=item.id)
        for item in items
        if item.status != "done"
    }


def _emit_normalize_text(
    *,
    remaps: list[dict[str, str]],
    residual: list[LedgerFinding],
    dry_run: bool,
) -> None:
    verb = "would remap" if dry_run else "remapped"
    if remaps:
        for remap in remaps:
            transition = f"{remap['from']} -> {remap['to']}"
            line = f"{verb}  {remap['item_id']}  {transition}  ({remap['reason']})\n"
            _ = write_stdout(text=line)
    else:
        _ = write_stdout(text="(nothing to normalize)\n")
    for finding in residual:
        severity = finding.severity.upper()
        line = f"RESIDUAL  {severity}  {finding.check}  {finding.item_id}  {finding.message}\n"
        _ = write_stdout(text=line)
    if not residual:
        _ = write_stdout(text="(no residual findings)\n")


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


def _resolve_fabro_factory_for(*, args: argparse.Namespace, repo: Path) -> FactoryTarget:
    factory = cast("str | None", getattr(args, "factory", None))
    return resolve_fabro_factory(cwd=repo, factory=factory)


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
    """Shared dispatch/loop entry validation: janitor spec, declaration, engine binary.

    Returns `(janitor, None)` to proceed (the parsed janitor override to thread
    downstream, which `build_plan` resolves against the repository's committed
    check-suite declaration), or `(None, exit_code)` to short-circuit the
    command: `_EXIT_USAGE_ERROR` for a malformed `--janitor`,
    `_EXIT_PRECONDITION_ERROR` for a declaration that does not satisfy the
    contract schema version this build requires, or for an unresolvable fabro
    engine binary. The fabro check runs BEFORE the caller arms the receiver,
    prepares the store, or admits anything, so a misconfigured engine binary
    refuses provably before admission (ready -> active) rather than stranding an
    item at active. Sets `args.fabro_bin` to the resolved path as a side effect.

    The schema-validation pass is where a defective declaration is refused, and
    it supersedes the per-key check-suite refusal that used to stand here: the
    ratified pass enumerates EVERY `Defective` point in one message, so an
    adopter learns its whole unmet set at once rather than one dispatch at a
    time. It gates ADMISSION only -- the reconcile valve, which carries an
    ALREADY-ADMITTED item forward, keeps its own narrow check-suite refusal, so
    an expectation a later build adds cannot strand a mid-pipeline item.

    The sandbox-capability refusal stands beside it for the node-timeout
    reason: `dispatcher.sandbox_capabilities` is the set the `dod_gate` node
    computes its missing-capability finding FROM, so a hyphenated or
    capitalised name there never errors — it fails to match, and the gate
    reports a finding against an item that was correct. An absent mirror is an
    answer and never refuses.

    The invoker refusal runs FIRST of all, ahead of even the janitor parse:
    with `dispatcher.require_invoker` true, a fallback-only invocation must be
    refused before ANY store mutation, journal write, or run creation, so that
    the refusal cannot itself leave a half-performed act or an unattributed
    record behind (the journal invoker attribution contract in contracts.md).

    Because this is the head of every `dispatch` AND of every `loop` iteration
    (`_start_loop` calls it before the loop selects any candidate), the single
    reconciliation pass at the end of it is BOTH "once per loop tick before
    selection" and "once before admission". A second call in the loop command
    would survey the same inventory twice for one answer.

    The closed step set's whole pre-dispatch discipline -- both preflights,
    their committed waivers, and the cross-dispatch persistence of a degraded
    post-merge outcome -- runs LAST, as one call into `_dispatcher_step_gate`.
    It is one call rather than a step-per-branch ladder here because the set is
    extensible by ratification: a fourth step should change the gate's own
    sequence, not this function.
    """
    invoker_refusal = require_invoker_refusal(args=args, repo=repo)
    if invoker_refusal is not None:
        _ = write_stderr(text=invoker_refusal)
        return None, _EXIT_PRECONDITION_ERROR
    janitor, janitor_ok = parse_janitor(raw=args.janitor)
    if not janitor_ok:
        return None, _EXIT_USAGE_ERROR
    # ONE arm, two refusals, because both answer one question -- does this
    # repository's committed `.livespec.jsonc` admit a dispatch at all -- and
    # both are read from that one file in this one pass. The ORDER is
    # deliberate: the integration-schema pass enumerates EVERY defective point
    # in one message, so reporting a capability-mirror typo ahead of it would
    # hand an adopter one fault out of a file carrying several.
    config_refusal = schema_validation_refusal(
        args=args, repo=repo
    ) or sandbox_capabilities_refusal(repo=repo)
    if config_refusal is not None:
        _ = write_stderr(text=config_refusal)
        return None, _EXIT_PRECONDITION_ERROR
    args.fabro_bin = _resolve_fabro_bin_for(args=args, repo=repo)
    args.fabro_factory_target = _resolve_fabro_factory_for(args=args, repo=repo)
    fabro_error = _fabro_preflight_error(fabro_bin=args.fabro_bin)
    if fabro_error is not None:
        _ = write_stderr(text=fabro_error)
        return None, _EXIT_PRECONDITION_ERROR
    step_refusal = step_discipline_refusal(
        args=args, repo=repo, identity=invoker_from_args(args=args)
    )
    if step_refusal is not None:
        _ = write_stderr(text=step_refusal)
        return None, _EXIT_PRECONDITION_ERROR
    # Reconciliation runs LAST, after every refusal above, so a refused
    # invocation keeps its zero-side-effect guarantee. It is not a refusal
    # itself and cannot become one: `reconcile_runs_pass` absorbs its own
    # failures into a journal record and returns, because an unsurveyable
    # factory says nothing about whether this item may be dispatched.
    _ = reconcile_runs_pass(args=args, repo=repo)
    return janitor, None


def requested_items_preflight_error(
    *,
    requested_ids: set[str],
    items: list[WorkItem],
    repo: Path,
    journal: JournalFile,
) -> str | None:
    """Return an operator-facing error string if a requested item fails preflight, else None.

    Validates in order: (1) items absent from the target-tenant entirely →
    target-tenant mismatch error; (2) items present in the tenant but neither
    `ready` nor rework-re-dispatch-eligible → not-in-ready-set error. A marked,
    lock-less `active` row passes because `--item` narrows the selection rather
    than bypassing it: the rework leg of the same drain is a route the named id
    is eligible THROUGH. Returns None when every requested id is dispatchable.
    """
    all_ids = {item.id for item in items}
    missing_from_tenant = requested_ids - all_ids
    if missing_from_tenant:
        missing_text = ", ".join(sorted(missing_from_tenant))
        return (
            f"ERROR: work-item(s) {missing_text} not found in the target-tenant "
            f"({repo.name}); --target-repo and --item must reference the same tenant\n"
        )
    eligible_ids = {item.id for item in ready_items(items=items, repo=repo)}
    eligible_ids |= rework_redispatch_eligible_ids(repo=repo, items=items, journal=journal)
    not_ready = requested_ids - eligible_ids
    if not_ready:
        return not_ready_requested_items_error(requested_ids=not_ready, items=items, repo=repo)
    return None
