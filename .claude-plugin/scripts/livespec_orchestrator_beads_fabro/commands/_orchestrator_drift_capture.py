"""`orchestrator drift-capture` subcommand — route drift to propose-change.

Per livespec/SPECIFICATION/contracts.md, drift-capture is a CAPTURE interface: the
spec-reader CLI and the propose-change CLI are injected as references,
and impl → spec drift findings are ROUTED to propose-change. Filing is
a machine path; acceptance stays human (the propose-change/revise gate
is the human adjudication mechanism, per the two-flow doctrine).

Each drift finding is wrapped into a `proposal_findings.schema.json`
payload (livespec's propose-change wire contract) and handed to the
injected propose-change CLI as

    <argv...> <topic> --findings-json <tmpfile>
              --project-root <path> --spec-target <path>

Payload wire shape (orchestrator-private):

    {"drifts": [{"topic": "<topic hint>", "name": "<proposal name>",
                 "target_spec_files": ["SPECIFICATION/<file>.md", ...],
                 "summary": "<prose>", "motivation": "<prose>",
                 "proposed_changes": "<prose>"}]}

The injected spec-reader CLI (when supplied) resolves the current spec
version, which is echoed in the result envelope for provenance.
"""

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._orchestrator_shared import (
    CliContext,
    PayloadInvalidError,
    as_non_empty_str_list,
    load_payload,
    require_str,
    resolve_spec_version,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = ["DriftFinding", "run_drift_capture", "validate_drifts"]

_EXIT_PRECONDITION_ERROR = 3


@dataclass(frozen=True, kw_only=True)
class DriftFinding:
    """One validated drift finding from the inbound payload."""

    topic: str
    name: str
    target_spec_files: tuple[str, ...]
    summary: str
    motivation: str
    proposed_changes: str


def run_drift_capture(
    *,
    drifts_json: str,
    propose_change_cli: list[str],
    spec_reader_cli: list[str] | None,
    context: CliContext,
    dry_run: bool,
    as_json: bool,
) -> int:
    """Run the drift-capture subcommand: validate, route, report."""
    drifts = validate_drifts(payload=load_payload(source=drifts_json))
    spec_version = resolve_spec_version(spec_reader_cli=spec_reader_cli, context=context)
    routed: list[dict[str, object]] = []
    for drift in drifts:
        exit_code = 0
        if not dry_run:
            exit_code = _route_one(
                drift=drift,
                propose_change_cli=propose_change_cli,
                context=context,
            )
        routed.append({"topic": drift.topic, "exit_code": exit_code})
    failed = [str(entry["topic"]) for entry in routed if entry["exit_code"] != 0]
    _emit(
        spec_version=spec_version,
        dry_run=dry_run,
        routed=routed,
        failed=failed,
        as_json=as_json,
    )
    return _EXIT_PRECONDITION_ERROR if failed else 0


def validate_drifts(*, payload: object) -> list[DriftFinding]:
    """Validate the inbound payload shape into `DriftFinding`s (or raise)."""
    if not isinstance(payload, dict):
        raise PayloadInvalidError(detail="payload must be a JSON object")
    root = cast("dict[str, Any]", payload)
    raw_drifts: object = root.get("drifts")
    if not isinstance(raw_drifts, list):
        raise PayloadInvalidError(detail="payload.drifts must be a list")
    entries = cast("list[Any]", raw_drifts)
    return [_validate_drift(entry=entry, index=index) for index, entry in enumerate(entries)]


def _validate_drift(*, entry: object, index: int) -> DriftFinding:
    where = f"payload.drifts[{index}]"
    if not isinstance(entry, dict):
        raise PayloadInvalidError(detail=f"{where} must be a JSON object")
    obj = cast("dict[str, Any]", entry)
    return DriftFinding(
        topic=require_str(obj=obj, key="topic", where=where),
        name=require_str(obj=obj, key="name", where=where),
        target_spec_files=_validate_target_files(obj=obj, where=where),
        summary=require_str(obj=obj, key="summary", where=where),
        motivation=require_str(obj=obj, key="motivation", where=where),
        proposed_changes=require_str(obj=obj, key="proposed_changes", where=where),
    )


def _validate_target_files(*, obj: dict[str, Any], where: str) -> tuple[str, ...]:
    files = as_non_empty_str_list(value=obj.get("target_spec_files"))
    if files is None:
        raise PayloadInvalidError(
            detail=f"{where}.target_spec_files must be a non-empty list of non-empty strings",
        )
    return tuple(files)


def _route_one(
    *,
    drift: DriftFinding,
    propose_change_cli: list[str],
    context: CliContext,
) -> int:
    findings_payload = {
        "findings": [
            {
                "name": drift.name,
                "target_spec_files": list(drift.target_spec_files),
                "summary": drift.summary,
                "motivation": drift.motivation,
                "proposed_changes": drift.proposed_changes,
            },
        ],
    }
    with tempfile.TemporaryDirectory(prefix="drift-capture-") as scratch:
        findings_path = Path(scratch) / "findings.json"
        _ = findings_path.write_text(json.dumps(findings_payload), encoding="utf-8")
        argv = [
            *propose_change_cli,
            drift.topic,
            "--findings-json",
            str(findings_path),
            "--project-root",
            str(context.project_root),
            "--spec-target",
            str(context.spec_root),
        ]
        completed = subprocess.run(  # noqa: S603 — fixed flag set over a caller-injected argv.
            argv,
            capture_output=True,
            text=True,
            check=False,
        )
    if completed.returncode != 0:
        detail = completed.stderr.strip()
        _ = write_stderr(
            text=f"ERROR: propose-change {drift.topic!r} exited {completed.returncode}: {detail}\n",
        )
    return completed.returncode


def _emit(
    *,
    spec_version: int,
    dry_run: bool,
    routed: list[dict[str, object]],
    failed: list[str],
    as_json: bool,
) -> None:
    if as_json:
        payload = {
            "spec_version": spec_version,
            "dry_run": dry_run,
            "routed": routed,
            "failed": failed,
        }
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return
    verb = "would route" if dry_run else "routed"
    for entry in routed:
        status = "ok" if entry["exit_code"] == 0 else f"FAILED (exit {entry['exit_code']})"
        _ = write_stdout(text=f"{verb} {entry['topic']}: {status}\n")
