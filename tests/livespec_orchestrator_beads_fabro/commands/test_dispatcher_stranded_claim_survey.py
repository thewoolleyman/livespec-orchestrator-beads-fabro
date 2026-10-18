"""Which claims the survey looks at, and which it leaves to somebody else.

The release itself is asserted in `test_dispatcher_stranded_claim_release.py`.
These are the survey's own decisions: who is surveyed at all, which host may
act, how each hold is reported, and what a dry projection does.

THE NOT-SURVEYED CASES ARE THE EXPENSIVE ONES TO GET WRONG. A `rework:pending`
row and a `merge-hold:` row are `active` with no live lock BY DESIGN — the
exact shape this survey reads as stranded — so without the discriminators a
pass would release a deliberate operator window. Each is asserted to change
NOTHING and to appear in NEITHER output, because a row reported as held would
be just as wrong: it would tell an operator their own hold is a fault.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimStamp,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    ATTRIBUTION_PENDING_REMEDY,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    STRANDED_CLAIM_HOLD_STAGE,
)
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_dispatcher_stranded_claim_survey.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_survey"

_ITEM_ID = "bd-ib-surveyone"
_RUN_ID = "01SURVEYRUN"
_HOST = "owning-host"
_FACTORY = "hp"
_SERVER = "https://hp.example:32276"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _module() -> object:
    return importlib.import_module(_MODULE_NAME)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A dispatched slice",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)


def _stamp(**overrides: object) -> ClaimStamp:
    base = ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host=_HOST,
        run_id=_RUN_ID,
        factory_name=_FACTORY,
        factory_server=_SERVER,
    )
    return replace(base, **overrides)


def _seed(*, item: WorkItem, stamp: ClaimStamp | None = None) -> None:
    append_work_item(path=_config(), item=item)
    if stamp is not None:
        record_claim_stamp(path=_config(), work_item_id=item.id, stamp=stamp)


def _label(*, label: str) -> None:
    make_beads_client(config=_config()).update_issue(issue_id=_ITEM_ID, add_labels=[label])


def _journal(*, repo: Path) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("", encoding="utf-8")
    return JournalFile(path=path)


class _Runner:
    """A fake subprocess seam; the forge reports no merged pull request."""

    def __init__(self) -> None:
        self.argvs: list[list[str]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        return CommandResult(exit_code=0, stdout="[]", stderr="")


def _inputs(
    *,
    module: object,
    repo: Path,
    items: tuple[WorkItem, ...],
    runner: _Runner,
    journal: JournalFile,
    surveyed: bool = True,
    status_kinds: dict[str, str | None] | None = None,
    dry_run: bool = False,
    declared: str = _FACTORY,
) -> object:
    return module.StrandedClaimInputs(
        repo=repo,
        items=items,
        journal=journal,
        runner=runner,
        inventories=(
            module.FactoryInventory(
                name=declared,
                server_url=_SERVER,
                fabro_bin="fabro",
                surveyed=surveyed,
                status_kinds={} if status_kinds is None else status_kinds,
            ),
        ),
        this_host=_HOST,
        now_iso="2026-10-18T09:00:00Z",
        dry_run=dry_run,
    )


def _stages(*, journal: JournalFile) -> list[object]:
    return [
        json.loads(line).get("stage")
        for line in journal.path.read_text(encoding="utf-8").splitlines()
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "ready"},
        {"assignee": None},
        {"rework_pending": True},
    ],
)
def test_a_row_that_is_not_a_dispatch_claim_is_not_surveyed(
    *, tmp_path: Path, overrides: dict[str, object]
) -> None:
    assert _MODULE_PATH.is_file()
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item(**overrides)
    _seed(item=item, stamp=_stamp())
    journal = _journal(repo=repo)

    survey = module.survey_stranded_claims(
        inputs=_inputs(module=module, repo=repo, items=(item,), runner=_Runner(), journal=journal)
    )

    assert (survey.recovered, survey.held) == ((), ())
    assert _stages(journal=journal) == []


def test_a_merge_held_row_is_not_surveyed(tmp_path: Path) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item, stamp=_stamp())
    _label(label="merge-hold:2500")
    journal = _journal(repo=repo)

    survey = module.survey_stranded_claims(
        inputs=_inputs(module=module, repo=repo, items=(item,), runner=_Runner(), journal=journal)
    )

    assert (survey.recovered, survey.held) == ((), ())
    assert next(iter(read_work_items(path=_config()))).status == "active"


@pytest.mark.parametrize(
    ("stamp", "declared", "reason"),
    [
        (None, _FACTORY, "claim-unattributable"),
        (_stamp(factory_name="retired"), _FACTORY, "claim-unattributable"),
        (_stamp(run_id=None), _FACTORY, "attribution-pending"),
        (_stamp(dispatching_host="host-b"), _FACTORY, "owner-elsewhere"),
    ],
)
def test_an_unattributable_claim_is_held_with_its_reason_and_journalled(
    *,
    tmp_path: Path,
    stamp: ClaimStamp | None,
    declared: str,
    reason: str,
) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item, stamp=stamp)
    journal = _journal(repo=repo)
    runner = _Runner()

    survey = module.survey_stranded_claims(
        inputs=_inputs(
            module=module,
            repo=repo,
            items=(item,),
            runner=runner,
            journal=journal,
            declared=declared,
        )
    )

    assert [held.hold_reason for held in survey.held] == [reason]
    assert survey.recovered == ()
    assert _stages(journal=journal) == [STRANDED_CLAIM_HOLD_STAGE]
    assert next(iter(read_work_items(path=_config()))).status == "active"
    # An attribution hold costs NO forge round trip: the claim is not this
    # host's to act on, so paying for the measurement would be pure cost.
    assert runner.argvs == []


def test_a_pending_stamp_carries_the_move_valve_as_its_remedy(tmp_path: Path) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item, stamp=_stamp(run_id=None))
    journal = _journal(repo=repo)

    survey = module.survey_stranded_claims(
        inputs=_inputs(module=module, repo=repo, items=(item,), runner=_Runner(), journal=journal)
    )

    assert [held.remedy for held in survey.held] == [ATTRIBUTION_PENDING_REMEDY]
    assert [held.run_id for held in survey.held] == [None]


def test_an_unsurveyed_factory_holds_its_claims_rather_than_releasing_them(
    tmp_path: Path,
) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item, stamp=_stamp())
    journal = _journal(repo=repo)

    survey = module.survey_stranded_claims(
        inputs=_inputs(
            module=module,
            repo=repo,
            items=(item,),
            runner=_Runner(),
            journal=journal,
            surveyed=False,
        )
    )

    assert [held.hold_reason for held in survey.held] == ["factory-unobservable"]
    assert next(iter(read_work_items(path=_config()))).status == "active"


def test_a_live_run_holds_its_claim(tmp_path: Path) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item, stamp=_stamp())
    journal = _journal(repo=repo)

    survey = module.survey_stranded_claims(
        inputs=_inputs(
            module=module,
            repo=repo,
            items=(item,),
            runner=_Runner(),
            journal=journal,
            status_kinds={_RUN_ID: "running"},
        )
    )

    assert [held.hold_reason for held in survey.held] == ["run-live"]
    assert [held.factory_name for held in survey.held] == [_FACTORY]
    assert [held.factory_server_url for held in survey.held] == [_SERVER]


def test_a_dry_projection_writes_nothing_and_reports_the_route_it_would_take(
    tmp_path: Path,
) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item, stamp=_stamp())
    journal = _journal(repo=repo)

    survey = module.survey_stranded_claims(
        inputs=_inputs(
            module=module,
            repo=repo,
            items=(item,),
            runner=_Runner(),
            journal=journal,
            dry_run=True,
        )
    )

    assert [projected.route for projected in survey.recovered] == ["absent-run-release"]
    assert [projected.effects_written for projected in survey.recovered] == [()]
    # The CURRENT status, never the one the route would land on: a projection
    # claiming the destination reads exactly like a pass that had written it.
    assert [projected.status for projected in survey.recovered] == ["active"]
    assert _stages(journal=journal) == []
    assert next(iter(read_work_items(path=_config()))).status == "active"


def test_a_dry_projection_journals_no_hold_either(tmp_path: Path) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item, stamp=_stamp(dispatching_host="host-b"))
    journal = _journal(repo=repo)

    survey = module.survey_stranded_claims(
        inputs=_inputs(
            module=module,
            repo=repo,
            items=(item,),
            runner=_Runner(),
            journal=journal,
            dry_run=True,
        )
    )

    assert [held.hold_reason for held in survey.held] == ["owner-elsewhere"]
    assert _stages(journal=journal) == []
