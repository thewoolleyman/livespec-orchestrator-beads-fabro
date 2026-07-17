"""Structured finding parsing for the out-of-band reflector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = ["ReflectorFinding", "parse_findings"]


@dataclass(frozen=True, kw_only=True)
class ReflectorFinding:
    """One finding from the LLM reflector's structured JSON output."""

    category: str
    stage: str
    severity: str
    subject: str
    detail: str
    occurrences: int
    work_item_id: str | None
    score: float
    label: str


def parse_findings(*, raw: str) -> tuple[ReflectorFinding, ...]:
    """Parse the reflector's structured-JSON output into findings."""
    payload = _coerce_findings_payload(raw=raw)
    findings: list[ReflectorFinding] = []
    for entry in payload:
        parsed = _parse_one_finding(entry=entry)
        if parsed is not None:
            findings.append(parsed)
    return tuple(findings)


def _coerce_findings_payload(*, raw: str) -> list[object]:
    text = raw.strip()
    if not text:
        return []
    top = parse_json(text=text)
    if isinstance(top, JsonParseFailure):
        return []
    return _extract_findings_list(top=top)


def _extract_findings_list(*, top: object) -> list[object]:
    if isinstance(top, list):
        return list(cast("list[object]", top))
    if isinstance(top, dict):
        obj = cast("dict[str, object]", top)
        direct = obj.get("findings")
        if isinstance(direct, list):
            return list(cast("list[object]", direct))
        result = obj.get("result")
        if isinstance(result, str):
            return _coerce_findings_payload(raw=result)
    return []


def _parse_one_finding(*, entry: object) -> ReflectorFinding | None:
    if not isinstance(entry, dict):
        return None
    obj = cast("dict[str, object]", entry)
    category = _str_field(obj=obj, key="category")
    severity = _str_field(obj=obj, key="severity")
    subject = _str_field(obj=obj, key="subject")
    if category is None or severity is None or subject is None:
        return None
    return ReflectorFinding(
        category=category,
        stage=_str_field(obj=obj, key="stage") or "",
        severity=severity,
        subject=subject,
        detail=_str_field(obj=obj, key="detail") or "",
        occurrences=_int_field(obj=obj, key="occurrences", default=1),
        work_item_id=_str_field(obj=obj, key="work_item_id"),
        score=_float_field(obj=obj, key="score", default=0.0),
        label=_str_field(obj=obj, key="label") or "",
    )


def _str_field(*, obj: dict[str, object], key: str) -> str | None:
    value = obj.get(key)
    return value if isinstance(value, str) else None


def _int_field(*, obj: dict[str, object], key: str, default: int) -> int:
    value = obj.get(key)
    if isinstance(value, bool):
        return default
    return value if isinstance(value, int) else default


def _float_field(*, obj: dict[str, object], key: str, default: float) -> float:
    value = obj.get(key)
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return float(value)
    return default
