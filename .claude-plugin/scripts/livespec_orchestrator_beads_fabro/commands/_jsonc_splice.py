"""Surgical JSONC object updates that preserve untouched source text."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

__all__: list[str] = ["set_path"]


@dataclass(frozen=True, kw_only=True)
class _Member:
    key: str
    value_start: int
    value_end: int


def set_path(*, text: str, path: Iterable[str], value: Any) -> str:
    """Set one object path by replacing or inserting only that member's value."""
    keys = tuple(path)
    if not keys:
        msg = "path must not be empty"
        raise ValueError(msg)
    root_start = _skip_ws_and_comments(text=text, index=0)
    if root_start >= len(text) or text[root_start] != "{":
        msg = "JSONC root must be an object"
        raise ValueError(msg)
    return _set_in_object(text=text, object_start=root_start, keys=keys, value=value)


def _set_in_object(*, text: str, object_start: int, keys: tuple[str, ...], value: Any) -> str:
    members, close = _object_members(text=text, object_start=object_start)
    target = keys[0]
    member = _find_member(members=members, key=target)
    if member is None:
        inserted_value = _nested_value(keys=keys[1:], value=value)
        return _insert_member(
            text=text,
            members=members,
            close=close,
            key=target,
            value=inserted_value,
        )
    if len(keys) == 1:
        encoded = json.dumps(value)
        return f"{text[: member.value_start]}{encoded}{text[member.value_end:]}"
    child_start = _skip_ws_and_comments(text=text, index=member.value_start)
    if child_start >= len(text) or text[child_start] != "{":
        msg = f"JSONC path member {member.key!r} must be an object"
        raise ValueError(msg)
    return _set_in_object(text=text, object_start=child_start, keys=keys[1:], value=value)


def _find_member(*, members: list[_Member], key: str) -> _Member | None:
    for member in members:
        if member.key == key:
            return member
    return None


def _nested_value(*, keys: tuple[str, ...], value: Any) -> Any:
    nested = value
    for key in reversed(keys):
        nested = {key: nested}
    return nested


def _insert_member(*, text: str, members: list[_Member], close: int, key: str, value: Any) -> str:
    close_indent = _line_indent(text=text, index=close)
    member_indent = _member_indent(text=text, members=members, close_indent=close_indent)
    member_text = _format_member(key=key, value=value, indent=member_indent)
    if members:
        insert_at = members[-1].value_end
        return f"{text[:insert_at]},\n{member_text}{text[insert_at:]}"
    insert = f"\n{member_text}\n{close_indent}"
    return f"{text[:close]}{insert}{text[close:]}"


def _member_indent(*, text: str, members: list[_Member], close_indent: str) -> str:
    if members:
        return _line_indent(text=text, index=members[0].value_start - 1)
    return f"{close_indent}  "


def _format_member(*, key: str, value: Any, indent: str) -> str:
    encoded = json.dumps(value, indent=2)
    lines = encoded.splitlines()
    first = f"{indent}{json.dumps(key)}: {lines[0]}"
    rest = [f"{indent}{line}" for line in lines[1:]]
    return "\n".join([first, *rest])


def _line_indent(*, text: str, index: int) -> str:
    line_start = text.rfind("\n", 0, index) + 1
    cursor = line_start
    while cursor < len(text) and text[cursor] in " \t":
        cursor += 1
    return text[line_start:cursor]


def _object_members(*, text: str, object_start: int) -> tuple[list[_Member], int]:
    members: list[_Member] = []
    index = _skip_ws_and_comments(text=text, index=object_start + 1)
    if index < len(text) and text[index] == "}":
        return members, index
    while index < len(text):
        key_start = _skip_ws_and_comments(text=text, index=index)
        key_end = _scan_string_end(text=text, index=key_start)
        key = json.loads(text[key_start:key_end])
        colon = _skip_ws_and_comments(text=text, index=key_end)
        if colon >= len(text) or text[colon] != ":":
            msg = "object member missing colon"
            raise ValueError(msg)
        value_start = _skip_ws_and_comments(text=text, index=colon + 1)
        value_end = _scan_value_end(text=text, index=value_start)
        members.append(_Member(key=str(key), value_start=value_start, value_end=value_end))
        delimiter = _skip_ws_and_comments(text=text, index=value_end)
        if delimiter >= len(text):
            msg = "object missing closing brace"
            raise ValueError(msg)
        if text[delimiter] == "}":
            return members, delimiter
        if text[delimiter] != ",":
            msg = "object member missing comma"
            raise ValueError(msg)
        index = delimiter + 1
    msg = "object missing closing brace"
    raise ValueError(msg)


def _scan_string_end(*, text: str, index: int) -> int:
    if index >= len(text) or text[index] != '"':
        msg = "expected JSON string"
        raise ValueError(msg)
    cursor = index + 1
    escaped = False
    while cursor < len(text):
        char = text[cursor]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            return cursor + 1
        cursor += 1
    msg = "unterminated JSON string"
    raise ValueError(msg)


def _scan_value_end(*, text: str, index: int) -> int:
    if index >= len(text):
        msg = "expected JSON value"
        raise ValueError(msg)
    if text[index] == '"':
        return _scan_string_end(text=text, index=index)
    if text[index] in "[{":
        return _scan_container_end(text=text, index=index)
    return _scan_scalar_end(text=text, index=index)


def _scan_container_end(*, text: str, index: int) -> int:
    stack = [text[index]]
    cursor = index + 1
    while cursor < len(text):
        char = text[cursor]
        if char == '"':
            cursor = _scan_string_end(text=text, index=cursor)
            continue
        if char == "/" and cursor + 1 < len(text) and text[cursor + 1] == "/":
            cursor = _skip_comment(text=text, index=cursor)
            continue
        if char in "[{":
            stack.append(char)
        elif char in "]}":
            opener = stack.pop()
            if (opener, char) not in (("[", "]"), ("{", "}")):
                msg = "mismatched JSON container"
                raise ValueError(msg)
            if not stack:
                return cursor + 1
        cursor += 1
    msg = "unterminated JSON container"
    raise ValueError(msg)


def _scan_scalar_end(*, text: str, index: int) -> int:
    cursor = index
    while cursor < len(text):
        char = text[cursor]
        if char in ",}] \t\r\n":
            return cursor
        if char == "/" and cursor + 1 < len(text) and text[cursor + 1] == "/":
            return cursor
        cursor += 1
    return cursor


def _skip_ws_and_comments(*, text: str, index: int) -> int:
    cursor = index
    while cursor < len(text):
        if text[cursor] in " \t\r\n":
            cursor += 1
            continue
        if text[cursor] == "/" and cursor + 1 < len(text) and text[cursor + 1] == "/":
            cursor = _skip_comment(text=text, index=cursor)
            continue
        return cursor
    return cursor


def _skip_comment(*, text: str, index: int) -> int:
    newline = text.find("\n", index)
    if newline == -1:
        return len(text)
    return newline + 1
