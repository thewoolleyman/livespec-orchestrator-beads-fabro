"""Tests for wiring the out-of-band reflector into the dispatcher (29f.4).

Covers `dispatcher._reflector_oob_after_verdict`: the 5th post-verdict
stage. The load-bearing invariants: it is fire-and-forget (a daemon thread
in production, injectable `spawn` for the hermetic tier), default-OFF (no
`claude -p` without the lever), and fail-open (it never raises and never
touches the already-computed verdict). NO real `claude -p` / MCP / PR ever
fires — the runner + lessons proposer are injected fakes.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_impl_beads.commands import _dispatcher_reflector_oob as reflector
from livespec_impl_beads.commands._dispatcher_engine import CommandResult
from livespec_impl_beads.commands._dispatcher_io import JournalFile
from livespec_impl_beads.commands._dispatcher_reflector_oob import RecordingLessonsProposer
from livespec_impl_beads.commands.dispatcher import (
    _reflector_oob_after_verdict,  # pyright: ignore[reportPrivateUsage]
    _reflector_oob_spans_path,  # pyright: ignore[reportPrivateUsage]
    _spawn_daemon,  # pyright: ignore[reportPrivateUsage]
)

_MCP_ENV = "HONEYCOMB_MCP_API_KEY_LIVESPEC"
_LEVER_ENV = "LIVESPEC_REFLECTOR_OOB"


@pytest.fixture(autouse=True)
def reset_auto_trip_fixture() -> None:
    reflector.reset_auto_trip()


@dataclass(kw_only=True)
class _FakeRunner:
    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        _ = (cwd, timeout_seconds)
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout="", stderr="")


def _args(*, journal: Path) -> argparse.Namespace:
    return argparse.Namespace(journal=str(journal))


def _sync_spawn() -> Callable[[Callable[[], None]], None]:
    """A spawn that runs the body inline (no real thread) for hermetic tests."""

    def _spawn(body: Callable[[], None]) -> None:
        body()

    return _spawn


def test_spans_path_is_a_journal_sibling(tmp_path: Path) -> None:
    journal = tmp_path / "j.jsonl"
    path = _reflector_oob_spans_path(args=_args(journal=journal), repo=tmp_path)
    assert path.name == "j-reflector-oob-spans.jsonl"
    assert path.parent == tmp_path


def test_off_by_default_does_not_run_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(_LEVER_ENV, raising=False)
    journal = JournalFile(path=tmp_path / "j.jsonl")
    runner = _FakeRunner()
    _reflector_oob_after_verdict(
        args=_args(journal=tmp_path / "j.jsonl"),
        repo=tmp_path,
        journal=journal,
        runner=runner,
        lessons_proposer=RecordingLessonsProposer(),
        spawn=_sync_spawn(),
    )
    assert runner.calls == []  # lever off -> no claude -p.


def test_armed_runs_the_reflector_through_the_injected_seams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_LEVER_ENV, "observe")
    monkeypatch.setenv(_MCP_ENV, "hcmk-secret")
    journal_path = tmp_path / "j.jsonl"
    journal = JournalFile(path=journal_path)
    runner = _FakeRunner()
    _reflector_oob_after_verdict(
        args=_args(journal=journal_path),
        repo=tmp_path,
        journal=journal,
        runner=runner,
        lessons_proposer=RecordingLessonsProposer(),
        spawn=_sync_spawn(),
    )
    # The reflector ran the claude -p reflector through the injected runner.
    assert any(call[:2] == ["claude", "-p"] for call in runner.calls)


def test_reflector_after_verdict_never_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_LEVER_ENV, "file")
    monkeypatch.setenv(_MCP_ENV, "hcmk-secret")

    @dataclass(kw_only=True)
    class _Boom:
        def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
            _ = (argv, cwd, timeout_seconds)
            raise RuntimeError("claude exploded")

    journal = JournalFile(path=tmp_path / "j.jsonl")
    # Must NOT raise — the stage is fail-open.
    _reflector_oob_after_verdict(
        args=_args(journal=tmp_path / "j.jsonl"),
        repo=tmp_path,
        journal=journal,
        runner=_Boom(),
        lessons_proposer=RecordingLessonsProposer(),
        spawn=_sync_spawn(),
    )


def test_spawn_daemon_starts_and_completes_a_thread() -> None:
    import threading as _threading

    done = _threading.Event()
    _spawn_daemon(done.set)
    # The daemon thread is fire-and-forget; wait deterministically for it.
    assert done.wait(timeout=2.0) is True


def test_default_seams_resolve_without_injection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No injected runner / lessons proposer: the lever is off, so the
    # default seams resolve but the reflector short-circuits before any
    # real subprocess / PR happens (no claude -p, no MCP, no PR).
    monkeypatch.delenv(_LEVER_ENV, raising=False)
    journal = JournalFile(path=tmp_path / "j.jsonl")
    _reflector_oob_after_verdict(
        args=_args(journal=tmp_path / "j.jsonl"),
        repo=tmp_path,
        journal=journal,
        spawn=_sync_spawn(),
    )
    assert not (tmp_path / "j.jsonl").exists()  # off -> nothing journaled.
