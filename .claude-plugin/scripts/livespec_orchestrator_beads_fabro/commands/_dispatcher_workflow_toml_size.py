"""Size limits for the run-config file handed to Fabro."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "FABRO_WORKFLOW_TOML_LIMIT_BYTES",
    "MATERIALIZED_WORKFLOW_TOML_BUILD_THRESHOLD_BYTES",
    "build_size_refusal",
    "build_size_report",
    "dispatch_size_refusal",
    "main",
    "representative_materialized_workflow_toml_size",
]

FABRO_WORKFLOW_TOML_LIMIT_BYTES = 524_288
MATERIALIZED_WORKFLOW_TOML_BUILD_THRESHOLD_BYTES = 471_859


def build_size_report(*, measured_bytes: int) -> str:
    """Describe one representative rendered run-config measurement."""
    return (
        f"materialized workflow.toml is {measured_bytes} bytes; build threshold is "
        f"{MATERIALIZED_WORKFLOW_TOML_BUILD_THRESHOLD_BYTES} bytes; Fabro limit is "
        f"{FABRO_WORKFLOW_TOML_LIMIT_BYTES} bytes"
    )


def build_size_refusal(*, measured_bytes: int) -> str | None:
    """Return the release-blocking diagnostic when the representative is too large."""
    return (
        build_size_report(measured_bytes=measured_bytes)
        if measured_bytes > MATERIALIZED_WORKFLOW_TOML_BUILD_THRESHOLD_BYTES
        else None
    )


def dispatch_size_refusal(*, measured_bytes: int) -> str | None:
    """Return the no-claim refusal for an engine-limit overrun."""
    if measured_bytes <= FABRO_WORKFLOW_TOML_LIMIT_BYTES:
        return None
    return (
        "REFUSED: materialized workflow.toml is "
        f"{measured_bytes} bytes; Fabro limit is {FABRO_WORKFLOW_TOML_LIMIT_BYTES} bytes; "
        "no claim was taken and no Fabro run was created"
    )


def representative_materialized_workflow_toml_size(*, workflow_toml: Path) -> int:
    """Measure a rendered launch overlay for the bundled release guard."""
    rendered = render_run_config_overlay(
        committed_text=workflow_toml.read_text(encoding="utf-8"),
        workflow_dir=workflow_toml.parent.resolve(),
        token="representative-claude-token",
        github_token="representative-github-token",
        siblings=None,
    )
    if rendered is None:
        raise ValueError(f"workflow config {workflow_toml} is not materializable")
    return len(rendered.encode("utf-8"))


def main() -> int:
    """Run the representative materialized-workflow size check."""
    workflow_toml = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.toml")
    measured_bytes = representative_materialized_workflow_toml_size(workflow_toml=workflow_toml)
    write_stdout(text=f"{build_size_report(measured_bytes=measured_bytes)}\n")
    return int(build_size_refusal(measured_bytes=measured_bytes) is not None)


if __name__ == "__main__":
    raise SystemExit(main())
