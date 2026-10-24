"""A citation that does not govern is held before admission, naming the heading.

Binds the last gherkin scenario of `SPECIFICATION/scenarios.md` "Scenario 206 —
The spec-change tier is decided by the spec-stated judgement, and a feature
waits for ratification": "Given a ready item whose References line names a
heading that does not govern its assertions / When the pre-admission judgement
runs / Then the item is held with the governing heading the spec-stated
judgement returned as the remedy." The heading's own registry entry is a TODO
owned by work-item `bd-ib-57ss2n`, which lands the tier binding for the rest of
that scenario; this module covers only the sub-scenario `bd-ib-m76p2n` carries,
and claims no registry row.

THE JUDGE IS STOOD IN AT THE EXECUTABLE, as in both Scenario 174 modules, so
the argv, the prompt read and the exit-code mapping are all exercised. One
script answers BOTH takings and tells them apart by their argv, which is how
they differ in production: the spec-stated judgement puts its prompt on
STANDARD INPUT (its argv ends `-p --model <model>`) because the prompt carries
the whole ratified tree and would overrun the kernel's single-argv-entry cap,
while the rubric judgement passes the prompt as the argument after `-p`.

THE RUBRIC JUDGE PASSES IN EVERY CASE, which is what makes the hold evidence
about the component rather than about the gate. If the rubric could refuse, an
item held by it and an item held by the citation rule would be indistinguishable
at the surfaces this module reads.

TWO CONTROLS CARRY IT. An item whose reference line NAMES the heading the
judgement returned must be admitted through the same fixture, since a hold
earned by a build that refuses everything satisfies the positive case exactly
as well. And a judgement that could not be taken must also admit, because a
failure to measure is not evidence that a citation fails to govern — and that
arm is the one an operator cannot repair by editing anything.
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

_ITEM_ID = "bd-ib-m76p2n"
_GOVERNING = "## Scenario 206 — The spec-change tier is decided by the spec-stated judgement"
_NON_GOVERNING = "## Effective acceptance criteria"
_REMEDY = "add that heading to the reference line"

_SPEC_STATED_REPLY = (
    '{\\"kind\\": \\"stated\\", \\"stated_by\\": [\\"' + _GOVERNING + '\\"],'
    ' \\"generalization_target\\": null, \\"rationale\\": \\"It states the behaviour.\\"}'
)
_PASS_REPLY = '{\\"outcome\\": \\"passed\\"}'


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
    """A governed tree carrying BOTH headings, so each citation resolves."""
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_NON_GOVERNING}\n\nThe criteria clause.\n", encoding="utf-8"
    )
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_GOVERNING}\n\nIt states the dispatched slice's behaviour.\n",
        encoding="utf-8",
    )
    return repo


def _install_judge(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One executable answering both takings, told apart by their own argv.

    The spec-stated judgement's argv ends `-p --model <model>` and its prompt
    arrives on standard input; the rubric judgement's second argument IS the
    prompt. So `$2 = --model` is the discriminator, and it is the production
    difference rather than a flag this fixture invented.
    """
    script = tmp_path / "fake-judge"
    _ = script.write_text(
        "#!/bin/sh\n"
        'if [ "$2" = "--model" ]; then\n'
        f'  printf "%s\\n" "{_SPEC_STATED_REPLY}"\n'
        "else\n"
        f'  printf "%s\\n" "{_PASS_REPLY}"\n'
        "fi\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))


def _install_absent_judge(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(tmp_path / "no-such-judge"))


def _item(*, reference: str) -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="feature",
        status="pending-approval",
        title="A judged slice",
        description=(
            "## Definition of Done\n\n- The dispatched slice lands its change.\n\n"
            f"References: {reference}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-23T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


_CHECKLIST = DefinitionOfReadyChecklist(
    single_coherent_done=True,
    autonomously_verifiable=True,
    autonomy_tiered=True,
    dependency_linked=True,
    repo_targeted=True,
    above_floor=True,
)


def _route_intake(*, repo: Path, reference: str) -> str:
    config = _config(repo=repo)
    append_work_item(path=config, item=_item(reference=reference))
    return str(
        unsafe_perform_io(
            apply_intake_dor(path=config, item_id=_ITEM_ID, checklist=_CHECKLIST).unwrap()
        )
    )


def _stored(*, repo: Path) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config(repo=repo)))[_ITEM_ID]


def _comments(*, repo: Path) -> str:
    return "\n".join(
        comment.text
        for comment in read_work_item_comments(path=_config(repo=repo), work_item_id=_ITEM_ID)
    )


def test_a_citation_that_does_not_govern_is_held_before_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The remedy an operator reads names the heading the judgement returned."""
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)

    routed = _route_intake(repo=repo, reference=_NON_GOVERNING)

    assert routed != "ready"
    assert _stored(repo=repo).status != "ready"
    recorded = _comments(repo=repo)
    assert _GOVERNING in recorded
    assert _REMEDY in recorded


def test_a_citation_the_judgement_returned_is_admitted_through_the_same_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: without it, the hold is consistent with refusing everything."""
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)

    routed = _route_intake(repo=repo, reference=_GOVERNING)

    assert routed == "ready"
    assert _stored(repo=repo).status == "ready"


def test_a_judgement_that_could_not_be_taken_does_not_hold_the_citation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure to measure is not evidence that a citation fails to govern."""
    repo = _repo(tmp_path=tmp_path)
    _install_absent_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)

    routed = _route_intake(repo=repo, reference=_NON_GOVERNING)

    assert routed == "ready"
    assert _GOVERNING not in _comments(repo=repo)


def test_the_approve_valve_refuses_the_same_citation_with_the_same_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second pre-admission surface, so one edit clears both doors."""
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)
    append_work_item(
        path=_config(repo=repo),
        item=replace(_item(reference=_NON_GOVERNING), admission_policy="manual"),
    )

    result = run_action(repo=repo, action_id=f"approve:{_ITEM_ID}")

    assert result["status"] != "green"
    assert _GOVERNING in str(result)
    assert _stored(repo=repo).status == "pending-approval"
