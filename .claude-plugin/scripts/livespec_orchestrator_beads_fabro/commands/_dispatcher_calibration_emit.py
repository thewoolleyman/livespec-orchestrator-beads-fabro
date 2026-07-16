"""Calibration telemetry emission and probe helpers for the Dispatcher."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration import (
    build_calibration_record,
    calibration_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_gate import derived_costs
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import journal_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import post_verdict_runner
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "calibration_token_cost",
    "emit_calibration",
    "merged_pr_diff_size",
    "parse_pr_diff_size",
    "read_journal_records_for",
]

# The merged-PR diff-size probe budget: fail-soft to None.
_PR_DIFF_PROBE_TIMEOUT_SECONDS = 60.0


def emit_calibration(  # noqa: PLR0913 — kw-only fail-open stage; each field is an independent caller input.
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
    resolved_runner = post_verdict_runner(runner=runner, token_supplier=token_supplier)
    try:
        record = build_calibration_record(
            item=item,
            outcome=outcome,
            repo_name=repo.name,
            journal_records=read_journal_records_for(args=args, repo=repo),
            wall_clock_seconds=wall_clock_seconds,
            token_cost_micros=calibration_token_cost(args=args, repo=repo, outcome=outcome),
            dispatch_context_size=dispatch_context_size,
            merged_pr_diff_size=merged_pr_diff_size(
                repo=repo,
                outcome=outcome,
                runner=resolved_runner,
            ),
        )
        journal.append(record=calibration_journal_record(record=record))
    except (AttributeError, OSError, RuntimeError) as exc:
        journal.append(
            record={
                "stage": "calibration-error",
                "work_item_id": item.id,
                "reason": f"{type(exc).__name__}",
            }
        )


def read_journal_records_for(
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


def calibration_token_cost(
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


def merged_pr_diff_size(
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
    return parse_pr_diff_size(stdout=result.stdout)


def parse_pr_diff_size(*, stdout: str) -> int | None:
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
