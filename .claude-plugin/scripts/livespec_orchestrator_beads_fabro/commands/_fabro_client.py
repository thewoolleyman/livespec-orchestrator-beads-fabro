"""Fabro client-version projections shared by plan recording and launch."""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = [
    "fabro_input_args",
    "fabro_label_args",
    "fabro_uses_workflow_package",
    "materialized_workflow_config",
    "overlay_graph_reference",
    "run_workflow",
]


def fabro_uses_workflow_package(*, version: str | None) -> bool:
    """Whether this client accepts a self-contained workflow package."""
    return (
        version is not None
        and version.startswith("fabro ")
        and not version.startswith("fabro 0.254.")
    )


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


def overlay_graph_reference(*, version: str | None, graph: Path, package_dir: Path) -> Path:
    """Name the rendered graph the way this client's resolved config can reach it.

    A Petri-era client is handed the package DIRECTORY, and the engine collects
    the `workflow.toml` inside it as a local workflow — so that config's
    `[workflow] graph` is an INLINE FILE REFERENCE, and the engine refuses an
    absolute path in one outright, before any run exists: `invalid file inline
    reference in workflow.toml: ...; invalid workflow path ...: absolute paths
    are not allowed`. An inline reference resolves against the collected
    package, so the graph beside the config is named relative to it.

    The pinned 0.254 client is handed the overlay FILE, which lives OUTSIDE the
    payload, so a relative reference there would resolve against a directory
    that is not the payload. Its graph keeps the absolute path it has always
    carried; this is the behaviour `materialized_workflow_config` above splits
    the two launch shapes for, named for the written config rather than for the
    launch argument.

    `relative_to` is what makes the relative form say "inside this package"
    rather than merely "this file name": a graph the package does not contain
    is a geometry bug in the caller, and raising is the honest answer to it.
    """
    if fabro_uses_workflow_package(version=version):
        return graph.relative_to(package_dir)
    return graph


def fabro_input_args(*, inputs: tuple[str, ...]) -> list[str]:
    """Render resolved workflow inputs as repeated CLI arguments."""
    argv: list[str] = []
    for item in inputs:
        argv.extend(["--input", item])
    return argv


def fabro_label_args(*, labels: tuple[str, ...]) -> list[str]:
    """Render resolved run labels as repeated CLI arguments.

    The FLAG and its operand are two argv tokens, as they are for
    `--input` above: the engine reads them as a pair, so a value spliced
    onto the flag is rejected at argument parsing rather than carried.
    """
    argv: list[str] = []
    for label in labels:
        argv.extend(["--label", label])
    return argv
