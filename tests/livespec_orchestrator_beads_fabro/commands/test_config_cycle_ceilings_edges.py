"""Edge cases for committed runtime-ceiling policy resolution."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config_cycle_ceilings import (
    resolve_adopted_cycle_ceilings,
    runtime_ceiling_policy_refusal,
)


def test_valid_runtime_ceilings_resolve_and_clear_the_pre_claim_refusal(tmp_path: Path) -> None:
    """Positive integers are adopted and an omitted setting remains inactive."""
    (tmp_path / ".livespec.jsonc").write_text(
        "{\n"
        '  "livespec-orchestrator-beads-fabro": {\n'
        '    "dispatcher": {\n'
        '      "adopted_cycle_product_lloc_ceiling": 40\n'
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )

    resolved = resolve_adopted_cycle_ceilings(cwd=tmp_path)

    assert not isinstance(resolved, str)
    assert resolved.product_lloc == 40
    assert resolved.duration_seconds is None
    assert runtime_ceiling_policy_refusal(repo=tmp_path) is None


def test_policy_refusal_reports_invalid_and_unreadable_committed_configuration(
    tmp_path: Path,
) -> None:
    """The pre-claim boundary distinguishes malformed policy from unreadable config."""
    config = tmp_path / ".livespec.jsonc"
    config.write_text(
        '{"livespec-orchestrator-beads-fabro":{"dispatcher":'
        '{"adopted_cycle_duration_seconds_ceiling":false}}}',
        encoding="utf-8",
    )

    invalid = runtime_ceiling_policy_refusal(repo=tmp_path)

    assert invalid is not None
    assert "adopted_cycle_duration_seconds_ceiling" in invalid

    config.write_text("not JSONC", encoding="utf-8")

    unreadable = runtime_ceiling_policy_refusal(repo=tmp_path)

    assert unreadable is not None
    assert "cannot resolve" in unreadable
