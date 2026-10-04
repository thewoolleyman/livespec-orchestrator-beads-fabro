"""The pre-dispatch seam that refuses a malformed sandbox-capability mirror.

Its own file rather than a case inside `test_dispatcher_sandbox_capabilities`
because the concern is different: that module's tests grade the MIRROR PARSE,
and these grade where the parse's refusal is CONSUMED — the shared
`dispatch_preamble` every `dispatch` and every `loop` iteration runs through.

WHY THE REFUSAL IS PRE-DISPATCH. The `dod_gate` node computes its
missing-capability finding from this array by comparing the capability an
assertion needs against the names the array holds. A hyphenated or capitalised
name therefore raises nothing anywhere: it fails to match, and the gate reports
a Definition-of-Done finding against an item whose declaration was correct —
naming a capability the image actually carries. Refusing the typo before any
Fabro run exists is the same discipline the node-timeout refusal keeps, for the
same reason, in the same pass.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands.dispatcher import dispatch_preamble

_EXIT_PRECONDITION_ERROR = 3
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"


def _repo_declaring(*, tmp_path: Path, dispatcher: dict[str, object]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({_PLUGIN_BLOCK: {"dispatcher": dispatcher}}), encoding="utf-8"
    )
    return repo


def _args(*, tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(fabro_bin=None, janitor=None, journal=str(tmp_path / "journal.jsonl"))


def test_a_non_snake_case_capability_name_refuses_the_dispatch_with_exit_three(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """The hyphenated spelling a human reaches for is named, not tolerated."""
    repo = _repo_declaring(
        tmp_path=tmp_path, dispatcher={"sandbox_capabilities": ["terminal", "headless-browser"]}
    )

    outcome = dispatch_preamble(args=_args(tmp_path=tmp_path), repo=repo)

    assert outcome == (None, _EXIT_PRECONDITION_ERROR)
    stderr = capsys.readouterr().err
    assert "dispatcher.sandbox_capabilities" in stderr
    assert "headless-browser" in stderr


def test_a_conforming_mirror_lets_the_whole_preamble_proceed(tmp_path: Path) -> None:
    """The positive control, asserted as a PROCEED rather than as an absence.

    `(None, None)` is the preamble's proceed answer — no janitor override to
    thread, no exit code to short-circuit on — so this is the one reading that
    cannot be satisfied by a seam that never ran: every refusal in the pass,
    this one included, returns an exit code in the second slot.

    Checking only that the capability message is absent from stderr would be
    the weaker instrument, because any LATER refusal would also leave it
    absent.
    """
    repo = _repo_declaring(
        tmp_path=tmp_path,
        dispatcher={"sandbox_capabilities": ["terminal", "headless_browser", "tmux"]},
    )

    assert dispatch_preamble(args=_args(tmp_path=tmp_path), repo=repo) == (None, None)


def test_an_absent_mirror_lets_the_preamble_proceed(tmp_path: Path) -> None:
    """A repository declaring no mirror is not refused — absence is an answer.

    The discriminating case for the whole seam: if the refusal had been written
    against an EMPTY resolved set rather than against a malformed one, every
    repository that declares no capabilities would stop dispatching.
    """
    repo = _repo_declaring(tmp_path=tmp_path, dispatcher={})

    assert dispatch_preamble(args=_args(tmp_path=tmp_path), repo=repo) == (None, None)
