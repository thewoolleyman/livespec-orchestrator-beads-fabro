"""Admission rules for ledger-held typed plan pointers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol, cast

from livespec_orchestrator_beads_fabro.commands._plan_result_reference import (
    parse_result_reference,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import (
    ResultReferenceRefusal,
)
from livespec_orchestrator_beads_fabro.effects import (
    IsoDatetimeParseFailure,
    parse_iso_datetime,
)

if TYPE_CHECKING:
    from typing import Any

__all__: list[str] = [
    "NextActionRefusal",
    "NextActionShape",
    "validate_next_action",
]

_EXECUTABLE_KINDS = ("impl", "spec-op", "proof", "review", "archive", "await")
_LEGACY_KINDS = ("impl", "spec-op", "human", "none")
_ALL_KINDS = (*_EXECUTABLE_KINDS, "human", "none")
_AWAIT_PREFIXES = ("run", "gate", "item", "epic")


class NextActionShape(Protocol):
    """The pointer fields needed by validation, without an import cycle."""

    @property
    def kind(self) -> str: ...

    @property
    def ref(self) -> str: ...

    @property
    def required_result(self) -> object: ...

    @property
    def budget(self) -> object: ...


@dataclass(frozen=True, kw_only=True)
class NextActionRefusal:
    """Why a writer refused to persist one typed next action."""

    detail: str


def validate_next_action(
    *,
    action: NextActionShape,
    epic_id: str,
    legacy_tracking: object,
) -> NextActionRefusal | None:
    """Admit one complete typed pointer, including its tracking contract."""
    refusal: NextActionRefusal | None = None
    result_is_legacy = action.required_result is legacy_tracking
    budget_is_legacy = action.budget is legacy_tracking
    if action.kind not in _ALL_KINDS:
        refusal = _refusal(detail=f"unknown next_action kind {action.kind!r}")
    elif result_is_legacy != budget_is_legacy:
        refusal = _refusal(detail="required_result and budget must be recorded together")
    elif result_is_legacy:
        if action.kind not in _LEGACY_KINDS:
            refusal = _refusal(detail=f"{action.kind} requires required_result and budget")
    else:
        refusal = _validate_ref(kind=action.kind, ref=action.ref, epic_id=epic_id)
        if refusal is None and action.kind in ("human", "none"):
            if action.required_result is not None or action.budget is not None:
                refusal = _refusal(detail=f"{action.kind} carries null required_result and budget")
        elif refusal is None:
            parsed_result = parse_result_reference(value=action.required_result)
            if isinstance(parsed_result, ResultReferenceRefusal):
                refusal = _refusal(detail=f"required_result is invalid: {parsed_result.detail}")
            else:
                refusal = _validate_budget(value=action.budget)
    return refusal


def _validate_ref(*, kind: str, ref: str, epic_id: str) -> NextActionRefusal | None:
    stripped = ref.strip()
    operation, spec_separator, topic = stripped.partition(":")
    await_prefix, await_separator, await_target = stripped.partition(":")
    valid = {
        "impl": bool(stripped),
        "spec-op": bool(spec_separator and operation and topic),
        "proof": stripped in (f"capture:{epic_id}", f"verify:{epic_id}"),
        "review": stripped == epic_id,
        "archive": stripped == epic_id,
        "await": bool(await_separator and await_prefix in _AWAIT_PREFIXES and await_target),
        "human": True,
        "none": not stripped,
    }
    details = {
        "impl": "impl requires a non-empty item ref",
        "spec-op": "spec-op requires an <operation>:<topic> ref",
        "proof": "proof requires capture:<epic-id> or verify:<epic-id>",
        "review": "review requires the epic id",
        "archive": "archive requires the epic id",
        "await": "await requires a non-empty run:, gate:, item:, or epic: ref",
        "human": "human accepts any ref",
        "none": "none requires an empty ref",
    }
    return None if valid[kind] else _refusal(detail=details[kind])


def _validate_budget(*, value: object) -> NextActionRefusal | None:
    refusal: NextActionRefusal | None = None
    if not isinstance(value, dict):
        refusal = _refusal(detail="budget must be an object")
    else:
        fields = cast("dict[str, Any]", value)
        deadline = fields.get("deadline")
        if not isinstance(deadline, str):
            refusal = _refusal(detail="budget deadline must be a string")
        else:
            parsed = parse_iso_datetime(text=deadline.replace("Z", "+00:00"))
            if isinstance(parsed, IsoDatetimeParseFailure):
                refusal = _refusal(detail="budget deadline must be an ISO datetime")
            else:
                refusal = _validate_deadline_and_handoffs(
                    deadline=parsed,
                    max_handoffs=fields.get("max_handoffs"),
                )
    return refusal


def _validate_deadline_and_handoffs(
    *,
    deadline: datetime,
    max_handoffs: object,
) -> NextActionRefusal | None:
    refusal: NextActionRefusal | None = None
    if deadline.tzinfo is None:
        refusal = _refusal(detail="budget deadline must carry a timezone")
    elif deadline.utcoffset() != timedelta(0):
        refusal = _refusal(detail="budget deadline must be UTC")
    elif not isinstance(max_handoffs, int) or isinstance(max_handoffs, bool):
        refusal = _refusal(detail="budget max_handoffs must be an integer")
    elif max_handoffs <= 0:
        refusal = _refusal(detail="budget max_handoffs must be positive")
    return refusal


def _refusal(*, detail: str) -> NextActionRefusal:
    return NextActionRefusal(detail=detail)
