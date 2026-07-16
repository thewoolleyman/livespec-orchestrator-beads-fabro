"""Edge coverage for drive's dispatcher config actions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import drive

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"


@pytest.mark.parametrize(
    "text",
    [
        "{not-json",
        "[]",
        json.dumps({_PLUGIN_BLOCK: 7}),
        json.dumps({_PLUGIN_BLOCK: {"dispatcher": 7}}),
    ],
)
def test_config_read_defaults_when_config_shape_is_not_readable(tmp_path: Path, text: str) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(text, encoding="utf-8")

    result = drive.run_action(repo=repo, action_id="config")

    assert result["status"] == "green"
    assert result["settings"][0] == {
        "key": "auto_approve_ready",
        "value": False,
        "source": "default",
    }


def test_config_read_defaults_when_config_file_is_absent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = drive.run_action(repo=repo, action_id="config")

    assert result["status"] == "green"
    assert result["settings"][-1] == {"key": "wip_cap", "value": 5, "source": "default"}


def test_config_write_creates_missing_file_and_nested_blocks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = drive.run_action(repo=repo, action_id="set-config:auto_approve_ready:false")

    assert result["status"] == "green"
    assert result["value"] is False
    assert json.loads((repo / ".livespec.jsonc").read_text(encoding="utf-8")) == {
        _PLUGIN_BLOCK: {"dispatcher": {"auto_approve_ready": False}}
    }


def test_config_write_accepts_bool_true_and_enum_values(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = drive.run_action(repo=repo, action_id="set-config:auto_approve_ready:true")

    result = drive.run_action(repo=repo, action_id="set-config:acceptance_mode:ai-only")

    assert result["status"] == "green"
    assert result["value"] == "ai-only"
    assert json.loads((repo / ".livespec.jsonc").read_text(encoding="utf-8"))[_PLUGIN_BLOCK][
        "dispatcher"
    ] == {"acceptance_mode": "ai-only", "auto_approve_ready": True}


@pytest.mark.parametrize(
    "action_id",
    [
        "set-config:",
        "set-config:wip_cap:",
        "set-config:merge_on_review_cap:maybe",
        "set-config:wip_cap:nope",
        "set-config:wip_cap:0",
    ],
)
def test_config_write_refuses_malformed_or_out_of_domain_values(
    tmp_path: Path, action_id: str
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = drive.run_action(repo=repo, action_id=action_id)

    assert result["status"] == "failed"
    assert result["kind"] == "config-write"
    assert not (repo / ".livespec.jsonc").exists()


@pytest.mark.parametrize(
    ("text", "summary_fragment"),
    [
        ("{not-json", "parses"),
        ("[]", "root must be an object"),
        (json.dumps({_PLUGIN_BLOCK: 7}), "dispatcher block must be an object"),
        (
            json.dumps({_PLUGIN_BLOCK: {"dispatcher": 7}}),
            "dispatcher block must be an object",
        ),
    ],
)
def test_config_write_refuses_unwritable_existing_config_shapes(
    tmp_path: Path, text: str, summary_fragment: str
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(text, encoding="utf-8")

    result = drive.run_action(repo=repo, action_id="set-config:wip_cap:4")

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-config-shape"
    assert summary_fragment in result["summary"]
