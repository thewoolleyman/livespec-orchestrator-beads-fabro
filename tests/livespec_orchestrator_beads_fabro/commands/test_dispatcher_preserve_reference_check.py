"""Tests for re-reading a preserved pointer to detect danglingness.

Nothing re-read a pointer before this reader existed, so a pointer whose
run had been pruned sat on the ledger reading exactly like a live one.

Every pointer under test here is produced by the REAL writer
(`_dispatcher_preserve_reference_body`) rather than hand-written. A
reader checked against a hand-rolled fixture proves only that it can
parse the fixture; if the writer's format moved, both would still agree
and the reader would silently stop reading real pointers.
"""

from __future__ import annotations

import hashlib
import importlib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_body import (
    artifact_pointer_body,
    dump_failed_body,
    missing_artifact_body,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult

_FABRO_BIN = "/home/factory/.fabro/bin/fabro"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_DIFF = "diff --git a/app.py b/app.py\n+print('kept')\n"
_ARTIFACT = "stages/002-implement@1/diff.patch"


def _module() -> ModuleType:
    module_path = (
        Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
        / "_dispatcher_preserve_reference_check.py"
    )
    assert module_path.is_file()
    return importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_check"
    )


def _stages_in_dump_order(*, payloads: dict[str, str]) -> dict[str, dict[str, int | str]]:
    """Build a `/state` projection whose event sequences match its dump paths."""
    stages: dict[str, dict[str, int | str]] = {}
    for relative, payload in sorted(payloads.items()):
        stage_directory = Path(relative).parts[1]
        ordinal_text, stage_name = stage_directory.split("-", 1)
        ordinal = int(ordinal_text)
        stages[stage_name] = {"first_event_seq": ordinal, "diff": payload}
    return stages


@dataclass(kw_only=True)
class _ExportRunner:
    """Re-exports `payloads` into the requested output dir, then exits `exit_code`."""

    exit_code: int = 0
    payloads: dict[str, str] = field(default_factory=dict)
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
        assert isinstance(runner, _ExportRunner)
        if runner.exit_code:
            return _StateApi(
                result=FabroHttpResult(
                    status=404,
                    body="run storage not found",
                    error=None,
                    payload=None,
                    succeeded=False,
                )
            )
        stages = _stages_in_dump_order(payloads=runner.payloads)
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


@pytest.mark.parametrize("blob_result", ["success", "body", "missing", "corrupt"])
def test_a_blob_backed_pointer_verifies_the_addressed_bytes(
    *, blob_result: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = _DIFF.encode()
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
                        "prepare@1": {"first_event_seq": 1, "diff": None},
                        "implement@1": {
                            "first_event_seq": 2,
                            "diff": f"blob://sha256/{digest}",
                        },
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
            returned = payload if blob_result in {"success", "body"} else b"wrong bytes"
            return FabroHttpResult(
                status=200,
                body=returned.decode(),
                error=None,
                payload=None,
                succeeded=True,
                raw_body=returned if blob_result != "body" else None,
            )

    monkeypatch.setattr(FabroPort, "server_api", lambda _port: _BlobApi())
    check = _check(body=_digested_body(tmp_path), runner=_ExportRunner(), repo=tmp_path)

    expected = "intact" if blob_result in {"success", "body"} else "dangling"
    assert check.state == expected


def _digested_body(tmp_path: Path) -> str:
    export_dir = tmp_path / "export"
    artifact = export_dir / _ARTIFACT
    artifact.parent.mkdir(parents=True)
    _ = artifact.write_text(_DIFF, encoding="utf-8")
    body, _ = artifact_pointer_body(
        run_id="01M0RUN",
        server_url=_SERVER,
        artifacts=(artifact,),
        export_dir=export_dir,
        fabro_bin=_FABRO_BIN,
    )
    return body


def _dump_failed_body() -> str:
    body, _ = dump_failed_body(
        run_id="01M0RUN",
        server_url=_SERVER,
        command=CommandResult(exit_code=2, stdout="", stderr="run storage not found"),
        fabro_bin=_FABRO_BIN,
    )
    return body


def _check(*, body: str, runner: _ExportRunner, repo: Path) -> object:
    module = _module()
    pointer = module.parse_preserved_pointer(body=body)
    assert pointer is not None
    return module.check_preserved_pointer(
        pointer=pointer, repo=repo, fabro_bin=_FABRO_BIN, runner=runner
    )


# ---------------------------------------------------------------------------
# parse_preserved_pointer
# ---------------------------------------------------------------------------


def test_a_comment_that_is_not_a_pointer_is_not_read_as_one(tmp_path: Path) -> None:
    _ = tmp_path
    module = _module()

    assert module.parse_preserved_pointer(body="") is None
    assert module.parse_preserved_pointer(body="just an ordinary ledger comment") is None


def test_a_pointer_missing_its_identifying_fields_is_not_read(tmp_path: Path) -> None:
    _ = tmp_path
    module = _module()
    marker = "livespec-preserve-by-reference"

    assert module.parse_preserved_pointer(body=f"{marker}\n\nfactory server url: {_SERVER}") is None
    assert module.parse_preserved_pointer(body=f"{marker}\n\nrun id: 01M0RUN") is None


def test_a_digested_pointer_parses_into_its_artifact_and_digest(tmp_path: Path) -> None:
    module = _module()

    pointer = module.parse_preserved_pointer(body=_digested_body(tmp_path))

    assert pointer is not None
    assert (pointer.run_id, pointer.server_url) == ("01M0RUN", _SERVER)
    assert pointer.digest_unavailable_reason is None
    assert [artifact.path for artifact in pointer.artifacts] == [_ARTIFACT]
    assert pointer.artifacts[0].digest == hashlib.sha256(_DIFF.encode()).hexdigest()


def test_a_digestless_pointer_parses_with_no_artifacts_and_carries_its_reason(
    tmp_path: Path,
) -> None:
    # The placeholder in the `sha256:` slot must NOT be mistaken for a
    # digest — verifying against it would always report a mismatch.
    _ = tmp_path
    module = _module()

    pointer = module.parse_preserved_pointer(body=_dump_failed_body())

    assert pointer is not None
    assert pointer.artifacts == ()
    assert pointer.digest_unavailable_reason is not None
    assert "the export failed (fabro dump exit 2)" in pointer.digest_unavailable_reason


# ---------------------------------------------------------------------------
# check_preserved_pointer
# ---------------------------------------------------------------------------


def test_a_pointer_whose_run_still_exports_matching_bytes_is_intact(tmp_path: Path) -> None:
    module = _module()
    runner = _ExportRunner(payloads={_ARTIFACT: _DIFF})

    check = _check(body=_digested_body(tmp_path), runner=runner, repo=tmp_path)

    assert check.state == module.POINTER_INTACT
    assert "every sha256 matching" in check.detail
    assert runner.calls == []


def test_a_pointer_whose_run_no_longer_exports_is_dangling(tmp_path: Path) -> None:
    module = _module()

    check = _check(body=_digested_body(tmp_path), runner=_ExportRunner(exit_code=1), repo=tmp_path)

    assert check.state == module.POINTER_DANGLING
    assert "no longer serves stage diffs" in check.detail


def test_a_pointer_whose_artifact_vanished_from_the_export_is_dangling(tmp_path: Path) -> None:
    module = _module()

    check = _check(
        body=_digested_body(tmp_path),
        runner=_ExportRunner(payloads={"stages/003-other@1/diff.patch": _DIFF}),
        repo=tmp_path,
    )

    assert check.state == module.POINTER_DANGLING
    assert f"no longer contains {_ARTIFACT}" in check.detail


def test_a_pointer_whose_artifact_bytes_changed_is_dangling(tmp_path: Path) -> None:
    # The export resolving is NOT the same as the work surviving intact:
    # a same-path artifact with different bytes is the case a presence-only
    # check would pass.
    module = _module()

    check = _check(
        body=_digested_body(tmp_path),
        runner=_ExportRunner(payloads={_ARTIFACT: "diff --git a/app.py b/app.py\n+other\n"}),
        repo=tmp_path,
    )

    assert check.state == module.POINTER_DANGLING
    assert "do not match the recorded sha256" in check.detail


def test_a_digestless_pointer_that_still_exports_is_unverifiable_not_intact(
    tmp_path: Path,
) -> None:
    module = _module()

    check = _check(
        body=_dump_failed_body(), runner=_ExportRunner(payloads={_ARTIFACT: _DIFF}), repo=tmp_path
    )

    assert check.state == module.POINTER_UNVERIFIABLE
    assert "recorded no digest to verify it against" in check.detail
    assert "the export failed (fabro dump exit 2)" in check.detail


def test_a_missing_artifact_pointer_reports_its_own_unavailability_reason(
    tmp_path: Path,
) -> None:
    module = _module()
    body, _ = missing_artifact_body(run_id="01M0RUN", server_url=_SERVER, fabro_bin=_FABRO_BIN)

    check = _check(body=body, runner=_ExportRunner(), repo=tmp_path)

    assert check.state == module.POINTER_UNVERIFIABLE
    assert "there were no bytes to digest" in check.detail


def test_a_digestless_pointer_with_no_recorded_reason_says_so(tmp_path: Path) -> None:
    module = _module()
    pointer = module.PreservedPointer(
        run_id="01M0RUN",
        server_url=_SERVER,
        artifacts=(),
        digest_unavailable_reason=None,
    )

    check = module.check_preserved_pointer(
        pointer=pointer, repo=tmp_path, fabro_bin=_FABRO_BIN, runner=_ExportRunner()
    )

    assert check.state == module.POINTER_UNVERIFIABLE
    assert "no reason recorded" in check.detail
