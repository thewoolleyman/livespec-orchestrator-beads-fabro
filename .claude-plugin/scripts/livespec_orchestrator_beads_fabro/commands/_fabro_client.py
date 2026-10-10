"""Fabro client-version projections shared by plan recording and launch."""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = [
    "fabro_input_args",
    "fabro_uses_workflow_package",
    "materialized_workflow_config",
    "run_workflow",
]


def fabro_uses_workflow_package(*, version: str | None) -> bool:
    """Whether this client accepts a self-contained workflow package."""
    return version is not None and version.startswith("fabro ")


def run_workflow(*, version: str | None, workflow_toml: Path) -> Path:
    """Project a materialized config path to this client's launch argument."""
    config = materialized_workflow_config(
        version=version,
        overlay=workflow_toml,
        package_dir=workflow_toml.parent,
    )
    if fabro_uses_workflow_package(version=version):
        return config.parent
    return config


def materialized_workflow_config(*, version: str | None, overlay: Path, package_dir: Path) -> Path:
    """Choose where this client's resolved per-dispatch config must live."""
    if fabro_uses_workflow_package(version=version):
        return package_dir / "workflow.toml"
    return overlay


def fabro_input_args(*, inputs: tuple[str, ...]) -> list[str]:
    """Render resolved workflow inputs as repeated CLI arguments."""
    argv: list[str] = []
    for item in inputs:
        argv.extend(["--input", item])
    return argv
