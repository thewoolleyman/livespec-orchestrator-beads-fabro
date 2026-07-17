"""Minimal JSONC parser — JSON with `// line` comments only.

The `.livespec.jsonc` configuration file uses `//`-style line comments
exclusively in the impl-beads templates; the wider `/* block */`
form is not required. Stripping the comments and delegating to stdlib
`json.loads` keeps the parser tiny and dependency-free.

Public surface:

- `loads(*, text)` — parse a JSONC string into a Python value. Raises
  `JsoncParseError` on malformed input (the only EXPECTED error per
  the Result-vs-bugs split).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = ["JsoncFailure", "JsoncParseError", "loads", "parse"]


@dataclass(frozen=True, kw_only=True)
class JsoncFailure:
    detail: str


class JsoncParseError(Exception):
    """Raised when the JSONC source does not parse as JSON after comment-strip."""

    def __init__(self, *, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


_TOKEN_PATTERN = re.compile(
    r'(?P<string>"(?:\\.|[^"\\])*")|(?P<comment>//[^\n]*)',
)


def _strip_line_comments(*, text: str) -> str:
    """Remove `//` line comments while preserving any `//` inside JSON strings."""

    def _replace(*, match: re.Match[str]) -> str:
        if match.group("string") is not None:
            return match.group("string")
        return ""

    return _TOKEN_PATTERN.sub(lambda match: _replace(match=match), text)


def loads(*, text: str) -> Any:
    """Parse a JSONC string and return the decoded Python value."""
    parsed = parse(text=text)
    if isinstance(parsed, JsoncFailure):
        raise JsoncParseError(detail=parsed.detail)
    return parsed


def parse(*, text: str) -> object | JsoncFailure:
    """Parse JSONC into a value, or return an explicit failure."""
    stripped = _strip_line_comments(text=text)
    parsed = parse_json(text=stripped)
    if isinstance(parsed, JsonParseFailure):
        exc = parsed.error
        return JsoncFailure(detail=f"jsonc parse failed: {exc}")
    return parsed
