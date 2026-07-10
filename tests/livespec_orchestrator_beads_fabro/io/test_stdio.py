"""Tests for the package-local terminal stream helpers."""

from io import StringIO

from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = []


def test_write_stdout_writes_to_injected_stream() -> None:
    stream = StringIO()

    write_stdout(text="hello", stream=stream)

    assert stream.getvalue() == "hello"


def test_write_stderr_writes_to_injected_stream() -> None:
    stream = StringIO()

    write_stderr(text="problem", stream=stream)

    assert stream.getvalue() == "problem"


def test_default_streams_are_process_streams(capsys) -> None:
    write_stdout(text="out")
    write_stderr(text="err")

    captured = capsys.readouterr()
    assert captured.out == "out"
    assert captured.err == "err"
