from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro._beads_client import (
    BeadsClient,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._otel_scrub import scrub as _scrub
from livespec_orchestrator_beads_fabro.commands._reflector_findings_parse import ReflectorFinding
from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "OpenItem",
    "file_new",
    "label_index",
    "make_client",
    "record_labels",
    "severity_priority",
]

_LABEL_REFLECTION = "reflection"
_LABEL_FINGERPRINT_PREFIX = "fingerprint:"
_LABEL_REFLECTION_MUTE = "reflection-mute"
_PRIORITY_CRITICAL = 1
_PRIORITY_WARN = 2
_PRIORITY_INFO = 4


def severity_priority(*, severity: str) -> int:
    if severity == "critical":
        return _PRIORITY_CRITICAL
    if severity == "warn":
        return _PRIORITY_WARN
    return _PRIORITY_INFO


@dataclass(frozen=True, kw_only=True)
class OpenItem:
    issue_id: str
    closed: bool
    muted: bool


def file_new(
    *, finding: ReflectorFinding, fingerprint_hex: str, client: BeadsClient, repo: Path
) -> str:
    _ = repo
    config = _store_config(repo=repo)
    title = f"[reflection] {finding.category}: {_scrub(value=finding.subject)}"
    body = _scrub(value=finding.detail) if finding.detail else _scrub(value=finding.subject)
    issue_id = new_work_item_id(prefix=config.prefix)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="bug" if finding.severity == "critical" else "task",
            title=title,
            description=body,
            priority=severity_priority(severity=finding.severity),
            assignee=None,
            created_at=_now_iso(),
            labels=[_LABEL_REFLECTION, f"{_LABEL_FINGERPRINT_PREFIX}{fingerprint_hex}"],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )
    return issue_id


def make_client(*, repo: Path) -> BeadsClient:
    return make_beads_client(config=_store_config(repo=repo))


def _store_config(*, repo: Path) -> StoreConfig:
    return resolve_store_config(cwd=repo, work_items_arg=None)


def label_index(*, client: BeadsClient) -> dict[str, OpenItem]:
    index: dict[str, OpenItem] = {}
    for record in client.list_issues():
        labels = record_labels(record=record)
        hex_key = _fingerprint_label_value(labels=labels)
        if hex_key is None:
            continue
        status = record.get("status")
        closed = status == "closed"
        muted = _LABEL_REFLECTION_MUTE in labels
        issue_id = record.get("id")
        if isinstance(issue_id, str):
            index[hex_key] = OpenItem(issue_id=issue_id, closed=closed, muted=muted)
    return index


def record_labels(*, record: dict[str, object]) -> list[str]:
    raw = record.get("labels")
    if not isinstance(raw, list):
        return []
    return [label for label in cast("list[object]", raw) if isinstance(label, str)]


def _fingerprint_label_value(*, labels: list[str]) -> str | None:
    for label in labels:
        if label.startswith(_LABEL_FINGERPRINT_PREFIX):
            return label[len(_LABEL_FINGERPRINT_PREFIX) :]
    return None


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
