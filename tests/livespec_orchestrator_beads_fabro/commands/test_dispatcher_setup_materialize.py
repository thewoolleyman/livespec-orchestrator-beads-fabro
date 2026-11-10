"""Moving a rendered overlay's prepare steps into the per-dispatch graph (bd-ib-dpsiwz).

`materialize_overlay` is graded end to end in
`test_dispatcher_setup_nodes_materialization`; these cases cover the decisions of
`materialize_setup_nodes` that a whole dispatch cannot reach cheaply: what it
does with an overlay it cannot split, a graph it cannot read or write, and a graph
that is not a workflow graph at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_setup_materialize import (
    SetupRefusal,
    materialize_setup_nodes,
    overlay_with_setup_nodes,
)

_GRAPH = """digraph G {
    start [shape=Mdiamond]
    exit [shape=Msquare]
    start -> exit
}
"""
_OVERLAY = '[workflow]\ngraph = "workflow.fabro"\n\n[[run.prepare.steps]]\nscript = "echo one"\n'
_STEPLESS_OVERLAY = '[workflow]\ngraph = "workflow.fabro"\n'


_PAYLOAD_OVERLAY = (
    '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "sandbox"\n\n'
    '[[run.prepare.steps]]\nscript = "printf %s \\"$PAYLOAD\\" > /a"\n'
    'env = { PAYLOAD = "the bytes" }\n\n[environments.sandbox.env]\nTOKEN = "t"\n'
)


def _graph(*, tmp_path: Path, text: str = _GRAPH) -> Path:
    path = tmp_path / "workflow.fabro"
    _ = path.write_text(text, encoding="utf-8")
    return path


def test_the_steps_leave_the_overlay_and_arrive_in_the_graph(tmp_path: Path) -> None:
    graph = _graph(tmp_path=tmp_path)
    result = materialize_setup_nodes(overlay_text=_OVERLAY, graph=graph, timeouts=None)
    assert result == _STEPLESS_OVERLAY.rstrip("\n") + "\n\n"
    written = graph.read_text(encoding="utf-8")
    assert "run_prepare_1 [" in written
    assert "start -> run_prepare_1" in written


def test_an_overlay_with_no_steps_leaves_the_graph_untouched(tmp_path: Path) -> None:
    missing = tmp_path / "never-written.fabro"
    result = materialize_setup_nodes(overlay_text=_STEPLESS_OVERLAY, graph=missing, timeouts=None)
    assert result == _STEPLESS_OVERLAY
    assert not missing.exists()


def test_an_overlay_whose_steps_cannot_be_separated_is_refused(tmp_path: Path) -> None:
    unsplittable = '[[run.prepare.steps]]\nscript = """\nmulti\n"""\n'
    result = materialize_setup_nodes(
        overlay_text=unsplittable, graph=_graph(tmp_path=tmp_path), timeouts=None
    )
    assert isinstance(result, SetupRefusal)
    assert "run_prepare_<N>" in result.message


def test_a_graph_that_cannot_be_read_is_refused_naming_it(tmp_path: Path) -> None:
    missing = tmp_path / "missing.fabro"
    result = materialize_setup_nodes(overlay_text=_OVERLAY, graph=missing, timeouts=None)
    assert isinstance(result, SetupRefusal)
    assert str(missing) in result.message
    assert "cannot be read" in result.message


@pytest.mark.parametrize(
    "text",
    [
        "not a graph at all",
        "digraph G {\n    a [label=x]\n    exit [shape=Msquare]\n    a -> exit\n}\n",
    ],
    ids=["unparseable", "no-start-node"],
)
def test_a_graph_that_is_not_a_workflow_graph_leaves_the_steps_where_they_were(
    tmp_path: Path, text: str
) -> None:
    """Every engine rejects it at run-create time, so no run's setup can silently not happen."""
    graph = _graph(tmp_path=tmp_path, text=text)
    result = materialize_setup_nodes(overlay_text=_OVERLAY, graph=graph, timeouts=None)
    assert result == _OVERLAY
    assert graph.read_text(encoding="utf-8") == text


def test_a_start_node_with_nothing_to_hang_the_chain_on_is_refused(tmp_path: Path) -> None:
    text = _GRAPH.replace("    start -> exit\n", "")
    result = materialize_setup_nodes(
        overlay_text=_OVERLAY, graph=_graph(tmp_path=tmp_path, text=text), timeouts=None
    )
    assert isinstance(result, SetupRefusal)
    assert "no unconditional edge" in result.message


def test_a_graph_that_cannot_be_written_back_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = _graph(tmp_path=tmp_path)

    def _refuse(self: Path, data: str, encoding: str | None = None) -> int:
        _ = (self, data, encoding)
        message = "read-only file system"
        raise OSError(message)

    monkeypatch.setattr(Path, "write_text", _refuse)
    result = materialize_setup_nodes(overlay_text=_OVERLAY, graph=graph, timeouts=None)
    assert isinstance(result, SetupRefusal)
    assert "cannot be written" in result.message
    assert "read-only file system" in result.message


def test_a_dispatch_with_no_graph_keeps_its_overlay_and_releases_nothing() -> None:
    released: list[str] = []
    result = overlay_with_setup_nodes(
        rendered=_OVERLAY, graph=None, timeouts=None, release=lambda: released.append("revoke")
    )
    assert result == _OVERLAY
    assert released == []


def test_a_refused_setup_gives_the_minted_credentials_back_once(tmp_path: Path) -> None:
    released: list[str] = []
    result = overlay_with_setup_nodes(
        rendered=_OVERLAY,
        graph=tmp_path / "missing.fabro",
        timeouts=None,
        release=lambda: released.append("revoke"),
    )
    assert isinstance(result, SetupRefusal)
    assert released == ["revoke"]


def test_a_carried_setup_releases_nothing(tmp_path: Path) -> None:
    released: list[str] = []
    result = overlay_with_setup_nodes(
        rendered=_OVERLAY,
        graph=_graph(tmp_path=tmp_path),
        timeouts=None,
        release=lambda: released.append("revoke"),
    )
    assert isinstance(result, str)
    assert "run.prepare" not in result
    assert released == []


def test_a_payload_step_moves_its_bytes_into_the_environment_table(tmp_path: Path) -> None:
    graph = _graph(tmp_path=tmp_path)
    result = materialize_setup_nodes(overlay_text=_PAYLOAD_OVERLAY, graph=graph, timeouts=None)
    assert isinstance(result, str)
    assert 'LIVESPEC_SETUP_1__PAYLOAD = "the bytes"' in result
    assert "run.prepare" not in result
    written = graph.read_text(encoding="utf-8")
    assert "$LIVESPEC_SETUP_1__PAYLOAD" in written
    assert "the bytes" not in written


def test_a_payload_with_no_environment_table_to_take_it_is_refused_before_the_graph_changes(
    tmp_path: Path,
) -> None:
    graph = _graph(tmp_path=tmp_path)
    overlay = _PAYLOAD_OVERLAY.split("[environments.sandbox.env]")[0]
    result = materialize_setup_nodes(overlay_text=overlay, graph=graph, timeouts=None)
    assert isinstance(result, SetupRefusal)
    assert "environment table" in result.message
    assert graph.read_text(encoding="utf-8") == _GRAPH
