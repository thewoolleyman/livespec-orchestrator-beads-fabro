"""Golden-master acceptance test for the Beads/Fabro implementation."""

from pathlib import Path

from livespec_orchestrator_beads_fabro.acceptance import AcceptanceConfig, run_acceptance


def _fixture_spec_root(*, fixture_name: str) -> Path:
    return Path("acceptance") / "fixtures" / fixture_name / "SPECIFICATION"


def test_beads_fabro_golden_master_generates_greeting_program(tmp_path: Path) -> None:
    result = run_acceptance(
        config=AcceptanceConfig(
            spec_root=_fixture_spec_root(fixture_name="hello-world-greets-a-name"),
            workspace=tmp_path / "run",
            name="Ada",
        )
    )

    assert result.fixture_name == "hello-world-greets-a-name"
    assert result.orchestrator_tier == "beads-fabro-hermetic"
    assert result.greeting == "Hello, Ada!"
    assert result.generated_program.is_file()
