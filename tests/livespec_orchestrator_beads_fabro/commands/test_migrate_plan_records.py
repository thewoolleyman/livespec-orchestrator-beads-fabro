"""The one-shot plan-record migration over a tenant and its repository.

Scenario 112, end to end against the hermetic fake tenant and a `tmp_path`
repository: anchors from existing slugs, derived slugs with a refused
collision, `next_action` seeded from the newest handoff, and a second run that
writes nothing.

Scenario 147's GENESIS leg is covered here too, because it is the second of the
two writes relay research note 007 permits to start a plan epic's authority
chain and it is only observable against a tenant. Its cases read the CHAIN
rather than the report alone: a leg that reported a write it did not record
would satisfy every report assertion and leave the epic chain-less, which is
the state the missing-tracking finding names this very migration as the remedy
for.
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
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    ChainHead,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    MISSING_TRACKING,
    ChainFinding,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_genesis import create_genesis_token
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    ChainCache,
    read_chain_cache,
)
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
    pointer: bool = False,
) -> None:
    metadata: dict[str, Any] = {"rank": "a1"}
    if plan_slug is not None:
        metadata["plan_slug"] = plan_slug
    if pointer:
        # A typed pointer already standing, so the seeding leg SKIPS this epic.
        # That matters whenever a case is about the chain: the seed is itself a
        # sanctioned write, so on an epic whose chain stands it would commit a
        # transition and move the very cache the case is measuring.
        metadata["next_action"] = {
            "kind": "human",
            "ref": "",
            "text": "Ask the maintainer what this plan does next.",
            "required_result": None,
            "budget": None,
        }
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


def _chain_cache(*, epic_id: str) -> ChainCache | None:
    metadata = _fake().show_issue(issue_id=epic_id)["metadata"]
    assert isinstance(metadata, dict)
    return read_chain_cache(metadata=metadata)


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


def test_a_live_plan_epic_carrying_no_chain_gains_a_genesis_token(tmp_path: Path) -> None:
    """The remedy every chain-less reader names finally creates a chain.

    Three controls, each ruling out a different way this could pass for the
    wrong reason. The CLOSED and the ARCHIVED epic have no work left to
    serialize, so a leg that started a chain for every epic it could see would
    satisfy the alpha assertions on its own. And the epic whose chain ALREADY
    STANDS is what tells "creates a chain where there is none" apart from
    "creates a chain": a second chain on one epic admits two simultaneous
    winners, which is the exact failure the design exists to prevent, so the
    standing token has to be the one still there afterwards.
    """
    _seed_epic(epic_id="bd-ib-alpha", plan_slug="alpha")
    _seed_epic(epic_id="bd-ib-standing", plan_slug="standing", pointer=True)
    _seed_epic(epic_id="bd-ib-archived", plan_slug="archived-plan")
    _seed_epic(epic_id="bd-ib-closed", plan_slug="closed-plan", closed=True)
    for slug in ("alpha", "standing", "closed-plan"):
        _ = _plan_dir(project_root=tmp_path, slug=slug)
    _ = _archive_dir(project_root=tmp_path, slug="archived-plan")
    standing = create_genesis_token(config=_config(), epic_id="bd-ib-standing")
    assert isinstance(standing, str)

    report = _run(project_root=tmp_path)

    tokens = _fake().no_history_issue_ids()
    assert len(tokens) == 2
    [created] = [token for token in tokens if token != standing]
    assert _chain_cache(epic_id="bd-ib-alpha") == ChainCache(latest_closed=None, current=created)
    assert report.genesis_written == (f"bd-ib-alpha genesis token {created}",)
    head = read_chain_head(config=_config(), epic_id="bd-ib-alpha")
    assert isinstance(head, ChainHead)
    assert head.current_token_id == created
    assert head.epoch == 0
    assert _chain_cache(epic_id="bd-ib-standing") == ChainCache(
        latest_closed=None, current=standing
    )
    for epic_id in ("bd-ib-archived", "bd-ib-closed"):
        assert _chain_cache(epic_id=epic_id) is None
        finding = read_chain_head(config=_config(), epic_id=epic_id)
        assert isinstance(finding, ChainFinding)
        assert finding.code == MISSING_TRACKING


def test_an_epic_whose_chain_already_stands_is_reported_as_skipped(tmp_path: Path) -> None:
    """A second migration of a migrated epic REPORTS it, rather than refusing it.

    Running this migration twice is an ordinary operator act, and the second
    run's whole claim is that it changed nothing — so the already-named outcome
    belongs in `skipped` beside "already carries next_action", never in
    `refused`, which is where an operator looks for state they must resolve by
    hand. Silence is the third option and the wrong one: an epic the leg passed
    over for a good reason and one it never considered owe opposite conclusions,
    and only the entry distinguishes them.

    The entry names the standing TOKEN because that is the value an operator
    compares the epic's own cache against when a walk reports trouble.
    """
    _seed_epic(epic_id="bd-ib-standing", plan_slug="standing", pointer=True)
    _ = _plan_dir(project_root=tmp_path, slug="standing")
    standing = create_genesis_token(config=_config(), epic_id="bd-ib-standing")
    assert isinstance(standing, str)

    report = _run(project_root=tmp_path)

    assert report.genesis_written == ()
    assert report.refused == ()
    assert (
        f"bd-ib-standing already names chain token {standing}, so no genesis was created"
        in report.skipped
    )
    assert _fake().no_history_issue_ids() == (standing,)
    assert _chain_cache(epic_id="bd-ib-standing") == ChainCache(
        latest_closed=None, current=standing
    )


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
    first_tokens = _fake().no_history_issue_ids()

    second = _run(project_root=tmp_path)

    # One slug, two anchors, two seeded pointers, two genesis tokens — then
    # nothing left to do.
    assert total_writes(report=first) == 7
    assert total_writes(report=second) == 0
    [alpha_token, kappa_token] = first_tokens
    assert first.genesis_written == (
        f"bd-ib-alpha genesis token {alpha_token}",
        f"bd-ib-kappa genesis token {kappa_token}",
    )
    assert second.genesis_written == ()
    assert second.skipped == (
        "bd-ib-alpha already carries plan_slug=alpha",
        "bd-ib-kappa already carries plan_slug=kappa",
        "plan/alpha/associated_work_item_id already anchored",
        "plan/kappa/associated_work_item_id already anchored",
        "bd-ib-alpha already carries next_action",
        "bd-ib-kappa already carries next_action",
        f"bd-ib-alpha already names chain token {alpha_token}, so no genesis was created",
        f"bd-ib-kappa already names chain token {kappa_token}, so no genesis was created",
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
    [token] = _fake().no_history_issue_ids()
    assert captured.out.splitlines() == [
        "migrate-plan-records: 3 write(s)",
        "wrote: plan/alpha/associated_work_item_id -> bd-ib-alpha",
        "wrote: bd-ib-alpha kind=none ref=''",
        f"wrote: bd-ib-alpha genesis token {token}",
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
