"""A recovery routing pass lists the needs-human refs once and records every one it passes over.

`SPECIFICATION/contracts.md`, in its recovery-from-preserved-work clause: "The
identification MUST be taken once per routing pass." Two items released for recovery in one pass are routed from the
same origin listing, so the listing is the pass's and not the item's — a second
`git ls-remote` per released item spends an origin round trip on a question the
first already answered, and each one is a read that can disagree with the other.

THE SUBPROCESS SEAM IS PATCHED ON THE CLASS, because the pass builds its own
`ShellCommandRunner`; patching `run` there covers it without this file knowing
which module constructs it. An unscripted argv FAILS rather than answering: a
default answer could not tell a pass that took the scripted measurements from one
that took some other measurement and got a blank reply.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_launch import (
    journal_recovery_route,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routing import (
    route_recovery,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_FIRST_ID = "bd-ib-aaaaaa"
_FIRST_RUN = "01M509HNX5KGKSRV04VQEYVWH6"
_FIRST_DISPATCH = "a7395318d0c945589105940e7936139f"
_FIRST_COMMIT = "1" * 40
_SECOND_ID = "bd-ib-bbbbbb"
_SECOND_RUN = "01M509HNX5KGKSRV04VQEYVWH7"
_SECOND_DISPATCH = "b7395318d0c945589105940e7936139f"
_SECOND_COMMIT = "2" * 40
_HEAD = "f3f139b28469c7efaae32dcb897d73518edbaadd"


class _Shell:
    """A scripted subprocess seam keyed by argv substring; unscripted argv fails."""

    answers: ClassVar[dict[str, CommandResult]] = {}
    calls: ClassVar[list[str]] = []

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
        joined = " ".join(argv)
        _Shell.calls.append(joined)
        for needle, result in _Shell.answers.items():
            if needle in joined:
                return result
        message = f"unscripted command reached the shell seam: {joined}"
        raise AssertionError(message)


def _arm(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Origin carries one needs-human ref per item, each named under its own run."""
    listing = (
        f"{_FIRST_COMMIT}\trefs/heads/needs-human/{_FIRST_RUN}\n"
        f"{_SECOND_COMMIT}\trefs/heads/needs-human/{_SECOND_RUN}\n"
    )
    _Shell.answers = {
        "gh pr list --head": CommandResult(exit_code=0, stdout="[]", stderr=""),
        "ls-remote origin refs/heads/needs-human/": CommandResult(
            exit_code=0, stdout=listing, stderr=""
        ),
        "ps -a --json": CommandResult(exit_code=0, stdout="[]", stderr=""),
        "ls-remote origin refs/heads/feat/": CommandResult(exit_code=0, stdout="", stderr=""),
        "^{tree}": CommandResult(exit_code=0, stdout=f"{'3' * 40}\n", stderr=""),
    }
    _Shell.calls = []
    monkeypatch.setattr(ShellCommandRunner, "run", _Shell.run)


def _work_item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="A released item whose resume has no anchor",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-17T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _journal(*, tmp_path: Path) -> JournalFile:
    """A journal whose newest dispatch of each item ended in a first-stall release."""
    journal = JournalFile(path=tmp_path / "fabro-dispatch-journal.jsonl")
    records: list[dict[str, object]] = []
    for item_id, run, dispatch in (
        (_FIRST_ID, _FIRST_RUN, _FIRST_DISPATCH),
        (_SECOND_ID, _SECOND_RUN, _SECOND_DISPATCH),
    ):
        records.extend(
            (
                {
                    "stage": "dispatch-id",
                    "work_item_id": item_id,
                    "dispatch_id": dispatch,
                    "workflow_name": "implement-work-item",
                },
                {"stage": "fabro-run", "work_item_id": item_id, "run_id": run},
                {
                    "stage": "watchdog-stall-cancel",
                    "work_item_id": item_id,
                    "dispatch_id": dispatch,
                    "run_id": run,
                    "factory": "hp",
                    "executing_stage": "proof_capture",
                    "published_head": _HEAD,
                },
                {"stage": "stall-cancel-release", "work_item_id": item_id, "status": "ready"},
            )
        )
    _ = journal.path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8"
    )
    return journal


def _args(*, repo: Path, journal: JournalFile) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(journal.path),
        item=None,
        items=None,
        budget=2,
        parallel=1,
        as_json=False,
        dry_run=False,
        skip_ledger_check=True,
        workflow_name=None,
        fabro_bin="/usr/local/bin/fabro",
    )


def test_two_released_items_in_one_pass_share_one_needs_human_listing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both items are seeded from their own ref, off a single origin listing."""
    _arm(monkeypatch=monkeypatch)
    journal = _journal(tmp_path=tmp_path)
    candidates: Sequence[WorkItem] = [
        _work_item(item_id=_FIRST_ID),
        _work_item(item_id=_SECOND_ID),
    ]

    routing = route_recovery(
        args=_args(repo=tmp_path, journal=journal),
        repo=tmp_path,
        candidates=list(candidates),
        journal=journal,
    )

    seeds = {
        item_id: routing.route_for(work_item_id=item_id) for item_id in (_FIRST_ID, _SECOND_ID)
    }
    assert [(one.route, one.seed.commit_sha) for one in seeds.values() if one and one.seed] == [
        ("seeded", _FIRST_COMMIT),
        ("seeded", _SECOND_COMMIT),
    ]
    listings = [call for call in _Shell.calls if "ls-remote origin refs/heads/needs-human/" in call]
    assert len(listings) == 1


def test_the_shell_seam_refuses_a_command_no_case_scripted() -> None:
    """The instrument's own control: an unscripted argv fails instead of answering."""
    _Shell.answers = {}
    _Shell.calls = []

    with pytest.raises(AssertionError, match="unscripted command"):
        _ = _Shell().run(
            argv=["git", "ls-remote", "origin", "refs/heads/x"],
            cwd=Path("/repo"),
            timeout_seconds=1.0,
        )


# The resume world: the item's first stall cancel anchors a resume at `proof_capture` on
# the head the dead run published, and the forge still names that pull request open.
_RESUME_ID = "bd-ib-cccccc"
_RESUME_RUN = "01M509HNX5KGKSRV04VQEYVWH8"
_RESUME_DISPATCH = "c7395318d0c945589105940e7936139f"
_RESUME_PR = 3001
_RESUME_OWN_COMMIT = "4" * 40
_RESUME_ALIAS_COMMIT = "5" * 40
_RESUME_OTHER_COMMIT = "6" * 40


def _arm_resume(*, monkeypatch: pytest.MonkeyPatch, listing: CommandResult) -> None:
    """Origin names the pull request open at the cancel's head and answers `listing`."""
    _Shell.answers = {
        f"gh pr list --head feat/{_RESUME_ID}": CommandResult(
            exit_code=0,
            stdout=json.dumps([{"number": _RESUME_PR, "state": "OPEN", "headRefOid": _HEAD}]),
            stderr="",
        ),
        f"gh pr view {_RESUME_PR} --json comments": CommandResult(
            exit_code=0, stdout=json.dumps({"comments": []}), stderr=""
        ),
        "ps -a --json": CommandResult(exit_code=0, stdout="[]", stderr=""),
        f"ls-remote origin refs/heads/feat/{_RESUME_ID}": CommandResult(
            exit_code=0, stdout=f"{_HEAD}\trefs/heads/feat/{_RESUME_ID}\n", stderr=""
        ),
        "ls-remote origin refs/heads/needs-human/": listing,
        f"--format=%B {_RESUME_ALIAS_COMMIT}": CommandResult(
            exit_code=0, stdout=f"fix: saved\n\nFabro-Run: {_RESUME_RUN}\n", stderr=""
        ),
        f"--format=%B {_RESUME_OTHER_COMMIT}": CommandResult(
            exit_code=0, stdout="fix: saved\n\nFabro-Run: another-run\n", stderr=""
        ),
    }
    _Shell.calls = []
    monkeypatch.setattr(ShellCommandRunner, "run", _Shell.run)


def _resume_journal(*, tmp_path: Path) -> JournalFile:
    journal = JournalFile(path=tmp_path / "fabro-dispatch-journal.jsonl")
    records: Sequence[dict[str, object]] = (
        {
            "stage": "dispatch-id",
            "work_item_id": _RESUME_ID,
            "dispatch_id": _RESUME_DISPATCH,
            "workflow_name": "implement-work-item",
        },
        {"stage": "fabro-run", "work_item_id": _RESUME_ID, "run_id": _RESUME_RUN},
        {
            "stage": "watchdog-stall-cancel",
            "work_item_id": _RESUME_ID,
            "dispatch_id": _RESUME_DISPATCH,
            "run_id": _RESUME_RUN,
            "factory": "hp",
            "executing_stage": "proof_capture",
            "pull_request": _RESUME_PR,
            "published_head": _HEAD,
        },
        {"stage": "stall-cancel-release", "work_item_id": _RESUME_ID, "status": "ready"},
    )
    _ = journal.path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8"
    )
    return journal


def _route_resume(*, tmp_path: Path) -> tuple[Any, JournalFile]:
    journal = _resume_journal(tmp_path=tmp_path)
    routing = route_recovery(
        args=_args(repo=tmp_path, journal=journal),
        repo=tmp_path,
        candidates=[_work_item(item_id=_RESUME_ID)],
        journal=journal,
    )
    return routing.route_for(work_item_id=_RESUME_ID), journal


def _route_rows(journal: JournalFile, stage: str) -> list[dict[str, Any]]:
    written = (
        json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line
    )
    return [record for record in written if record.get("stage") == stage]


def test_a_resume_row_lists_every_needs_human_ref_that_carries_its_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is taken on a resume, so each ref carrying the run is passed over."""
    # The listing names the ref under the run, an alias carrying the run in its tip
    # trailer, and a third ref carrying ANOTHER run, which must not be listed.
    _arm_resume(
        monkeypatch=monkeypatch,
        listing=CommandResult(
            exit_code=0,
            stdout=(
                f"{_RESUME_OWN_COMMIT}\trefs/heads/needs-human/{_RESUME_RUN}\n"
                f"{_RESUME_ALIAS_COMMIT}\trefs/heads/needs-human/alias\n"
                f"{_RESUME_OTHER_COMMIT}\trefs/heads/needs-human/other-item\n"
            ),
            stderr="",
        ),
    )

    route, journal = _route_resume(tmp_path=tmp_path)
    journal_recovery_route(route=route, journal=journal)

    assert route.route == "resume"
    assert [row["passed_over_needs_human"] for row in _route_rows(journal, "recovery-route")] == [
        [
            {
                "ref": f"refs/heads/needs-human/{_RESUME_RUN}",
                "commit": _RESUME_OWN_COMMIT,
                "reason": "not-taken",
            },
            {
                "ref": "refs/heads/needs-human/alias",
                "commit": _RESUME_ALIAS_COMMIT,
                "reason": "not-taken",
            },
        ]
    ]


def test_a_resume_row_with_no_carrying_ref_lists_an_empty_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The field is present and empty, which says the listing was taken and held nothing."""
    _arm_resume(monkeypatch=monkeypatch, listing=CommandResult(exit_code=0, stdout="", stderr=""))

    route, journal = _route_resume(tmp_path=tmp_path)
    journal_recovery_route(route=route, journal=journal)

    assert route.route == "resume"
    assert [row["passed_over_needs_human"] for row in _route_rows(journal, "recovery-route")] == [
        []
    ]


def test_a_resume_whose_needs_human_listing_cannot_be_taken_is_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unanswered listing is a held measurement, never a resume recorded as having none."""
    _arm_resume(
        monkeypatch=monkeypatch, listing=CommandResult(exit_code=128, stdout="", stderr="no")
    )

    route, journal = _route_resume(tmp_path=tmp_path)

    assert route.route == "held"
    assert route.hold is not None
    assert [one.name for one in route.hold.measurements] == ["preserved-work"]
    assert len(_route_rows(journal, "recovery-held")) == 1
