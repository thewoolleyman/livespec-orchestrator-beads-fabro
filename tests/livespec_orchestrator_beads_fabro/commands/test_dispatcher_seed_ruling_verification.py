"""Origin verification of coordinator seed instructions."""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import (
    SeedRuling,
    record_verified_seed_ruling,
    verify_seed_ruling,
)

_REF = "refs/heads/needs-human/ruled"
_SHA = "a" * 40


class _Runner:
    """A complete origin answer seam that also exposes the requested argv."""

    def __init__(self, *, stdout: str) -> None:
        self.stdout = stdout
        self.argv: list[str] | None = None

    def run(self, **kwargs: object) -> CommandResult:
        argv = kwargs["argv"]
        assert isinstance(argv, list)
        self.argv = argv
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


def _ruling() -> SeedRuling:
    return SeedRuling(
        work_item_id="bd-ib-ltlg4i",
        preservation_ref=_REF,
        commit_sha=_SHA,
        invoker="coordinator",
        reason="retain the checked tree",
        instant="2026-11-07T22:00:00Z",
    )


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        ("", "absent"),
        (f"{'b' * 40}\t{_REF}\n", "b" * 40),
        (f"{_SHA}\trefs/heads/needs-human/other\n", "absent"),
    ],
)
def test_an_absent_or_moved_ruling_ref_names_the_expected_and_observed_commits(
    *, stdout: str, expected: str
) -> None:
    """No fallback can mistake an invalid ruling for permission to seed elsewhere."""
    runner = _Runner(stdout=stdout)

    detail = verify_seed_ruling(runner=runner, repo=Path("/repo"), ruling=_ruling())

    assert detail == f"ruled seed ref {_REF} expected {_SHA} but origin observed {expected}"
    assert runner.argv == ["git", "ls-remote", "origin", _REF]


@pytest.mark.parametrize(
    ("verified_commit", "reason", "expected"),
    [
        ("", "retain the checked tree", "origin observed absent"),
        ("b" * 40, "retain the checked tree", f"origin observed {'b' * 40}"),
        (_SHA, "{{ disallowed }}", "template opener present: {{"),
    ],
)
def test_a_refusal_writes_neither_the_ledger_comment_nor_the_journal_record(
    *, verified_commit: str, reason: str, expected: str
) -> None:
    """Both preconditions refuse before either durable output is written."""
    written_comments: list[str] = []
    journaled: list[dict[str, object]] = []
    ruling = SeedRuling(
        work_item_id="bd-ib-ltlg4i",
        preservation_ref=_REF,
        commit_sha=_SHA,
        invoker="coordinator",
        reason=reason,
        instant="2026-11-07T22:00:00Z",
    )

    refusal = record_verified_seed_ruling(
        ruling=ruling,
        verified_commit=verified_commit,
        append_comment=written_comments.append,
        append_journal=journaled.append,
    )

    assert refusal is not None
    assert expected in refusal
    assert written_comments == []
    assert journaled == []
