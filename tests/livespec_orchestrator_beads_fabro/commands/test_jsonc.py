"""Tests for the minimal JSONC stripper."""

import pytest
from livespec_orchestrator_beads_fabro.commands import _jsonc


def test_loads_plain_json() -> None:
    parsed = _jsonc.loads(text='{"a": 1, "b": [1, 2, 3]}')
    assert parsed == {"a": 1, "b": [1, 2, 3]}


def test_loads_strips_line_comments() -> None:
    text = """
    {
      // top comment
      "a": 1,
      "b": 2 // trailing comment
    }
    """
    parsed = _jsonc.loads(text=text)
    assert parsed == {"a": 1, "b": 2}


def test_loads_preserves_double_slash_inside_strings() -> None:
    text = '{"url": "https://example.com/path"}'
    parsed = _jsonc.loads(text=text)
    assert parsed == {"url": "https://example.com/path"}


def test_loads_handles_escaped_quote_in_string() -> None:
    text = r'{"q": "say \"hi\" //not a comment"}'
    parsed = _jsonc.loads(text=text)
    assert parsed == {"q": 'say "hi" //not a comment'}


def test_loads_raises_on_malformed_json() -> None:
    with pytest.raises(_jsonc.JsoncParseError):
        _ = _jsonc.loads(text="{not valid")
