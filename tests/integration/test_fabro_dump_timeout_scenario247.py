"""Scenario 247 — slow Fabro dumps retain their preserved work.

The three Dispatcher reads are exercised through their production entry points:
the preserve-by-reference export writes a real pointer to the fake ledger, its
read-back check re-exports that pointer, and the worker-exit recovery reads the
exported log.  The factory double completes only when it receives the seven
hundred seconds the scenario says the slow export needs, so every successful
leg proves it received the shared nine-hundred-second bound.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference import (
    preserve_checkpointed_work_reference,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_check import (
    POINTER_INTACT,
    check_preserved_pointer,
    parse_preserved_pointer,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_worker_exit_log_cause import (
    WORKER_EXIT_BEFORE_TERMINAL_EVENT,
    worker_exit_engine_failure_outcome,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroFailureDetail,
    FabroInspectResult,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_SERVER = "https://petri.example.test:32276"
_ITEM_ID = "bd-ib-exyiqr"
_RUN_ID = "01M5SLOWDUMP"
_WORKER_RUN_ID = "01M5WORKERLOG"
_DIFF = "diff --git a/app.py b/app.py\n+print('kept')\n"
_ENGINE_FAILURE = "Workflow run failed deterministic failure cycle detected: signature janitor|deterministic|exit 1"


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _SevenMinuteFactory:
    timeouts: list[float] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, env, stdin)
        self.timeouts.append(timeout_seconds)
        if timeout_seconds < 700:
            return CommandResult(exit_code=124, stdout="", stderr="dump timed out")
        output_dir = Path(argv[argv.index("-o") + 1])
        run_id = argv[2]
        if run_id == _WORKER_RUN_ID:
            _ = (output_dir / "run.log").write_text(_ENGINE_FAILURE, encoding="utf-8")
        else:
            diff = output_dir / "stages" / "002-implement@1" / "diff.patch"
            diff.parent.mkdir(parents=True)
            _ = diff.write_text(_DIFF, encoding="utf-8")
        return CommandResult(exit_code=0, stdout="", stderr="")


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="scenario247",
        prefix="scenario247",
        server_user="scenario247",
        database="scenario247",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="Keep slow dumps",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-27T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "scenario247"}}}',
        encoding="utf-8",
    )
    return repo


def _outcome(*, run_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="terminal",
        fabro_run_id=run_id,
        fabro_failure_cause=WORKER_EXIT_BEFORE_TERMINAL_EVENT,
        fabro_failure_category="deterministic",
        fabro_failure_signature=None,
    )


def _plan(*, repo: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=repo,
        work_item_id=_ITEM_ID,
        branch=f"feat/{_ITEM_ID}",
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="petri",
        fabro_factory_server=_SERVER,
        fabro_factory_dev_token=None,
        janitor=("just", "check"),
        janitor_checkout=repo / ".janitor",
        janitor_core_checkout=repo / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def test_slow_export_and_all_dispatcher_readers_share_the_nine_hundred_second_bound(
    tmp_path: Path,
) -> None:
    """A 700-second export succeeds, digests its pointer, and serves every reader."""
    append_work_item(path=_config(), item=_item())
    repo = _repo(tmp_path=tmp_path)
    factory = _SevenMinuteFactory()
    journal = _Journal()
    preserve_checkpointed_work_reference(
        args=argparse.Namespace(
            fabro_bin="fabro",
            fabro_factory_target=FactoryTarget(name="petri", server=_SERVER, dev_token=None),
        ),
        repo=repo,
        item=_item(),
        outcome=_outcome(run_id=_RUN_ID),
        journal=journal,
        runner=factory,
    )

    body = str(make_beads_client(config=_config()).list_comments(issue_id=_ITEM_ID)[-1]["text"])
    assert factory.timeouts == [900]
    assert "sha256: 66cea3fffd55d2674c51819b19f4a7dee70484243ba4ed26408fa70e05b074dd" in body
    pointer = parse_preserved_pointer(body=body)
    assert pointer is not None
    assert (
        check_preserved_pointer(
            pointer=pointer,
            repo=repo,
            fabro_bin="fabro",
            runner=factory,
        ).state
        == POINTER_INTACT
    )

    surfaced = worker_exit_engine_failure_outcome(
        plan=_plan(repo=repo),
        runner=factory,
        journal=journal,
        run_id=_WORKER_RUN_ID,
        inspect=FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""),
            payload=[],
            status_kind="failed",
            failure=FabroFailureDetail(
                cause=WORKER_EXIT_BEFORE_TERMINAL_EVENT,
                category="deterministic",
                signature=None,
            ),
        ),
        terminal=_outcome(run_id=_WORKER_RUN_ID),
    )

    assert surfaced is not None
    assert surfaced.fabro_failure_cause == _ENGINE_FAILURE
    assert factory.timeouts == [900, 900, 900]
