"""Integration-tier acceptance for Scenario 206 — the hold, and its release.

Binds `SPECIFICATION/scenarios.md` "Scenario 206": an unstated feature is held
and the wall refuses it, a bug is routed as today, and ratification releases the
hold with no human valve — to `ready` under `auto` admission and to
`pending-approval` under `manual`.

THE REAL SURFACES ARE DRIVEN. `apply_intake_dor` is the filing-time route every
capture front-end takes, and `pre_dispatch_wall_exit` is what both dispatch
paths call before `admit_and_select` — so a refusal returning from it is one
that moved no item `ready -> active` and created no run. Neither is stood in
for, because the assertions are about where the item COMES TO REST and what the
dispatch did NOT do.

THE JUDGE IS STOOD IN AT THE EXECUTABLE, as every other judgement-driving module
here stands it in, so the argv, the standard-input prompt and the exit-code
mapping are exercised rather than mocked.

RATIFICATION IS PERFORMED THE WAY A REVISE PERFORMS IT: a new `history/vNNN/`
directory carrying the topic's proposal and its `decision: accept` revision
record. That single act does two things the release depends on, and the test
would pass against a weaker build if it did only one — it makes the topic
ratified, AND it bumps the specification version, which is what retires the
recorded classification so the judgement is re-taken against the ratified tree.

THE `manual` CASE IS NOT A SECOND SPELLING OF THE `auto` ONE. The clause
requires the release to remove the SPEC hold only and to leave the item's own
admission policy in force, so the two cases must come to rest in different
places from the same release — `ready` and `pending-approval`. A build that
treated release as "route to ready" passes the `auto` case and auto-approves a
manual item, which is exactly what Scenario 10 forbids.
"""

from __future__ import annotations

import argparse
import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import _dispatcher_pre_dispatch_wall as wall
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_UNGRADEABLE_CRITERIA,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.unsafe import unsafe_perform_io

_ITEM = "bd-ib-206"
_HEADING = "## A governing clause"
_TOPIC = "a-new-observable-behaviour"
_TITLE = "A new observable behaviour"
_UNSTATED = (
    '{"kind": "unstated", "stated_by": [], "generalization_target": '
    f'"{_HEADING}", "rationale": "the ratified text does not state it"}}'
)
_STATED = (
    f'{{"kind": "stated", "stated_by": ["{_HEADING}"], '
    '"generalization_target": null, "rationale": "the clause states it"}'
)
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
    (spec / "history" / "v001" / "proposed_changes").mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"},'
        ' "dispatcher": {"auto_approve_ready": true}}}',
        encoding="utf-8",
    )
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nThe clause body.\n", encoding="utf-8"
    )
    return repo


def _ratify(*, repo: Path) -> None:
    """Ratify the topic exactly as a revise does: a new version carrying it.

    One act, two effects the release depends on — the topic becomes ratified AND
    the specification version moves, which retires the classification that held
    the item so the judgement is re-taken against the ratified tree.
    """
    changes = repo / "SPECIFICATION" / "history" / "v002" / "proposed_changes"
    changes.mkdir(parents=True, exist_ok=True)
    _ = (changes / f"{_TOPIC}.md").write_text("the proposal\n", encoding="utf-8")
    _ = (changes / f"{_TOPIC}-revision.md").write_text(
        f"---\nproposal: {_TOPIC}.md\ndecision: accept\n---\n", encoding="utf-8"
    )


def _item(**overrides: object) -> WorkItem:
    base: dict[str, object] = {
        "id": _ITEM,
        # STORED as a bug while the classifier calls it a feature: the measured
        # population this plan exists for, where 22 of 29 actionable ungoverned
        # items were typed `bug`.
        "type": "bug",
        "status": "pending-approval",
        "title": _TITLE,
        "description": (
            "## Definition of Done\n\n- The slice lands its change.\n\n" f"References: {_HEADING}\n"
        ),
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
        "acceptance_policy": "ai-only",
    }
    base.update(overrides)
    return WorkItem(**base)  # pyright: ignore[reportArgumentType]


def _install_judge(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replies: tuple[str, ...]
) -> None:
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
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_DISABLED", "")


def _checklist() -> DefinitionOfReadyChecklist:
    return DefinitionOfReadyChecklist(
        single_coherent_done=True,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    )


def _route(*, repo: Path) -> str:
    return unsafe_perform_io(
        apply_intake_dor(path=_config(repo=repo), item_id=_ITEM, checklist=_checklist()).unwrap()
    )


def _stored(*, repo: Path) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config(repo=repo)))[_ITEM]


def _comments(*, repo: Path) -> tuple[str, ...]:
    return tuple(
        comment.text
        for comment in read_work_item_comments(path=_config(repo=repo), work_item_id=_ITEM)
    )


def _run_wall(*, repo: Path, tmp_path: Path) -> int | None:
    return wall.pre_dispatch_wall_exit(
        args=argparse.Namespace(workflow_name=None, workflow=None, items=[]),
        repo=repo,
        items=[_stored(repo=repo)],
        journal=JournalFile(path=tmp_path / "journal.jsonl", identity="role:test"),
    )


def test_scenario206_an_unstated_feature_is_held_and_the_wall_refuses_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        replies=("feature", _UNSTATED, "feature", _UNSTATED),
    )
    append_work_item(path=_config(repo=repo), item=_item())
    _stand_down_earlier_rows(monkeypatch=monkeypatch)

    # The verdict, the generalization target and the topic are recorded ON the
    # item, and the item is NOT routed to ready.
    assert _route(repo=repo) == "pending-approval"
    assert _stored(repo=repo).status == "pending-approval"
    recorded = "\n".join(_comments(repo=repo))
    assert "verdict-kind: unstated" in recorded
    assert f"generalization-target: {_HEADING}" in recorded
    assert f"linked-proposal-topic: {_TOPIC}" in recorded

    assert _run_wall(repo=repo, tmp_path=tmp_path) == EXIT_UNGRADEABLE_CRITERIA


def test_scenario206_ratification_releases_the_hold_to_ready_with_no_human_valve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        replies=("feature", _UNSTATED, "feature", _STATED),
    )
    append_work_item(path=_config(repo=repo), item=_item())
    assert _route(repo=repo) == "pending-approval"

    _ratify(repo=repo)
    # The NEXT intake pass releases it. No approve valve was turned.
    assert _route(repo=repo) == "ready"
    assert _stored(repo=repo).status == "ready"
    assert "tier: none" in "\n".join(_comments(repo=repo))


def test_scenario206_a_released_manual_item_rests_at_pending_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        replies=("feature", _UNSTATED, "feature", _STATED),
    )
    append_work_item(path=_config(repo=repo), item=_item(admission_policy="manual"))
    assert _route(repo=repo) == "pending-approval"

    _ratify(repo=repo)
    # The spec hold is gone — the record says so — and the item's OWN manual
    # admission policy is what now rests it for the approve valve.
    assert _route(repo=repo) == "pending-approval"
    assert "tier: none" in "\n".join(_comments(repo=repo))


@pytest.mark.parametrize("classification", ["bug", "chore", "non_functional"])
def test_scenario206_an_exempt_classification_is_routed_through_intake_exactly_as_today(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, classification: str
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, replies=(classification,))
    append_work_item(path=_config(repo=repo), item=_item())
    _stand_down_earlier_rows(monkeypatch=monkeypatch)

    assert _route(repo=repo) == "ready"
    assert _run_wall(repo=repo, tmp_path=tmp_path) is None
    assert "tier: none" in "\n".join(_comments(repo=repo))


def _stand_down_earlier_rows(*, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _EARLIER_WALL_ROWS:
        monkeypatch.setattr(wall, name, lambda **_kwargs: None)
