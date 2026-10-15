"""The durable records the overtaken-arming ending leaves behind.

Scenario 184's "An armed pull request overtaken by a conflicting commit rests
at needs-human with a named cause" sub-scenario, and the v145 "Armed pull
request overtaken by the default branch" clause: the ending writes one
`livespec-base-advanced-after-arming` ledger comment and one
`needs-human-blocked` journal row, and its outcome detail names the recovery
chain.

THE NEW MODULE IS IMPORTED INSIDE TEST BODIES, never at module top. A
top-level import of a module this Red predates makes the Red a COLLECTION
error, which proves only that the module is missing — the first assertion
below is instead a genuine check against code that already exists (the outcome
detail, which at Red names the cause but not the chain), and the module-shaped
cases assert the file exists before importing it.

WHY THE COMMENT IS GRADED THREE WAYS RATHER THAN TWO. A name may be present
and identifier-shaped, present and NOT identifier-shaped, or ABSENT because
the view never reported it. The clause requires the second to be left out and
counted; the third is a different fact and must not be counted as a shape
failure, because that would make the comment state something false about a
reading nobody took. A renderer that collapsed the two would satisfy every
assertion about the count while mis-describing the one case an operator
triages differently.
"""

from __future__ import annotations

import importlib
import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance import (
    BASE_ADVANCED_AFTER_ARMING,
    base_advanced_detail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_RECORD_MODULE = f"{_PACKAGE}._dispatcher_base_advance_record"

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RECORD_SOURCE = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_base_advance_record.py"
)

_MARKER = "livespec-base-advanced-after-arming"
_ITEM_ID = "bd-ib-overtaken"
_RUN_ID = "01M509QRWWNKK6H8VK865JGFC9"
_FACTORY = "hp"
_PR_HEAD = "aaaa1111bbbb2222"
_BASE_TIP = "cccc3333dddd4444"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _write_config(*, project_root: Path) -> None:
    _ = (project_root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "bd",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="An armed pull request the default branch overtook",
        description="Its auto-merge request outlived the base it was armed for.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason=None,
    )


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _record_module() -> object:
    assert _RECORD_SOURCE.is_file(), f"{_RECORD_SOURCE} does not exist yet"
    return importlib.import_module(_RECORD_MODULE)


def _detail(*, work_item_id: str) -> str:
    """The detail, reached through an assertion that the parameter EXISTS.

    Calling the renderer with a parameter it does not take raises `TypeError`,
    which is an error rather than a finding: it says the call was malformed,
    not that the chain is missing. Asserting the signature first makes the Red
    state the unimplemented thing in its own words.
    """
    parameters = inspect.signature(base_advanced_detail).parameters
    assert "work_item_id" in parameters, (
        "base_advanced_detail does not take the work-item id yet, so it cannot name the "
        "recovery chain"
    )
    return base_advanced_detail(work_item_id=work_item_id)


def _outcome(
    *,
    factory: str = _FACTORY,
    pr_head: str | None = _PR_HEAD,
    default_branch_tip: str | None = _BASE_TIP,
    status: str = "blocked",
    stage: str = "merge-poll",
) -> DispatchOutcome:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance import (
        BaseAdvancedAfterArming,
    )

    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status=status,
        stage=stage,
        pr_number=2606,
        merge_sha=None,
        detail=_detail(work_item_id=_ITEM_ID),
        fabro_run_id=_RUN_ID,
        base_advanced=BaseAdvancedAfterArming(
            factory=factory,
            pr_head=pr_head,
            default_branch_tip=default_branch_tip,
        ),
    )


def test_the_outcome_detail_names_the_recovery_chain_in_order() -> None:
    """The chain, and its ORDER: resolve-blocked first, then resume.

    The order is asserted by INDEX rather than by two membership checks,
    because a detail naming both in the wrong order satisfies membership while
    telling an operator to resume an item that is still blocked.
    """
    detail = _detail(work_item_id=_ITEM_ID)

    release = f"resolve-blocked:{_ITEM_ID}:ready"
    resume = f"resume --item {_ITEM_ID}"
    assert release in detail
    assert resume in detail
    assert detail.index(release) < detail.index(resume)
    assert BASE_ADVANCED_AFTER_ARMING in detail


def test_the_comment_opens_with_the_marker_line_and_carries_every_measurement() -> None:
    module = _record_module()

    body = module.base_advanced_comment_body(  # type: ignore[attr-defined]
        work_item_id=_ITEM_ID,
        run_id=_RUN_ID,
        factory=_FACTORY,
        pr_number=2606,
        pr_head=_PR_HEAD,
        default_branch_tip=_BASE_TIP,
    )

    assert body.splitlines()[0] == _MARKER
    for measurement in (_ITEM_ID, _RUN_ID, _FACTORY, "2606", _PR_HEAD, _BASE_TIP):
        assert measurement in body, measurement
    assert "0 names were left out" in body


def test_a_name_that_is_not_identifier_shaped_is_left_out_and_counted() -> None:
    """Two unpassable names, both gone from the body, and the count says two."""
    module = _record_module()

    body = module.base_advanced_comment_body(  # type: ignore[attr-defined]
        work_item_id=_ITEM_ID,
        run_id="run id with spaces",
        factory="hp/candidate",
        pr_number=2606,
        pr_head=_PR_HEAD,
        default_branch_tip=_BASE_TIP,
    )

    assert "run id with spaces" not in body
    assert "hp/candidate" not in body
    assert "2 names were left out" in body
    # The passable names are untouched by a sibling's refusal.
    assert _PR_HEAD in body
    assert _BASE_TIP in body


def test_an_unreported_reading_is_stated_as_unreported_rather_than_counted() -> None:
    """An absent reading is not a shape failure, and must not inflate the count."""
    module = _record_module()

    body = module.base_advanced_comment_body(  # type: ignore[attr-defined]
        work_item_id=_ITEM_ID,
        run_id=_RUN_ID,
        factory=_FACTORY,
        pr_number=2606,
        pr_head=None,
        default_branch_tip=None,
    )

    assert "0 names were left out" in body
    assert body.count("not reported") == 2


def test_the_ending_writes_one_comment_and_journals_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments

    monkeypatch.chdir(tmp_path)
    _write_config(project_root=tmp_path)
    append_work_item(path=_config(), item=_item())
    module = _record_module()
    journal = _Journal()

    module.record_base_advanced_after_arming(  # type: ignore[attr-defined]
        repo=tmp_path, item=_item(), outcome=_outcome(), journal=journal
    )

    comments = read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
    marker_comments = [c for c in comments if c.text.splitlines()[0] == _MARKER]
    assert len(marker_comments) == 1
    assert [r for r in journal.records if r.get("stage") == "base-advanced-after-arming-record"]


def test_the_writer_is_a_no_op_for_any_other_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control. A writer that commented on every dispatch would satisfy the
    case above while putting this record on work it does not describe."""
    from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments

    monkeypatch.chdir(tmp_path)
    _write_config(project_root=tmp_path)
    append_work_item(path=_config(), item=_item())
    module = _record_module()
    journal = _Journal()

    green = DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="green",
        stage="done",
        pr_number=2606,
        merge_sha="cafe01",
        detail="merged",
    )
    module.record_base_advanced_after_arming(  # type: ignore[attr-defined]
        repo=tmp_path, item=_item(), outcome=green, journal=journal
    )

    assert read_work_item_comments(path=_config(), work_item_id=_ITEM_ID) == ()
    assert journal.records == []


def test_a_body_that_fails_the_opener_detector_is_journaled_and_never_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fail-closed arm, reached by poisoning the RENDER rather than an input.

    No identifier-shaped value can carry a template opener, so the detector
    cannot fire on a body this renderer built from graded inputs. That makes
    the guard unreachable from the input side and is exactly why it is worth
    having: it stands between a future renderer change and a comment that
    would refuse every later dispatch of the item, permanently. Poisoning the
    render is the only honest way to exercise it.
    """
    from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments

    monkeypatch.chdir(tmp_path)
    _write_config(project_root=tmp_path)
    append_work_item(path=_config(), item=_item())
    module = _record_module()
    journal = _Journal()
    opener = "{" + "{ item.id }" + "}"
    monkeypatch.setattr(
        module, "base_advanced_comment_body", lambda **_kwargs: f"{_MARKER}\n{opener}\n"
    )

    module.record_base_advanced_after_arming(  # type: ignore[attr-defined]
        repo=tmp_path, item=_item(), outcome=_outcome(), journal=journal
    )

    assert read_work_item_comments(path=_config(), work_item_id=_ITEM_ID) == ()
    refused = [r for r in journal.records if r.get("stage") == "base-advanced-after-arming-refused"]
    assert len(refused) == 1
    assert refused[0].get("reason") is not None


def test_a_ledger_write_failure_is_journaled_and_never_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The clause: a comment that cannot be written MUST NOT prevent the
    blocked transition, so the failure is journaled and the call returns."""
    from livespec_orchestrator_beads_fabro.errors import BeadsCommandError

    monkeypatch.chdir(tmp_path)
    _write_config(project_root=tmp_path)
    append_work_item(path=_config(), item=_item())
    module = _record_module()
    journal = _Journal()

    def _refuse(**_kwargs: object) -> None:
        raise BeadsCommandError(command="bd comment add", exit_code=1, stderr="refused")

    monkeypatch.setattr(module, "append_work_item_comment", _refuse)

    module.record_base_advanced_after_arming(  # type: ignore[attr-defined]
        repo=tmp_path, item=_item(), outcome=_outcome(), journal=journal
    )

    errored = [r for r in journal.records if r.get("stage") == "base-advanced-after-arming-error"]
    assert len(errored) == 1
    assert errored[0].get("reason") == "BeadsCommandError"


def test_the_comment_is_written_before_the_blocked_transition() -> None:
    """The clause says BEFORE, and the order is observable only in the sequence.

    `_dispatcher_needs_human_cause` is deliberately written AFTER its
    escalation, for a reason its own call site records, so "the disposition
    sequence writes comments after the transition" is the established habit
    this ending departs from. The departure is asserted against the source
    order, because both calls are fail-soft and neither's return value can
    report which ran first.
    """
    source = (
        _REPO_ROOT
        / ".claude-plugin"
        / "scripts"
        / "livespec_orchestrator_beads_fabro"
        / "commands"
        / "_dispatcher_loop_selection.py"
    ).read_text(encoding="utf-8")

    assert (
        "record_base_advanced_after_arming(" in source
    ), "the disposition sequence does not call the record writer at all"
    assert "escalate_needs_human_block(repo=repo" in source
    writer = source.index("record_base_advanced_after_arming(")
    escalation = source.index("escalate_needs_human_block(repo=repo")
    assert writer < escalation
