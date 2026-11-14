"""Parser registration for operator-only dispatcher commands (valves and recovery)."""

from __future__ import annotations

import argparse
from collections.abc import Callable

from livespec_orchestrator_beads_fabro.commands._acp_hold_clear import (
    add_clear_acp_availability_hold_arguments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fresh_ruling import (
    add_fresh_ruling_arguments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion_clear import (
    add_clear_provider_exhaustion_arguments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_supersede_contaminated import (
    add_supersede_contaminated_arguments,
    run_supersede_contaminated_command,
)

__all__: list[str] = ["add_operator_valve_subcommands", "run_supersede_contaminated_command"]


def add_operator_valve_subcommands(*, add_parser: Callable[[str], argparse.ArgumentParser]) -> None:
    """Register the dispatcher commands that alter human-held admission valves."""
    add_clear_provider_exhaustion_arguments(parser=add_parser("clear-provider-exhaustion"))
    add_clear_acp_availability_hold_arguments(parser=add_parser("clear-acp-availability-hold"))
    add_fresh_ruling_arguments(parser=add_parser("fresh-ruling"))
    add_supersede_contaminated_arguments(parser=add_parser("supersede-contaminated"))
