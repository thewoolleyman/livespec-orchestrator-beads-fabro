"""Whether any run of one item is still live, as the reclaim valve must ask it.

The publish-branch reclaim deletes a remote ref, so it may only act on a branch
nobody is about to push to. This module's answer is what authorizes that
deletion, which fixes both of its properties: it must FAIL CLOSED when the
factory cannot be asked, and it must be OVER-inclusive about which runs belong to
the item.

WHY FAIL-CLOSED IS THE WHOLE POINT HERE. An unanswerable `fabro ps` and a factory
with no runs at all produce the same empty set of live runs, and the difference is
invisible downstream. A gauge that reported "nothing alive" when it could not see
would clear a running publish's branch and leave a journal record that reads
exactly like a healthy reclaim — the blinded-gauge failure this repository's own
rules name as worse than the honest refusal, because it falsifies the record an
operator would use to reconstruct what happened.

WHY THE GOAL-TEXT LEG IS NOT REDUNDANT. A run exists for a short window before the
Dispatcher journals its id, and in that window its rendered brief is the only thing
that names its item. Attributing by journaled id alone would read such a run as
somebody else's and clear the branch it is about to push to. Over-inclusion costs a
hold an operator can clear by hand; under-inclusion costs a live run its branch, so
the two errors are not symmetric and the reading is deliberately the wider one.
"""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_run_summaries_from_stdout,
)

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_liveness"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_publish_branch_liveness.py"
)

_ITEM_ID = "bd-ib-qm4luz"
_BRANCH = f"feat/{_ITEM_ID}"
_JOURNALED_RUN_ID = "01M44F9E56XCEWZNMVJX4M14Z6"
# A run the Dispatcher has not journaled yet: attributable by its goal text alone.
_UNSTAMPED_RUN_ID = "01M44PQW4DAJF5J6N1XQNYVKX3"


def _liveness() -> Any:
    """Import the liveness module, asserting the file exists first.

    The `is_file()` assertion is what makes this a genuine failing assertion
    before the module is written, rather than a collection-time import error that
    proves only unimportability.
    """
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE)


@dataclass(kw_only=True)
class _Runner:
    """A subprocess seam answering every argv with ONE scripted result.

    Unconditional rather than keyed by argv, because this probe issues exactly one
    command: a seam that selected among answers would carry a branch no test here
    could reach, and an unreachable branch in a fake is a gap in the suite rather
    than a property of the thing under test. Every argv is recorded, so what was
    actually asked is still assertable.
    """

    answer: CommandResult
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        return self.answer


def _ps_stdout(*, runs: Sequence[tuple[str, str, str | None]]) -> str:
    """A `fabro ps -a --json` payload: one `(run id, status, item named in the goal)`.

    The SHAPE is the pinned build's — a bare list whose status is a nested
    `{"kind": ...}` — so these rows reach the reading under test through the same
    parser production uses rather than through a shape invented here.
    """
    return json.dumps(
        [
            {
                "run_id": run_id,
                "status": {"kind": status},
                "goal": "" if item_id is None else f"Work-item: {item_id}\n",
            }
            for run_id, status, item_id in runs
        ]
    )


def _args() -> argparse.Namespace:
    """The dispatch namespace the probe reads its factory client off.

    `fabro_factory_target` absent is the shape a non-dispatching caller has, and
    the one the probe must degrade on rather than raise.
    """
    return argparse.Namespace(fabro_bin="/usr/local/bin/fabro")


def test_a_non_terminal_run_of_the_item_is_live_by_either_attribution_leg() -> None:
    """Both legs count, and each catches a run the other is blind to."""
    module = _liveness()
    runs = fabro_run_summaries_from_stdout(
        stdout=_ps_stdout(
            runs=(
                (_JOURNALED_RUN_ID, "running", None),
                (_UNSTAMPED_RUN_ID, "blocked", _ITEM_ID),
            )
        )
    )

    assert module.live_run_ids_for_item(
        runs=runs, journaled=(_JOURNALED_RUN_ID,), work_item_id=_ITEM_ID
    ) == (_JOURNALED_RUN_ID, _UNSTAMPED_RUN_ID)
    # Each leg alone: the journaled id for a run whose goal names nobody, and the
    # goal text for a run the journal has never heard of.
    assert module.live_run_ids_for_item(runs=runs, journaled=(), work_item_id=_ITEM_ID) == (
        _UNSTAMPED_RUN_ID,
    )


def test_a_terminal_run_of_the_item_and_a_live_run_of_another_are_both_ignored() -> None:
    """The dead run being reclaimed must not hold its own reclaim.

    Reading a terminal run as live would hold every reclaim this valve exists to
    perform — the branch belongs to a run that has already ended, which is the
    whole premise — and reading another item's running run as live would hold
    every reclaim on a busy factory.
    """
    module = _liveness()
    runs = fabro_run_summaries_from_stdout(
        stdout=_ps_stdout(
            runs=(
                (_JOURNALED_RUN_ID, "failed", _ITEM_ID),
                ("01M44SOMEBODYELSESRUNAAAAA", "running", "bd-ib-somebody-else"),
            )
        )
    )

    assert (
        module.live_run_ids_for_item(
            runs=runs, journaled=(_JOURNALED_RUN_ID,), work_item_id=_ITEM_ID
        )
        == ()
    )


def test_an_unanswerable_factory_is_unobserved_and_never_reclaimable(tmp_path: Path) -> None:
    """The fail-closed arm: no answer is not the same value as no live runs.

    The two produce the same empty `live_run_ids`, so the reclaimable decision is
    asserted alongside it — that is the only place the difference is visible, and
    it is the one that authorizes a deletion.
    """
    module = _liveness()
    journal_path = tmp_path / "fabro-dispatch-journal.jsonl"
    runner = _Runner(answer=CommandResult(exit_code=1, stdout="", stderr="connection refused"))

    liveness = module.item_run_liveness(
        args=_args(),
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        journal_path=journal_path,
        runner=runner,
    )

    assert liveness.live_run_ids == ()
    assert liveness.observed is False
    assert liveness.reclaimable is False
    assert module.HELD_FACTORY_UNOBSERVABLE in liveness.held_reason
    assert "fabro ps" in liveness.detail(branch=_BRANCH)
    assert _BRANCH in liveness.detail(branch=_BRANCH)
    # An empty-but-OBSERVED reading is the one that may proceed, and it is the
    # control that keeps the assertion above about the gauge rather than the shape.
    assert module.ItemRunLiveness(live_run_ids=(), observed=True).reclaimable is True


def test_the_probe_reads_this_items_runs_off_the_factory_and_the_journal(
    tmp_path: Path,
) -> None:
    """End to end: the factory is asked, and the journal supplies the strong leg.

    The journal is a real file in the production record shape, because the
    journaled leg is what makes a run whose goal names nobody attributable at all
    — a probe handed its ids directly would pass against a build that could not
    recover them.
    """
    module = _liveness()
    journal_path = tmp_path / "fabro-dispatch-journal.jsonl"
    _ = journal_path.write_text(
        json.dumps({"stage": "fabro-run", "work_item_id": _ITEM_ID, "run_id": _JOURNALED_RUN_ID})
        + "\n",
        encoding="utf-8",
    )
    runner = _Runner(
        answer=CommandResult(
            exit_code=0,
            stdout=_ps_stdout(runs=((_JOURNALED_RUN_ID, "running", None),)),
            stderr="",
        )
    )

    liveness = module.item_run_liveness(
        args=_args(),
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        journal_path=journal_path,
        runner=runner,
    )

    assert liveness.observed is True
    assert liveness.live_run_ids == (_JOURNALED_RUN_ID,)
    assert liveness.reclaimable is False
    assert module.HELD_LIVE_RUN in liveness.held_reason
    assert _JOURNALED_RUN_ID in liveness.detail(branch=_BRANCH)
    # One `fabro ps -a --json` against the configured factory, and nothing else:
    # this probe asks a question and never mutates anything.
    assert [argv[1:4] for argv in runner.argvs] == [["ps", "-a", "--json"]]
