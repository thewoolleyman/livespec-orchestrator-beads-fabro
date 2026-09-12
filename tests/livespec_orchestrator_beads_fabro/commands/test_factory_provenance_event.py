"""Tests for the factory-provenance gate's forge-side inputs.

The new-module slice pattern: the module import happens INSIDE each test body
through `importlib`, and the first assertion is a genuine check that the module
file exists. A top-level `import` would make the Red leg a collection error,
which proves only unimportability rather than that the behavior is
unimplemented.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._factory_provenance_event"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_factory_provenance_event.py"
)


class RecordingRunner:
    """A CommandRunner that records the argv it was handed and answers canned."""

    def __init__(self, *, result: CommandResult) -> None:
        self.result = result
        self.argvs: list[list[str]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        self.argvs.append(argv)
        return self.result


def _module() -> Any:
    """Import the event module, proving its file exists first."""
    assert _MODULE_PATH.is_file(), f"expected the event module at {_MODULE_PATH}"
    return importlib.import_module(_MODULE_NAME)


def _payload(
    *,
    login: str = "thewoolleyman",
    labels: list[dict[str, str]] | None = None,
) -> str:
    return json.dumps(
        {
            "pull_request": {
                "user": {"login": login},
                "labels": [] if labels is None else labels,
                "base": {"sha": "base1234"},
                "head": {"sha": "head5678"},
            }
        }
    )


def test_parse_event_reduces_a_pull_request_payload_to_its_four_fields() -> None:
    module = _module()
    event = module.parse_event(payload_text=_payload(labels=[{"name": "factory-override"}]))
    assert event is not None
    assert event.author_login == "thewoolleyman"
    assert event.labels == ("factory-override",)
    assert event.base_sha == "base1234"
    assert event.head_sha == "head5678"


def test_parse_event_returns_none_for_non_json_text() -> None:
    module = _module()
    assert module.parse_event(payload_text="not json at all") is None


def test_parse_event_returns_none_for_a_json_payload_that_is_not_an_object() -> None:
    module = _module()
    assert module.parse_event(payload_text="[]") is None


def test_parse_event_returns_none_for_an_event_without_a_pull_request() -> None:
    module = _module()
    assert module.parse_event(payload_text=json.dumps({"push": {}})) is None


def test_parse_event_reads_absent_and_mistyped_fields_as_empty() -> None:
    module = _module()
    event = module.parse_event(
        payload_text=json.dumps({"pull_request": {"user": 7, "labels": "nope"}})
    )
    assert event is not None
    assert event.author_login == ""
    assert event.labels == ()
    assert event.base_sha == ""
    assert event.head_sha == ""


def test_parse_event_reads_a_mistyped_label_entry_as_an_empty_name() -> None:
    module = _module()
    event = module.parse_event(
        payload_text=json.dumps({"pull_request": {"labels": [{"name": 3}, "bare"]}})
    )
    assert event is not None
    assert event.labels == ("", "")


def test_read_event_reduces_a_payload_written_on_disk(tmp_path: Path) -> None:
    module = _module()
    payload_path = tmp_path / "event.json"
    _ = payload_path.write_text(_payload(login="thewoolleyman-factory-bot[bot]"), encoding="utf-8")
    event = module.read_event(path=payload_path)
    assert event is not None
    assert event.author_login == "thewoolleyman-factory-bot[bot]"


def test_read_event_returns_none_when_the_payload_file_is_absent(tmp_path: Path) -> None:
    module = _module()
    assert module.read_event(path=tmp_path / "missing.json") is None


def test_diff_range_is_merge_base_relative() -> None:
    module = _module()
    event = module.parse_event(payload_text=_payload())
    assert module.diff_range(event=event) == "base1234...head5678"


def test_read_changed_paths_asks_git_for_the_merge_base_relative_range(tmp_path: Path) -> None:
    module = _module()
    event = module.parse_event(payload_text=_payload())
    runner = RecordingRunner(
        result=CommandResult(exit_code=0, stdout="a.py\n\n  b.md  \n", stderr="")
    )
    paths = module.read_changed_paths(event=event, repo=tmp_path, runner=runner)
    assert paths == ("a.py", "b.md")
    assert runner.argvs == [["git", "diff", "--name-only", "base1234...head5678"]]


def test_read_changed_paths_returns_none_when_the_diff_cannot_be_read(tmp_path: Path) -> None:
    module = _module()
    event = module.parse_event(payload_text=_payload())
    runner = RecordingRunner(result=CommandResult(exit_code=128, stdout="", stderr="bad revision"))
    assert module.read_changed_paths(event=event, repo=tmp_path, runner=runner) is None
