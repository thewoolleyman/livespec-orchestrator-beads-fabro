"""Tests for the Dispatcher's fabro engine-binary preflight (work-item bd-ib-qz7b54).

The Dispatcher resolves its `fabro` engine binary from `--fabro-bin` / env /
config / an absolute default, then REFUSES at preflight — BEFORE arming the
OTLP receiver, preparing the store, or admitting anything (ready -> active) —
when the resolved binary is not an existing executable. Refusing before
admission is the fix for bd-ib-qz7b54: a bare-name `fabro` that failed to
resolve under the fleet credential wrapper's sanitized PATH used to strand the
admitted item at active (ready -> active, assignee=fabro) before the launch
subprocess raised FileNotFoundError.

Coverage here spans the resolution helper's two arcs (explicit flag wins vs.
defer to resolution), the preflight predicate's path-vs-bare-name arms (each
resolvable and not), and the end-to-end refusal exit code for both `dispatch`
and `loop`. The end-to-end refusals need NO live store: the preflight returns
before `_prepare`, so they run purely hermetically on a bare `tmp_path`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands.dispatcher import dispatch_preamble, main


def _make_executable(path: Path) -> None:
    _ = path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


_EXIT_PRECONDITION_ERROR = 3


# --- dispatch_preamble resolution ------------------------------------------


def test_resolve_fabro_bin_for_explicit_flag_wins(tmp_path: Path) -> None:
    """A non-None --fabro-bin is an operator override, returned verbatim."""
    exe = tmp_path / "explicit-fabro"
    _make_executable(exe)
    args = argparse.Namespace(fabro_bin=str(exe), janitor=None)
    janitor, rc = dispatch_preamble(args=args, repo=tmp_path)
    assert (janitor, rc) == (None, None)
    assert args.fabro_bin == str(exe)


def test_resolve_fabro_bin_for_none_defers_to_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A None flag defers to resolve_fabro_bin (exercised here via the env override)."""
    exe = tmp_path / "resolved-fabro"
    _make_executable(exe)
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", str(exe))
    args = argparse.Namespace(fabro_bin=None, janitor=None)
    janitor, rc = dispatch_preamble(args=args, repo=tmp_path)
    assert (janitor, rc) == (None, None)
    assert args.fabro_bin == str(exe)


# --- _fabro_preflight_error: absolute-path arm ------------------------------


def test_preflight_absolute_missing_is_error(tmp_path: Path) -> None:
    """A path-shaped value naming no existing file refuses, naming every knob."""
    missing = tmp_path / "nope" / "fabro"
    args = argparse.Namespace(fabro_bin=str(missing), janitor=None)
    janitor, rc = dispatch_preamble(args=args, repo=tmp_path)
    assert (janitor, rc) == (None, _EXIT_PRECONDITION_ERROR)


def test_preflight_absolute_executable_is_ok(tmp_path: Path) -> None:
    """A path-shaped value naming an existing executable file is resolvable."""
    exe = tmp_path / "fabro"
    _make_executable(exe)
    args = argparse.Namespace(fabro_bin=str(exe), janitor=None)
    assert dispatch_preamble(args=args, repo=tmp_path) == (None, None)


def test_preflight_absolute_non_executable_is_error(tmp_path: Path) -> None:
    """A path that exists but is not executable (no +x) refuses."""
    plain = tmp_path / "fabro"
    _ = plain.write_text("not executable\n", encoding="utf-8")
    plain.chmod(0o644)
    args = argparse.Namespace(fabro_bin=str(plain), janitor=None)
    assert dispatch_preamble(args=args, repo=tmp_path) == (
        None,
        _EXIT_PRECONDITION_ERROR,
    )


# --- _fabro_preflight_error: bare-name arm ----------------------------------


def test_preflight_bare_name_not_on_path_is_error() -> None:
    """A bare name absent from PATH refuses (the original bare-`fabro` failure mode)."""
    args = argparse.Namespace(fabro_bin="definitely-not-a-real-binary-xyz", janitor=None)
    assert dispatch_preamble(args=args, repo=Path.cwd()) == (
        None,
        _EXIT_PRECONDITION_ERROR,
    )


def test_preflight_bare_name_on_path_is_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare name found on PATH (shutil.which) is resolvable."""
    exe = tmp_path / "myfabro"
    _make_executable(exe)
    monkeypatch.setenv("PATH", str(tmp_path))
    args = argparse.Namespace(fabro_bin="myfabro", janitor=None)
    assert dispatch_preamble(args=args, repo=tmp_path) == (None, None)


# --- end-to-end refusal before admission ------------------------------------


def test_loop_refuses_before_admission_on_unresolvable_fabro(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`loop` with an unresolvable explicit --fabro-bin refuses at preflight (exit 3).

    The refusal is before `_prepare`, so no live store / `.livespec.jsonc` is
    needed on `tmp_path`; the explicit flag overrides the hermetic env stub.
    """
    rc = main(
        argv=[
            "loop",
            "--repo",
            str(tmp_path),
            "--budget",
            "1",
            "--fabro-bin",
            "/nonexistent/fabro",
            "--json",
        ]
    )
    assert rc == _EXIT_PRECONDITION_ERROR
    assert "not resolvable" in capsys.readouterr().err


def test_dispatch_refuses_before_admission_on_unresolvable_fabro(tmp_path: Path) -> None:
    """`dispatch` with an unresolvable explicit --fabro-bin refuses at preflight (exit 3)."""
    rc = main(
        argv=[
            "dispatch",
            "--repo",
            str(tmp_path),
            "--item",
            "any-id",
            "--fabro-bin",
            "/nonexistent/fabro",
        ]
    )
    assert rc == _EXIT_PRECONDITION_ERROR
