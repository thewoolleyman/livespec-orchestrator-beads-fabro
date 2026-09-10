"""Integration-tier acceptance for per-node timeouts as configuration.

Binds SPECIFICATION/scenarios.md "Scenario 89 — Node timeouts resolve from
configuration and land as literal durations" and the contracts.md section
"ACP node timeouts":

    Every node timeout of the `implement-work-item` workflow, and the run's
    stall watchdog, MUST resolve from configuration rather than from
    literals hard-coded in the workflow graph.

This is the top-of-pyramid behavior journey: it drives the real
`dispatcher.main(argv=["dispatch", ...])` CLI through the REAL store/client
seam against the in-memory `FakeBeadsClient`, with `run_dispatch` replaced
by a stand-in that captures the plan and READS BACK the workflow graph the
run would actually have received. The four cases mirror the scenario's four:
a default target renders 1800s everywhere, a configured node keeps its value
while the others take the default, the subprocess ceiling follows the
resolved graph, and an invalid timeout refuses before any run exists.

The literal-duration assertion is the load-bearing one. A `timeout`
templated from a workflow input would render to a string the pinned Fabro
build cannot read as a duration, leaving the node with NO timeout at all and
reporting nothing — so the rendered graph is checked for template openers
rather than trusted.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    default_node_timeouts,
    derive_fabro_timeout_seconds,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_FLEET_MANIFEST_TEXT = (
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [\n'
    '    { "repo": "livespec", "class": "core" },\n'
    '    { "repo": "repo", "class": "impl-plugin" }\n'
    "  ]\n"
    "}\n"
)

_COMMITTED_WORKFLOW_TOML = (
    '[workflow]\ngraph = "graph.toml"\n\n[run.environment]\nid = "fabro-sandbox"\n'
)

# Three nodes with timeouts plus the run-level watchdog: enough to show a
# configured node diverging from the defaulted ones in one rendered graph.
_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        acp.command="{{ inputs.acp_adapter }}"\n'
    '        timeout="14400s"\n'
    "    ]\n"
    "\n"
    "    janitor [\n"
    '        timeout="3600s"\n'
    "    ]\n"
    "\n"
    "    pr [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)

_TIMEOUT_ATTR_RE = re.compile(r'(?<![\w.])timeout[ \t]*=[ \t]*"(?P<value>[^"]*)"')
_TEMPLATE_OPENERS = ("{" "{", "{" "%", "{" "#")


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic C-mode dispatch environment + fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("fabro-node-timeouts")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id="livespec-impl-beads-slice1",
        type="task",
        status="ready",
        title="A dispatched slice",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        # A dispatchable fixture carries gradeable criteria: the entry-to-`ready`
        # and pre-dispatch walls (the effective-acceptance-criteria clause of contracts.md)
        # refuse an AI-dispositive item whose effective criteria parse to zero
        # gradeable assertions.
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def _repo_with_workflow(*, tmp_path: Path, dispatcher: dict[str, object]) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    block: dict[str, object] = {"connection": {"prefix": "bd-ib"}}
    if dispatcher:
        block["dispatcher"] = dispatcher
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Chad Woolley",
                    "operator_email": "thewoolleyman@gmail.com",
                },
                "livespec-orchestrator-beads-fabro": block,
            }
        ),
        encoding="utf-8",
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow.parent / "graph.toml").write_text(_GRAPH, encoding="utf-8")
    return repo, workflow


class _CapturingRunDispatch:
    """A `run_dispatch` stand-in that reads back the graph the run receives."""

    def __init__(self) -> None:
        self.graph_text = ""
        self.timeout_seconds = 0.0

    def __call__(self, **kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        overlay = plan.workflow_toml.read_text(encoding="utf-8")
        graph = Path(overlay.split('graph = "', 1)[1].split('"', 1)[0])
        self.graph_text = graph.read_text(encoding="utf-8")
        self.timeout_seconds = plan.fabro_timeout_seconds
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="failed",
            stage="fabro-run",
            pr_number=None,
            merge_sha=None,
            detail="hermetic stand-in",
        )


def _dispatch(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dispatcher: dict[str, object],
) -> tuple[int, _CapturingRunDispatch]:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path, dispatcher=dispatcher)
    item = _item()
    append_work_item(path=_config(), item=item)
    capturing = _CapturingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", capturing)
    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )
    return exit_code, capturing


def _timeout_values(*, graph_text: str) -> list[str]:
    return [match.group("value") for match in _TIMEOUT_ATTR_RE.finditer(graph_text)]


def test_default_target_renders_every_node_at_1800_seconds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A target with no node_timeouts table renders 1800s and no template opener."""
    _exit_code, capturing = _dispatch(tmp_path=tmp_path, monkeypatch=monkeypatch, dispatcher={})
    assert _timeout_values(graph_text=capturing.graph_text) == ["1800s", "1800s", "1800s"]
    assert 'stall_timeout="7200s"' in capturing.graph_text
    for value in _timeout_values(graph_text=capturing.graph_text):
        assert not any(opener in value for opener in _TEMPLATE_OPENERS)
    # The adapter template is UNTOUCHED: `acp.command` is a string on both
    # sides of Fabro's expansion, which is why it may be templated and a
    # timeout may not.
    assert "inputs.acp_adapter" in capturing.graph_text


def test_configured_node_keeps_its_value_and_others_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured implement timeout renders; the other nodes stay at 1800s."""
    _exit_code, capturing = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        dispatcher={"node_timeouts": {"implement": 7200}},
    )
    assert _timeout_values(graph_text=capturing.graph_text) == ["7200s", "1800s", "1800s"]


def test_dispatch_record_names_the_repository_layer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The journal reports the rendered seconds and which layer supplied them."""
    repo, workflow = _repo_with_workflow(
        tmp_path=tmp_path, dispatcher={"node_timeouts": {"implement": 7200}}
    )
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _CapturingRunDispatch())
    _ = main(argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)])
    records = [
        json.loads(line)
        for line in (repo / "tmp" / "fabro-dispatch-journal.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    [timeouts_record] = [record for record in records if record["stage"] == "node-timeouts"]
    assert timeouts_record["node_timeouts"]["implement"] == {
        "seconds": 7200,
        "layer": "repository",
    }
    assert timeouts_record["node_timeouts"]["janitor"] == {"seconds": 1800, "layer": "default"}
    assert timeouts_record["stall_timeout"] == {"seconds": 7200, "layer": "default"}


def test_subprocess_ceiling_follows_the_resolved_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A longer resolved node lengthens the `fabro run` subprocess ceiling."""
    _exit_code, defaulted = _dispatch(tmp_path=tmp_path, monkeypatch=monkeypatch, dispatcher={})
    assert defaulted.timeout_seconds == derive_fabro_timeout_seconds(
        timeouts=default_node_timeouts()
    )
    reset_fake_singleton()
    _exit_code, configured = _dispatch(
        tmp_path=tmp_path / "second",
        monkeypatch=monkeypatch,
        dispatcher={"node_timeouts": {"implement": 14400}},
    )
    assert configured.timeout_seconds > defaulted.timeout_seconds


def test_invalid_timeout_refuses_before_any_run_exists(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A zero timeout refuses the dispatch, names the key, and releases the claim."""
    repo, workflow = _repo_with_workflow(
        tmp_path=tmp_path, dispatcher={"node_timeouts": {"implement": 0}}
    )
    item = _item()
    append_work_item(path=_config(), item=item)
    capturing = _CapturingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", capturing)
    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "dispatcher.node_timeouts.implement" in out
    # No run was ever launched, and the pre-run claim is released rather than
    # stranding the item `active` with nothing behind it.
    assert capturing.graph_text == ""
    assert _stored()[item.id].status == "ready"
