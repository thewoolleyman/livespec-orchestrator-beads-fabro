"""Coverage control for the Scenario 247 slow-export factory."""

from __future__ import annotations

from pathlib import Path

from tests.integration.test_fabro_dump_timeout_scenario247 import _SevenMinuteFactory


def test_the_slow_export_factory_times_out_before_the_required_duration(
    tmp_path: Path,
) -> None:
    """The control makes the seven-minute threshold informative."""
    result = _SevenMinuteFactory().run(
        argv=[
            "fabro",
            "dump",
            "control",
            "--server",
            "https://petri.example.test",
            "-o",
            str(tmp_path),
        ],
        cwd=tmp_path,
        timeout_seconds=600,
    )

    assert result.exit_code == 124
