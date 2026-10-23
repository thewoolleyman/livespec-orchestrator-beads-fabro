"""The classification runs once per cadence point, and says so when it cannot run.

Assertion 7 of `bd-ib-57ss2n`: "When the classification cannot run, the item is
routed as it is today and the did-not-run cause is recorded on the item." It
also carries the SPEND half of assertion 1's cadence: the classification is
taken at a cadence point and REUSED while nothing about the item or the
specification has changed, which is what makes "on each dispatch path" a read
rather than two model calls per ready item per pass.

THE JUDGE IS STOOD IN AT THE EXECUTABLE, as the Definition-of-Done judgement's
own tests stand theirs in, so the argv, the standard-input prompt and the
exit-code mapping are all exercised rather than mocked away.

EVERY CASE READS THE JUDGE CALL COUNT, because that is the one observation a
return value cannot carry. A gate that re-took the classification on every pass
returns the identical answer, so an assertion on the answer alone is satisfied by
the build whose cost the reuse rule exists to avoid.

THE `bug` CASE IS WHERE THE TWO CALLS SEPARATE. Three of the four classes are
exempt outright, so a `bug` must pay for the classification and NOT for the
judgement — one call, not two. A gate that judged first, or judged regardless,
returns the same tier and spends twice.

AN UNAVAILABLE CLASSIFIER RECORDS NO TIER AT ALL, which is deliberately not a
`none` tier: `none` reads as a classification that ran and found the item free,
and the hold read would treat that as a release. The absence is what the
did-not-run record makes legible.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import _spec_change_tier_record as record
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_gate import (
    CAUSE_CLASSIFICATION_UNREADABLE,
    CAUSE_SPEC_TREE_UNREADABLE,
    classify_item_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_DISPATCH,
    STAGE_FILING,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM = "bd-ib-gate"
_HEADING = "## A governing clause"
# Spelled as a LITERAL and bound to the exported name by the assertion below,
# because this module's Red predates the constant and a Red's test bytes are
# fixed across its Red-to-Green pair.
_UNAVAILABLE_MARKER = "livespec-spec-change-tier-unavailable"
_UNSTATED = (
    '{"kind": "unstated", "stated_by": [], "generalization_target": '
    f'"{_HEADING}", "rationale": "the ratified text does not state it"}}'
)


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _repo(*, tmp_path: Path, with_spec: bool = True) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    if with_spec:
        spec = repo / "SPECIFICATION"
        (spec / "history" / "v001").mkdir(parents=True, exist_ok=True)
        _ = (spec / "contracts.md").write_text(
            f"# Contracts\n\n{_HEADING}\n\nThe clause body.\n", encoding="utf-8"
        )
    return repo


def _item(**overrides: object) -> WorkItem:
    base: dict[str, object] = {
        "id": _ITEM,
        "type": "bug",
        "status": "backlog",
        "title": "Hold an unstated feature for its proposal",
        "description": "New observable behaviour.",
        "origin": "freeform",
        "gap_id": None,
        "rank": "a0",
        "assignee": None,
        "depends_on": (),
        "captured_at": "2026-10-15T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
    }
    base.update(overrides)
    return WorkItem(**base)  # pyright: ignore[reportArgumentType]


def _install_judge(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replies: tuple[str, ...]
) -> Path:
    """A real judge executable answering in turn, and recording every call."""
    ledger = tmp_path / "judge-calls"
    script = tmp_path / "fake-judge"
    arms = "\n".join(
        f"{index})\n  cat <<'REPLY'\n{reply}\nREPLY\n  ;;"
        for index, reply in enumerate(replies, start=1)
    )
    _ = script.write_text(
        "#!/bin/sh\n"
        f"echo call >> {ledger}\n"
        f"calls=$(wc -l < {ledger} | tr -d ' ')\n"
        "case $calls in\n"
        f"{arms}\n"
        "*)\n  exit 1\n  ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))
    return ledger


def _calls(*, ledger: Path) -> int:
    return len(ledger.read_text(encoding="utf-8").splitlines()) if ledger.is_file() else 0


def _comments(*, repo: Path) -> tuple[str, ...]:
    return tuple(
        comment.text
        for comment in read_work_item_comments(path=_config(repo=repo), work_item_id=_ITEM)
    )


def test_an_unstated_feature_is_classified_once_and_reused_on_the_next_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    ledger = _install_judge(
        tmp_path=tmp_path, monkeypatch=monkeypatch, replies=("feature", _UNSTATED)
    )
    append_work_item(path=_config(repo=repo), item=_item())

    first = classify_item_spec_change_tier(
        item=_item(), repo=repo, path=_config(repo=repo), stage=STAGE_FILING
    )
    assert first.is_spec_change is True
    assert first.reused is False
    assert first.recorded is not None
    assert first.recorded.verdict_kind == "unstated"
    assert first.recorded.generalization_target == _HEADING
    assert first.recorded.linked_proposal_topic == "hold-an-unstated-feature-for"
    assert _calls(ledger=ledger) == 2

    second = classify_item_spec_change_tier(
        item=_item(), repo=repo, path=_config(repo=repo), stage=STAGE_DISPATCH
    )
    assert second.is_spec_change is True
    assert second.reused is True
    # The second cadence point spent NOTHING, which is what makes "on every
    # dispatch path" a ledger read rather than two model calls per pass.
    assert _calls(ledger=ledger) == 2
    assert len(_comments(repo=repo)) == 1


def test_a_bug_pays_for_the_classification_and_not_for_the_judgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    ledger = _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, replies=("bug",))
    append_work_item(path=_config(repo=repo), item=_item())

    outcome = classify_item_spec_change_tier(
        item=_item(), repo=repo, path=_config(repo=repo), stage=STAGE_FILING
    )
    assert outcome.is_spec_change is False
    assert outcome.recorded is not None
    assert outcome.recorded.classification == "bug"
    assert outcome.recorded.linked_proposal_topic is None
    assert _calls(ledger=ledger) == 1


def test_an_edited_item_is_re_classified_rather_than_reusing_the_old_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    ledger = _install_judge(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        replies=("feature", _UNSTATED, "bug"),
    )
    append_work_item(path=_config(repo=repo), item=_item())
    _ = classify_item_spec_change_tier(
        item=_item(), repo=repo, path=_config(repo=repo), stage=STAGE_FILING
    )
    assert _calls(ledger=ledger) == 2

    edited = classify_item_spec_change_tier(
        item=_item(acceptance_criteria="- A newly added assertion."),
        repo=repo,
        path=_config(repo=repo),
        stage=STAGE_DISPATCH,
    )
    assert edited.reused is False
    assert edited.is_spec_change is False
    assert _calls(ledger=ledger) == 3


def test_an_unreadable_classification_records_the_cause_once_and_no_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    ledger = _install_judge(
        tmp_path=tmp_path, monkeypatch=monkeypatch, replies=("not-a-class", "not-a-class")
    )
    append_work_item(path=_config(repo=repo), item=_item())

    first = classify_item_spec_change_tier(
        item=_item(), repo=repo, path=_config(repo=repo), stage=STAGE_FILING
    )
    assert first.recorded is None
    assert first.is_spec_change is False
    assert first.cause == CAUSE_CLASSIFICATION_UNREADABLE
    assert record.SPEC_CHANGE_TIER_UNAVAILABLE_MARKER == _UNAVAILABLE_MARKER
    bodies = _comments(repo=repo)
    assert len(bodies) == 1
    assert bodies[0].startswith(_UNAVAILABLE_MARKER)
    assert CAUSE_CLASSIFICATION_UNREADABLE in bodies[0]

    second = classify_item_spec_change_tier(
        item=_item(), repo=repo, path=_config(repo=repo), stage=STAGE_DISPATCH
    )
    assert second.cause == CAUSE_CLASSIFICATION_UNREADABLE
    # The cap is per distinct CAUSE, so a second pass under the same outage
    # writes nothing: a comment per item per pass buries the item's history.
    assert len(_comments(repo=repo)) == 1
    assert _calls(ledger=ledger) == 2


def test_an_unreadable_spec_tree_records_its_own_cause_and_spends_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, with_spec=False)
    ledger = _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, replies=("feature",))
    append_work_item(path=_config(repo=repo), item=_item())

    outcome = classify_item_spec_change_tier(
        item=_item(), repo=repo, path=_config(repo=repo), stage=STAGE_FILING
    )
    assert outcome.recorded is None
    assert outcome.cause == CAUSE_SPEC_TREE_UNREADABLE
    assert CAUSE_SPEC_TREE_UNREADABLE in _comments(repo=repo)[0]
    assert _calls(ledger=ledger) == 0
