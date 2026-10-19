"""Scenario 200 — declared shared record files merge during a refresh."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._jsonc import loads

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dispatcher_declares_the_shared_record_files() -> None:
    """The committed declaration is the authority the refresh stage reads."""
    config = cast(
        "dict[str, object]",
        loads(text=(_REPO_ROOT / ".livespec.jsonc").read_text(encoding="utf-8")),
    )
    plugin_value = config.get("livespec-orchestrator-beads-fabro")
    assert isinstance(plugin_value, dict)
    dispatcher_value = plugin_value.get("dispatcher")
    assert isinstance(dispatcher_value, dict)
    dispatcher = cast("dict[str, object]", dispatcher_value)

    record_files = dispatcher.get("record_files")
    assert record_files == [
        {
            "path": "tests/heading-coverage.json",
            "format": "json-array",
            "key": ["spec_root", "spec_file", "heading"],
        },
        {
            "path": "tests/heading-coverage-debt.json",
            "format": "json-array",
            "key": ["spec_root", "spec_file", "heading"],
        },
        {"path": "tests/integration/CLAUDE.md", "format": "markdown-insertions"},
        {"path": "tests/prompts/CLAUDE.md", "format": "markdown-insertions"},
    ]
