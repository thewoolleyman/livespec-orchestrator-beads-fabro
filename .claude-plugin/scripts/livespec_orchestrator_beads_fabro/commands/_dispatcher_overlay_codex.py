"""Codex credential, telemetry, and Driver-hook projections for a run overlay.

`_dispatcher_overlay` assembles runtime-neutral projections into a run config.
This module owns the Codex-only subset: these three prepare-step blocks all
depend on the same optional Codex credential, and none has meaning when the
sandbox does not receive a per-run `CODEX_HOME`.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth_projection import (
    codex_auth_env_lines,
    codex_auth_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_driver_hooks import (
    codex_driver_hooks_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_otel_config import (
    codex_otel_env_lines,
    codex_otel_prepare_steps_block,
)

__all__: list[str] = [
    "codex_env_lines",
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
    """Render setup that is meaningful only when a Codex credential is routed.

    The Driver installer writes into `CODEX_HOME`, so it must remain conditional
    with its credential projection. The telemetry writer has the same guard.
    """
    if codex_auth_snapshot is None:
        return ""
    return (
        codex_auth_prepare_steps_block(codex_auth_snapshot=codex_auth_snapshot)
        + codex_otel_prepare_steps_block(codex_otel_config=codex_otel_config)
        + codex_driver_hooks_prepare_steps_block()
    )
