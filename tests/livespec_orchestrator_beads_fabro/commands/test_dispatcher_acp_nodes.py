"""The dispatch-time seam that assembles the three ACP adapter layers.

`test_acp_node_layers` binds the resolution itself; this file binds the
plumbing around it — reading the WORKFLOW layer out of the committed
`workflow.toml`, journaling what resolved, and carrying the per-dispatch
argument from the two operator entry points (`dispatcher.py dispatch` /
`loop`, and `drive`'s `impl:<id>` action) down to the Dispatcher.

The committed workflow of THIS repo is read directly in one test, on
purpose: an assertion against a hand-written fixture would keep passing if
the real workflow stopped declaring an input, which is the regression that
would silently strand a node on a hard-coded adapter.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands import dispatcher, drive
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import (
    DISPATCH_LAYER,
    REPOSITORY_LAYER,
    WORKFLOW_LAYER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import (
    ACP_NODES_STAGE,
    prepare_acp_nodes,
    workflow_adapter_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_materialize import (
    MaterializationRefusal,
    materialize_dispatch,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMITTED_WORKFLOW = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
)
_CLAUDE = "npx -y @agentclientprotocol/claude-agent-acp"
_ACP_NODES = ("implement", "fix", "review_fix", "pr", "review", "disposition")

_WORKFLOW_TOML = """_version = 1

[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "ANTHROPIC_MODEL=claude-opus-5 npx -y claude-acp"
fix_adapter = "npx -y claude-acp"
review_fix_adapter = "npx -y claude-acp"
pr_adapter = "npx -y claude-acp"
review_adapter = "npx -y claude-acp"
disposition_adapter = "npx -y claude-acp"
review_fix_visit_cap = 4
merge_on_review_cap_outcome = "__merge_on_review_cap_disabled__"

[run.environment]
id = "livespec-ci"
"""


class _RecordingJournal:
    """Collects journal records so the dispatch record can be asserted on."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _dispatcher_parser() -> argparse.ArgumentParser:
    """The Dispatcher's own argument parser.

    Reaching for the parser builder is deliberate: the claim under test is
    that the CLI SURFACE accepts `--acp-node`, and the parser is where that
    surface is defined. Driving `main` instead would run a real dispatch to
    assert an argument declaration.
    """
    return dispatcher._build_parser()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


def _write_workflow(*, tmp_path: Path, text: str = _WORKFLOW_TOML) -> Path:
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(text, encoding="utf-8")
    return committed


def _write_dispatcher_config(*, repo: Path, dispatcher_block: dict[str, object]) -> None:
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Operator",
                    "operator_email": "operator@example.com",
                },
                "livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher_block},
            }
        ),
        encoding="utf-8",
    )


def test_the_committed_workflow_declares_an_adapter_input_for_every_acp_node() -> None:
    """This repo's own workflow declares one adapter input per node.

    Read from the real committed file rather than a fixture: a fixture
    would keep passing while the shipped workflow stopped declaring an
    input, which is exactly how a node ends up unconfigurable.
    """
    declared = workflow_adapter_inputs(
        committed_text=_COMMITTED_WORKFLOW.read_text(encoding="utf-8")
    )
    assert set(declared) == {f"{node}_adapter" for node in _ACP_NODES}
    assert declared["implement_adapter"].endswith(_CLAUDE)
    assert "ANTHROPIC_MODEL=claude-opus-5" in declared["implement_adapter"]


def test_reading_adapter_inputs_ignores_non_adapter_inputs() -> None:
    """The `[run.inputs]` scan takes adapters and leaves the other inputs alone."""
    declared = workflow_adapter_inputs(committed_text=_WORKFLOW_TOML)
    assert "review_fix_visit_cap" not in declared
    assert "merge_on_review_cap_outcome" not in declared
    assert declared["pr_adapter"] == "npx -y claude-acp"


def test_a_workflow_with_no_run_inputs_table_declares_nothing() -> None:
    """An absent table is an empty declaration, not a crash."""
    assert workflow_adapter_inputs(committed_text="_version = 1\n") == {}


def test_prepare_resolves_journals_and_names_the_layer_per_node(tmp_path: Path) -> None:
    """The dispatch record carries the rendered adapter and its supplying layer."""
    committed = _write_workflow(tmp_path=tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_dispatcher_config(
        repo=repo,
        dispatcher_block={"acp_nodes": {"review": {"command": "uvx review-acp"}}},
    )
    journal = _RecordingJournal()
    resolution = prepare_acp_nodes(
        repo=repo,
        committed=committed,
        overrides=("disposition=uvx disposition-acp",),
        journal=journal,
        work_item_id="bd-ib-tsna",
    )
    assert not isinstance(resolution, str), resolution
    [record] = [entry for entry in journal.records if entry["stage"] == ACP_NODES_STAGE]
    assert record["work_item_id"] == "bd-ib-tsna"
    nodes: Any = record["acp_nodes"]
    assert nodes["review"]["adapter"] == "uvx review-acp"
    assert nodes["review"]["layers"]["command"] == REPOSITORY_LAYER
    assert nodes["disposition"]["adapter"] == "uvx disposition-acp"
    assert nodes["disposition"]["layers"]["command"] == DISPATCH_LAYER
    assert nodes["fix"]["layers"]["command"] == WORKFLOW_LAYER
    assert set(nodes) == set(_ACP_NODES)


def test_prepare_refuses_an_unreadable_workflow_config(tmp_path: Path) -> None:
    """A missing committed config refuses naming the path rather than raising."""
    journal = _RecordingJournal()
    refusal = prepare_acp_nodes(
        repo=tmp_path,
        committed=tmp_path / "absent.toml",
        overrides=(),
        journal=journal,
        work_item_id="bd-ib-tsna",
    )
    assert isinstance(refusal, str)
    assert "absent.toml" in refusal
    assert journal.records == []


def test_prepare_refuses_a_malformed_repository_entry_without_journaling(
    tmp_path: Path,
) -> None:
    """A refusal happens BEFORE any run exists, and records no resolution."""
    committed = _write_workflow(tmp_path=tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_dispatcher_config(repo=repo, dispatcher_block={"acp_nodes": {"nope": "uvx acp"}})
    journal = _RecordingJournal()
    refusal = prepare_acp_nodes(
        repo=repo,
        committed=committed,
        overrides=(),
        journal=journal,
        work_item_id="bd-ib-tsna",
    )
    assert isinstance(refusal, str)
    assert "nope" in refusal
    assert journal.records == []


def test_prepare_refuses_a_malformed_per_dispatch_argument(tmp_path: Path) -> None:
    """A `--acp-node` typo refuses before the run rather than being ignored."""
    committed = _write_workflow(tmp_path=tmp_path)
    journal = _RecordingJournal()
    refusal = prepare_acp_nodes(
        repo=tmp_path,
        committed=committed,
        overrides=("implement",),
        journal=journal,
        work_item_id="bd-ib-tsna",
    )
    assert isinstance(refusal, str)
    assert "<node>=<adapter command>" in refusal
    assert journal.records == []


def test_dispatch_and_loop_accept_a_repeatable_acp_node_argument() -> None:
    """Both dispatching subcommands carry the per-dispatch layer."""
    parser = _dispatcher_parser()
    for subcommand, extra in (("dispatch", []), ("loop", ["--budget", "1"])):
        args = parser.parse_args(
            [
                subcommand,
                "--repo",
                ".",
                "--item",
                "bd-ib-tsna",
                *extra,
                "--acp-node",
                f"implement=ANTHROPIC_MODEL=qwen3 {_CLAUDE}",
                "--acp-node",
                "pr=uvx pr-acp",
            ]
        )
        assert args.acp_node == [
            f"implement=ANTHROPIC_MODEL=qwen3 {_CLAUDE}",
            "pr=uvx pr-acp",
        ], subcommand


def test_omitting_the_argument_leaves_the_two_lower_layers_in_charge() -> None:
    """No per-dispatch override is the normal case and resolves to None."""
    parser = _dispatcher_parser()
    args = parser.parse_args(["dispatch", "--repo", ".", "--item", "bd-ib-tsna"])
    assert args.acp_node is None


def test_drive_forwards_each_override_as_its_own_argv_pair(tmp_path: Path) -> None:
    """`drive impl:<id>` carries the override through to `dispatcher.py loop`.

    Each override is its own `--acp-node VALUE` pair so an adapter carrying
    spaces reaches the Dispatcher as ONE argv element — a single joined
    string would split at the first space and name a command nobody wrote.
    """
    argv = drive.build_dispatcher_argv(
        repo=tmp_path,
        dispatcher_bin=tmp_path / "dispatcher.py",
        work_item_ref="bd-ib-tsna",
        acp_nodes=(f"implement=ANTHROPIC_MODEL=qwen3 {_CLAUDE}", "pr=uvx pr-acp"),
    )
    assert argv.count("--acp-node") == 2
    assert f"implement=ANTHROPIC_MODEL=qwen3 {_CLAUDE}" in argv
    assert "pr=uvx pr-acp" in argv
    # The overrides precede `--json`, which stays the terminal flag.
    assert argv[-1] == "--json"


def test_drive_without_overrides_builds_the_argv_it_always_did(tmp_path: Path) -> None:
    """The default operator path is unchanged: no override, no argument."""
    argv = drive.build_dispatcher_argv(
        repo=tmp_path,
        dispatcher_bin=tmp_path / "dispatcher.py",
        work_item_ref="bd-ib-tsna",
    )
    assert "--acp-node" not in argv


def test_drive_main_passes_its_overrides_into_the_action(tmp_path: Path) -> None:
    """The `drive` CLI wires `--acp-node` all the way into the dispatcher argv."""
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
            "impl:bd-ib-tsna",
            "--acp-node",
            "review=uvx review-acp",
            "--json",
        ],
        runner=_runner,
    )
    assert exit_code == 0
    [argv] = seen
    assert "--acp-node" in argv
    assert "review=uvx review-acp" in argv


def test_prepare_routes_a_malformed_acp_nodes_table_as_a_refusal(tmp_path: Path) -> None:
    """A non-table `dispatcher.acp_nodes` refuses through the config seam.

    Distinct from the unknown-node case: this one is refused while READING
    the target's configuration, before any resolution is attempted, so it
    exercises the seam's own refusal path rather than the resolver's.
    """
    committed = _write_workflow(tmp_path=tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_dispatcher_config(repo=repo, dispatcher_block={"acp_nodes": "not-a-table"})
    journal = _RecordingJournal()
    refusal = prepare_acp_nodes(
        repo=repo,
        committed=committed,
        overrides=(),
        journal=journal,
        work_item_id="bd-ib-tsna",
    )
    assert isinstance(refusal, str)
    assert "dispatcher.acp_nodes" in refusal
    assert journal.records == []


def test_materialize_dispatch_routes_an_adapter_refusal_to_its_own_stage(
    tmp_path: Path,
) -> None:
    """A bad adapter config fails the dispatch at `acp-nodes`, not at the payload.

    The two pre-run materialization steps share a call site but not a
    stage: a reader of the journal has to be able to tell a timeout typo
    from an adapter typo without opening the detail string.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    # The REAL committed workflow directory, so the payload step (which
    # renders the graph) genuinely succeeds and the adapter step is what
    # fails — a fixture without a graph would refuse one stage earlier and
    # the test would pass while proving nothing about the adapter stage.
    workflow_dir = tmp_path / "workflow"
    _ = shutil.copytree(_COMMITTED_WORKFLOW.parent, workflow_dir)
    committed = workflow_dir / "workflow.toml"
    _write_dispatcher_config(repo=repo, dispatcher_block={"acp_nodes": {"nope": "uvx acp"}})
    journal = _RecordingJournal()
    refusal = materialize_dispatch(
        args=argparse.Namespace(workflow=str(committed), repo=str(repo)),
        repo=repo,
        work_item_id="bd-ib-tsna",
        journal=journal,
    )
    assert isinstance(refusal, MaterializationRefusal)
    assert refusal.stage == ACP_NODES_STAGE
    assert "nope" in refusal.detail
    # The payload step ran and journaled first; only the adapter step refused.
    assert [record["stage"] for record in journal.records] == ["node-timeouts"]
