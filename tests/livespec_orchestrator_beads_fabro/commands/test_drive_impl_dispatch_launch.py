"""What an `impl:` dispatch's launch decides and leaves behind, without a slice.

The scoped launch is bound at the integration tier by
`tests/integration/test_impl_dispatch_memory_slice_scenario371.py`. These cover
the other half the same clause owes: a host that does not provide the slice
launches with exactly the argv it always did, says so, and a fault writing the
launch's journal record never fails the dispatch.
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._drive_impl_dispatch import (
    CommandRun,
    build_dispatcher_argv,
    run_impl_dispatch,
)

_ITEM = "bd-ib-szbxu7"


class _Runner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        del cwd
        self.calls.append(argv)
        return CommandRun(argv=argv, returncode=0, stdout="[]", stderr="")


def _dispatch(*, repo: Path, runner: _Runner) -> dict[str, object]:
    return run_impl_dispatch(
        repo=repo,
        work_item_ref=_ITEM,
        runner=runner,
        dispatcher_bin=repo / "dispatcher.py",
        acp_nodes=(),
        workflow_name=None,
        identity=None,
    )


def test_a_host_without_the_slice_launches_the_unchanged_argv_and_says_so(tmp_path: Path) -> None:
    runner = _Runner()

    result = _dispatch(repo=tmp_path, runner=runner)

    loop_argv = build_dispatcher_argv(
        repo=tmp_path, dispatcher_bin=tmp_path / "dispatcher.py", work_item_ref=_ITEM
    )
    assert runner.calls == [loop_argv]
    assert result["launch"] == "unscoped"
    assert "scope_unit" not in result
    journal = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    (record,) = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert record["stage"] == "dispatch-launch-scope"
    assert record["work_item_id"] == _ITEM
    assert record["launch"] == "unscoped"
    assert "scope_unit" not in record


def test_a_fault_writing_the_launch_record_does_not_fail_the_dispatch(tmp_path: Path) -> None:
    _ = (tmp_path / "tmp").write_text(
        "a file where the journal directory belongs", encoding="utf-8"
    )
    runner = _Runner()

    result = _dispatch(repo=tmp_path, runner=runner)

    assert len(runner.calls) == 1
    assert result["status"] == "green"
    assert result["launch"] == "unscoped"
