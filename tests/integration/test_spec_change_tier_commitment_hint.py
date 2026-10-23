"""A commitment hint is not the tier, and does not exempt unstated behaviour.

Assertion 5 of `bd-ib-57ss2n`: "An item carrying a ratified
`spec_commitment_hint` whose asked-for behaviour the judgement reports `stated`
is not held as spec-change tier, while a hint-carrying feature with unstated
behaviour is held." It is the absorbed work of `bd-ib-yykjko` — the inverted
predicate that read the tier off the hint — and the two cases are each other's
control in BOTH directions, which is what the clause demands: "An
implementation that gates disposition on the hint being non-null gates the
wrong set in both directions, and does not satisfy this clause."

THE TWO FIELDS ARE NEAR-OPPOSITES, which is the whole reason the inversion was
invisible. A non-null `spec_commitment_hint` marks an implementation FOLLOW-UP
to an ALREADY-RATIFIED change, so it is ordinary dispatchable work; the item
the tier must hold is one whose OWN proposal has not ratified, whether or not
it also carries a hint from an earlier one. A predicate keyed on the hint
therefore holds every ratified follow-up and releases every unratified feature,
and both answers look perfectly reasonable on the item in front of you.

BOTH CASES CARRY THE HINT, and that is what makes them discriminating. A build
that had simply stopped reading the hint satisfies the first; a build that still
reads it satisfies neither; and only a build that reads the recorded
classification satisfies both.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
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

_ITEM = "bd-ib-hint"
_HEADING = "## A governing clause"
_HINT = "SC-1"
_UNSTATED = (
    '{"kind": "unstated", "stated_by": [], "generalization_target": '
    f'"{_HEADING}", "rationale": "the ratified text does not state it"}}'
)
_STATED = (
    f'{{"kind": "stated", "stated_by": ["{_HEADING}"], '
    '"generalization_target": null, "rationale": "the clause states it"}'
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


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="task",
        status="pending-approval",
        title="A follow-up to a ratified change",
        description=(
            "## Definition of Done\n\n- The follow-up lands its change.\n\n"
            f"References: {_HEADING}\n"
        ),
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
        # The hint from an earlier, already-ratified change. Present in BOTH
        # cases, which is what makes them discriminate.
        spec_commitment_hint=_HINT,
        acceptance_policy="ai-only",
    )


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


def _route(*, repo: Path) -> str:
    return unsafe_perform_io(
        apply_intake_dor(
            path=_config(repo=repo),
            item_id=_ITEM,
            checklist=DefinitionOfReadyChecklist(
                single_coherent_done=True,
                autonomously_verifiable=True,
                autonomy_tiered=True,
                dependency_linked=True,
                repo_targeted=True,
                above_floor=True,
            ),
        ).unwrap()
    )


def _stored(*, repo: Path) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config(repo=repo)))[_ITEM]


def _recorded(*, repo: Path) -> str:
    return "\n".join(
        comment.text
        for comment in read_work_item_comments(path=_config(repo=repo), work_item_id=_ITEM)
    )


def test_a_hint_carrying_item_whose_behaviour_is_stated_is_not_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, replies=("feature", _STATED))
    append_work_item(path=_config(repo=repo), item=_item())

    assert _route(repo=repo) == "ready"
    assert _stored(repo=repo).status == "ready"
    assert _stored(repo=repo).spec_commitment_hint == _HINT
    assert "tier: none" in _recorded(repo=repo)


def test_a_hint_carrying_feature_with_unstated_behaviour_is_still_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, replies=("feature", _UNSTATED))
    append_work_item(path=_config(repo=repo), item=_item())

    assert _route(repo=repo) == "pending-approval"
    assert _stored(repo=repo).status == "pending-approval"
    assert "tier: spec-change" in _recorded(repo=repo)
