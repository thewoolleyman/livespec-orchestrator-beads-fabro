"""Tests for the Beads/Fabro golden-master acceptance harness."""

from pathlib import Path

from livespec_orchestrator_beads_fabro.acceptance import AcceptanceConfig, run_acceptance


def _seed_fixture(*, spec_root: Path) -> None:
    spec_root.mkdir(parents=True)
    _ = (spec_root / "spec.md").write_text(
        "\n".join(
            [
                "# hello-world-greets-a-name",
                "",
                "The generated program accepts one name and returns a greeting.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _ = (spec_root / "contracts.md").write_text(
        "\n".join(
            [
                "# contracts.md",
                "",
                "The runtime behavior is exactly: `Hello, <name>!`.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _ = (spec_root / "constraints.md").write_text(
        "# constraints.md\n\nNo network, credentials, or host services for the hermetic tier.\n",
        encoding="utf-8",
    )
    _ = (spec_root / "scenarios.md").write_text(
        "# scenarios.md\n\nWhen the supplied name is Ada, the greeting is `Hello, Ada!`.\n",
        encoding="utf-8",
    )


def test_acceptance_harness_materializes_beads_fabro_fixture(tmp_path: Path) -> None:
    spec_root = tmp_path / "fixture" / "SPECIFICATION"
    _seed_fixture(spec_root=spec_root)

    result = run_acceptance(
        config=AcceptanceConfig(
            spec_root=spec_root,
            workspace=tmp_path / "run",
            name="Ada",
        )
    )

    assert result.fixture_name == "hello-world-greets-a-name"
    assert result.orchestrator_tier == "beads-fabro-hermetic"
    assert result.greeting == "Hello, Ada!"
    assert result.generated_program.read_text(encoding="utf-8") == (
        '"""Generated Beads/Fabro hello-world program."""\n\n'
        "def greet(name: str) -> str:\n"
        '    return f"Hello, {name}!"\n'
    )
