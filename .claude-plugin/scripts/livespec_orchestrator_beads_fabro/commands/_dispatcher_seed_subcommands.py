"""The two subcommands that decide which preserved tree a released item's next dispatch seeds from.

`seed-ruling` records an operator's ruled seed, and `reseed` moves a stale seed onto the
default branch's tip and rules the result. They are wired as one group because the second
feeds the first's carrier (Scenario 185): a reseed ends by writing the same ruling
`seed-ruling` writes. Grouping them also keeps `dispatcher.py` under its file LLOC ceiling.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable

from livespec_orchestrator_beads_fabro.commands._dispatcher_reseed_command import (
    add_reseed_arguments,
    run_reseed_cli,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling_command import (
    add_seed_ruling_arguments,
    run_seed_ruling_cli,
)

__all__: list[str] = [
    "SEED_SUBCOMMAND_HANDLERS",
    "add_seed_subcommands",
]

SEED_SUBCOMMAND_HANDLERS: dict[str, Callable[..., int]] = {
    "reseed": run_reseed_cli,
    "seed-ruling": run_seed_ruling_cli,
}


def add_seed_subcommands(*, add_parser: Callable[[str], argparse.ArgumentParser]) -> None:
    """Register both subcommands' flag surfaces on the dispatcher's subparsers."""
    add_seed_ruling_arguments(parser=add_parser("seed-ruling"))
    add_reseed_arguments(parser=add_parser("reseed"))
