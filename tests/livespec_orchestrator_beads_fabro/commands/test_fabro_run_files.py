"""Every run-files response shape the reader accepts, and every one it refuses."""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._fabro_port_http import (
    FabroHttpPort,
    FabroHttpResult,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_run_files import (
    RunFile,
    RunFiles,
    RunFilesUnreadable,
    read_run_files,
    run_files_from_payload,
)

_RUN_ID = "01M4YJGC55V86C9V1X07QG3Y2H"


@dataclass(kw_only=True)
class _FixedTransport:
    """Answer every request with one prepared exchange."""

    result: FabroHttpResult

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        _ = method
        _ = url
        _ = headers
        _ = body
        _ = timeout_seconds
        return self.result


def _port(*, result: FabroHttpResult) -> FabroHttpPort:
    return FabroHttpPort(
        target=FabroTarget(server_url="https://factory.example:32276"),
        transport=_FixedTransport(result=result),
    )


def _unserved(*files: RunFile) -> RunFiles:
    """The expected read of a response that named no scope and no source.

    Every payload in this module is a bare list, or a container carrying no
    readable `meta`, so each one leaves both absent. The MEASURED shape and its
    `meta` are covered by `test_fabro_run_files_measured_shape`.
    """
    return RunFiles(files=files, scope=None, source=None)


def test_a_refused_read_is_unreadable_and_names_the_status_and_the_run() -> None:
    read = read_run_files(
        port=_port(
            result=FabroHttpResult(
                status=401,
                body="Authentication required",
                error=None,
                payload=None,
                succeeded=False,
            )
        ),
        run_id=_RUN_ID,
    )
    assert isinstance(read, RunFilesUnreadable)
    assert "401" in read.detail
    assert _RUN_ID in read.detail
    assert "Authentication required" in read.detail


def test_a_transport_fault_reports_its_own_error_rather_than_an_empty_body() -> None:
    read = read_run_files(
        port=_port(
            result=FabroHttpResult(
                status=0,
                body="",
                error="URLError: refused",
                payload=None,
                succeeded=False,
            )
        ),
        run_id=_RUN_ID,
    )
    assert isinstance(read, RunFilesUnreadable)
    assert "URLError: refused" in read.detail


def test_a_refusal_with_neither_error_nor_body_still_says_what_it_saw() -> None:
    read = read_run_files(
        port=_port(
            result=FabroHttpResult(
                status=500, body="   ", error=None, payload=None, succeeded=False
            )
        ),
        run_id=_RUN_ID,
    )
    assert isinstance(read, RunFilesUnreadable)
    assert "no body" in read.detail


def test_a_successful_read_parses_the_served_payload() -> None:
    read = read_run_files(
        port=_port(
            result=FabroHttpResult(
                status=200,
                body='[{"path": "a.py", "content": "x\\n"}]',
                error=None,
                payload=None,
                succeeded=True,
            )
        ),
        run_id=_RUN_ID,
    )
    assert read == _unserved(RunFile(path="a.py", content=b"x\n", mode="100644"))


def test_a_bare_list_a_data_key_and_a_files_key_all_read_as_the_same_changes() -> None:
    expected = _unserved(RunFile(path="a.py", content=b"x\n", mode="100644"))
    entry = {"path": "a.py", "content": "x\n"}
    assert run_files_from_payload(payload=[entry]) == expected
    assert run_files_from_payload(payload={"data": [entry]}) == expected
    assert run_files_from_payload(payload={"files": [entry]}) == expected


def test_a_name_key_stands_in_for_a_path_and_contents_or_text_for_content() -> None:
    assert run_files_from_payload(payload=[{"name": "a.py", "contents": "x\n"}]) == _unserved(
        RunFile(path="a.py", content=b"x\n", mode="100644")
    )
    assert run_files_from_payload(payload=[{"path": "a.py", "text": "x\n"}]) == _unserved(
        RunFile(path="a.py", content=b"x\n", mode="100644")
    )


def test_an_unrecognized_container_is_unreadable_rather_than_an_empty_change_set() -> None:
    for payload in (None, 7, "files", {"items": [{"path": "a.py"}]}, {}):
        read = run_files_from_payload(payload=payload)
        assert isinstance(read, RunFilesUnreadable), payload
        assert "no list of changed files" in read.detail


def test_an_entry_that_is_not_an_object_is_unreadable_and_names_its_type() -> None:
    read = run_files_from_payload(payload=["a.py"])
    assert isinstance(read, RunFilesUnreadable)
    assert "str rather than an object" in read.detail


def test_an_entry_naming_no_path_is_unreadable() -> None:
    read = run_files_from_payload(payload=[{"content": "x\n"}])
    assert isinstance(read, RunFilesUnreadable)
    assert "named no path" in read.detail


def test_an_entry_that_is_neither_a_removal_nor_carries_content_is_unreadable() -> None:
    read = run_files_from_payload(payload=[{"path": "a.py", "size": 12}])
    assert isinstance(read, RunFilesUnreadable)
    assert "neither a removal nor carries content" in read.detail


def test_both_removal_spellings_read_as_a_removal_and_neither_as_empty_content() -> None:
    for entry in (
        {"path": "gone.py", "deleted": True},
        {"path": "gone.py", "removed": True},
        {"path": "gone.py", "status": "Deleted"},
        {"path": "gone.py", "change": "removed"},
    ):
        read = run_files_from_payload(payload=[entry])
        assert read == _unserved(RunFile(path="gone.py", content=None, mode="100644")), entry


def test_a_non_removal_state_word_leaves_the_entry_on_the_content_path() -> None:
    read = run_files_from_payload(payload=[{"path": "a.py", "status": "modified", "text": "x\n"}])
    assert read == _unserved(RunFile(path="a.py", content=b"x\n", mode="100644"))


def test_base64_content_is_decoded_and_undecodable_base64_is_unreadable() -> None:
    assert run_files_from_payload(
        payload=[{"path": "a.py", "content": "eA==", "encoding": "base64"}]
    ) == _unserved(RunFile(path="a.py", content=b"x", mode="100644"))
    read = run_files_from_payload(
        payload=[{"path": "a.py", "content": "not base64!", "encoding": "base64"}]
    )
    assert isinstance(read, RunFilesUnreadable)
    assert "does not decode" in read.detail


def test_a_declared_mode_is_carried_and_an_unusable_one_falls_back_to_a_regular_file() -> None:
    assert run_files_from_payload(
        payload=[{"path": "run.sh", "text": "x\n", "mode": "100755"}]
    ) == _unserved(RunFile(path="run.sh", content=b"x\n", mode="100755"))
    for unusable in ("0644", 100644, "1006xx", None):
        read = run_files_from_payload(payload=[{"path": "a.py", "text": "x\n", "mode": unusable}])
        assert read == _unserved(RunFile(path="a.py", content=b"x\n", mode="100644")), unusable


def test_an_entry_whose_path_is_not_a_string_names_no_path() -> None:
    read = run_files_from_payload(payload=[{"path": 7, "content": "x\n"}])
    assert isinstance(read, RunFilesUnreadable)
    assert "named no path" in read.detail


def test_a_later_unreadable_entry_refuses_the_whole_read() -> None:
    read = run_files_from_payload(payload=[{"path": "a.py", "content": "x\n"}, {"content": "y\n"}])
    assert isinstance(read, RunFilesUnreadable)
    assert "named no path" in read.detail
