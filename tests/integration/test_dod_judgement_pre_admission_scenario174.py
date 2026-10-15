"""Integration-tier acceptance for Scenario 174's pre-admission sub-scenarios.

Binds the three routing sub-scenarios of `SPECIFICATION/scenarios.md`
"Scenario 174" — an item the judgement would rest at needs-human is held out of
`ready`, an item it admits moves to `ready` as before, and a judgement that
cannot run does not hold the item — through the two surfaces the ratified clause
names as routing toward `ready`: intake (`apply_intake_dor`, which `groom` also
routes through) and the human `approve` valve.

THE JUDGE IS STOOD IN AT THE EXECUTABLE, NOT AT THE SEAM. The judgement reaches
the model through a subprocess, so an in-process double would leave the argv,
the prompt read and the exit-code mapping unexercised — and those are exactly
where a host-side judgement breaks. A real script on disk, named through the
documented path override, exercises the whole path and still never calls a
provider. The node's OWN `dod-gate.md` is read off the real payload, so the
prompt the judge receives here is the shipped one.

THE UNAVAILABLE CASE IS ASSERTED IN BOTH HALVES. "Routed as it would be without
the judgement" AND "a ledger comment records that it did not run and why": a
build that simply skipped the judgement satisfies the first on its own, and the
record is the only thing that distinguishes an unjudged item from a judged one.

Sibling module: `test_dod_judgement_pre_dispatch_scenario174.py` binds the same
scenario's dispatch-time sub-scenarios.
"""

from __future__ import annotations

import stat
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands.drive import run_action
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

_HEADING = "## Effective acceptance criteria"
_HELD_FINDING = "bd-ib-174: the References line omits the governing scenario; add that heading."
_HELD_REPLY = '{"outcome": "failed", "failure_reason": "' + _HELD_FINDING + '"}'
_PASS_REPLY = '{"outcome": "passed"}'


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


def _install_judge(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reply: str) -> None:
    """Name a real executable that answers as the judge would, through the override."""
    script = tmp_path / "fake-judge"
    _ = script.write_text(f"#!/bin/sh\ncat <<'REPLY'\n{reply}\nREPLY\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))


def _install_absent_judge(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(tmp_path / "no-such-judge"))


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-174",
        type="feature",
        status="pending-approval",
        title="A judged slice",
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


_CHECKLIST = DefinitionOfReadyChecklist(
    single_coherent_done=True,
    autonomously_verifiable=True,
    autonomy_tiered=True,
    dependency_linked=True,
    repo_targeted=True,
    above_floor=True,
)


def _stored(*, repo: Path) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config(repo=repo)))["bd-ib-174"]


def _comments(*, repo: Path) -> str:
    return "\n".join(
        comment.text
        for comment in read_work_item_comments(path=_config(repo=repo), work_item_id="bd-ib-174")
    )


def _route_intake(*, repo: Path) -> str:
    config = _config(repo=repo)
    append_work_item(path=config, item=_item())
    return str(
        unsafe_perform_io(
            apply_intake_dor(path=config, item_id="bd-ib-174", checklist=_CHECKLIST).unwrap()
        )
    )


def test_scenario174_intake_holds_an_item_the_judgement_rests_at_needs_human(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, reply=_HELD_REPLY)

    routed = _route_intake(repo=repo)

    assert routed != "ready"
    assert _stored(repo=repo).status != "ready"
    # The verdict, with its remedy, is on the item: a hold nobody can read is a
    # hold nobody can clear.
    assert _HELD_FINDING in _comments(repo=repo)


def test_scenario174_intake_admits_an_item_the_judgement_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, reply=_PASS_REPLY)

    routed = _route_intake(repo=repo)

    assert routed == "ready"
    assert _stored(repo=repo).status == "ready"


def test_scenario174_a_judgement_that_cannot_run_routes_the_item_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_absent_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)

    routed = _route_intake(repo=repo)

    assert routed == "ready"
    comments = _comments(repo=repo)
    assert "livespec-dod-judgement-unavailable" in comments
    assert "no-eligible-model" in comments


def test_scenario174_the_approve_valve_refuses_an_item_the_judgement_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, reply=_HELD_REPLY)
    append_work_item(path=_config(repo=repo), item=_item(admission_policy="manual"))

    result = run_action(repo=repo, action_id="approve:bd-ib-174")

    assert result["status"] != "green"
    assert _HELD_FINDING in str(result)
    assert _stored(repo=repo).status == "pending-approval"
    assert _HELD_FINDING in _comments(repo=repo)


def test_scenario174_the_approve_valve_admits_an_item_the_judgement_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, reply=_PASS_REPLY)
    append_work_item(path=_config(repo=repo), item=_item(admission_policy="manual"))

    result = run_action(repo=repo, action_id="approve:bd-ib-174")

    assert result["status"] == "green"
    assert _stored(repo=repo).status == "ready"
