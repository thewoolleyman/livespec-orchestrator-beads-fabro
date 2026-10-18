"""The three-valued measurements a claim is graded on.

Every case here exists because the two-valued helper it replaces answers the
same question correctly for a DIFFERENT caller. `live_dispatch_lock` collapses
"absent" and "unreadable" into `None`, which is right for WIP accounting and
would be a release here; `journal_records_or_none` keeps "the file is not
there" apart from "the file would not read", which is what lets an unreadable
history hold a claim while a fresh checkout's empty one does not.

THE LIVENESS CASES ARE ASSERTED OVER MORE THAN ONE CHECKOUT, which is the only
shape that can fail for the right reason: "no live owner" is a claim about the
COMPLETE set of lock locations, so a reading that stopped at the first absent
one would satisfy a single-checkout fixture while leaving the set
unestablished.
"""

from __future__ import annotations

import importlib
import json
import os
import time
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_dispatcher_stranded_claim_observe.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_observe"

_ITEM_ID = "bd-ib-observe"


def _module() -> object:
    return importlib.import_module(_MODULE_NAME)


class _Runner:
    """A fake subprocess seam replaying one scripted forge answer."""

    def __init__(self, *, exit_code: int, stdout: str) -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.argvs: list[list[str]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        return CommandResult(exit_code=self.exit_code, stdout=self.stdout, stderr="")


def _lock(*, checkout: Path, pid: int, started_at_epoch: float = 1.0) -> None:
    path = checkout / "tmp" / f"fabro-dispatch-{_ITEM_ID}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps(
            {
                "work_item_id": _ITEM_ID,
                "pid": pid,
                "started_at_epoch": started_at_epoch,
                "dispatch_id": "01DISPATCH",
            }
        ),
        encoding="utf-8",
    )


def _checkouts(*, module: object, monkeypatch: pytest.MonkeyPatch, paths: tuple[Path, ...]) -> None:
    def _registered(*, repo: Path) -> tuple[Path, ...]:
        _ = repo
        return paths

    monkeypatch.setattr(module, "tenant_checkouts", _registered)


def test_no_lock_anywhere_on_this_host_establishes_no_live_owner(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _MODULE_PATH.is_file()
    module = _module()
    first = tmp_path / "primary"
    second = tmp_path / "worktree"
    first.mkdir()
    second.mkdir()
    _checkouts(module=module, monkeypatch=monkeypatch, paths=(first, second))

    assert module.observe_owner_liveness(repo=first, work_item_id=_ITEM_ID) == "none"


def test_a_lock_naming_a_dead_process_is_not_a_live_owner(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    checkout = tmp_path / "primary"
    checkout.mkdir()
    # Pid 0 is refused by the payload reader as out of range, which is the
    # unreadable arm; a pid the kernel does not know is the dead arm. Use a
    # pid that cannot exist on any Linux host.
    _lock(checkout=checkout, pid=2**31 - 1)
    _checkouts(module=module, monkeypatch=monkeypatch, paths=(checkout,))

    assert module.observe_owner_liveness(repo=checkout, work_item_id=_ITEM_ID) == "none"


def test_a_live_lock_in_any_checkout_is_a_live_owner(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    first = tmp_path / "primary"
    second = tmp_path / "worktree"
    first.mkdir()
    second.mkdir()
    # The SECOND checkout holds it, so a reading that answered from the
    # invoking checkout alone would report no owner.
    _lock(checkout=second, pid=os.getpid(), started_at_epoch=time.time())
    _checkouts(module=module, monkeypatch=monkeypatch, paths=(first, second))

    assert module.observe_owner_liveness(repo=first, work_item_id=_ITEM_ID) == "live"


def test_one_unreadable_lock_location_leaves_the_whole_reading_unobservable(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    first = tmp_path / "primary"
    second = tmp_path / "worktree"
    first.mkdir()
    second.mkdir()
    unreadable = second / "tmp" / f"fabro-dispatch-{_ITEM_ID}.lock"
    unreadable.parent.mkdir(parents=True, exist_ok=True)
    _ = unreadable.write_text("not json", encoding="utf-8")
    _checkouts(module=module, monkeypatch=monkeypatch, paths=(first, second))

    assert module.observe_owner_liveness(repo=first, work_item_id=_ITEM_ID) == "unobservable"


def test_a_live_lock_outranks_an_unreadable_one(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live owner is a POSITIVE finding; doubt elsewhere cannot soften it."""
    module = _module()
    live = tmp_path / "live"
    broken = tmp_path / "broken"
    live.mkdir()
    broken.mkdir()
    _lock(checkout=live, pid=os.getpid(), started_at_epoch=time.time())
    unreadable = broken / "tmp" / f"fabro-dispatch-{_ITEM_ID}.lock"
    unreadable.parent.mkdir(parents=True, exist_ok=True)
    _ = unreadable.write_text("not json", encoding="utf-8")
    # The UNREADABLE one is read FIRST, so a reading that latched its doubt
    # would answer `unobservable` for a host that demonstrably has an owner.
    _checkouts(module=module, monkeypatch=monkeypatch, paths=(broken, live))

    assert module.observe_owner_liveness(repo=live, work_item_id=_ITEM_ID) == "live"


@pytest.mark.parametrize(
    ("exit_code", "stdout", "expected"),
    [
        (7, "", "unobservable"),
        (0, "not json", "unobservable"),
        (0, '{"number": 1}', "unobservable"),
        (0, "[7]", "unobservable"),
        (0, "[]", "no-merged-pr"),
        (0, '[{"number": 1, "state": "CLOSED"}]', "no-merged-pr"),
        (0, '[{"number": 1, "state": "MERGED"}]', "merged-pr"),
    ],
)
def test_the_forge_reading_never_reports_a_failure_as_a_negative(
    *,
    tmp_path: Path,
    exit_code: int,
    stdout: str,
    expected: str,
) -> None:
    module = _module()
    runner = _Runner(exit_code=exit_code, stdout=stdout)

    observed = module.observe_merged_pull_request(
        repo=tmp_path, runner=runner, work_item_id=_ITEM_ID
    )

    assert observed == expected
    # Searched BY WORK-ITEM ID and restricted to merged pull requests: a query
    # pinned to anything else would answer about the wrong population.
    assert runner.argvs[0][:6] == ["gh", "pr", "list", "--state", "merged", "--search"]
    assert runner.argvs[0][6] == _ITEM_ID


def test_an_absent_journal_is_readable_and_empty_rather_than_unavailable(*, tmp_path: Path) -> None:
    module = _module()

    assert module.journal_records_or_none(journal_path=tmp_path / "missing.jsonl") == ()


def test_an_unreadable_journal_is_unavailable_rather_than_empty(*, tmp_path: Path) -> None:
    module = _module()
    directory = tmp_path / "journal.jsonl"
    directory.mkdir()

    assert module.journal_records_or_none(journal_path=directory) is None


def test_a_journal_line_that_is_not_a_mapping_is_dropped_rather_than_raising(
    *, tmp_path: Path
) -> None:
    module = _module()
    path = tmp_path / "journal.jsonl"
    _ = path.write_text('{"stage": "one"}\nnot json\n[1, 2]\n', encoding="utf-8")

    assert module.journal_records_or_none(journal_path=path) == ({"stage": "one"},)


@pytest.mark.parametrize(
    ("records", "expected"),
    [
        (None, "unavailable"),
        ((), "unavailable"),
        (({"stage": "dispatch-id", "work_item_id": "bd-ib-other"},), "unavailable"),
        (({"stage": "dispatch-id", "work_item_id": _ITEM_ID},), "no-predecessor"),
        (
            (
                {"stage": "dispatch-id", "work_item_id": _ITEM_ID},
                {"stage": "outcome", "work_item_id": _ITEM_ID},
                {"stage": "dispatch-id", "work_item_id": _ITEM_ID},
            ),
            "other-outcome",
        ),
        (
            (
                {"stage": "dispatch-id", "work_item_id": _ITEM_ID},
                {"stage": "stranded-claim-release", "work_item_id": _ITEM_ID},
                {"stage": "dispatch-id", "work_item_id": _ITEM_ID},
            ),
            "absent-run-release",
        ),
    ],
)
def test_the_predecessor_reading_is_about_the_preceding_dispatch(
    *,
    records: tuple[dict[str, object], ...] | None,
    expected: str,
) -> None:
    module = _module()

    assert module.observe_predecessor_history(records=records, work_item_id=_ITEM_ID) == expected


def test_a_release_outside_the_preceding_segment_is_not_the_predecessors_ending() -> None:
    """A lifetime count would disagree, and the clause says PRECEDING."""
    module = _module()
    records = (
        {"stage": "dispatch-id", "work_item_id": _ITEM_ID},
        {"stage": "stranded-claim-release", "work_item_id": _ITEM_ID},
        {"stage": "dispatch-id", "work_item_id": _ITEM_ID},
        {"stage": "outcome", "work_item_id": _ITEM_ID},
        {"stage": "dispatch-id", "work_item_id": _ITEM_ID},
    )

    # The release sits two dispatches back, so the PRECEDING dispatch ended some
    # other way and the next absent run earns a release rather than a rest.
    assert module.observe_predecessor_history(records=records, work_item_id=_ITEM_ID) == (
        "other-outcome"
    )
