"""Codex credential, telemetry, and Driver-hook projections for a run overlay."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth_projection import (
    codex_auth_env_lines,
    codex_auth_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_otel_config import (
    codex_otel_env_lines,
    codex_otel_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_driver_hooks import (
    codex_driver_hooks_prepare_steps_block,
)

__all__: list[str] = [
    "codex_env_lines",
    "codex_fragments",
    "codex_prepare_steps_block",
]


def codex_env_lines(*, codex_auth_snapshot: str | None, codex_otel_config: str | None) -> str:
    """Render every Codex-specific environment projection for a routed sandbox."""
    return codex_auth_env_lines(codex_auth_snapshot=codex_auth_snapshot) + codex_otel_env_lines(
        codex_otel_config=codex_otel_config
    )


def codex_prepare_steps_block(
    *, codex_auth_snapshot: str | None, codex_otel_config: str | None
) -> str:
    """Render setup meaningful only when a Codex credential is routed."""
    if codex_auth_snapshot is None:
        return ""
    return (
        codex_auth_prepare_steps_block(codex_auth_snapshot=codex_auth_snapshot)
        + codex_otel_prepare_steps_block(codex_otel_config=codex_otel_config)
        + codex_driver_hooks_prepare_steps_block()
    )


def codex_fragments(
    *, codex_auth_snapshot: str | None, codex_otel_config: str | None
) -> tuple[str, str]:
    """Render the prepare and environment projections as one Codex concern."""
    return (
        codex_prepare_steps_block(
            codex_auth_snapshot=codex_auth_snapshot,
            codex_otel_config=codex_otel_config,
        ),
        codex_env_lines(
            codex_auth_snapshot=codex_auth_snapshot,
            codex_otel_config=codex_otel_config,
        ),
    )
