"""A held spec-change-tier item refuses the dispatch with exit 5, naming its topic.

The second half of assertion 3 of `bd-ib-57ss2n`: "the pre-dispatch wall refuses
it with exit code 5 naming the unratified topic".

THE WALL IS DRIVEN, NOT THE ROW. "Refused with exit code 5" is a claim about the
code the whole wall returns, and a row returning a refusal string cannot show
it: the wall is what both dispatch paths call before `admit_and_select`, so a
refusal returning from it is one that moved no item `ready -> active` and created
no run. The rows BEFORE this one are stood down at the wall's own imported
symbols, exactly as `tests/integration/test_dod_judgement_pre_dispatch_scenario174.py`
stands them down and for the same reason: each is an independent precondition
with its own fixture needs, and none of them is what this assertion is about.

THE RATIFIED CASE IS THE CONTROL, and without it every assertion here is
satisfied by a wall that refuses every dispatch. It is built as a RELEASED
record — tier `none` — because that is what the release pass writes, and because
a ratified topic alone does NOT release the hold: the judgement has to be re-run,
which is the `awaiting-rejudgement` reason its own sibling module exercises.

THE DRAIN FILTER IS ASSERTED BESIDE THE ROW because the row alone would stop the
queue: a wave-level refusal refuses the WHOLE selection, so one held item at the
head of the ranking would refuse every dispatch behind it. The filter is read
over a selection carrying BOTH a held row and a free one, which is the only
shape that can fail for the right reason — a filter that dropped everything, and
one that dropped nothing, each satisfy a single-row fixture.
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands import _dispatcher_pre_dispatch_wall as wall
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_UNGRADEABLE_CRITERIA,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    decide_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_DISPATCH,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.spec_stated import SpecStatedVerdict

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_HELD_ITEM = "bd-ib-held"
_FREE_ITEM = "bd-ib-free"
_TOPIC = "hold-an-unstated-feature-for"
_TARGET = "## A governing clause"

# Every wall row that runs BEFORE this one. Each is an independent precondition
# with its own fixture needs, and none of them is what this module is about.
_EARLIER_WALL_ROWS = (
    "implementation_pr_override_refusal",
    "fabro_currency_refusal",
    "pre_dispatch_criteria_refusal",
    "dod_judgement_refusal",
    "definition_of_done_workflow_refusal",
    "proof_assets_refusal_for_items",
    "proof_credentials_refusal_for_items",
    "codex_credential_refusal_for_items",
)


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


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


def _repo(*, tmp_path: Path, ratified: bool) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    if ratified:
        changes = spec / "history" / "v001" / "proposed_changes"
        changes.mkdir(parents=True, exist_ok=True)
        _ = (changes / f"{_TOPIC}.md").write_text("the proposal\n", encoding="utf-8")
        _ = (changes / f"{_TOPIC}-revision.md").write_text(
            f"---\nproposal: {_TOPIC}.md\ndecision: accept\n---\n", encoding="utf-8"
        )
    return repo


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
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
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _record(*, repo: Path, item_id: str, kind: str) -> None:
    item = _item(item_id=item_id)
    append_work_item(path=_config(repo=repo), item=item)
    decision = decide_spec_change_tier(
        item=item,
        classification="feature",
        verdict=SpecStatedVerdict(
            kind=kind,  # pyright: ignore[reportArgumentType]
            stated_by=() if kind == "unstated" else (_TARGET,),
            generalization_target=_TARGET,
            rationale="the ratified text does not state the whole of it",
        ),
    )
    append_work_item_comment(
        path=_config(repo=repo),
        work_item_id=item_id,
        body=spec_change_tier_comment(
            item_id=item_id,
            stage=STAGE_DISPATCH,
            decision=decision,
            spec_version="1",
            digest="a-digest",
        ),
    )


def _stand_down_earlier_rows(*, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _EARLIER_WALL_ROWS:
        monkeypatch.setattr(wall, name, lambda **_kwargs: None)


def _run_wall(*, repo: Path, tmp_path: Path, item_ids: tuple[str, ...]) -> int | None:
    return wall.pre_dispatch_wall_exit(
        args=argparse.Namespace(workflow_name=None, workflow=None, items=[]),
        repo=repo,
        items=[_item(item_id=one) for one in item_ids],
        journal=JournalFile(path=tmp_path / "journal.jsonl", identity="role:test"),
    )


def test_the_wall_refuses_a_held_item_with_exit_five_naming_its_topic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path=tmp_path, ratified=False)
    _stand_down_earlier_rows(monkeypatch=monkeypatch)
    _record(repo=repo, item_id=_HELD_ITEM, kind="unstated")

    assert (
        _run_wall(repo=repo, tmp_path=tmp_path, item_ids=(_HELD_ITEM,)) == EXIT_UNGRADEABLE_CRITERIA
    )
    refusal = capsys.readouterr().err
    assert _TOPIC in refusal
    assert _HELD_ITEM in refusal
    assert "no claim was taken and no factory run was created" in refusal
    assert _TARGET in refusal


def test_a_released_record_lets_the_wall_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, ratified=True)
    _stand_down_earlier_rows(monkeypatch=monkeypatch)
    _record(repo=repo, item_id=_FREE_ITEM, kind="stated")

    assert _run_wall(repo=repo, tmp_path=tmp_path, item_ids=(_FREE_ITEM,)) is None


def test_the_drain_filter_drops_the_held_row_and_keeps_the_free_one(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, ratified=False)
    _record(repo=repo, item_id=_HELD_ITEM, kind="unstated")
    _record(repo=repo, item_id=_FREE_ITEM, kind="stated")

    kept = _module(name="_spec_change_tier_wall").spec_change_unrefused_candidates(
        items=[_item(item_id=_HELD_ITEM), _item(item_id=_FREE_ITEM)], repo=repo
    )
    assert [one.id for one in kept] == [_FREE_ITEM]


def test_an_unresolvable_connection_refuses_nothing_and_drops_nothing(
    tmp_path: Path,
) -> None:
    module = _module(name="_spec_change_tier_wall")
    bare = tmp_path / "bare"
    bare.mkdir()
    items = [_item(item_id=_HELD_ITEM)]

    assert module.spec_change_tier_refusal(repo=bare, items=items) is None
    assert module.spec_change_unrefused_candidates(items=items, repo=bare) == items
    # An EMPTY selection is answered before anything is read at all, which is
    # the common idle-drain case.
    assert module.spec_change_tier_refusal(repo=bare, items=[]) is None
    assert module.spec_change_unrefused_candidates(items=[], repo=bare) == []


def test_an_item_with_no_recorded_classification_is_not_held(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, ratified=False)
    append_work_item(path=_config(repo=repo), item=_item(item_id=_FREE_ITEM))
    module = _module(name="_spec_change_tier_wall")

    assert module.spec_change_tier_refusal(repo=repo, items=[_item(item_id=_FREE_ITEM)]) is None
