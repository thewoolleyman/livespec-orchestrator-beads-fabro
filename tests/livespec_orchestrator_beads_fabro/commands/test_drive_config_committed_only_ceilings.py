"""The API policy surface excludes committed runtime ceilings."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._drive_config import run_config_action


def test_policy_updates_refuse_each_committed_only_runtime_ceiling_without_writing(
    tmp_path: Path,
) -> None:
    """Runtime ceilings must be adopted through reviewed committed configuration."""
    config = tmp_path / ".livespec.jsonc"
    original = '{"livespec-orchestrator-beads-fabro":{"dispatcher":{"wip_cap":3}}}\n'
    config.write_text(original, encoding="utf-8")

    for key in (
        "adopted_cycle_product_lloc_ceiling",
        "adopted_cycle_duration_seconds_ceiling",
    ):
        result = run_config_action(repo=tmp_path, action_id=f"set-config:{key}:10")

        assert result["status"] == "failed"
        assert result["domain_error"] == "non-api-configurable-setting"
        assert config.read_text(encoding="utf-8") == original
