"""Plan-identity write side: the `plan_slug` epic tag and the anchor file."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_plan_identity.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._plan_identity"
_CAPTURE_PROSE = _REPO_ROOT / ".claude-plugin" / "prose" / "capture-work-item.md"


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


def _seed_epic(*, issue_id: str, title: str) -> None:
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="epic",
            title=title,
            description="captured epic",
            assignee=None,
            created_at="2026-09-04T00:00:00Z",
            metadata={"rank": "a1"},
        )
    )


def test_plan_identity_module_exposes_the_two_write_primitives() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)
    assert module.PLAN_ANCHOR_FILENAME == "associated_work_item_id"
    assert module.UNASSIGNED_ANCHOR == "unassigned"
    assert module.PLAN_SLUG_METADATA_KEY == "plan_slug"
    assert sorted(module.__all__) == [
        "PLAN_ANCHOR_FILENAME",
        "PLAN_SLUG_METADATA_KEY",
        "UNASSIGNED_ANCHOR",
        "canonical_plan_slug",
        "tag_epic_plan_slug",
        "write_plan_anchor",
    ]


def test_canonical_slug_is_dash_cased_truncated_and_idempotent() -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    assert module.canonical_plan_slug(text="Beta Topic!") == "beta-topic"
    assert module.canonical_plan_slug(text="  --Not_Canonical Slug--  ") == "not-canonical-slug"

    # Truncation lands exactly on the separator, so the strip must run again
    # after it for the written value to equal its own canonicalization.
    long_slug = module.canonical_plan_slug(text="a" * 63 + " " + "b" * 20)
    assert long_slug == "a" * 63
    assert module.canonical_plan_slug(text=long_slug) == long_slug


def test_anchor_is_written_with_the_epic_id_when_the_directory_has_none(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    anchor = module.write_plan_anchor(project_root=tmp_path, slug="gamma", epic_id="bd-ib-gamma")

    assert anchor == tmp_path / "plan" / "gamma" / "associated_work_item_id"
    assert anchor.read_text(encoding="utf-8") == "bd-ib-gamma\n"


def test_unassigned_anchor_is_completed_to_the_adopting_epic_id(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)
    directory = tmp_path / "plan" / "eta"
    (directory / "research").mkdir(parents=True)
    _ = (directory / "associated_work_item_id").write_text("unassigned\n", encoding="utf-8")

    anchor = module.write_plan_anchor(project_root=tmp_path, slug="eta", epic_id="bd-ib-eta")

    assert anchor.read_text(encoding="utf-8") == "bd-ib-eta\n"


def test_an_anchor_already_naming_an_epic_is_left_untouched(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)
    directory = tmp_path / "plan" / "delta"
    directory.mkdir(parents=True)
    _ = (directory / "associated_work_item_id").write_text("bd-ib-first\n", encoding="utf-8")

    anchor = module.write_plan_anchor(project_root=tmp_path, slug="delta", epic_id="bd-ib-second")

    assert anchor.read_text(encoding="utf-8") == "bd-ib-first\n"


def test_plan_slug_is_derived_from_the_title_when_the_caller_supplies_none() -> None:
    assert _MODULE_PATH.is_file()
    reset_fake_singleton()
    module = importlib.import_module(_MODULE_NAME)
    _seed_epic(issue_id="bd-ib-beta", title="Beta Topic!")

    written = module.tag_epic_plan_slug(config=_config(), epic_id="bd-ib-beta", title="Beta Topic!")

    assert written == "beta-topic"
    record = _fake().show_issue(issue_id="bd-ib-beta")
    assert record["metadata"]["plan_slug"] == "beta-topic"
    assert module.canonical_plan_slug(text=written) == written


def test_a_supplied_slug_is_canonicalized_before_it_is_written() -> None:
    assert _MODULE_PATH.is_file()
    reset_fake_singleton()
    module = importlib.import_module(_MODULE_NAME)
    _seed_epic(issue_id="bd-ib-alpha", title="Alpha planning")

    written = module.tag_epic_plan_slug(
        config=_config(),
        epic_id="bd-ib-alpha",
        title="Alpha planning",
        slug="Alpha_Topic ",
    )

    assert written == "alpha-topic"
    record = _fake().show_issue(issue_id="bd-ib-alpha")
    assert record["metadata"]["plan_slug"] == "alpha-topic"
    assert record["metadata"]["rank"] == "a1"


def test_a_metadata_less_epic_record_is_tagged_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    class _SparseClient:
        """A tenant whose epic record omits the `metadata` key entirely."""

        def __init__(self) -> None:
            self.written: tuple[str, dict[str, Any]] | None = None

        def show_issue(self, *, issue_id: str) -> dict[str, Any]:
            # `omitempty`-sparse: a record holding no metadata carries no key.
            return {"id": issue_id, "issue_type": "epic", "title": "Sparse Topic"}

        def update_issue(self, *, issue_id: str, metadata: dict[str, Any]) -> None:
            self.written = (issue_id, metadata)

    sparse = _SparseClient()

    def _sparse_client(*, config: StoreConfig) -> _SparseClient:
        assert config.fake
        return sparse

    monkeypatch.setattr(module, "make_beads_client", _sparse_client)

    written = module.tag_epic_plan_slug(
        config=_config(), epic_id="bd-ib-sparse", title="Sparse Topic"
    )

    assert written == "sparse-topic"
    assert sparse.written == ("bd-ib-sparse", {"plan_slug": "sparse-topic"})


def test_create_thread_anchors_the_directory_and_tags_the_epic(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")

    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="gamma",
        title="Gamma planning",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-09-04T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )

    anchor = tmp_path / "plan" / "gamma" / "associated_work_item_id"
    assert anchor.read_text(encoding="utf-8") == f"{created['epic_id']}\n"
    assert created["anchor_path"] == "plan/gamma/associated_work_item_id"
    [record] = _fake().list_issues()
    assert record["metadata"]["plan_slug"] == "gamma"


def test_create_thread_adopts_a_standalone_research_directory(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    directory = tmp_path / "plan" / "eta"
    (directory / "research").mkdir(parents=True)
    _ = (directory / "research" / "earlier.md").write_text("standalone\n", encoding="utf-8")
    _ = (directory / "associated_work_item_id").write_text("unassigned\n", encoding="utf-8")

    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="eta",
        title="Eta planning",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-09-04T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )

    assert (directory / "associated_work_item_id").read_text(
        encoding="utf-8"
    ) == f"{created['epic_id']}\n"
    assert (directory / "research" / "earlier.md").read_text(encoding="utf-8") == "standalone\n"


def test_capture_prose_tags_every_epic_it_files_through_the_primitive() -> None:
    body = _CAPTURE_PROSE.read_text(encoding="utf-8")

    assert "_plan_identity import tag_epic_plan_slug" in body
    assert "tag_epic_plan_slug(" in body
