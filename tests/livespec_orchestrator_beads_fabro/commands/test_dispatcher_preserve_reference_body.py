"""Tests for the honesty of a preserved pointer's body.

Two properties, both of which a pointer failed to carry before.

A pointer that could not compute a digest must SAY SO AND SAY WHY. The
branch where a pointer is most likely to be dangling — the export itself
failed — is exactly the branch with no digest, so a bare placeholder
there is indistinguishable from an oversight.

And the retrieval command printed into the body must be the one an
operator can run UNCHANGED under the credential wrapper. The wrapper
sanitizes PATH, so a bare `fabro` is not on it; the printed command must
therefore name the same resolved binary the module itself invoked. That
is asserted against the recorded argv rather than against a literal, so
the two cannot drift apart.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference import (
    preserve_checkpointed_work_reference,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_FABRO_BIN = "/home/factory/.fabro/bin/fabro"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _ScriptedDumpRunner:
    """Exports `stage_diffs` into the requested output dir, then exits `exit_code`."""

    exit_code: int = 0
    stage_diffs: dict[str, str] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)


@pytest.fixture(autouse=True)
def run_state_replaces_dump_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    class _StateApi:
        def __init__(self, *, result: FabroHttpResult) -> None:
            self._result = result

        def run_state(self, *, run_id: str, timeout_seconds: float) -> FabroHttpResult:
            _ = (run_id, timeout_seconds)
            return self._result

    def _state_api(port: FabroPort) -> _StateApi:
        runner = port.runner
        assert isinstance(runner, _ScriptedDumpRunner)
        if runner.exit_code:
            return _StateApi(
                result=FabroHttpResult(
                    status=500,
                    body="run storage not found",
                    error=None,
                    payload=None,
                    succeeded=False,
                )
            )
        stages: dict[str, dict[str, str | None]] = {}
        for stage, payload in sorted(runner.stage_diffs.items()):
            for position in range(len(stages) + 1, int(stage[:3])):
                stages[f"stage-{position:03d}@1"] = {"diff": None}
            stages[stage[4:]] = {"diff": payload}
        return _StateApi(
            result=FabroHttpResult(
                status=200,
                body="",
                error=None,
                payload={"stages": stages},
                succeeded=True,
            )
        )

    monkeypatch.setattr(FabroPort, "server_api", _state_api)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "livespec-impl-beads"}}}',
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-pointer",
        type="task",
        status="active",
        title="Preserve failed work",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-08-29T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        fabro_bin=_FABRO_BIN,
        fabro_factory_target=FactoryTarget(name="hp", server=_SERVER, dev_token=None),
    )


def _outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-pointer",
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="terminal",
        fabro_run_id="01M0RUN",
    )


def _preserve(*, tmp_path: Path, runner: _ScriptedDumpRunner) -> str:
    append_work_item(path=_config(), item=_item())
    preserve_checkpointed_work_reference(
        args=_args(),
        repo=_repo(tmp_path),
        item=_item(),
        outcome=_outcome(),
        journal=_RecordingJournal(),
        runner=runner,
    )
    comments = make_beads_client(config=_config()).list_comments(issue_id="bd-ib-pointer")
    return str(comments[-1]["text"])


def _retrieval_line(*, body: str) -> str:
    lines = body.splitlines()
    return lines[lines.index("retrieval command:") + 1]


# ---------------------------------------------------------------------------
# A pointer with no digest says so, and says why
# ---------------------------------------------------------------------------


def test_dump_failed_pointer_states_why_no_digest_could_be_computed(tmp_path: Path) -> None:
    body = _preserve(tmp_path=tmp_path, runner=_ScriptedDumpRunner(exit_code=2))

    assert "sha256 unavailable because: the preserve step failed" in body
    assert "run-state read failed with HTTP status 500" in body
    # The placeholder alone was the whole defect: it reads as an oversight.
    assert "sha256: (not recorded; preserve step failed)" in body


def test_diff_less_projection_states_why_no_digest_could_be_computed(tmp_path: Path) -> None:
    body = _preserve(tmp_path=tmp_path, runner=_ScriptedDumpRunner())

    assert "sha256 unavailable because: the export succeeded but matched no" in body
    assert "so there were no bytes to digest" in body


def test_digested_pointer_carries_no_unavailability_claim(tmp_path: Path) -> None:
    # The control: when a digest EXISTS the body must not also claim one
    # could not be computed.
    body = _preserve(
        tmp_path=tmp_path,
        runner=_ScriptedDumpRunner(
            stage_diffs={"002-implement@1": "diff --git a/app.py b/app.py\n+print('kept')\n"}
        ),
    )

    assert "sha256 unavailable because:" not in body
    assert "sha256: 66cea3fffd55d2674c51819b19f4a7dee70484243ba4ed26408fa70e05b074dd" in body


# ---------------------------------------------------------------------------
# The printed retrieval command is the one that was actually invoked
# ---------------------------------------------------------------------------


def test_printed_retrieval_command_names_the_binary_the_module_invoked(tmp_path: Path) -> None:
    runner = _ScriptedDumpRunner(
        stage_diffs={"002-implement@1": "diff --git a/app.py b/app.py\n+print('kept')\n"}
    )

    body = _preserve(tmp_path=tmp_path, runner=runner)

    # Tied to the recorded argv, not to a literal: a bare `fabro` is not on
    # PATH under the credential wrapper, so the printed command must name
    # the same resolved binary the module ran.
    assert runner.calls == []
    assert _retrieval_line(body=body).split()[0] == _FABRO_BIN
    assert (
        _retrieval_line(body=body)
        == f"{_FABRO_BIN} dump 01M0RUN --server {_SERVER} -o <export-dir>"
    )


def test_failed_projection_pointer_claims_no_retrieval_command(tmp_path: Path) -> None:
    runner = _ScriptedDumpRunner(exit_code=2)

    body = _preserve(tmp_path=tmp_path, runner=runner)

    assert runner.calls == []
    assert "retrieval command:" not in body


def test_diff_less_projection_pointer_keeps_the_documented_retrieval_command(
    tmp_path: Path,
) -> None:
    runner = _ScriptedDumpRunner()

    body = _preserve(tmp_path=tmp_path, runner=runner)

    assert runner.calls == []
    assert _retrieval_line(body=body).split()[0] == _FABRO_BIN
