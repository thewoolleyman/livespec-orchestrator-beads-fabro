"""The seed subcommand group registers both flag surfaces and both handlers."""

from __future__ import annotations

import argparse

from livespec_orchestrator_beads_fabro.commands._dispatcher_reseed_command import run_reseed_cli
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling_command import (
    run_seed_ruling_cli,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_subcommands import (
    SEED_SUBCOMMAND_HANDLERS,
    add_seed_subcommands,
)


def test_the_group_wires_seed_ruling_and_reseed_to_their_own_handlers() -> None:
    assert {
        "reseed": run_reseed_cli,
        "seed-ruling": run_seed_ruling_cli,
    } == SEED_SUBCOMMAND_HANDLERS


def test_the_group_registers_one_parser_per_subcommand() -> None:
    top = argparse.ArgumentParser()
    subparsers = top.add_subparsers(dest="command")

    add_seed_subcommands(add_parser=subparsers.add_parser)

    assert sorted(subparsers.choices) == ["reseed", "seed-ruling"]
    parsed = top.parse_args(["reseed", "--item", "bd-ib-x", "--seed-ref", "refs/heads/s"])
    assert (parsed.command, parsed.item, parsed.seed_ref) == ("reseed", "bd-ib-x", "refs/heads/s")
