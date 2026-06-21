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

import json
import re
from typing import Any

__all__: list[str] = ["JsoncParseError", "loads"]


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

    def _replace(match: re.Match[str]) -> str:
        if match.group("string") is not None:
            return match.group("string")
        return ""

    return _TOKEN_PATTERN.sub(_replace, text)


def loads(*, text: str) -> Any:
    """Parse a JSONC string and return the decoded Python value."""
    stripped = _strip_line_comments(text=text)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise JsoncParseError(detail=f"jsonc parse failed: {exc}") from exc
