"""`dispatcher.py idle-slot-audit` — the read-only rendering of the audit.

The clause fixes two things about this surface, and both are about what a
reader is allowed to conclude from an absence.

AN UNREADABLE BOARD IS PRINTED AS UNKNOWN, never as zero. A zero live count
and a zero queued count are exactly the reading that makes the finding line
fire, so a board nobody could read must not render as an empty one.

THE FINDING LINE IS THE LAST LINE, or there is no finding line. A reader
scanning the tail for it must not find a stale one, so it is emitted from the
one place the audit computes it and nowhere else.

The exit status distinguishes the three configuration outcomes: a well-formed
audit and an absent object both exit 0 — the audit found what it found, and an
unconfigured repository has nothing to audit — while a MALFORMED object exits
non-zero, because the clause makes that a refusal naming the offending key
rather than an empty result.
"""

from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_audit import (
    EntryAudit,
    IdleSlotAuditResult,
    IdleSlotFinding,
    idle_slot_audit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_classify import (
    ClassifiedChild,
)
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "CONFIGURATION_REFUSAL_EXIT",
    "NOT_CONFIGURED_LINE",
    "add_idle_slot_audit_arguments",
    "idle_slot_audit_command",
    "render_idle_slot_audit",
    "render_idle_slot_audit_json",
    "run_idle_slot_audit_command",
]

CONFIGURATION_REFUSAL_EXIT = 2
NOT_CONFIGURED_LINE = "idle-slot audit: dispatcher.idle_slot_audit is not configured"
_UNKNOWN = "unknown"


def add_idle_slot_audit_arguments(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--repo", dest="repo", default=None)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")


def run_idle_slot_audit_command(*, args: argparse.Namespace) -> int:
    """Print the per-entry classification and the finding line; write nothing."""
    project_root = Path(args.repo) if args.repo is not None else Path.cwd()
    result = idle_slot_audit(project_root=project_root)
    text = (
        render_idle_slot_audit_json(result=result)
        if args.as_json
        else render_idle_slot_audit(result=result)
    )
    _ = write_stdout(text=text)
    if result.configuration_finding is not None:
        return CONFIGURATION_REFUSAL_EXIT
    return 0


def idle_slot_audit_command(*, project_root: Path) -> str:
    """The exact read-only invocation an inspection handoff hands an operator."""
    wrapper = Path(__file__).parents[2] / "bin" / "dispatcher.py"
    return (
        f"python3 {shlex.quote(str(wrapper))} idle-slot-audit "
        f"--repo {shlex.quote(str(project_root))} --json"
    )


def render_idle_slot_audit_json(*, result: IdleSlotAuditResult) -> str:
    """The whole result as JSON, with the one set-valued field rendered sorted.

    `live_item_ids` is a `frozenset`, which JSON has no form for. It is
    projected to a SORTED list rather than left to an encoder hook so the
    payload is deterministic: an unordered rendering would make two invocations
    against an unchanged board disagree byte for byte.
    """
    payload: dict[str, Any] = asdict(result)
    board = cast("dict[str, Any]", payload["board"])
    board["live_item_ids"] = sorted(result.board.live_item_ids)
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render_idle_slot_audit(*, result: IdleSlotAuditResult) -> str:
    if result.configuration_finding is not None:
        return f"idle-slot audit refused: {result.configuration_finding}\n"
    if not result.configured:
        return f"{NOT_CONFIGURED_LINE}\n"
    lines = [f"idle-slot audit — factory {result.factory}", _board_line(result=result)]
    for entry in result.entries:
        lines.extend(_entry_lines(entry=entry))
    finding = result.finding
    if finding is not None:
        lines.append(_finding_line(finding=finding))
    return "".join(f"{line}\n" for line in lines)


def _finding_line(*, finding: IdleSlotFinding) -> str:
    """The last line, naming the factory, its live count and the child ids."""
    children = ", ".join(finding.child_ids)
    return (
        f"FINDING: factory {finding.factory} shows no runnable run with "
        f"{finding.live_count} live row(s) attributed to the Fabro server; "
        f"dispatchable or stale-edge priority children: {children}"
    )


def _board_line(*, result: IdleSlotAuditResult) -> str:
    board = result.board
    if not board.observable:
        return f"board: UNOBSERVABLE — live {_UNKNOWN}, queued {_UNKNOWN}"
    return f"board: live {board.live_count}, queued {board.queued_count}"


def _entry_lines(*, entry: EntryAudit) -> list[str]:
    subject = (
        f"epic {entry.epic}" if entry.epic is not None else f"items {','.join(entry.item_ids)}"
    )
    header = f"{entry.repo}  {subject}"
    if entry.unreadable:
        return [f"{header}  UNREADABLE-TENANT at {entry.root}"]
    lines = [header]
    lines.extend(f"  {_child_line(child=child)}" for child in entry.children)
    lines.extend(f"  MISSING  {item_id}  absent from its tenant" for item_id in entry.missing_ids)
    return lines


def _child_line(*, child: ClassifiedChild) -> str:
    parts = [child.id, child.classification, f"status={child.status}"]
    if child.blockers:
        shown = ", ".join(f"{blocker.id}({blocker.status})" for blocker in child.blockers)
        parts.append(f"open-blocks={shown}")
    if child.reason is not None:
        parts.append(f"reason={child.reason}")
    return "  ".join(parts)
