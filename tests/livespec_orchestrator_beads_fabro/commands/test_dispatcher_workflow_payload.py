"""Per-dispatch workflow-payload materialization.

The resolved node timeouts cannot be templated into the graph, so the
Dispatcher renders them into a per-dispatch COPY of the whole workflow
payload and points the run-config overlay at that copy. These tests pin the
three properties that copy has to have: the rendered graph carries literal
durations, the prompts travel with it (Fabro resolves `@prompts/...`
against the graph file's own path, so a graph rendered anywhere else would
resolve its prompts nowhere), and every refusal happens BEFORE any run.
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
    workflow_graph_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
    WorkflowPayload,
    materialize_workflow_payload,
    prepare_workflow_payload,
    remove_workflow_payload,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import default_node_timeouts

_CONFIG_NAME = ".livespec.jsonc"
_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"
_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)
_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="14400s"\n'
    '        prompt="@prompts/implement.md"\n'
    "    ]\n"
    "}\n"
)


# One ACP node's attributes, carrying the adapter-input token the generator
# resolves. The template opener is assembled rather than written literally,
# because the literal pair poisons ledger and goal rendering wherever this
# file's text is quoted (the fleet convention of livespec-dev-tooling-9yb4).
_TOKEN = "{" + "{ inputs.implement_adapter }" + "}"
_ACP_NODE_ATTRS = f'        backend="acp"\n        acp.command="{_TOKEN}"\n'
_ACP_NODE_ATTRS += '        timeout="14400s"\n'


class _RecordingJournal:
    """Minimal JournalWriter seam that keeps every appended record."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _committed_workflow(*, root: Path, graph_text: str = _GRAPH) -> Path:
    workflow_dir = root / "workflow"
    prompts = workflow_dir / "prompts"
    prompts.mkdir(parents=True)
    _ = (prompts / "implement.md").write_text("implement prompt\n", encoding="utf-8")
    _ = (workflow_dir / "workflow.fabro").write_text(graph_text, encoding="utf-8")
    committed = workflow_dir / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    return committed


def _write_dispatcher_config(*, cwd: Path, dispatcher: dict[str, object]) -> None:
    _ = (cwd / _CONFIG_NAME).write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )


def test_payload_renders_the_graph_and_carries_its_prompts(tmp_path: Path) -> None:
    """The materialized payload holds the rendered graph next to its prompts."""
    committed = _committed_workflow(root=tmp_path)
    payload = materialize_workflow_payload(
        committed=committed,
        payload_dir=tmp_path / "payload",
        timeouts=default_node_timeouts(),
        adapters={},
    )
    assert isinstance(payload, WorkflowPayload)
    assert payload.graph == tmp_path / "payload" / "workflow.fabro"
    assert 'timeout="1800s"' in payload.graph.read_text(encoding="utf-8")
    assert (payload.graph.parent / "prompts" / "implement.md").is_file()
    assert payload.node_seconds == {"implement": 1800}
    # The committed source is left exactly as it was.
    assert 'timeout="14400s"' in (committed.parent / "workflow.fabro").read_text(encoding="utf-8")


def test_payload_replaces_a_stale_directory_from_an_earlier_dispatch(tmp_path: Path) -> None:
    """A leftover payload cannot contribute a stale prompt to this run."""
    committed = _committed_workflow(root=tmp_path)
    payload_dir = tmp_path / "payload"
    payload_dir.mkdir()
    _ = (payload_dir / "stale.md").write_text("from an earlier dispatch\n", encoding="utf-8")
    payload = materialize_workflow_payload(
        committed=committed,
        payload_dir=payload_dir,
        timeouts=default_node_timeouts(),
        adapters={},
    )
    assert isinstance(payload, WorkflowPayload)
    assert not (payload_dir / "stale.md").exists()


def test_prepare_journals_the_resolved_timeouts_with_their_layers(tmp_path: Path) -> None:
    """The dispatch record names the supplying layer for every rendered node."""
    committed = _committed_workflow(root=tmp_path)
    _write_dispatcher_config(cwd=tmp_path, dispatcher={"node_timeouts": {"implement": 7200}})
    journal = _RecordingJournal()
    payload = prepare_workflow_payload(
        repo=tmp_path,
        committed=committed,
        payload_dir=tmp_path / "payload",
        journal=journal,
        work_item_id="bd-ib-test",
        adapters={},
    )
    assert isinstance(payload, WorkflowPayload)
    assert 'timeout="7200s"' in payload.graph.read_text(encoding="utf-8")
    assert len(journal.records) == 1
    record = journal.records[0]
    assert record["stage"] == "node-timeouts"
    assert record["work_item_id"] == "bd-ib-test"
    assert record["node_timeouts"] == {"implement": {"seconds": 7200, "layer": "repository"}}


def test_prepare_refuses_an_invalid_timeout_before_materializing(tmp_path: Path) -> None:
    """A config typo refuses, and no payload directory is created."""
    committed = _committed_workflow(root=tmp_path)
    _write_dispatcher_config(cwd=tmp_path, dispatcher={"node_timeouts": {"implement": 0}})
    journal = _RecordingJournal()
    payload_dir = tmp_path / "payload"
    refusal = prepare_workflow_payload(
        repo=tmp_path,
        committed=committed,
        payload_dir=payload_dir,
        journal=journal,
        work_item_id="bd-ib-test",
        adapters={},
    )
    assert isinstance(refusal, str)
    assert "dispatcher.node_timeouts.implement" in refusal
    assert not payload_dir.exists()
    assert journal.records == []


def test_prepare_reports_a_materialization_refusal(tmp_path: Path) -> None:
    """A payload that cannot be rendered refuses rather than journaling."""
    committed = _committed_workflow(root=tmp_path, graph_text="digraph G {\n}\n")
    journal = _RecordingJournal()
    refusal = prepare_workflow_payload(
        repo=tmp_path,
        committed=committed,
        payload_dir=tmp_path / "payload",
        journal=journal,
        work_item_id="bd-ib-test",
        adapters={},
    )
    assert isinstance(refusal, str)
    assert "stall_timeout" in refusal
    assert journal.records == []


def test_unreadable_committed_config_is_refused(tmp_path: Path) -> None:
    """A missing run config refuses, naming the file."""
    refusal = materialize_workflow_payload(
        committed=tmp_path / "absent" / "workflow.toml",
        payload_dir=tmp_path / "payload",
        timeouts=default_node_timeouts(),
        adapters={},
    )
    assert isinstance(refusal, str)
    assert "is unreadable" in refusal


def test_config_without_a_graph_key_is_refused(tmp_path: Path) -> None:
    """A run config declaring no graph refuses, naming what it must carry."""
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text("_version = 1\n", encoding="utf-8")
    refusal = materialize_workflow_payload(
        committed=committed,
        payload_dir=tmp_path / "payload",
        timeouts=default_node_timeouts(),
        adapters={},
    )
    assert isinstance(refusal, str)
    assert "declares no [workflow] graph" in refusal


def test_missing_graph_file_is_refused(tmp_path: Path) -> None:
    """A run config naming a graph that does not exist refuses."""
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    refusal = materialize_workflow_payload(
        committed=committed,
        payload_dir=tmp_path / "payload",
        timeouts=default_node_timeouts(),
        adapters={},
    )
    assert isinstance(refusal, str)
    assert "workflow graph" in refusal
    assert "is unreadable" in refusal


def test_uncopyable_payload_destination_is_refused(tmp_path: Path) -> None:
    """A destination the copy cannot create refuses, naming the directory."""
    committed = _committed_workflow(root=tmp_path)
    blocker = tmp_path / "blocker"
    _ = blocker.write_text("not a directory\n", encoding="utf-8")
    refusal = materialize_workflow_payload(
        committed=committed,
        payload_dir=blocker / "payload",
        timeouts=default_node_timeouts(),
        adapters={},
    )
    assert isinstance(refusal, str)
    assert "is not materializable" in refusal


def test_overlay_points_the_run_at_the_rendered_graph(tmp_path: Path) -> None:
    """`graph_override` replaces the committed graph path in the overlay."""
    override = tmp_path / "payload" / "workflow.fabro"
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        graph_override=override,
    )
    assert rendered is not None
    assert f'graph = "{override}"' in rendered


def test_overlay_absolutizes_the_committed_graph_without_an_override(tmp_path: Path) -> None:
    """No override keeps the pre-existing absolutization behaviour."""
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )
    assert rendered is not None
    assert f'graph = "{tmp_path / "workflow.fabro"}"' in rendered


def test_workflow_graph_path_reads_the_declared_graph(tmp_path: Path) -> None:
    """The shared reader resolves relative and absolute declarations alike."""
    assert workflow_graph_path(committed_text=_COMMITTED_WORKFLOW_TOML, workflow_dir=tmp_path) == (
        tmp_path / "workflow.fabro"
    )
    absolute = f'[workflow]\ngraph = "{tmp_path / "elsewhere.fabro"}"\n'
    assert workflow_graph_path(committed_text=absolute, workflow_dir=tmp_path) == (
        tmp_path / "elsewhere.fabro"
    )
    assert workflow_graph_path(committed_text="_version = 1\n", workflow_dir=tmp_path) is None


def test_payload_removal_tolerates_an_absent_directory(tmp_path: Path) -> None:
    """Teardown is best-effort: None and an already-gone directory both pass."""
    payload_dir = tmp_path / "payload"
    payload_dir.mkdir()
    remove_workflow_payload(payload_dir=payload_dir)
    assert not payload_dir.exists()
    remove_workflow_payload(payload_dir=payload_dir)
    remove_workflow_payload(payload_dir=None)


def test_payload_renders_each_acp_node_command_as_a_literal(tmp_path: Path) -> None:
    """The graph the run receives carries the resolved adapter, not the token.

    Plan `fabro-currency` P4: a templated `acp.command` kills the agent before
    the ACP protocol completes on the Petri-era engine, so the generator is the
    seam that resolves it.
    """
    graph = _GRAPH.replace(
        '        timeout="14400s"\n',
        _ACP_NODE_ATTRS,
        1,
    )
    committed = _committed_workflow(root=tmp_path, graph_text=graph)
    payload = materialize_workflow_payload(
        committed=committed,
        payload_dir=tmp_path / "payload",
        timeouts=default_node_timeouts(),
        adapters={"implement_adapter": "npx -y claude-agent-acp"},
    )
    assert isinstance(payload, WorkflowPayload)
    assert payload.node_commands == {"implement": "npx -y claude-agent-acp"}
    assert 'acp.command="npx -y claude-agent-acp"' in payload.graph.read_text(encoding="utf-8")


def test_payload_refuses_an_acp_node_whose_adapter_did_not_resolve(tmp_path: Path) -> None:
    """A half-rendered graph never reaches the engine: the materializer refuses."""
    graph = _GRAPH.replace(
        '        timeout="14400s"\n',
        _ACP_NODE_ATTRS,
        1,
    )
    committed = _committed_workflow(root=tmp_path, graph_text=graph)
    refusal = materialize_workflow_payload(
        committed=committed,
        payload_dir=tmp_path / "payload",
        timeouts=default_node_timeouts(),
        adapters={},
    )
    assert isinstance(refusal, str)
    assert "implement_adapter" in refusal
    assert not (tmp_path / "payload").exists()
