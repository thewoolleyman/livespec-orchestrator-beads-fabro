"""Tests for comment-preserving JSONC text splices."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands import _jsonc, _jsonc_splice


def test_set_path_replaces_values_without_confusing_strings_or_nested_containers() -> None:
    text = r"""{
  // leading comment
  "target": {
    "value": "old \"// not a comment }\"",
    "array": [1, {"inner": "// still a string"}],
    "flag": true// scalar comment
  }
}
"""

    updated = _jsonc_splice.set_path(text=text, path=("target", "value"), value="new")

    assert updated == text.replace('"old \\"// not a comment }\\""', '"new"')
    parsed = _jsonc.loads(text=updated)
    assert isinstance(parsed, dict)
    assert parsed["target"]["value"] == "new"


def test_set_path_inserts_nested_members_in_nonempty_and_empty_objects() -> None:
    nonempty = '{\n  "a": 1\n}\n'
    empty = "{}\n"

    assert _jsonc_splice.set_path(text=nonempty, path=("b", "c"), value=True) == (
        '{\n  "a": 1,\n  "b": {\n    "c": true\n  }\n}\n'
    )
    assert _jsonc_splice.set_path(text=empty, path=("b",), value=2) == '{\n  "b": 2\n}\n'


@pytest.mark.parametrize(
    "text",
    [
        "",
        "[]",
        "// comment without newline",
    ],
)
def test_set_path_rejects_non_object_roots(text: str) -> None:
    with pytest.raises(ValueError, match="root must be an object"):
        _ = _jsonc_splice.set_path(text=text, path=("a",), value=1)


def test_set_path_rejects_empty_path() -> None:
    with pytest.raises(ValueError, match="path must not be empty"):
        _ = _jsonc_splice.set_path(text="{}", path=(), value=1)


def test_set_path_rejects_non_object_intermediate_member() -> None:
    with pytest.raises(ValueError, match="must be an object"):
        _ = _jsonc_splice.set_path(text='{"a": 1}', path=("a", "b"), value=2)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('{"a" 1}', "missing colon"),
        ('{"a": 1', "missing closing brace"),
        ('{"a": 1 "b": 2}', "missing comma"),
        ("{   ", "missing closing brace"),
        ("{a: 1}", "expected JSON string"),
        ('{"a": "unterminated}', "unterminated JSON string"),
        ('{"a": ', "expected JSON value"),
        ('{"a": [}}', "mismatched JSON container"),
        ('{"a": [1', "unterminated JSON container"),
    ],
)
def test_set_path_rejects_malformed_objects(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _ = _jsonc_splice.set_path(text=text, path=("z",), value=1)
