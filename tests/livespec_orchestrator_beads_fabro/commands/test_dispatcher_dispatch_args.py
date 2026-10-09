"""The `--workflow-name` recorded argument, end to end across its surfaces.

`_dispatcher_dispatch_args` declares the flag group every DISPATCHING
subcommand shares, so the parser assertions belong here. The drive-transport
and journal assertions ride along because they are the SAME claim at its other
two ends: a selector that is an argument rather than an environment variable
is only worth anything if it survives into the recorded argv and onto the
dispatch record, where a later reader can see which graph ran.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import dispatcher, drive
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
    append_dispatch_id_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_binary_record import (
    EngineBinary,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_contract import (
    resolve_integration_contract,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile


def _dispatcher_parser() -> argparse.ArgumentParser:
    """The Dispatcher's own argument parser.

    Reaching for the parser builder is deliberate: the claim under test is
    that the CLI SURFACE accepts `--workflow-name`, and the parser is where
    that surface is defined. Driving `main` instead would run a real dispatch
    to assert an argument declaration.
    """
    return dispatcher._build_parser()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


def test_dispatch_loop_and_probe_accept_a_workflow_name_argument() -> None:
    """All three dispatching subcommands carry the per-dispatch selector."""
    parser = _dispatcher_parser()
    for subcommand, extra in (
        ("dispatch", []),
        ("loop", ["--budget", "1"]),
        ("probe", []),
    ):
        args = parser.parse_args(
            [
                subcommand,
                "--repo",
                ".",
                "--item",
                "bd-ib-u7arwz",
                *extra,
                "--workflow-name",
                "codex-first",
            ]
        )
        assert args.workflow_name == "codex-first", subcommand


def test_omitting_the_argument_leaves_the_ledger_and_default_in_charge() -> None:
    """No explicit selection is the normal case and resolves to None."""
    parser = _dispatcher_parser()
    args = parser.parse_args(["dispatch", "--repo", ".", "--item", "bd-ib-u7arwz"])
    assert args.workflow_name is None


def test_the_probe_still_carries_the_rest_of_the_shared_flag_surface() -> None:
    """The extracted group moved WHOLE: the probe's namespace is unchanged.

    `--acp-node` and the `force=False` default are the two ends of that group
    the probe depends on, so asserting both proves the split carried the
    surface rather than a slice of it.
    """
    parser = _dispatcher_parser()

    args = parser.parse_args(
        ["probe", "--repo", ".", "--item", "bd-ib-u7arwz", "--acp-node", "pr=uvx pr-acp"]
    )

    assert args.acp_node == ["pr=uvx pr-acp"]
    assert args.force is False


def test_drive_re_emits_the_selected_variant_as_its_own_argv_pair(tmp_path: Path) -> None:
    """`drive impl:<id>` carries the selector through to `dispatcher.py loop`.

    It is its own `--workflow-name VALUE` pair for the reason the ACP
    overrides are: the value reaches the Dispatcher as ONE argv element, and
    the argv is what the drive result payload publishes back.
    """
    argv = drive.build_dispatcher_argv(
        repo=tmp_path,
        dispatcher_bin=tmp_path / "dispatcher.py",
        work_item_ref="bd-ib-u7arwz",
        workflow_name="codex-first",
    )

    assert argv.count("--workflow-name") == 1
    assert argv[argv.index("--workflow-name") + 1] == "codex-first"
    # The selector precedes `--json`, which stays the terminal flag.
    assert argv[-1] == "--json"


def test_drive_without_a_selection_builds_the_argv_it_always_did(tmp_path: Path) -> None:
    """No selection means NO argument, so the Dispatcher's own precedence runs.

    Emitting an empty value instead would pre-empt the item's recorded pin
    with a name that selects nothing.
    """
    argv = drive.build_dispatcher_argv(
        repo=tmp_path,
        dispatcher_bin=tmp_path / "dispatcher.py",
        work_item_ref="bd-ib-u7arwz",
    )

    assert "--workflow-name" not in argv


def test_drive_main_passes_its_selection_into_the_dispatcher_argv(tmp_path: Path) -> None:
    """The `drive` CLI wires `--workflow-name` all the way into the argv."""
    seen: list[tuple[str, ...]] = []

    def _runner(*, argv: tuple[str, ...], cwd: Path | None = None) -> drive.CommandRun:
        _ = cwd
        seen.append(argv)
        return drive.CommandRun(argv=argv, returncode=0, stdout="[]", stderr="")

    exit_code = drive.main(
        argv=[
            "--repo",
            str(tmp_path),
            "--action",
            "impl:bd-ib-u7arwz",
            "--workflow-name",
            "codex-first",
            "--json",
        ],
        runner=_runner,
    )

    assert exit_code == 0
    [argv] = seen
    assert "--workflow-name" in argv
    assert "codex-first" in argv


def test_the_dispatch_record_carries_workflow_name_beside_workflow_toml(
    tmp_path: Path,
) -> None:
    """The journal names WHICH variant ran, not only which file resolved.

    Neither field recovers the other once a target registers more than one
    directory, so a reader reconstructing a finished run needs both.
    """
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    committed = tmp_path / ".fabro" / "workflows" / "codex-first" / "workflow.toml"

    append_dispatch_id_record(
        journal=journal,
        work_item_id="li-wfl-journal",
        identity=DispatchJournalIdentity(dispatch_id="d-1", dispatch_factory=None),
        engine=EngineBinary(path="/global/fabro", version="fabro 0.254.0"),
        started_at_epoch=1.0,
        workflow_toml=committed,
        workflow_name="codex-first",
        integration=resolve_integration_contract(declaration={}),
        merge_hold=False,
    )

    record = json.loads((tmp_path / "journal.jsonl").read_text(encoding="utf-8").strip())
    assert record["workflow_name"] == "codex-first"
    assert record["workflow_toml"] == str(committed)
