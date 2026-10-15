"""Tests for the orphaned-factory-runs needs-attention lane."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_reconcile_runs_inputs as reconcile_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_container_port import (
    DOCKER_BIN,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroTarget
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_needs_attention_orphan_runs.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._needs_attention_orphan_runs"

_HP_SERVER = "https://hp.example:32276"
_VPS_SERVER = "https://vps.example:32276"
_HP_DOCKER_HOST = "ssh://cwoolley@hp.example"
_VPS_DOCKER_HOST = "ssh://cwoolley@vps.example"


@dataclass(kw_only=True)
class _Runner:
    """One fake `fabro` CLI, keyed by the server the argv names.

    The reconciliation pass also sweeps this host's sandbox containers, so the
    one subprocess seam now carries two binaries. The Docker leg is recorded
    SEPARATELY and answered as a host with no sandbox container on it: `calls`
    is this file's record of which FACTORY was addressed, and a `docker ps` —
    which names no `--server` at all — would otherwise read as a survey.
    """

    ps_by_server: dict[str, str] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)
    docker_calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        if argv[0] == DOCKER_BIN:
            self.docker_calls.append(argv)
            return CommandResult(exit_code=0, stdout="", stderr="")
        self.calls.append(argv)
        server = argv[argv.index("--server") + 1] if "--server" in argv else ""
        return CommandResult(exit_code=0, stdout=self.ps_by_server.get(server, "[]"), stderr="")


def test_the_lane_renders_the_whole_join_and_the_narrowed_remedy(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    runner = _Runner(ps_by_server={_HP_SERVER: _ps(run_id="01ORPHAN", kind="blocked")})

    items = module.orphan_run_items(
        project_root=repo,
        repo="livespec-orchestrator-beads-fabro",
        items=[_item(id="bd-ib-orphan", status="closed")],
        runner=runner,
    )

    assert len(items) == 1
    lane = items[0]
    assert lane.id == "hygiene:orphaned-factory-run:01ORPHAN"
    assert (lane.kind, lane.urgency) == ("hygiene", "high")
    assert lane.source_ref.work_item == "bd-ib-orphan"
    # Every field the lane must carry, asserted by presence in the rendered
    # summary rather than by re-deriving them from the projection.
    for fragment in ("01ORPHAN", "hp", _HP_SERVER, "blocked", "bd-ib-orphan", "item-not-active"):
        assert fragment in lane.summary
    assert "closed" in lane.summary
    assert "dispatcher.py reconcile-runs" in lane.handoff.command.replace("\n", " ")
    assert "--factory hp" in lane.handoff.command


def test_each_factory_is_addressed_by_its_declared_server_target(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A bare `FabroTarget` would answer for whichever server the client defaults to.

    Two independent proofs, because each can fail without the other noticing:
    every constructed target carries a server url, AND every `ps` argv that
    reached the wire named one.
    """
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    runner = _Runner()
    built: list[FabroTarget] = []

    def _record(**kwargs: object) -> FabroTarget:
        target = FabroTarget(**kwargs)  # pyright: ignore[reportArgumentType]
        built.append(target)
        return target

    # The port is opened by the seams module, which is where the target is
    # built; patching the survey module would patch a name that is not there.
    monkeypatch.setattr(reconcile_inputs, "FabroTarget", _record)

    _ = module.orphan_run_items(
        project_root=repo,
        repo="livespec-orchestrator-beads-fabro",
        items=[],
        runner=runner,
    )

    assert [target.server_url for target in built] == [_HP_SERVER, _VPS_SERVER]
    assert all(target.server_url is not None for target in built)
    assert [call[call.index("--server") + 1] for call in runner.calls] == [
        _HP_SERVER,
        _VPS_SERVER,
    ]


def test_reading_the_lane_writes_neither_a_journal_nor_a_comment(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The seams handed in cannot write, so the guarantee outlives the dry-run arm."""
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    runner = _Runner(ps_by_server={_HP_SERVER: _ps(run_id="01ORPHAN", kind="blocked")})

    _ = module.orphan_run_items(
        project_root=repo,
        repo="livespec-orchestrator-beads-fabro",
        items=[_item(id="bd-ib-orphan", status="closed")],
        runner=runner,
    )

    assert not (repo / "tmp" / "fabro-dispatch-journal.jsonl").exists()
    journal = module.InertJournal()
    journal.append(record={"stage": "anything"})
    ledger = module.InertLedger()
    ledger.add_comment(issue_id="bd-ib-orphan", body="anything")
    assert ledger.list_comments(issue_id="bd-ib-orphan") == []


def test_an_unreadable_config_empties_the_lane_rather_than_the_envelope(
    *,
    tmp_path: Path,
) -> None:
    """One broken lane must never cost the other lanes their envelope."""
    module = importlib.import_module(_MODULE_NAME)
    repo = tmp_path / "unconfigured"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text("{ not json", encoding="utf-8")

    items = module.orphan_run_items(
        project_root=repo,
        repo="livespec-orchestrator-beads-fabro",
        items=[],
        runner=_Runner(),
    )

    assert items == []


def test_an_item_missing_orphan_says_so_rather_than_rendering_none(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    runner = _Runner(
        ps_by_server={_HP_SERVER: _ps(run_id="01GONE", kind="starting", work_item_id="bd-ib-gone")}
    )

    items = module.orphan_run_items(
        project_root=repo,
        repo="livespec-orchestrator-beads-fabro",
        items=[],
        runner=runner,
    )

    assert len(items) == 1
    assert "absent from the ledger" in items[0].summary
    assert "None" not in items[0].summary


def _repo(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", "fabro")
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {
                        "default_factory": "hp",
                        # Each declares the daemon running ITS sandbox
                        # containers, which the container lane of each pass
                        # addresses. A factory declaring none is reported as
                        # unobserved rather than swept through the reconciling
                        # host's own daemon.
                        "factories": {
                            "hp": {
                                "server": _HP_SERVER,
                                "docker_host": _HP_DOCKER_HOST,
                            },
                            "vps": {
                                "server": _VPS_SERVER,
                                "docker_host": _VPS_DOCKER_HOST,
                            },
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _ps(*, run_id: str, kind: str, work_item_id: str = "bd-ib-orphan") -> str:
    return json.dumps(
        [
            {
                "run_id": run_id,
                "goal": f"Work-item: {work_item_id}\nRepo: /tmp/repo",
                "status": {"kind": kind},
            }
        ]
    )


def _item(*, id: str, status: str) -> WorkItem:
    return WorkItem(
        id=id,
        type="task",
        status=status,
        title=id,
        description=id,
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-08-30T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
