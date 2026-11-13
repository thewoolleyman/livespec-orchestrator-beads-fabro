"""The API policy surface refuses both committed-only runtime ceilings.

Scenario 165 requires that when either runtime ceiling is named in an API policy
update, the public configuration update surface "refuses that
non-API-configurable setting without changing committed policy". The refusal is
its OWN verdict rather than the generic unknown-key one, because the two faults
have different remedies: an unknown key is a typo to correct, while these keys
are real settings that may only be adopted by a reviewed committed change.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_ceilings import (
    COMMITTED_ONLY_RUNTIME_CEILING_KEYS,
)
from livespec_orchestrator_beads_fabro.commands._drive_config import run_config_action
from livespec_orchestrator_beads_fabro.commands._drive_config_schema import (
    api_configurable_key_manifest,
)

_COMMITTED_POLICY = (
    "{\n"
    '  "livespec-orchestrator-beads-fabro": {\n'
    '    "dispatcher": {\n'
    '      "wip_cap": 3\n'
    "    }\n"
    "  }\n"
    "}\n"
)


def test_neither_runtime_ceiling_is_api_configurable() -> None:
    manifest_keys = {entry["key"] for entry in api_configurable_key_manifest()["keys"]}

    assert manifest_keys.isdisjoint(set(COMMITTED_ONLY_RUNTIME_CEILING_KEYS))


def test_a_policy_update_naming_either_ceiling_refuses_as_committed_only(tmp_path: Path) -> None:
    config = tmp_path / ".livespec.jsonc"
    config.write_text(_COMMITTED_POLICY, encoding="utf-8")

    for key in COMMITTED_ONLY_RUNTIME_CEILING_KEYS:
        result = run_config_action(repo=tmp_path, action_id=f"set-config:{key}:10")

        assert result["status"] == "failed"
        assert result["domain_error"] == "non-api-configurable-setting"
        assert key in str(result["summary"])
        assert "committed" in str(result["summary"])
        assert config.read_text(encoding="utf-8") == _COMMITTED_POLICY


def test_an_unknown_key_still_reports_the_generic_refusal(tmp_path: Path) -> None:
    config = tmp_path / ".livespec.jsonc"
    config.write_text(_COMMITTED_POLICY, encoding="utf-8")

    result = run_config_action(repo=tmp_path, action_id="set-config:not_a_setting:10")

    assert result["domain_error"] == "invalid-config-key"
    assert config.read_text(encoding="utf-8") == _COMMITTED_POLICY
