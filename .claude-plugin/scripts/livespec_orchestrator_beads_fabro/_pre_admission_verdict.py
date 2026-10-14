"""Decode the gate's verdict without reproducing any of its authoring rules.

The host transports are Claude's result envelope and Codex's agent-message
JSONL. A failed judgement must carry findings; a transport failure or malformed
verdict is unavailable, never an invented semantic refusal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from returns.result import Failure, Result, Success

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.effects import parse_json

__all__: list[str] = [
    "DodVerdict",
    "parse_judgement",
]


@dataclass(frozen=True, kw_only=True)
class DodVerdict:
    """The semantic verdict and its ordered remedies, as authored by the judge."""

    failure_reason: str | None = None
    remedies: tuple[str, ...] = ()


def parse_judgement(*, response: CommandResult) -> Result[DodVerdict, str]:
    """Decode an explicit pass, failure with findings, or an unavailable reason."""
    if response.exit_code != 0:
        return Failure(f"judgement runner exited {response.exit_code}: {response.stderr.strip()}")
    envelope = _object(text=response.stdout)
    if envelope.get("is_error") is True:
        return Failure(f"judgement runner reported an error: {envelope.get('result', '')}")
    return _decode(text=_assistant_text(stdout=response.stdout, envelope=envelope))


def _decode(*, text: str) -> Result[DodVerdict, str]:
    lines = text.strip().splitlines()
    verdict = _object(text=lines[-1]) if lines else {}
    outcome = verdict.get("outcome")
    if outcome == "passed":
        return Success(DodVerdict())
    if outcome == "unavailable":
        return Failure(str(verdict.get("reason") or "the judge could not complete the judgement"))
    reason = verdict.get("failure_reason")
    if outcome != "failed" or not isinstance(reason, str) or not reason.strip():
        return Failure("unparseable Definition-of-Done judgement verdict")
    remedies = verdict.get("remedies", [reason])
    if not isinstance(remedies, list):
        return Failure("unparseable Definition-of-Done judgement remedies")
    entries = cast("list[object]", remedies)
    if not entries or any(not isinstance(entry, str) or not entry.strip() for entry in entries):
        return Failure("unparseable Definition-of-Done judgement remedies")
    return Success(DodVerdict(failure_reason=reason, remedies=tuple(cast("list[str]", entries))))


def _assistant_text(*, stdout: str, envelope: dict[str, object]) -> str:
    result = envelope.get("result")
    if isinstance(result, str):
        return result
    # Codex emits events for tool calls as well as assistant text. Only a
    # completed agent message can carry the verdict; a tool result cannot.
    messages: list[str] = []
    for line in stdout.splitlines():
        event = _object(text=line)
        item = event.get("item")
        if event.get("type") != "item.completed" or not isinstance(item, dict):
            continue
        record = cast("dict[str, object]", item)
        text = record.get("text")
        if record.get("type") == "agent_message" and isinstance(text, str):
            messages.append(text)
    return messages[-1] if messages else stdout


def _object(*, text: str) -> dict[str, object]:
    value = parse_json(text=text)
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}
