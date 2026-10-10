"""The one-shot plan-record migration over a tenant and its repository.

Scenario 112, end to end against the hermetic fake tenant and a `tmp_path`
repository: anchors from existing slugs, derived slugs with a refused
collision, `next_action` seeded from the newest handoff, and a second run that
writes nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro.commands import _plan_identity
from livespec_orchestrator_beads_fabro.commands import migrate_plan_records as module
from livespec_orchestrator_beads_fabro.commands._plan_record_migration import (
    PlanRecordMigrationReport,
    total_writes,
)
from livespec_orchestrator_beads_fabro.commands.migrate_plan_records import (
    main,
    migrate_plan_records,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    from pathlib import Path

_NOW = "2026-09-04T18:00:00Z"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


@pytest.fixture(autouse=True)
def _in_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )


def _seed_epic(
    *,
    epic_id: str,
    title: str = "Plan topic",
    issue_type: str = "epic",
    plan_slug: str | None = None,
    spec_id: str | None = None,
    notes: str | None = None,
    closed: bool = False,
) -> None:
    metadata: dict[str, Any] = {"rank": "a1"}
    if plan_slug is not None:
        metadata["plan_slug"] = plan_slug
    client = _fake()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=epic_id,
            issue_type=issue_type,
            title=title,
            description="seeded",
            assignee=None,
            created_at="2026-09-01T00:00:00Z",
            metadata=metadata,
            spec_id=spec_id,
            notes=notes,
        )
    )
    if closed:
        client.close_issue(issue_id=epic_id, reason="archived")


def _seed_handoff(*, epic_id: str, body: str) -> None:
    _fake().seed_comment(
        issue_id=epic_id,
        text=f"plan-handoff-entry\nauthor: session\ntimestamp: {_NOW}\n\n{body}",
        author="session",
        created_at=_NOW,
    )


def _plan_dir(*, project_root: Path, slug: str) -> Path:
    directory = project_root / "plan" / slug
    directory.mkdir(parents=True)
    return directory


def _archive_dir(*, project_root: Path, slug: str) -> Path:
    directory = project_root / "plan" / "archive" / slug
    directory.mkdir(parents=True)
    return directory


def _anchor(*, directory: Path) -> str:
    return (directory / "associated_work_item_id").read_text(encoding="utf-8")


def _run(*, project_root: Path) -> PlanRecordMigrationReport:
    return migrate_plan_records(config=_config(), project_root=project_root, now=_NOW)


def test_every_plan_directory_is_anchored_to_its_epic_or_to_unassigned(
    tmp_path: Path,
) -> None:
    _seed_epic(epic_id="bd-ib-alpha", plan_slug="alpha")
    _seed_epic(epic_id="bd-ib-gamma", plan_slug="gamma", closed=True)
    _seed_epic(epic_id="bd-ib-task", issue_type="task", title="Not an epic")
    alpha = _plan_dir(project_root=tmp_path, slug="alpha")
    research_only = _plan_dir(project_root=tmp_path, slug="beta")
    gamma = _archive_dir(project_root=tmp_path, slug="gamma")

    report = _run(project_root=tmp_path)

    assert _anchor(directory=alpha) == "bd-ib-alpha\n"
    assert _anchor(directory=research_only) == "unassigned\n"
    assert _anchor(directory=gamma) == "bd-ib-gamma\n"
    assert report.anchors_written == (
        "plan/alpha/associated_work_item_id -> bd-ib-alpha",
        "plan/beta/associated_work_item_id -> unassigned",
        "plan/archive/gamma/associated_work_item_id -> bd-ib-gamma",
    )


def test_an_unassigned_anchor_completes_and_a_named_one_is_left_alone(
    tmp_path: Path,
) -> None:
    _seed_epic(epic_id="bd-ib-eta", plan_slug="eta")
    _seed_epic(epic_id="bd-ib-theta", plan_slug="theta")
    eta = _plan_dir(project_root=tmp_path, slug="eta")
    _ = (eta / "associated_work_item_id").write_text("unassigned\n", encoding="utf-8")
    theta = _plan_dir(project_root=tmp_path, slug="theta")
    _ = (theta / "associated_work_item_id").write_text("bd-ib-earlier\n", encoding="utf-8")

    report = _run(project_root=tmp_path)

    assert _anchor(directory=eta) == "bd-ib-eta\n"
    assert _anchor(directory=theta) == "bd-ib-earlier\n"
    assert report.anchors_written == ("plan/eta/associated_work_item_id -> bd-ib-eta",)
    assert report.skipped == (
        "bd-ib-eta already carries plan_slug=eta",
        "bd-ib-theta already carries plan_slug=theta",
        "plan/theta/associated_work_item_id already anchored",
    )


def test_a_missing_slug_is_derived_and_a_colliding_one_is_refused(tmp_path: Path) -> None:
    _seed_epic(epic_id="bd-ib-kappa", title="Anything", spec_id="plan:kappa")
    _seed_epic(epic_id="bd-ib-holder", title="Shared topic", plan_slug="shared-topic")
    _seed_epic(epic_id="bd-ib-collides", title="Shared Topic!")
    _seed_epic(epic_id="bd-ib-noted", title="Anything", notes="plan_slug=noted-topic")

    report = _run(project_root=tmp_path)

    assert _fake().show_issue(issue_id="bd-ib-kappa")["metadata"]["plan_slug"] == "kappa"
    assert _fake().show_issue(issue_id="bd-ib-noted")["metadata"]["plan_slug"] == "noted-topic"
    assert "plan_slug" not in _fake().show_issue(issue_id="bd-ib-collides")["metadata"]
    assert report.slugs_written == (
        "bd-ib-kappa plan_slug=kappa",
        "bd-ib-noted plan_slug=noted-topic",
    )
    assert report.refused == (
        "bd-ib-collides derives plan_slug=shared-topic, already carried by bd-ib-holder",
    )
    assert report.skipped == ("bd-ib-holder already carries plan_slug=shared-topic",)


def test_next_action_is_seeded_from_the_newest_handoff_of_each_open_plan(
    tmp_path: Path,
) -> None:
    _seed_epic(epic_id="bd-ib-impl", plan_slug="impl-plan")
    _seed_epic(epic_id="bd-ib-human", plan_slug="human-plan")
    _seed_epic(epic_id="bd-ib-silent", plan_slug="silent-plan")
    _seed_handoff(epic_id="bd-ib-impl", body="next action: land bd-ib-earlier\n")
    _seed_handoff(epic_id="bd-ib-impl", body="next action: run impl:bd-ib-ott6 in the factory\n")
    _seed_handoff(epic_id="bd-ib-human", body="next action: ask the maintainer to rule\n")
    for slug in ("impl-plan", "human-plan", "silent-plan"):
        _ = _plan_dir(project_root=tmp_path, slug=slug)

    report = _run(project_root=tmp_path)

    impl = _fake().show_issue(issue_id="bd-ib-impl")["metadata"]
    human = _fake().show_issue(issue_id="bd-ib-human")["metadata"]
    silent = _fake().show_issue(issue_id="bd-ib-silent")["metadata"]
    assert impl["next_action"] == {
        "kind": "human",
        "ref": "bd-ib-ott6",
        "text": "Confirm required-result tracking and budget before dispatching bd-ib-ott6.",
        "required_result": None,
        "budget": None,
    }
    assert human["next_action"]["kind"] == "human"
    assert human["next_action"]["text"] == "ask the maintainer to rule"
    assert silent["next_action"]["kind"] == "none"
    assert impl["last_session"] == f"plan-record-migration at {_NOW}"
    assert report.next_actions_seeded == (
        "bd-ib-human kind=human ref=''",
        "bd-ib-impl kind=human ref='bd-ib-ott6'",
        "bd-ib-silent kind=none ref=''",
    )


def test_a_closed_or_archived_plan_epic_is_not_seeded(tmp_path: Path) -> None:
    _seed_epic(epic_id="bd-ib-closed", plan_slug="closed-plan", closed=True)
    _seed_epic(epic_id="bd-ib-archived", plan_slug="archived-plan")
    _ = _plan_dir(project_root=tmp_path, slug="closed-plan")
    _ = _archive_dir(project_root=tmp_path, slug="archived-plan")

    report = _run(project_root=tmp_path)

    assert report.next_actions_seeded == ()
    assert "next_action" not in _fake().show_issue(issue_id="bd-ib-closed")["metadata"]
    assert "next_action" not in _fake().show_issue(issue_id="bd-ib-archived")["metadata"]


def test_a_second_run_writes_nothing_and_leaves_every_record_identical(
    tmp_path: Path,
) -> None:
    _seed_epic(epic_id="bd-ib-kappa", title="Kappa", spec_id="plan:kappa")
    _seed_epic(epic_id="bd-ib-alpha", plan_slug="alpha")
    _seed_handoff(epic_id="bd-ib-alpha", body="next action: run impl:bd-ib-ott6 in the factory\n")
    alpha = _plan_dir(project_root=tmp_path, slug="alpha")
    _ = _plan_dir(project_root=tmp_path, slug="kappa")

    first = _run(project_root=tmp_path)
    first_anchor = _anchor(directory=alpha)
    first_records = _fake().list_issues()

    second = _run(project_root=tmp_path)

    # One slug, two anchors, two seeded pointers — then nothing left to do.
    assert total_writes(report=first) == 5
    assert total_writes(report=second) == 0
    assert second.skipped == (
        "bd-ib-alpha already carries plan_slug=alpha",
        "bd-ib-kappa already carries plan_slug=kappa",
        "plan/alpha/associated_work_item_id already anchored",
        "plan/kappa/associated_work_item_id already anchored",
        "bd-ib-alpha already carries next_action",
        "bd-ib-kappa already carries next_action",
    )
    assert second.slugs_written == ()
    assert second.anchors_written == ()
    assert second.next_actions_seeded == ()
    assert second.refused == ()
    assert _anchor(directory=alpha) == first_anchor
    assert _fake().list_issues() == first_records


def test_a_sparse_record_reads_as_untagged_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_epic(epic_id="bd-ib-sparse", title="Sparse Plan")

    class _SparseClient:
        def list_issues(self) -> list[dict[str, Any]]:
            # `omitempty`-sparse: no metadata, notes, status or spec_id keys.
            return [{"id": "bd-ib-sparse", "issue_type": "epic", "title": "Sparse Plan"}]

    def _sparse_client(*, config: StoreConfig) -> _SparseClient:
        assert config.fake
        return _SparseClient()

    monkeypatch.setattr(module, "make_beads_client", _sparse_client)

    report = _run(project_root=tmp_path)

    assert report.slugs_written == ("bd-ib-sparse plan_slug=sparse-plan",)
    assert _fake().show_issue(issue_id="bd-ib-sparse")["metadata"]["plan_slug"] == "sparse-plan"


def test_a_metadata_less_epic_is_tagged_rather_than_aborting_the_migration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The whole migration over a tenant whose only epic omits `metadata`.

    The sparse-record test above patches the migration's OWN client, so the
    slug write still ran against the fake tenant's key-carrying record. Here
    the write side reads the sparse record too, which is the tenant shape that
    aborted the first real run before it wrote anything.
    """

    class _MetadataLessTenant:
        def __init__(self) -> None:
            self.written: list[tuple[str, dict[str, Any]]] = []

        def list_issues(self) -> list[dict[str, Any]]:
            return [self._record(issue_id="bd-ib-bare")]

        def show_issue(self, *, issue_id: str) -> dict[str, Any]:
            return self._record(issue_id=issue_id)

        def update_issue(self, *, issue_id: str, metadata: dict[str, Any]) -> None:
            self.written.append((issue_id, metadata))

        def _record(self, *, issue_id: str) -> dict[str, Any]:
            # `omitempty`-sparse: an epic holding no metadata carries no key.
            return {"id": issue_id, "issue_type": "epic", "title": "Bare Plan", "status": "open"}

    tenant = _MetadataLessTenant()

    def _tenant_client(*, config: StoreConfig) -> _MetadataLessTenant:
        assert config.fake
        return tenant

    monkeypatch.setattr(module, "make_beads_client", _tenant_client)
    monkeypatch.setattr(_plan_identity, "make_beads_client", _tenant_client)

    report = _run(project_root=tmp_path)

    assert report.slugs_written == ("bd-ib-bare plan_slug=bare-plan",)
    assert tenant.written == [("bd-ib-bare", {"plan_slug": "bare-plan"})]
    assert report.refused == ()


def test_main_reports_the_migration_over_the_project_root(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _seed_epic(epic_id="bd-ib-alpha", plan_slug="alpha")
    _ = _plan_dir(project_root=tmp_path, slug="alpha")

    rc = main(argv=["--project-root", str(tmp_path)])
    captured = capsys.readouterr()

    assert rc == 0
    assert captured.out.splitlines() == [
        "migrate-plan-records: 2 write(s)",
        "wrote: plan/alpha/associated_work_item_id -> bd-ib-alpha",
        "wrote: bd-ib-alpha kind=none ref=''",
        "skipped: bd-ib-alpha already carries plan_slug=alpha",
    ]


def test_main_defaults_to_the_current_directory(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _seed_epic(epic_id="bd-ib-alpha", plan_slug="alpha")
    _ = _plan_dir(project_root=tmp_path, slug="alpha")

    rc = main(argv=[])
    captured = capsys.readouterr()

    assert rc == 0
    assert "plan/alpha/associated_work_item_id -> bd-ib-alpha" in captured.out
