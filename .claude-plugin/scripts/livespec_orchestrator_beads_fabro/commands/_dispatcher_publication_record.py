"""Run-to-head bindings that publication stages leave on pull requests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

__all__: list[str] = ["publication_pairs"]

_MARKER = "livespec-publication-record"
_REQUIRED_FIELDS = ("run-id", "head", "pull-request", "stage", "pushed-at")
_SHA_LENGTH = 40
_SHA_CHARACTERS = frozenset("0123456789abcdef")


def publication_pairs(
    *, comments: tuple[Mapping[str, object], ...], publication_identity: str
) -> tuple[tuple[str, str], ...]:
    """Return the ordered head/run bindings authored by the configured identity."""
    if not publication_identity:
        return ()
    return tuple(
        (fields["head"], fields["run-id"])
        for comment in comments
        if _author_login(comment=comment) == publication_identity
        and (fields := _record_fields(body=comment.get("body"))) is not None
    )


def _author_login(*, comment: Mapping[str, object]) -> str | None:
    author = comment.get("author")
    if not isinstance(author, Mapping):
        return None
    login = cast("Mapping[str, object]", author).get("login")
    return login if isinstance(login, str) and login else None


def _record_fields(*, body: object) -> dict[str, str] | None:
    if not isinstance(body, str):
        return None
    lines = body.splitlines()
    if not lines or lines[0] != _MARKER:
        return None
    fields = {
        key: value.strip()
        for line in lines[1:]
        if ":" in line
        for key, value in (line.split(":", maxsplit=1),)
        if key in _REQUIRED_FIELDS and value.strip()
    }
    if set(fields) != set(_REQUIRED_FIELDS):
        return None
    head = fields["head"]
    if len(head) != _SHA_LENGTH or any(character not in _SHA_CHARACTERS for character in head):
        return None
    return fields
