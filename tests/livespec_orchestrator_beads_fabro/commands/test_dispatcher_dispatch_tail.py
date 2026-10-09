"""The post-verdict tail both single-dispatch entry points run, as ONE sequence.

`run_dispatch_command` ended with eight calls that are not the dispatch itself:
the outcome emission, the verdict, the alarm, the cost gate, the self-update, the
run-turn checks, the reflection and the out-of-band reflector. The ratified
`resume --item` surface must "journal exactly as a dispatch does -- including the
fail-closed cost-gate record, under the hand-picked posture", and its outcome
"maps to the Dispatcher exit codes as a `dispatch --item` outcome does". So the
sequence has a second caller.

WHY IT IS ONE SHARED FUNCTION RATHER THAN A SECOND COPY. A copy makes "both paths
journal the same" a claim about two sequences that can drift, and it requires
every future post-verdict stage to be wired twice -- which is exactly the drift
the one-wall consolidation (`_dispatcher_pre_dispatch_wall`) retired for the
pre-dispatch half. The tail is the post-verdict half of the same argument.

THE ORDERING THIS FILE PINS IS LOAD-BEARING, not stylistic. The exit code is
computed BEFORE the alarm, the cost gate, the self-update, the reflection and the
reflector, and is immutable by all five (loop-reflection-gate best-practices
section 6). Those stages are FAIL-OPEN by design, so a tail that computed the
verdict afterwards would let a best-effort notification change a dispatch
verdict. A test that only checked the returned code would pass against that
inversion, because in the green case the two orderings agree -- so the order is
asserted directly, as a recorded call sequence.
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_commands as run_commands
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_tail"

# Every post-verdict stage, in the order `run_dispatch_command` ran them. The
# verdict sits where it sat: after the emission and before every fail-open stage.
_EXPECTED_ORDER = (
    "emit_outcomes",
    "dispatch_exit_code",
    "alarm_on_terminal_failure",
    "cost_gate_after_verdict",
    "self_update_after_verdict",
    "append_run_turn_checks",
    "reflect",
    "reflector_oob_after_verdict",
)


def _module_path() -> Path:
    """Where the extracted tail is expected on disk."""
    return Path(run_commands.__file__).parent / "_dispatcher_dispatch_tail.py"


def _outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-one",
        status="green",
        stage="done",
        pr_number=7,
        merge_sha="deadbeef",
        detail="merged, post-merge janitor green",
    )


def _args(*, repo: Path) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(repo / "journal.jsonl"),
        as_json=False,
    )


def _record_every_stage(
    *,
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    verdict: int,
) -> None:
    """Replace every collaborator the tail calls with one that records its name."""

    def _recorder(name: str, *, answer: object = None) -> object:
        def _call(**_kwargs: object) -> object:
            calls.append(name)
            return answer

        return _call

    for name in _EXPECTED_ORDER:
        answer = verdict if name == "dispatch_exit_code" else None
        monkeypatch.setattr(module, name, _recorder(name, answer=answer))


def test_the_extracted_tail_exists_on_disk() -> None:
    """The first genuine assertion of the move: the module is a file."""
    assert _module_path().is_file()


def test_the_tail_exposes_exactly_one_public_entry_point() -> None:
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)

    assert module.__all__ == ["dispatch_tail_exit"]


def test_every_post_verdict_stage_runs_in_the_order_the_dispatch_ran_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verdict is computed before every fail-open stage and cannot be moved."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    calls: list[str] = []
    _record_every_stage(module=module, monkeypatch=monkeypatch, calls=calls, verdict=0)
    journal = JournalFile(path=tmp_path / "journal.jsonl", identity="test:tail")

    exit_code = module.dispatch_tail_exit(
        args=_args(repo=tmp_path), repo=tmp_path, outcome=_outcome(), journal=journal
    )

    assert exit_code == 0
    assert tuple(calls) == _EXPECTED_ORDER


def test_the_returned_code_is_the_verdict_the_stages_cannot_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fail-open stage running after the verdict must not be able to move it."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    calls: list[str] = []
    _record_every_stage(module=module, monkeypatch=monkeypatch, calls=calls, verdict=4)
    journal = JournalFile(path=tmp_path / "journal.jsonl", identity="test:tail")

    exit_code = module.dispatch_tail_exit(
        args=_args(repo=tmp_path), repo=tmp_path, outcome=_outcome(), journal=journal
    )

    assert exit_code == 4
    assert tuple(calls) == _EXPECTED_ORDER


def test_the_dispatch_command_runs_the_shared_tail_rather_than_its_own_copy() -> None:
    """A second copy of the sequence is the drift this extraction exists to retire."""
    assert _module_path().is_file()
    source = Path(run_commands.__file__).read_text(encoding="utf-8")

    assert "dispatch_tail_exit" in source
    inlined = [name for name in _EXPECTED_ORDER if f"{name}(" in source]
    assert inlined == []
