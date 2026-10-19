"""The `ledger-normalize` command: self-heal beads-native statuses, then report.

Moved VERBATIM out of `_dispatcher_run_checks` once that module reached its file
LLOC ceiling. The cut is along a real cohesion seam rather than at a convenient
line: `_dispatcher_run_checks` is the DISPATCH PREFLIGHT — the preamble every
`dispatch` and every `loop` tick runs, plus the three read-only `*-check`
surfaces that share its findings emitter — while this is a MUTATING operator
command that heals a tenant's statuses in place and shares nothing with the
preflight but the repository root it reads.

The public entry point moves with the two private emitters that ONLY it uses, so
nothing crosses the new boundary but public names. `_emit_check_findings` stayed
behind, because `run_ledger_check` and `run_spec_check` share it and a helper
shared by several public entry points belongs with them.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

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
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "run_ledger_normalize",
]

_EXIT_FAILURE = 1


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
