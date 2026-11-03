"""Construction of the Fabro CLI facade from one resolved dispatch plan."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroRunner, FabroTarget

__all__: list[str] = ["fabro_port_for_plan"]

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort


def fabro_port_for_plan(*, plan: Any, runner: FabroRunner) -> FabroPort:
    """Construct the Fabro CLI port from a dispatch plan."""
    from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

    return FabroPort(
        fabro_bin=plan.fabro_bin,
        target=FabroTarget(
            server_url=plan.fabro_factory_server,
            dev_token=plan.fabro_factory_dev_token,
            environment=plan.fabro_factory_environment,
        ),
        runner=runner,
        cwd=plan.repo,
        fabro_version=getattr(plan, "fabro_version", None),
    )
