"""Integration-tier acceptance for the `groom` regroom front-end.

Binds SPECIFICATION/scenarios.md "Scenario 7 — Regroom an oversized
work-item" and the contracts.md §"Gap-detectable behavior clauses" clause:

    Given a `needs-regroom` item, the groom regroom front-end MUST produce
    a READ-ONLY drafted decomposition (candidate slices pre-filled with
    acceptance / autonomy tier / dependency links / repo target / scope
    and arranged into dependency layers) and MUST file nothing until the
    maintainer approves; on approval it MUST file the approved slices via
    `capture-work-item` with dependency edges linked, and MUST route any
    spec-change slice to `/livespec:propose-change` rather than to the
    factory.

This is the top-of-pyramid behavior journey for the groom front-end's
mechanical seam (`livespec_impl_beads.commands.groom`): it drives
`load_groom_context` (read-only) and `file_approved_slices` (the
approval-time commit) through the REAL store/client seam against the
in-memory `FakeBeadsClient` — the same backend the hermetic CI tier and
the no-live-connection runtime use, and the same boundary every other
test in this repo mocks. The Scenario-7 journey (draft read-only → file
approved slices `ready` with deps linked → spec-change routed → original
regroomed-out) is the bound case; the rest pin read-only-until-approval,
the spec-change routing, and the refuse-don't-drop / expected-error
surface.
"""

from __future__ import annotations

import pytest
from livespec_impl_beads._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_impl_beads.commands.groom import (
    CandidateSlice,
    file_approved_slices,
    load_groom_context,
)
from livespec_impl_beads.errors import (
    GroomDraftError,
    GroomTargetNotRegroomError,
    RegroomExitRefusedError,
    WorkItemNotFoundError,
)
from livespec_impl_beads.intake_dor import READY_LABEL
from livespec_impl_beads.regroom import NEEDS_REGROOM_LABEL, enter, is_needs_regroom
from livespec_impl_beads.store import materialize_work_items, read_work_items
from livespec_impl_beads.types import StoreConfig


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> object:
    """Reset the process-singleton fake tenant before and after each case."""
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    """A hermetic connection descriptor — `fake=True` selects the in-memory backend."""
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _seed_regroom_item(*, issue_id: str, title: str = "", description: str = "") -> None:
    """Create an item already at `needs-regroom` — the groom target."""
    client = make_beads_client(config=_config())
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="epic",
            title=title or issue_id,
            description=description,
            priority=1,
            assignee=None,
            created_at="2026-06-19T00:00:00Z",
            labels=[],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )
    enter(path=_config(), item_id=issue_id)


def _factory_slice(*, title: str, depends_on: tuple[str, ...] = ()) -> CandidateSlice:
    return CandidateSlice(
        title=title,
        description=f"{title} body",
        acceptance="just check + the named scenario pass",
        autonomy_tier="factory",
        repo_target="livespec-impl-beads",
        depends_on=depends_on,
    )


def _all_items() -> dict[str, object]:
    return dict(materialize_work_items(read_work_items(path=_config())))


def _labels_of(*, issue_id: str) -> list[str]:
    record = make_beads_client(config=_config()).show_issue(issue_id=issue_id)
    raw = record["labels"]
    assert isinstance(raw, list)
    return [label for label in raw if isinstance(label, str)]


# --------------------------------------------------------------------------
# Scenario 7: An oversized item is regroomed into ready slices and drained.
# --------------------------------------------------------------------------


def test_groom_journey_files_ready_slices_links_deps_and_regrooms_out() -> None:
    _seed_regroom_item(
        issue_id="li-epic", title="Oversized epic", description="More than one done."
    )

    # 1. The read-only entry: groom reads the item, mutates nothing.
    context = load_groom_context(path=_config(), item_id="li-epic")
    assert context.item_id == "li-epic"
    assert context.title == "Oversized epic"
    assert context.description == "More than one done."
    # Nothing was filed by reading the draft context — still just the epic.
    assert set(_all_items()) == {"li-epic"}
    assert is_needs_regroom(path=_config(), item_id="li-epic") is True

    # 2. The maintainer approves a two-layer decomposition: a base factory
    #    slice and a second factory slice depending on it (by its draft
    #    title handle), plus one spec-change slice that must route to
    #    /livespec:propose-change.
    result = file_approved_slices(
        path=_config(),
        regroom_item_id="li-epic",
        slices=[
            _factory_slice(title="layer-0 base slice"),
            _factory_slice(
                title="layer-1 dependent slice",
                depends_on=("layer-0 base slice",),
            ),
            CandidateSlice(
                title="spec-change slice",
                description="needs a spec amendment first",
                acceptance="propose-change accepted",
                autonomy_tier="human-gated",
                repo_target="livespec",
                is_spec_change=True,
            ),
        ],
    )

    # Two factory slices were filed; the spec-change slice was routed, not filed.
    assert len(result.filed_slice_ids) == 2
    assert len(result.spec_change_slices) == 1
    assert result.spec_change_slices[0].title == "spec-change slice"
    assert result.regroomed_out is True

    # Each filed factory slice is tagged `ready` and is in the ledger.
    items = materialize_work_items(read_work_items(path=_config()))
    for slice_id in result.filed_slice_ids:
        assert slice_id in items
        assert READY_LABEL in _labels_of(issue_id=slice_id)
    # The spec-change slice was never filed into the factory ledger.
    assert all(items[k].title != "spec-change slice" for k in items if k != "li-epic")

    # The original item is regroomed OUT — needs-regroom cleared, not dropped.
    assert is_needs_regroom(path=_config(), item_id="li-epic") is False
    assert "li-epic" in items  # still present in the ledger (never deleted)
    assert NEEDS_REGROOM_LABEL not in _labels_of(issue_id="li-epic")


def test_filed_factory_slices_link_their_dependency_edges() -> None:
    _seed_regroom_item(issue_id="li-epic")

    result = file_approved_slices(
        path=_config(),
        regroom_item_id="li-epic",
        slices=[
            _factory_slice(title="base"),
            # The dependent slice names the base slice's DRAFT TITLE as a
            # handle; the filer resolves it to the base slice's minted id.
            _factory_slice(title="dependent", depends_on=("base",)),
        ],
    )
    base_id, dependent_id = result.filed_slice_ids
    items = materialize_work_items(read_work_items(path=_config()))
    dependent = items[dependent_id]
    # The dependency edge points at the base slice's REAL minted id.
    assert base_id in items
    assert dependent.depends_on == ({"kind": "local", "work_item_id": base_id},)


def test_dependency_on_unknown_draft_title_is_rejected() -> None:
    """A handle that names no earlier factory slice is a malformed cut."""
    _seed_regroom_item(issue_id="li-epic")

    with pytest.raises(GroomDraftError, match="not an earlier factory slice"):
        file_approved_slices(
            path=_config(),
            regroom_item_id="li-epic",
            slices=[_factory_slice(title="orphan", depends_on=("ghost-layer",))],
        )


# --------------------------------------------------------------------------
# Read-only-until-approval + refuse-don't-drop guarantees.
# --------------------------------------------------------------------------


def test_load_groom_context_is_read_only() -> None:
    _seed_regroom_item(issue_id="li-epic")
    before = set(_all_items())

    _ = load_groom_context(path=_config(), item_id="li-epic")

    # No new items; the target is untouched and still needs-regroom.
    assert set(_all_items()) == before
    assert is_needs_regroom(path=_config(), item_id="li-epic") is True


def test_all_spec_change_decomposition_refuses_exit() -> None:
    """An all-spec-change cut files no factory slice → exit is refused (don't-drop)."""
    _seed_regroom_item(issue_id="li-epic")

    with pytest.raises(RegroomExitRefusedError):
        file_approved_slices(
            path=_config(),
            regroom_item_id="li-epic",
            slices=[
                CandidateSlice(
                    title="only a spec change",
                    description="",
                    acceptance="propose-change accepted",
                    autonomy_tier="human-gated",
                    repo_target="livespec",
                    is_spec_change=True,
                )
            ],
        )

    # The original is NOT dropped — it stays needs-regroom.
    assert is_needs_regroom(path=_config(), item_id="li-epic") is True


# --------------------------------------------------------------------------
# Expected-error surface.
# --------------------------------------------------------------------------


def test_groom_refuses_a_non_regroom_target() -> None:
    client = make_beads_client(config=_config())
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id="li-ready",
            issue_type="task",
            title="li-ready",
            description="",
            priority=2,
            assignee=None,
            created_at="2026-06-19T00:00:00Z",
            labels=[READY_LABEL],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )

    with pytest.raises(GroomTargetNotRegroomError) as excinfo:
        load_groom_context(path=_config(), item_id="li-ready")
    assert excinfo.value.item_id == "li-ready"


def test_groom_unknown_target_raises_not_found() -> None:
    with pytest.raises(WorkItemNotFoundError):
        load_groom_context(path=_config(), item_id="li-ghost")
