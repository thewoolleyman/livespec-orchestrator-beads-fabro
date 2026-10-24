"""The gate's three did-not-run arms a healthy tenant never reaches.

CONTROLS for `test_spec_change_tier_gate.py` rather than claims of their own:
every arm here is already implemented, so none of them could have failed before
the gate landed, and they are what WOULD fail if a later edit collapsed the four
did-not-run causes into one shared "unavailable". That collapse is the easy
simplification and the expensive one — the record is what an operator reads to
find out why an item carries no tier, and the four causes send them to four
different places: a model answering outside its own vocabulary, a model whose
verdict will not parse, a spec tree nobody could read, and a ledger nobody could
read.

THE UNREADABLE-VERDICT ARM IS THE ONE THE SIBLING MODULE CANNOT REACH, because
its judge fixture answers in turn and the arms it exercises all return before the
judgement is taken. Here the classification succeeds as a `feature` — which is
the only class that owes a judgement at all — and the judge then answers
something the shared parser refuses.

THE UNREADABLE-LEDGER ARM RECORDS NOTHING, which is asserted as the ABSENCE of a
write: the comments are both where a reusable classification is read from and
where the once-per-cause cap is read from, so a classification taken without
them would re-comment on every pass, and the write that would say so is the one
that cannot be deduplicated.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import _spec_change_tier_gate as gate
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    decide_spec_change_tier,
    exempt_decision,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_gate import (
    CAUSE_LEDGER_UNREADABLE,
    CAUSE_VERDICT_UNREADABLE,
    classify_item_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_FILING,
    classification_did_not_run_comment,
    recorded_did_not_run_causes,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.spec_stated import SpecStatedVerdict

_ITEM = "bd-ib-arms"
_HEADING = "## A governing clause"


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


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    (spec / "history" / "v001").mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nThe clause body.\n", encoding="utf-8"
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="bug",
        status="backlog",
        title="Hold an unstated feature for its proposal",
        description="New observable behaviour.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _install_judge(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replies: tuple[str, ...]
) -> None:
    script = tmp_path / "fake-judge"
    ledger = tmp_path / "judge-calls"
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


def _comments(*, repo: Path) -> tuple[str, ...]:
    return tuple(
        comment.text
        for comment in read_work_item_comments(path=_config(repo=repo), work_item_id=_ITEM)
    )


def test_an_unreadable_verdict_records_its_own_cause_and_no_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, replies=("feature", "not a verdict"))
    append_work_item(path=_config(repo=repo), item=_item())

    outcome = classify_item_spec_change_tier(
        item=_item(), repo=repo, path=_config(repo=repo), stage=STAGE_FILING
    )
    assert outcome.recorded is None
    assert outcome.cause == CAUSE_VERDICT_UNREADABLE
    assert CAUSE_VERDICT_UNREADABLE in _comments(repo=repo)[0]


def test_an_unreadable_ledger_records_nothing_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(repo=repo), item=_item())
    monkeypatch.setattr(gate, "item_comment_bodies", lambda **_kwargs: None)

    outcome = classify_item_spec_change_tier(
        item=_item(), repo=repo, path=_config(repo=repo), stage=STAGE_FILING
    )
    assert outcome.recorded is None
    assert outcome.cause == CAUSE_LEDGER_UNREADABLE
    assert _comments(repo=repo) == ()


def test_the_cause_scan_stops_at_the_last_taken_classification() -> None:
    taken = spec_change_tier_comment(
        item_id=_ITEM,
        stage=STAGE_FILING,
        decision=decide_spec_change_tier(
            item=_item(),
            classification="feature",
            verdict=SpecStatedVerdict(
                kind="unstated",
                stated_by=(),
                generalization_target=_HEADING,
                rationale="not stated",
            ),
        ),
        spec_version="1",
        digest="a-digest",
    )

    def _unavailable(*, cause: str) -> str:
        return classification_did_not_run_comment(
            item_id=_ITEM,
            stage=STAGE_FILING,
            spec_version="1",
            digest="a-digest",
            cause=cause,
        )

    # An outage recorded BEFORE a classification that then ran is an outage that
    # classification disproves, so it must not suppress a fresh occurrence.
    assert recorded_did_not_run_causes(
        comments=(_unavailable(cause="an-older-outage"), taken, _unavailable(cause="a-fresh-one"))
    ) == frozenset({"a-fresh-one"})


def test_an_exempt_decision_records_that_no_judgement_was_taken() -> None:
    body = spec_change_tier_comment(
        item_id=_ITEM,
        stage=STAGE_FILING,
        decision=exempt_decision(classification="chore"),
        spec_version="1",
        digest="a-digest",
    )
    assert "verdict-kind: (not taken)" in body
    assert "rationale: (not taken)" in body
    # `(none)` marks a field a TAKEN judgement left empty, so the two markers
    # must stay distinguishable: one says nobody asked, the other says the
    # answer named no clause.
    assert "generalization-target: (none)" in body


def test_the_did_not_run_record_keeps_its_write_inputs_in_one_context() -> None:
    """The recorder takes one cohesive record context, not a suppressed arg list."""
    assert hasattr(gate, "_DidNotRunContext")
