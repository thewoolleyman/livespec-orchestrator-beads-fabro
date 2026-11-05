"""Tests for failed/blocked Fabro run preserve-by-reference comments."""

from __future__ import annotations

import argparse
import hashlib
import importlib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import (
    minijinja_openers_in_goal_sources,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_records import (
    PROVIDER_LIMIT_RELEASE_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult
from livespec_orchestrator_beads_fabro.store import WorkItemComment, append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _DumpRunner:
    export_diff: bool
    stage_diffs: dict[str, str] | None = None
    calls: list[list[str]] = field(default_factory=list)


@dataclass(kw_only=True)
class _FailingDumpRunner:
    stderr: str


@dataclass(kw_only=True)
class _SixHundredSecondDumpRunner:
    timeouts: list[float] = field(default_factory=list)


@pytest.fixture(autouse=True)
def run_state_replaces_the_legacy_dump_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model the projection response that now supplies this module's diffs."""

    class _StateApi:
        def __init__(self, *, result: FabroHttpResult) -> None:
            self._result = result

        def run_state(self, *, run_id: str, timeout_seconds: float) -> FabroHttpResult:
            _ = (run_id, timeout_seconds)
            return self._result

    def _state_api(port: FabroPort) -> _StateApi:
        runner = port.runner
        if isinstance(runner, _FailingDumpRunner):
            return _StateApi(
                result=FabroHttpResult(
                    status=500,
                    body=runner.stderr,
                    error=None,
                    payload=None,
                    succeeded=False,
                )
            )
        if isinstance(runner, _DumpRunner):
            stage_diffs = runner.stage_diffs
            if stage_diffs is None:
                stage_diffs = (
                    {"002-implement@1": "diff --git a/app.py b/app.py\n+print('kept')\n"}
                    if runner.export_diff
                    else {}
                )
        else:
            stage_diffs = {"002-implement@1": "diff --git a/app.py b/app.py\n+print('kept')\n"}
        stages = {
            stage[4:]: {"first_event_seq": int(stage[:3]), "diff": diff}
            for stage, diff in stage_diffs.items()
        }
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


def test_preserve_pointer_reads_stage_diffs_without_running_fabro_dump(*, tmp_path: Path) -> None:
    append_work_item(path=_config(), item=_item())
    runner = _DumpRunner(export_diff=True)

    _module().preserve_checkpointed_work_reference(
        args=_args(),
        repo=_repo(tmp_path),
        item=_item(),
        outcome=_outcome(status="failed"),
        journal=_RecordingJournal(),
        runner=runner,
    )

    assert runner.calls == []


@pytest.mark.parametrize("blob_result", ["success", "missing", "corrupt"])
def test_preserve_pointer_reads_and_validates_each_referenced_blob(
    *,
    blob_result: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"diff --git a/app.py b/app.py\n+binary \xff\n"
    digest = hashlib.sha256(payload).hexdigest()

    class _BlobApi:
        def run_state(self, *, run_id: str, timeout_seconds: float) -> FabroHttpResult:
            _ = (run_id, timeout_seconds)
            return FabroHttpResult(
                status=200,
                body="",
                error=None,
                payload={
                    "stages": {
                        "implement@1": {
                            "first_event_seq": 239551,
                            "dump_ordinal": 55,
                            "diff": f"blob://sha256/{digest}",
                        }
                    }
                },
                succeeded=True,
            )

        def run_blob(
            self, *, run_id: str, blob_sha256: str, timeout_seconds: float
        ) -> FabroHttpResult:
            _ = (run_id, blob_sha256, timeout_seconds)
            if blob_result == "missing":
                return FabroHttpResult(
                    status=404, body="gone", error=None, payload=None, succeeded=False
                )
            returned = payload if blob_result == "success" else b"wrong bytes"
            return FabroHttpResult(
                status=200,
                body=returned.decode("utf-8", errors="replace"),
                error=None,
                payload=None,
                succeeded=True,
                raw_body=returned,
            )

    monkeypatch.setattr(FabroPort, "server_api", lambda _port: _BlobApi())
    append_work_item(path=_config(), item=_item())
    journal = _RecordingJournal()
    _module().preserve_checkpointed_work_reference(
        args=_args(),
        repo=_repo(tmp_path),
        item=_item(),
        outcome=_outcome(status="failed"),
        journal=journal,
        runner=_DumpRunner(export_diff=False),
    )

    if blob_result == "success":
        comments = make_beads_client(config=_config()).list_comments(issue_id="bd-ib-preserve")
        body = str(comments[-1]["text"])
        assert "stages/055-implement@1/diff.patch" in body
        assert f"sha256: {digest}" in body
    else:
        assert journal.records[-1]["stage"] == "preserve-by-reference-error"
        body = str(journal.records[-1]["pointer_body"])
        assert "sha256: (not recorded;" in body
        assert "sha256 unavailable because:" in body


def _module() -> ModuleType:
    module_path = (
        Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
        / "_dispatcher_preserve_reference.py"
    )
    assert module_path.is_file()
    return importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference"
    )


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
        id="bd-ib-preserve",
        type="task",
        status="active",
        title="Preserve failed work",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-08-23T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _outcome(*, status: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-preserve",
        status=status,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="terminal",
        fabro_run_id="01M0RUN",
    )


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        fabro_bin="fabro",
        fabro_factory_target=FactoryTarget(
            name="hp",
            server="https://hp-xubuntu.perch-rudd.ts.net:32276",
            dev_token=None,
        ),
    )


def test_fabro_dump_timeout_is_defined_once_at_nine_hundred_seconds() -> None:
    module_path = (
        Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
        / "_dispatcher_fabro_dump_timeout.py"
    )

    assert module_path.is_file()
    timeout = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_dump_timeout"
    )
    assert timeout.FABRO_DUMP_TIMEOUT_SECONDS == 900


def test_every_dispatcher_dump_consumer_imports_the_shared_timeout() -> None:
    timeout = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_dump_timeout"
    )
    checker = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_check"
    )
    worker_exit = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_worker_exit_log_cause"
    )

    assert not hasattr(_module(), "FABRO_DUMP_TIMEOUT_SECONDS")
    assert checker.FABRO_DUMP_TIMEOUT_SECONDS is timeout.FABRO_DUMP_TIMEOUT_SECONDS
    assert worker_exit.FABRO_DUMP_TIMEOUT_SECONDS is timeout.FABRO_DUMP_TIMEOUT_SECONDS


def test_a_six_hundred_second_dump_writes_a_digested_preserve_pointer(tmp_path: Path) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    runner = _SixHundredSecondDumpRunner()

    module.preserve_checkpointed_work_reference(
        args=_args(),
        repo=_repo(tmp_path),
        item=_item(),
        outcome=_outcome(status="failed"),
        journal=_RecordingJournal(),
        runner=runner,
    )

    comments = make_beads_client(config=_config()).list_comments(issue_id="bd-ib-preserve")
    body = str(comments[-1]["text"])
    assert runner.timeouts == []
    assert "sha256: 66cea3fffd55d2674c51819b19f4a7dee70484243ba4ed26408fa70e05b074dd" in body
    assert "fabro dump failed" not in body


def test_failed_run_comment_records_resolvable_diff_pointer(tmp_path: Path) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    journal = _RecordingJournal()
    runner = _DumpRunner(export_diff=True)

    module.preserve_checkpointed_work_reference(
        args=_args(),
        repo=_repo(tmp_path),
        item=_item(),
        outcome=_outcome(status="failed"),
        journal=journal,
        runner=runner,
    )

    comments = make_beads_client(config=_config()).list_comments(issue_id="bd-ib-preserve")
    body = str(comments[-1]["text"])
    assert "livespec-preserve-by-reference" in body
    assert "run id: 01M0RUN" in body
    assert "factory server url: https://hp-xubuntu.perch-rudd.ts.net:32276" in body
    assert "stage artifact path: stages/002-implement@1/diff.patch" in body
    assert "byte size: 44" in body
    assert "sha256:" in body
    assert "sha256: 66cea3fffd55d2674c51819b19f4a7dee70484243ba4ed26408fa70e05b074dd" in body
    assert "recorded sha256 is the integrity check" in body
    assert "normalized diff payload byte size" not in body
    assert "fabro dump 01M0RUN --server https://hp-xubuntu.perch-rudd.ts.net:32276 -o" in body
    assert runner.calls == []
    assert journal.records[-1]["stage"] == "preserve-by-reference"


def test_failed_run_comment_records_every_stage_diff_pointer(tmp_path: Path) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    journal = _RecordingJournal()
    runner = _DumpRunner(
        export_diff=False,
        stage_diffs={
            "002-implement@1": "diff --git a/app.py b/app.py\n+print('kept')\n",
            "006-fix@1": "diff --git a/app.py b/app.py\n+print('fixed')\n",
        },
    )

    module.preserve_checkpointed_work_reference(
        args=_args(),
        repo=_repo(tmp_path),
        item=_item(),
        outcome=_outcome(status="failed"),
        journal=journal,
        runner=runner,
    )

    comments = make_beads_client(config=_config()).list_comments(issue_id="bd-ib-preserve")
    body = str(comments[-1]["text"])
    assert "stage artifact path: stages/002-implement@1/diff.patch" in body
    assert "stage artifact path: stages/006-fix@1/diff.patch" in body
    assert body.count("byte size:") == 2
    assert body.count("sha256:") == 2
    assert "sha256sum <export-dir>/stages/002-implement@1/diff.patch" in body
    assert "sha256sum <export-dir>/stages/006-fix@1/diff.patch" in body
    assert journal.records[-1]["artifact_present"] is True


def test_failed_run_comment_records_fix_stage_only_diff_pointer(tmp_path: Path) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    journal = _RecordingJournal()

    module.preserve_checkpointed_work_reference(
        args=_args(),
        repo=_repo(tmp_path),
        item=_item(),
        outcome=_outcome(status="failed"),
        journal=journal,
        runner=_DumpRunner(
            export_diff=False,
            stage_diffs={"006-fix@1": "diff --git a/app.py b/app.py\n+print('fixed')\n"},
        ),
    )

    comments = make_beads_client(config=_config()).list_comments(issue_id="bd-ib-preserve")
    body = str(comments[-1]["text"])
    assert "stage artifact path: stages/006-fix@1/diff.patch" in body
    assert "run produced no checkpointed diff artifact" not in body
    assert "byte size:" in body
    assert "sha256:" in body
    assert journal.records[-1]["artifact_present"] is True


def test_blocked_run_comment_is_honest_when_no_diff_was_produced(tmp_path: Path) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    journal = _RecordingJournal()

    module.preserve_checkpointed_work_reference(
        args=_args(),
        repo=_repo(tmp_path),
        item=_item(),
        outcome=_outcome(status="blocked"),
        journal=journal,
        runner=_DumpRunner(export_diff=False),
    )

    comments = make_beads_client(config=_config()).list_comments(issue_id="bd-ib-preserve")
    body = str(comments[-1]["text"])
    assert "livespec-preserve-by-reference" in body
    assert "run produced no checkpointed diff artifact" in body
    assert "stage artifact path: stages/*/diff.patch (none found)" in body
    assert "byte size: (not recorded; artifact missing)" in body
    assert "sha256: (not recorded; artifact missing)" in body
    assert journal.records[-1]["artifact_present"] is False


def test_dump_failure_comment_escapes_and_bounds_external_stderr(tmp_path: Path) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    stderr = "{{ bricking }}\n{% also_bricking %}\n" + ("x" * 5000)

    module.preserve_checkpointed_work_reference(
        args=_args(),
        repo=_repo(tmp_path),
        item=_item(),
        outcome=_outcome(status="failed"),
        journal=_RecordingJournal(),
        runner=_FailingDumpRunner(stderr=stderr),
    )

    comments = make_beads_client(config=_config()).list_comments(issue_id="bd-ib-preserve")
    body = str(comments[-1]["text"])
    findings = minijinja_openers_in_goal_sources(
        item=_item(),
        comments=(
            WorkItemComment(
                text=body,
                author="tester",
                created_at="2026-08-23T00:00:00Z",
            ),
        ),
        lessons="",
    )
    assert findings == ()
    assert "stderr: " in body
    assert "x" * 5000 not in body
    assert len(body) < 2000


def test_a_provider_limit_release_still_writes_the_artifact_pointer(tmp_path: Path) -> None:
    """The release re-routes an ending that used to arrive here as `blocked`.

    So the pointer must still be written for it. Without this the whole
    provider-limit class loses the durable `livespec-preserve-by-reference`
    comment -- the artifact pointer with the byte size and sha256 -- while the
    release re-queues the item, which is the discarded-work path the clause
    exists to close. The release's own `recovery_source` is a journal field,
    and the journal is not the durable authority.

    The status is spelled as a LITERAL and bound to the product constant, so a
    gate widened for some other spelling of the release cannot pass here.
    """
    assert PROVIDER_LIMIT_RELEASE_STAGE == "provider-limit-release"
    module = _module()
    append_work_item(path=_config(), item=_item())
    journal = _RecordingJournal()
    runner = _DumpRunner(export_diff=True)

    module.preserve_checkpointed_work_reference(
        args=_args(),
        repo=_repo(tmp_path),
        item=_item(),
        outcome=_outcome(status="provider-limit-release"),
        journal=journal,
        runner=runner,
    )

    comments = make_beads_client(config=_config()).list_comments(issue_id="bd-ib-preserve")
    body = str(comments[-1]["text"])
    assert "livespec-preserve-by-reference" in body
    assert "stage artifact path: stages/002-implement@1/diff.patch" in body
    assert "sha256: 66cea3fffd55d2674c51819b19f4a7dee70484243ba4ed26408fa70e05b074dd" in body
    assert journal.records[-1]["stage"] == "preserve-by-reference"


def test_green_run_adds_no_preserve_comment(tmp_path: Path) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    runner = _DumpRunner(export_diff=True)

    module.preserve_checkpointed_work_reference(
        args=_args(),
        repo=_repo(tmp_path),
        item=_item(),
        outcome=_outcome(status="green"),
        journal=_RecordingJournal(),
        runner=runner,
    )

    assert runner.calls == []
    assert make_beads_client(config=_config()).list_comments(issue_id="bd-ib-preserve") == []
