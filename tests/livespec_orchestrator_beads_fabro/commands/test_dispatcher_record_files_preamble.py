"""The pre-dispatch seam that refuses a malformed record-file `generator`.

Its own file rather than a case inside `test_dispatcher_record_files` because the
concern is different: that module's tests grade the GRADE itself, and these grade
where the grade's refusal is CONSUMED — the shared `dispatch_preamble` every
`dispatch` and every `loop` iteration runs through.

WHY THE REFUSAL IS PRE-DISPATCH. The declared-record-file clause makes a
generated record file's correct content "its generator's output over the tree it
sits in", and a refresh resolves a conflict in such a file by RUNNING that argv
rather than by merging the file's text. A declaration naming anything other than
a non-empty argv array therefore has no command for the refresh to run, and the
refresh is the point at which that would be discovered — after a whole run's
implement, janitor and publication. Refusing before any item is claimed is the
same discipline the overflow array and the capability mirror keep, in the same
pass.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands.dispatcher import dispatch_preamble

_EXIT_PRECONDITION_ERROR = 3
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_REGISTER = "tests/heading-coverage-debt.json"
_GENERATOR = ["tools/generate-register", "--write"]


def _repo_declaring(*, tmp_path: Path, record_files: object) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({_PLUGIN_BLOCK: {"dispatcher": {"record_files": record_files}}}),
        encoding="utf-8",
    )
    return repo


def _args(*, tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(fabro_bin=None, janitor=None, journal=str(tmp_path / "journal.jsonl"))


def test_an_empty_generator_argv_refuses_the_dispatch_with_exit_three(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """The refusal reaches the operator naming the entry's own `generator` key."""
    repo = _repo_declaring(
        tmp_path=tmp_path,
        record_files=[{"path": _REGISTER, "format": "json-array", "generator": []}],
    )

    outcome = dispatch_preamble(args=_args(tmp_path=tmp_path), repo=repo)

    assert outcome == (None, _EXIT_PRECONDITION_ERROR)
    stderr = capsys.readouterr().err
    assert "dispatcher.record_files[0].generator" in stderr


def test_a_well_formed_generator_lets_the_whole_preamble_proceed(tmp_path: Path) -> None:
    """The positive control, asserted as a PROCEED rather than as an absence.

    `(None, None)` is the preamble's proceed answer — no janitor override to
    thread, no exit code to short-circuit on — so this is the one reading that
    cannot be satisfied by a seam that never ran: every refusal in the pass, this
    one included, returns an exit code in the second slot.

    Checking only that the record-file message is absent from stderr would be the
    weaker instrument, because any LATER refusal would also leave it absent.
    """
    repo = _repo_declaring(
        tmp_path=tmp_path,
        record_files=[{"path": _REGISTER, "format": "json-array", "generator": _GENERATOR}],
    )

    assert dispatch_preamble(args=_args(tmp_path=tmp_path), repo=repo) == (None, None)


def test_a_record_file_declaring_no_generator_lets_the_preamble_proceed(
    tmp_path: Path,
) -> None:
    """A declared record file that no generator rewrites is not refused.

    The discriminating case for the whole seam: the clause makes `generator`
    optional, so if the refusal had been written against an entry that declares
    NONE rather than against one declaring a malformed value, every repository
    that declares a record file at all would stop dispatching — and that is every
    repository the entry-wise merge is for.
    """
    repo = _repo_declaring(
        tmp_path=tmp_path,
        record_files=[{"path": _REGISTER, "format": "json-array", "key": ["heading"]}],
    )

    assert dispatch_preamble(args=_args(tmp_path=tmp_path), repo=repo) == (None, None)
