"""Tests for drive's API-configurable dispatcher settings surface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands import drive
from livespec_orchestrator_beads_fabro.commands._drive_config_schema import (
    ConfigKey,
    coerce_config_value,
    config_key_by_name,
    parse_config_value,
    value_domain,
)

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_V049_WIP_CAP_ZERO_MESSAGE = (
    "v049 Per-repo WIP cap clause requires wip_cap to accept 0; retiring it "
    "requires a propose-change."
)


def test_config_schema_distinguishes_positive_and_non_negative_integer_domains() -> None:
    review_fix_cap = config_key_by_name(key="review_fix_cap")
    ready_aging_threshold_hours = config_key_by_name(key="ready_aging_threshold_hours")
    wip_cap = config_key_by_name(key="wip_cap")

    assert review_fix_cap is not None
    assert ready_aging_threshold_hours is not None
    assert wip_cap is not None
    assert coerce_config_value(config_key=review_fix_cap, raw_value=4) == 4
    assert coerce_config_value(config_key=review_fix_cap, raw_value=0) is None
    assert coerce_config_value(config_key=ready_aging_threshold_hours, raw_value=24) == 24
    assert coerce_config_value(config_key=ready_aging_threshold_hours, raw_value=0) is None
    assert parse_config_value(config_key=review_fix_cap, raw_value="nope") is None
    assert parse_config_value(config_key=ready_aging_threshold_hours, raw_value="24") == 24
    assert parse_config_value(config_key=ready_aging_threshold_hours, raw_value="0") is None
    assert parse_config_value(config_key=wip_cap, raw_value="0") == 0
    assert value_domain(config_key=wip_cap) == "a non-negative integer"


def test_v049_wip_cap_guard_accepts_zero_on_schema_and_manifest_surfaces() -> None:
    schema_key = config_key_by_name(key="wip_cap")
    manifest = json.loads(
        Path(".claude-plugin/api-configurable-keys.json").read_text(encoding="utf-8")
    )
    manifest_entries = {str(entry["key"]): entry for entry in manifest["keys"]}
    manifest_entry = manifest_entries["wip_cap"]
    manifest_key = ConfigKey(
        key="wip_cap",
        value_type=str(manifest_entry["type"]),
        default=manifest_entry["default"],
        per_item_override=bool(manifest_entry["per_item_override"]),
        values=tuple(str(value) for value in manifest_entry.get("values", ())),
    )

    assert schema_key is not None
    assert coerce_config_value(config_key=schema_key, raw_value=0) == 0, _V049_WIP_CAP_ZERO_MESSAGE
    assert (
        coerce_config_value(config_key=manifest_key, raw_value=0) == 0
    ), _V049_WIP_CAP_ZERO_MESSAGE


def _settings_by_key(*, payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    settings = payload["settings"]
    assert isinstance(settings, list)
    return {str(setting["key"]): setting for setting in settings}


def test_drive_reads_all_effective_dispatcher_settings_with_sources(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                _PLUGIN_BLOCK: {
                    "dispatcher": {
                        "auto_approve_ready": True,
                        "acceptance_mode": "human-only",
                        "ready_aging_threshold_hours": 36,
                        "wip_cap": 0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = drive.run_action(repo=repo, action_id="config")

    assert result["status"] == "green"
    assert result["kind"] == "config-read"
    by_key = _settings_by_key(payload=result)
    assert set(by_key) == {
        "auto_approve_ready",
        "merge_on_review_cap",
        "acceptance_mode",
        "review_fix_cap",
        "acceptance_rework_cap",
        "groom_cut_approval",
        "automated_regroom_cap",
        "ready_aging_threshold_hours",
        "wip_cap",
        "drift_capture_merge_threshold",
        "drift_proposal_queue_cap",
    }
    assert by_key["auto_approve_ready"] == {
        "key": "auto_approve_ready",
        "value": True,
        "source": "explicit",
    }
    assert by_key["merge_on_review_cap"] == {
        "key": "merge_on_review_cap",
        "value": False,
        "source": "default",
    }
    assert by_key["acceptance_mode"] == {
        "key": "acceptance_mode",
        "value": "human-only",
        "source": "explicit",
    }
    assert by_key["review_fix_cap"] == {"key": "review_fix_cap", "value": 3, "source": "default"}
    assert by_key["acceptance_rework_cap"] == {
        "key": "acceptance_rework_cap",
        "value": 2,
        "source": "default",
    }
    assert by_key["ready_aging_threshold_hours"] == {
        "key": "ready_aging_threshold_hours",
        "value": 36,
        "source": "explicit",
    }
    assert by_key["wip_cap"] == {"key": "wip_cap", "value": 0, "source": "explicit"}


def test_drive_writes_one_dispatcher_setting_without_clobbering_siblings(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "credential_wrapper": ["op", "run"],
                _PLUGIN_BLOCK: {
                    "connection": {"tenant": "tenant", "prefix": "bd-ib"},
                    "dispatcher": {"fabro_bin": "/opt/fabro", "wip_cap": 5},
                },
            }
        ),
        encoding="utf-8",
    )

    result = drive.run_action(repo=repo, action_id="set-config:review_fix_cap:6")

    assert result["status"] == "green"
    assert result["kind"] == "config-write"
    assert result["key"] == "review_fix_cap"
    assert result["value"] == 6
    persisted = json.loads((repo / ".livespec.jsonc").read_text(encoding="utf-8"))
    assert persisted == {
        "credential_wrapper": ["op", "run"],
        _PLUGIN_BLOCK: {
            "connection": {"tenant": "tenant", "prefix": "bd-ib"},
            "dispatcher": {"fabro_bin": "/opt/fabro", "wip_cap": 5, "review_fix_cap": 6},
        },
    }


def test_drive_config_write_preserves_comments_and_unrelated_order(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config_path = repo / ".livespec.jsonc"
    original = f"""{{
  // template rationale stays with the first key
  "template": "impl-plugin",
  "credential_wrapper": [
    "op",
    "run"
  ],
  "{_PLUGIN_BLOCK}": {{
    "connection": {{
      "tenant": "tenant",
      "prefix": "bd-ib"
    }},
    // dispatcher settings are operator-owned
    "dispatcher": {{
      // wip cap keeps queue pressure bounded
      "wip_cap": 5,
      "acceptance_mode": "ai-then-human"
    }},
    "compat": {{
      // pins track releases rather than raw master
      "pinned": "v0.16.0"
    }}
  }},
  "livespec": {{
    "version": 1
  }}
}}
"""
    _ = config_path.write_text(original, encoding="utf-8")

    result = drive.run_action(repo=repo, action_id="set-config:wip_cap:9")

    assert result["status"] == "green"
    updated = config_path.read_text(encoding="utf-8")
    assert [line for line in updated.splitlines() if line.strip().startswith("//")] == [
        line for line in original.splitlines() if line.strip().startswith("//")
    ]
    assert updated.index('"template"') < updated.index('"credential_wrapper"')
    assert updated.index('"connection"') < updated.index('"dispatcher"') < updated.index('"compat"')
    assert updated == original.replace('"wip_cap": 5', '"wip_cap": 9')
    assert (
        json.loads(
            "\n".join(line for line in updated.splitlines() if not line.strip().startswith("//"))
        )[_PLUGIN_BLOCK]["dispatcher"]["wip_cap"]
        == 9
    )


def test_drive_refuses_invalid_config_key_and_value(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    invalid_key = drive.run_action(repo=repo, action_id="set-config:fabro_bin:/tmp/fabro")
    invalid_value = drive.run_action(repo=repo, action_id="set-config:acceptance_mode:sometimes")

    assert invalid_key["status"] == "failed"
    assert invalid_key["domain_error"] == "invalid-config-key"
    assert "Expected one of" in invalid_key["summary"]
    assert invalid_value["status"] == "failed"
    assert invalid_value["domain_error"] == "invalid-config-value"
    assert "ai-only" in invalid_value["summary"]
    assert not (repo / ".livespec.jsonc").exists()


def test_drive_publishes_api_configurable_key_manifest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = drive.run_action(repo=repo, action_id="config-manifest")
    manifest_path = Path(".claude-plugin/api-configurable-keys.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert result["status"] == "green"
    assert result["kind"] == "config-manifest"
    assert result["manifest"] == manifest
    keys = {str(entry["key"]): entry for entry in manifest["keys"]}
    assert keys == {
        "auto_approve_ready": {
            "key": "auto_approve_ready",
            "type": "boolean",
            "default": False,
            "per_item_override": True,
        },
        "merge_on_review_cap": {
            "key": "merge_on_review_cap",
            "type": "boolean",
            "default": False,
            "per_item_override": True,
        },
        "acceptance_mode": {
            "key": "acceptance_mode",
            "type": "enum",
            "default": "ai-then-human",
            "values": ["ai-only", "ai-then-human", "human-only"],
            "per_item_override": True,
        },
        "review_fix_cap": {
            "key": "review_fix_cap",
            "type": "positive_integer",
            "default": 3,
            "per_item_override": True,
        },
        "acceptance_rework_cap": {
            "key": "acceptance_rework_cap",
            "type": "positive_integer",
            "default": 2,
            "per_item_override": True,
        },
        "groom_cut_approval": {
            "key": "groom_cut_approval",
            "type": "enum",
            "default": "human",
            "values": ["human", "consensus"],
            "per_item_override": True,
        },
        "automated_regroom_cap": {
            "key": "automated_regroom_cap",
            "type": "positive_integer",
            "default": 2,
            "per_item_override": True,
        },
        "ready_aging_threshold_hours": {
            "key": "ready_aging_threshold_hours",
            "type": "positive_integer",
            "default": 24,
            "per_item_override": False,
        },
        "wip_cap": {
            "key": "wip_cap",
            "type": "non_negative_integer",
            "default": 5,
            "per_item_override": False,
        },
        "drift_capture_merge_threshold": {
            "key": "drift_capture_merge_threshold",
            "type": "positive_integer",
            "default": 1,
            "per_item_override": False,
        },
        "drift_proposal_queue_cap": {
            "key": "drift_proposal_queue_cap",
            "type": "positive_integer",
            "default": 5,
            "per_item_override": False,
        },
    }
