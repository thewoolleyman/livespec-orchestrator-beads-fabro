"""Size limits for the run-config file handed to Fabro."""

from __future__ import annotations

__all__: list[str] = [
    "FABRO_WORKFLOW_TOML_LIMIT_BYTES",
    "MATERIALIZED_WORKFLOW_TOML_BUILD_THRESHOLD_BYTES",
    "build_size_refusal",
    "build_size_report",
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
