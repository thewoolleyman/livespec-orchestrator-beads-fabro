"""Narrow expected-exception capture boundary.

Callers stay on the Result-style railway by receiving either the produced value
or an explicit failure object. The actual `try/except` is confined to this
declared effect boundary and requires a caller-supplied exception tuple.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar

__all__: list[str] = [
    "AttemptFailure",
    "FloatParseFailure",
    "IsoDatetimeParseFailure",
    "JsonParseFailure",
    "attempt",
    "parse_float",
    "parse_iso_datetime",
    "parse_json",
]

_Value = TypeVar("_Value")
_Error = TypeVar("_Error", bound=Exception)


@dataclass(frozen=True, kw_only=True)
class AttemptFailure:
    error: Exception


@dataclass(frozen=True, kw_only=True)
class JsonParseFailure:
    error: json.JSONDecodeError


@dataclass(frozen=True, kw_only=True)
class FloatParseFailure:
    error: ValueError


@dataclass(frozen=True, kw_only=True)
class IsoDatetimeParseFailure:
    error: ValueError


def attempt(
    *,
    action: Callable[[], _Value],
    exceptions: tuple[type[_Error], ...],
) -> _Value | AttemptFailure:
    try:
        return action()
    except exceptions as exc:
        return AttemptFailure(error=exc)


def parse_json(*, text: str) -> object | JsonParseFailure:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        return JsonParseFailure(error=exc)


def parse_float(*, text: str) -> float | FloatParseFailure:
    try:
        return float(text)
    except ValueError as exc:
        return FloatParseFailure(error=exc)


def parse_iso_datetime(*, text: str) -> datetime | IsoDatetimeParseFailure:
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        return IsoDatetimeParseFailure(error=exc)
