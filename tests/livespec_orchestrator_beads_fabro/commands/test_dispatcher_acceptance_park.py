"""Tests for the park disposition's ledger write and its three outcomes.

The park's ordinary path through a real dispatch is bound in
`tests/integration/test_acceptance_parking_record_scenario138.py`, and the
RENDERING of the record it writes is covered beside it in
`test_dispatcher_acceptance_parking_record.py`. What THIS module owns is the
write itself: the append, the unchanged re-run that appends nothing, and the two
ways the comment sidecar can be unavailable.

NOTHING HERE MAY RAISE. The park has already happened and the item's work has
already merged by the time this module runs, so each failure arm is asserted to
JOURNAL and return rather than to propagate: a parked item must never become a
crashed dispatch because its comment sidecar was unavailable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_acceptance_park
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    NEEDS_ATTENTION_VERDICT,
    TELEMETRY_LEG,
    AcceptancePassResult,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_criteria import (
    CriterionCheck,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_park import (
    PARKING_RECORD_STAGE,
    UNCHANGED_PARKING_RECORD_STAGE,
    record_acceptance_park,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    change_classification,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError

_ITEM_ID = "bd-ib-park"


def _result(
    *,
    verdict: str = NEEDS_ATTENTION_VERDICT,
    absent_evidence: tuple[str, ...] = (),
    criteria: tuple[CriterionCheck, ...] = (),
) -> AcceptancePassResult:
    return AcceptancePassResult(
        verdict=verdict,
        merged_diff="diff --git a/x b/x\n",
        diff_reason="merged diff read",
        telemetry_observed=True,
        telemetry_passed=True,
        telemetry_reason="green merged dispatch with PR and merge sha",
        criteria=criteria,
        absent_evidence=absent_evidence,
        classification=change_classification(),
    )


def _repo(*, tmp_path: Path) -> Path:
    """A repository whose `.livespec.jsonc` resolves a store connection.

    The write resolves the store from the repository, so a bare `tmp_path` refuses
    on the missing `connection.prefix` before either ledger arm is reached — and
    that refusal would be read as the fail-soft arm passing.
    """
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _records(*, journal: JournalFile) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in journal.path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_the_write_appends_once_and_an_unchanged_re_run_appends_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The idempotence rule, driven through the module's own write.

    The second call is given the IDENTICAL verdict and pending-leg set, which is
    the clause's "a re-run whose verdict and pending-leg set are unchanged appends
    nothing". It is asserted against the recorded BODIES rather than against a
    call count, because an append the module made and the ledger rejected would
    satisfy a call count just as well.
    """
    appended: list[str] = []
    monkeypatch.setattr(
        _dispatcher_acceptance_park,
        "read_work_item_comments",
        lambda **_: tuple(_Comment(text=one) for one in appended),
    )
    monkeypatch.setattr(
        _dispatcher_acceptance_park,
        "append_work_item_comment",
        lambda **kwargs: appended.append(str(kwargs["body"])),
    )
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    result = _result(absent_evidence=(TELEMETRY_LEG,))

    for _ in range(2):
        record_acceptance_park(
            repo=_repo(tmp_path=tmp_path),
            item_id=_ITEM_ID,
            policy="ai-only",
            result=result,
            pull_request=7,
            journal=journal,
        )

    assert len(appended) == 1
    stages = [one["stage"] for one in _records(journal=journal)]
    assert stages == [PARKING_RECORD_STAGE, UNCHANGED_PARKING_RECORD_STAGE]


@pytest.mark.parametrize("failing", ["read_work_item_comments", "append_work_item_comment"])
def test_an_unavailable_comment_sidecar_is_journaled_and_never_raises(
    failing: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both ledger arms fail soft, and each names the error class that stopped it."""

    def _boom(**_: object) -> object:
        raise BeadsCommandError(command="bd comments", exit_code=1, stderr="unavailable")

    monkeypatch.setattr(_dispatcher_acceptance_park, "read_work_item_comments", lambda **_: ())
    monkeypatch.setattr(_dispatcher_acceptance_park, "append_work_item_comment", lambda **_: None)
    monkeypatch.setattr(_dispatcher_acceptance_park, failing, _boom)
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    record_acceptance_park(
        repo=_repo(tmp_path=tmp_path),
        item_id=_ITEM_ID,
        policy="human-only",
        result=_result(verdict="FAIL"),
        pull_request=7,
        journal=journal,
    )

    recorded = _records(journal=journal)
    assert [one["stage"] for one in recorded] == ["acceptance-parking-record-error"]
    assert recorded[0]["work_item_id"] == _ITEM_ID
    assert recorded[0]["reason"] == "BeadsCommandError"


class _Comment:
    """The one field the idempotence test reads off a comment: its `text`.

    Named `text` rather than `body` deliberately: that is the key a beads comment
    record actually carries, and reaching for `body` yields an empty string per
    comment — an observation indistinguishable from a lost write.
    """

    def __init__(self, *, text: str) -> None:
        self.text = text
