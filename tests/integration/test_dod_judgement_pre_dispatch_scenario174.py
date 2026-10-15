"""Integration-tier acceptance for Scenario 174's dispatch-time sub-scenarios.

Binds the four dispatch-time sub-scenarios of `SPECIFICATION/scenarios.md`
"Scenario 174": an item that reached `ready` without admission is judged before
any claim, a judgement that cannot run does not refuse, a refused item is
neither judged nor commented again while it is unchanged, and it re-enters
enumeration once its criteria change.

THE WALL IS DRIVEN, NOT THE GATE. "Refused before any claim is taken and before
any factory run is created" is a claim about what did NOT happen, and a gate
returning a refusal string cannot show it: the wall is what both dispatch paths
call before `admit_and_select`, so a refusal returning from it is one that moved
no item `ready -> active` and created no run. The rows BEFORE this one are stood
down at the wall's own imported symbols — each is an independent precondition
with its own fixture needs (a factory block, a repository prerelease, a bounded
provider renewal), and none of them is what this scenario is about.

THE JUDGE IS STOOD IN AT THE EXECUTABLE, as in the pre-admission sibling, so the
argv, the shipped prompt read and the exit-code mapping are all exercised.

Sibling module: `test_dod_judgement_pre_admission_scenario174.py`.
"""

from __future__ import annotations

import argparse
import stat
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import _dispatcher_pre_dispatch_wall as wall
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_UNGRADEABLE_CRITERIA,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_wall import (
    dod_unrefused_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._needs_attention_definition_of_done import (
    held_definition_of_done_items,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_HEADING = "## Effective acceptance criteria"
_FINDING = "bd-ib-174: the References line omits the governing scenario; add that heading."
_HELD_REPLY = '{"outcome": "failed", "failure_reason": "' + _FINDING + '"}'
_EARLIER_WALL_ROWS = (
    "implementation_pr_override_refusal",
    "fabro_currency_refusal",
    "pre_dispatch_criteria_refusal",
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
    spec.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nThe criteria clause.\n", encoding="utf-8"
    )
    return repo


def _stand_down_earlier_rows(*, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _EARLIER_WALL_ROWS:
        monkeypatch.setattr(wall, name, lambda **_kwargs: None)


def _install_judge(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reply: str) -> list[Path]:
    """A real judge executable that also records every invocation it receives."""
    ledger = tmp_path / "judge-calls"
    script = tmp_path / "fake-judge"
    _ = script.write_text(
        f"#!/bin/sh\necho call >> {ledger}\ncat <<'REPLY'\n{reply}\nREPLY\n", encoding="utf-8"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))
    return [ledger]


def _judge_calls(*, ledger: Path) -> int:
    return len(ledger.read_text(encoding="utf-8").splitlines()) if ledger.is_file() else 0


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-174",
        type="feature",
        status="ready",
        title="A released slice",
        description=(
            "## Definition of Done\n"
            "\n"
            "- The dispatched slice lands its change.\n"
            "\n"
            f"References: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a2",
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
    return replace(base, **overrides)


def _args() -> argparse.Namespace:
    return argparse.Namespace(workflow_name=None, workflow=None, items=[])


def _stored(*, repo: Path) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config(repo=repo)))["bd-ib-174"]


def _comments(*, repo: Path) -> tuple[str, ...]:
    return tuple(
        comment.text
        for comment in read_work_item_comments(path=_config(repo=repo), work_item_id="bd-ib-174")
    )


def _run_wall(*, repo: Path, tmp_path: Path, item: WorkItem | None = None) -> int | None:
    return wall.pre_dispatch_wall_exit(
        args=_args(),
        repo=repo,
        items=[_item() if item is None else item],
        journal=JournalFile(path=tmp_path / "journal.jsonl", identity="role:test"),
    )


def test_scenario174_a_held_item_refuses_the_dispatch_before_any_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _stand_down_earlier_rows(monkeypatch=monkeypatch)
    _ = _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, reply=_HELD_REPLY)
    append_work_item(path=_config(repo=repo), item=_item())

    exit_code = _run_wall(repo=repo, tmp_path=tmp_path)

    # The dedicated code of "The pre-dispatch wall", not the generic
    # precondition code — the clause requires them to be DISTINCT.
    assert exit_code == EXIT_UNGRADEABLE_CRITERIA
    assert exit_code != 3
    # No claim: the wall returns before `admit_and_select`, so the row is
    # untouched and no assignee was set.
    stored = _stored(repo=repo)
    assert stored.status == "ready"
    assert stored.assignee is None
    assert any(_FINDING in body for body in _comments(repo=repo))


def test_scenario174_an_unchanged_refused_item_is_neither_rejudged_nor_recommented(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _stand_down_earlier_rows(monkeypatch=monkeypatch)
    (ledger,) = _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, reply=_HELD_REPLY)
    append_work_item(path=_config(repo=repo), item=_item())

    first = _run_wall(repo=repo, tmp_path=tmp_path)
    after_first = len(_comments(repo=repo))
    second = _run_wall(repo=repo, tmp_path=tmp_path)

    assert first == EXIT_UNGRADEABLE_CRITERIA
    # A reused refusing verdict still refuses, and spends nothing doing it.
    assert second == EXIT_UNGRADEABLE_CRITERIA
    assert len(_comments(repo=repo)) == after_first
    assert _judge_calls(ledger=ledger) == 1


def test_scenario174_a_refused_item_leaves_and_re_enters_drain_enumeration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _stand_down_earlier_rows(monkeypatch=monkeypatch)
    _ = _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, reply=_HELD_REPLY)
    item = _item()
    append_work_item(path=_config(repo=repo), item=item)
    # The control: before any verdict stands, the item IS a candidate, so the
    # exclusion below is evidence of the refusal rather than of an empty filter.
    assert dod_unrefused_candidates(items=[item], repo=repo) == [item]

    _ = _run_wall(repo=repo, tmp_path=tmp_path)

    assert dod_unrefused_candidates(items=[item], repo=repo) == []
    # Criteria that moved retire the verdict, so the item is enumerated again.
    edited = _item(
        description=(
            "## Definition of Done\n\n- The dispatched slice lands its change now.\n\n"
            f"References: {_HEADING}\n"
        )
    )
    assert dod_unrefused_candidates(items=[edited], repo=repo) == [edited]


def test_scenario174_a_held_item_is_named_by_needs_attention_with_its_first_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _stand_down_earlier_rows(monkeypatch=monkeypatch)
    _ = _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, reply=_HELD_REPLY)
    append_work_item(path=_config(repo=repo), item=_item())
    assert held_definition_of_done_items(project_root=repo, repo="repo", items=[_item()]) == []

    _ = _run_wall(repo=repo, tmp_path=tmp_path)

    facts = held_definition_of_done_items(project_root=repo, repo="repo", items=[_item()])
    assert len(facts) == 1
    assert "bd-ib-174" in facts[0].summary
    assert "add that heading." in facts[0].summary


def test_scenario174_a_judgement_that_cannot_run_does_not_refuse_the_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _stand_down_earlier_rows(monkeypatch=monkeypatch)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(tmp_path / "no-such-judge"))
    append_work_item(path=_config(repo=repo), item=_item())

    exit_code = _run_wall(repo=repo, tmp_path=tmp_path)

    assert exit_code is None
    comments = _comments(repo=repo)
    assert any("livespec-dod-judgement-unavailable" in body for body in comments)
    assert any("no-eligible-model" in body for body in comments)


def test_scenario174_an_empty_selection_spends_no_judgement_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _stand_down_earlier_rows(monkeypatch=monkeypatch)
    (ledger,) = _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, reply=_HELD_REPLY)

    exit_code = wall.pre_dispatch_wall_exit(
        args=_args(),
        repo=repo,
        items=[],
        journal=JournalFile(path=tmp_path / "journal.jsonl", identity="role:test"),
    )

    # The drain reaches this wall on every pass that finds no ready work, so an
    # idle pass must not spend a model call.
    assert exit_code is None
    assert _judge_calls(ledger=ledger) == 0
