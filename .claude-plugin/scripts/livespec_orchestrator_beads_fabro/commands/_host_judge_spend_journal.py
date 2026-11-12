"""Write non-persisted Claude responses where the host spend emitter reads them.

Host judgements deliberately use ``--no-session-persistence``, so Claude never
writes the transcript the spend emitter normally consumes.  This journal keeps
that isolation while preserving the stream-json assistant events, one response
per line, for the emitter's next cycle.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from uuid import uuid4

__all__: list[str] = [
    "HostJudgeSpendJournal",
    "append_assistant_event",
    "append_result_event",
    "append_stream_event",
    "is_claude_agent",
    "spend_journal_name",
    "start_spend_journal",
]

_JOURNAL_DIRECTORY = Path(".claude") / "spend-journal"
_FIRST_PROMPT_LIMIT = 2_000
_CLAUDE_AGENT = "claude-acp"


@dataclass(frozen=True, kw_only=True)
class HostJudgeSpendJournal:
    """One host launch's journal destination and generated session identity."""

    path: Path
    session_id: str


def start_spend_journal(
    *, home: Path, name: str, cwd: Path, first_prompt: str
) -> HostJudgeSpendJournal:
    """Create a journal with its emitter-required header before launching Claude."""
    session_id = uuid4().hex
    path = home / _JOURNAL_DIRECTORY / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    header: dict[str, object] = {
        "session_id": session_id,
        "name": name,
        "cwd": str(cwd),
        "started_at": _utc_now(),
        "first_prompt": first_prompt[:_FIRST_PROMPT_LIMIT],
        "final_usage_line": True,
    }
    _append(path=path, record=header, mode="x")
    return HostJudgeSpendJournal(path=path, session_id=session_id)


def append_assistant_event(*, journal: HostJudgeSpendJournal, line: str) -> None:
    """Append one timestamped Claude assistant event, ignoring other stream records."""
    try:
        decoded: object = json.loads(line)
    except ValueError:
        return
    if not isinstance(decoded, dict):
        return
    record = cast("dict[str, object]", decoded)
    if not _is_spendable_assistant_event(record=record):
        return
    _append(path=journal.path, record={**record, "ts": _utc_now()}, mode="a")


def append_result_event(*, journal: HostJudgeSpendJournal, line: str) -> None:
    """Append Claude's closing usage and the assistant message ids it completes."""
    try:
        decoded: object = json.loads(line)
    except ValueError:
        return
    if not isinstance(decoded, dict):
        return
    record = cast("dict[str, object]", decoded)
    usage = record.get("usage")
    if record.get("type") != "result" or not isinstance(usage, Mapping):
        return
    final_usage = cast("Mapping[str, object]", usage)
    _append(
        path=journal.path,
        record={
            "type": "result",
            "usage": final_usage,
            "message_ids": _assistant_message_ids(path=journal.path),
            "ts": _utc_now(),
        },
        mode="a",
    )


def append_stream_event(*, journal: HostJudgeSpendJournal, line: str) -> None:
    """Record whichever spend-relevant event one Claude stream line carries."""
    append_assistant_event(journal=journal, line=line)
    append_result_event(journal=journal, line=line)


def is_claude_agent(*, agent_id: str | None) -> bool:
    """Whether an ACP candidate is Claude and emits the journalled stream format."""
    return agent_id == _CLAUDE_AGENT


def spend_journal_name(*, caller: str | None, cwd: Path) -> str:
    """The purpose carrier the emitter uses to attribute a host judgement."""
    role = "host_judgement" if caller is None else caller
    return f"purpose:{role}@{cwd.name}"


def _is_spendable_assistant_event(*, record: dict[str, object]) -> bool:
    """Whether an event carries the exact Claude response fields the emitter prices."""
    message = record.get("message")
    if record.get("type") != "assistant" or not isinstance(message, Mapping):
        return False
    payload = cast("Mapping[str, object]", message)
    return (
        isinstance(payload.get("id"), str)
        and isinstance(payload.get("model"), str)
        and isinstance(payload.get("usage"), Mapping)
    )


def _assistant_message_ids(*, path: Path) -> list[str]:
    return [
        cast(str, cast(Mapping[str, object], json.loads(line)["message"])["id"])
        for line in path.read_text(encoding="utf-8").splitlines()[1:]
    ]


def _append(*, path: Path, record: Mapping[str, object], mode: str) -> None:
    with path.open(mode, encoding="utf-8") as journal:
        _ = journal.write(json.dumps(record) + "\n")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
