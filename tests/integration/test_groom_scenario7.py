"""Integration-tier acceptance for the `groom` backlog-decomposition front-end.

Binds SPECIFICATION/scenarios.md "Scenario 7 — Regroom an oversized
work-item" and the contracts.md clause:

    Given a `backlog` item, the groom front-end MUST produce
    a READ-ONLY drafted decomposition (candidate slices pre-filled with
    acceptance / autonomy tier / dependency links / repo target / scope
    and arranged into dependency layers) and MUST file nothing until the
    maintainer approves; on approval it MUST file the approved slices via
    `capture-work-item` with dependency edges linked, and MUST route any
    spec-change slice to `/livespec:propose-change` rather than to the
    factory.

This is the top-of-pyramid behavior journey for the groom front-end's
mechanical seam (`livespec_orchestrator_beads_fabro.commands.groom`): it drives
`load_groom_context` (read-only) and `file_approved_slices` (the
approval-time commit) through the REAL store/client seam against the
in-memory `FakeBeadsClient` — the same backend the hermetic CI tier and
the no-live-connection runtime use, and the same boundary every other
test in this repo mocks. The Scenario-7 journey (draft read-only → file
approved slices through intake routing with deps linked → spec-change routed
→ original regroomed-out) is the bound case; the rest pin read-only-until-approval,
the spec-change routing, and the refuse-don't-drop / expected-error
surface.

Cross-repo filing (bd-ib-735bh2): factory slices whose `repo_target`
differs from `local_repo` MUST NOT be filed in the local tenant; they
are returned in `GroomResult.cross_repo_slices` with their minted id
so the skill can route them to the appropriate repo. Local slices that
depend (by draft-title handle) on a cross-repo blocker record the dep
as `sibling_work_item` so the Dispatcher can gate on it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_groom_approval import groom_approval_for
from livespec_orchestrator_beads_fabro.commands.groom import (
    CandidateSlice,
    CrossRepoSlice,
    GroomApproval,
    file_approved_slices,
    load_groom_context,
)
from livespec_orchestrator_beads_fabro.errors import (
    GroomApprovalRequiredError,
    GroomDraftError,
    GroomExitRefusedError,
    GroomTargetNotBacklogError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig


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
        repo_root=_LOCAL_REPO_ROOT,
    )


_LOCAL_REPO = "livespec-orchestrator-beads-fabro"
_LOCAL_REPO_ROOT = Path("tests/nonexistent-groom-policy-cwd")
_CROSS_REPO = "livespec-runtime"
# The approval every filing case is made under: who approved the cut, and the
# route the approval arrived on. Filing refuses without it.
_APPROVAL = GroomApproval(
    approver="thewoolleyman",
    route="resolve-blocked:li-epic:ready ledger comment 41",
)


def _seed_backlog_item(*, issue_id: str, title: str = "", description: str = "") -> None:
    """Create an item already in `backlog` — the groom target."""
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
    client.update_issue(issue_id=issue_id, status="backlog")


def _factory_slice(*, title: str, depends_on: tuple[str, ...] = ()) -> CandidateSlice:
    return CandidateSlice(
        title=title,
        description=f"{title} body",
        acceptance="just check + the named scenario pass",
        autonomy_tier="factory",
        repo_target=_LOCAL_REPO,
        depends_on=depends_on,
    )


def _cross_repo_slice(*, title: str, depends_on: tuple[str, ...] = ()) -> CandidateSlice:
    return CandidateSlice(
        title=title,
        description=f"{title} body",
        acceptance="done when filed in the target repo",
        autonomy_tier="factory",
        repo_target=_CROSS_REPO,
        depends_on=depends_on,
    )


def _all_items() -> dict[str, object]:
    return dict(materialize_work_items(records=read_work_items(path=_config())))


def _labels_of(*, issue_id: str) -> list[str]:
    record = make_beads_client(config=_config()).show_issue(issue_id=issue_id)
    raw = record["labels"]
    assert isinstance(raw, list)
    return [label for label in raw if isinstance(label, str)]


def _item_status(*, issue_id: str) -> str:
    return materialize_work_items(records=read_work_items(path=_config()))[issue_id].status


# --------------------------------------------------------------------------
# Scenario 7: An oversized item is regroomed into ready slices and drained.
# --------------------------------------------------------------------------


def test_groom_journey_files_ready_slices_links_deps_and_regrooms_out() -> None:
    _seed_backlog_item(
        issue_id="li-epic", title="Oversized epic", description="More than one done."
    )

    # 1. The read-only entry: groom reads the item, mutates nothing.
    context = load_groom_context(path=_config(), item_id="li-epic")
    assert context.item_id == "li-epic"
    assert context.title == "Oversized epic"
    assert context.description == "More than one done."
    # Nothing was filed by reading the draft context — still just the epic.
    assert set(_all_items()) == {"li-epic"}
    assert _item_status(issue_id="li-epic") == "backlog"

    # 2. The maintainer approves a two-layer decomposition: a base factory
    #    slice and a second factory slice depending on it (by its draft
    #    title handle), plus one spec-change slice that must route to
    #    /livespec:propose-change.
    result = file_approved_slices(
        path=_config(),
        regroom_item_id="li-epic",
        local_repo=_LOCAL_REPO,
        approval=_APPROVAL,
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

    # Each filed factory slice is in the ledger and was routed by the shared
    # intake DoR path: the independent slice reaches ready through auto
    # admission, while the dependent slice stays out of direct ready routing.
    items = materialize_work_items(records=read_work_items(path=_config()))
    base_id, dependent_id = result.filed_slice_ids
    assert items[base_id].status == "ready"
    assert items[dependent_id].status == "pending-approval"
    assert "ready" not in _labels_of(issue_id=base_id)
    assert "ready" not in _labels_of(issue_id=dependent_id)
    # The spec-change slice was never filed into the factory ledger.
    assert all(items[k].title != "spec-change slice" for k in items if k != "li-epic")

    # The original item is regroomed OUT — explicitly closed, not dropped.
    assert "li-epic" in items  # still present in the ledger (never deleted)
    assert items["li-epic"].status == "done"
    assert items["li-epic"].resolution == "no-longer-applicable"
    assert items["li-epic"].reason is not None
    assert base_id in items["li-epic"].reason
    assert dependent_id in items["li-epic"].reason


def test_filed_factory_slices_link_their_dependency_edges() -> None:
    _seed_backlog_item(issue_id="li-epic")

    result = file_approved_slices(
        path=_config(),
        regroom_item_id="li-epic",
        local_repo=_LOCAL_REPO,
        approval=_APPROVAL,
        slices=[
            _factory_slice(title="base"),
            # The dependent slice names the base slice's DRAFT TITLE as a
            # handle; the filer resolves it to the base slice's minted id.
            _factory_slice(title="dependent", depends_on=("base",)),
        ],
    )
    base_id, dependent_id = result.filed_slice_ids
    items = materialize_work_items(records=read_work_items(path=_config()))
    dependent = items[dependent_id]
    # The dependency edge points at the base slice's REAL minted id.
    assert base_id in items
    assert dependent.depends_on == ({"kind": "local", "work_item_id": base_id},)


def test_dependency_on_unknown_draft_title_is_rejected() -> None:
    """A handle that names no earlier factory slice is a malformed cut."""
    _seed_backlog_item(issue_id="li-epic")

    with pytest.raises(GroomDraftError, match="not an earlier factory slice"):
        file_approved_slices(
            path=_config(),
            regroom_item_id="li-epic",
            local_repo=_LOCAL_REPO,
            approval=_APPROVAL,
            slices=[_factory_slice(title="orphan", depends_on=("ghost-layer",))],
        )


# --------------------------------------------------------------------------
# All-or-nothing dependency resolution (bd-ib-cebp3u).
#
# The whole approved cut is resolved BEFORE the first write, so a malformed
# draft leaves the ledger exactly as it found it — the same guarantee an
# absent approval already carried. The discriminating fixture puts a VALID
# factory slice BETWEEN the spec-change slice and the slice that names it:
# a seam that resolved dependencies mid-loop would have filed that middle
# slice, routed it through intake and stamped its approval before raising,
# and there is no compensating delete. A one-slice draft cannot tell the two
# implementations apart, because neither files anything before the raise.
# --------------------------------------------------------------------------


def _spec_change_slice(*, title: str) -> CandidateSlice:
    return CandidateSlice(
        title=title,
        description=f"{title} body",
        acceptance="propose-change accepted",
        autonomy_tier="human-gated",
        repo_target="livespec",
        is_spec_change=True,
    )


def _cut_depending_on_a_spec_change_slice() -> list[CandidateSlice]:
    """The 2026-09-07 shape: slice 3 is blocked by a never-minted slice 1."""
    return [
        _spec_change_slice(title="slice 1 spec change"),
        _factory_slice(title="slice 2 factory"),
        _factory_slice(
            title="slice 3 factory",
            depends_on=("slice 1 spec change", "slice 2 factory"),
        ),
    ]


def test_dependency_on_a_spec_change_slice_files_no_work_item() -> None:
    """The refusal lands before the first write, so the ledger holds no slice."""
    _seed_backlog_item(issue_id="li-epic")

    with pytest.raises(GroomDraftError):
        file_approved_slices(
            path=_config(),
            regroom_item_id="li-epic",
            local_repo=_LOCAL_REPO,
            approval=_APPROVAL,
            slices=_cut_depending_on_a_spec_change_slice(),
        )

    # ZERO slices filed — not "the ones after the raise are missing".
    assert set(_all_items()) == {"li-epic"}


def test_a_refused_spec_change_dependency_leaves_the_original_unclosed() -> None:
    """The regroom target is untouched, so a corrected cut can simply re-run."""
    _seed_backlog_item(issue_id="li-epic")

    with pytest.raises(GroomDraftError):
        file_approved_slices(
            path=_config(),
            regroom_item_id="li-epic",
            local_repo=_LOCAL_REPO,
            approval=_APPROVAL,
            slices=_cut_depending_on_a_spec_change_slice(),
        )

    assert _item_status(issue_id="li-epic") == "backlog"
    assert groom_approval_for(path=_config(), work_item_id="li-epic") is None


def test_the_spec_change_dependency_refusal_names_both_slices() -> None:
    """The message must say WHICH slice depends on WHICH unmintable slice."""
    _seed_backlog_item(issue_id="li-epic")

    with pytest.raises(GroomDraftError) as excinfo:
        file_approved_slices(
            path=_config(),
            regroom_item_id="li-epic",
            local_repo=_LOCAL_REPO,
            approval=_APPROVAL,
            slices=_cut_depending_on_a_spec_change_slice(),
        )

    detail = excinfo.value.detail
    assert "slice 3 factory" in detail
    assert "slice 1 spec change" in detail
    assert "spec-change" in detail
    assert "never minted" in detail


def test_an_unresolvable_handle_after_a_valid_slice_files_nothing() -> None:
    """The all-or-nothing guarantee is the handle rule's, not just the spec-change case."""
    _seed_backlog_item(issue_id="li-epic")

    with pytest.raises(GroomDraftError, match="not an earlier factory slice"):
        file_approved_slices(
            path=_config(),
            regroom_item_id="li-epic",
            local_repo=_LOCAL_REPO,
            approval=_APPROVAL,
            slices=[
                _factory_slice(title="valid earlier slice"),
                _factory_slice(title="orphan", depends_on=("ghost-layer",)),
            ],
        )

    assert set(_all_items()) == {"li-epic"}
    assert _item_status(issue_id="li-epic") == "backlog"


def test_a_resolvable_cut_still_files_every_factory_slice_and_regrooms_out() -> None:
    """The control: validating first must not stop a well-formed cut landing.

    Same three-slice shape as the refused cut above, differing only in that
    the last slice names the factory slice rather than the spec-change one.
    Without this leg, a seam that refused EVERY cut would pass the refusal
    cases just as well.
    """
    _seed_backlog_item(issue_id="li-epic")

    result = file_approved_slices(
        path=_config(),
        regroom_item_id="li-epic",
        local_repo=_LOCAL_REPO,
        approval=_APPROVAL,
        slices=[
            _spec_change_slice(title="slice 1 spec change"),
            _factory_slice(title="slice 2 factory"),
            _factory_slice(title="slice 3 factory", depends_on=("slice 2 factory",)),
        ],
    )

    base_id, dependent_id = result.filed_slice_ids
    items = materialize_work_items(records=read_work_items(path=_config()))
    assert items[dependent_id].depends_on == ({"kind": "local", "work_item_id": base_id},)
    assert result.regroomed_out is True
    assert _item_status(issue_id="li-epic") == "done"


# --------------------------------------------------------------------------
# Read-only-until-approval + refuse-don't-drop guarantees.
# --------------------------------------------------------------------------


def test_load_groom_context_is_read_only() -> None:
    _seed_backlog_item(issue_id="li-epic")
    before = set(_all_items())

    _ = load_groom_context(path=_config(), item_id="li-epic")

    # No new items; the target is untouched and still backlog.
    assert set(_all_items()) == before
    assert _item_status(issue_id="li-epic") == "backlog"


def test_all_spec_change_decomposition_refuses_exit() -> None:
    """An all-spec-change cut files no factory slice → exit is refused (don't-drop)."""
    _seed_backlog_item(issue_id="li-epic")

    with pytest.raises(GroomExitRefusedError):
        file_approved_slices(
            path=_config(),
            regroom_item_id="li-epic",
            local_repo=_LOCAL_REPO,
            approval=_APPROVAL,
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

    # The original is NOT dropped — it stays backlog.
    assert _item_status(issue_id="li-epic") == "backlog"


# --------------------------------------------------------------------------
# Approval provenance (bd-ib-ouoq): who approved the cut, stamped where a
# later reader can query it.
#
# Every assertion below reads the approval back FROM THE STORE, never off the
# `GroomResult` the call returned. That is the discriminating leg: an
# implementation that accepts an approval argument and discards it satisfies a
# return-value assertion exactly as well as one that persists it, and the
# whole point of the record is that it survives the call.
# --------------------------------------------------------------------------


def test_a_filed_slice_carries_the_approval_record_in_the_store() -> None:
    """The filed slice is attributable after the fact, from the ledger alone."""
    _seed_backlog_item(issue_id="li-epic")

    result = file_approved_slices(
        path=_config(),
        regroom_item_id="li-epic",
        local_repo=_LOCAL_REPO,
        approval=_APPROVAL,
        slices=[_factory_slice(title="approved slice")],
    )

    (slice_id,) = result.filed_slice_ids
    stored = groom_approval_for(path=_config(), work_item_id=slice_id)
    assert stored is not None
    assert stored.approver == "thewoolleyman"
    assert stored.route == "resolve-blocked:li-epic:ready ledger comment 41"


def test_the_regroomed_out_original_carries_the_same_approval_record() -> None:
    """The closed original is where provenance is otherwise unrecoverable."""
    _seed_backlog_item(issue_id="li-epic")

    _ = file_approved_slices(
        path=_config(),
        regroom_item_id="li-epic",
        local_repo=_LOCAL_REPO,
        approval=_APPROVAL,
        slices=[_factory_slice(title="approved slice")],
    )

    assert _item_status(issue_id="li-epic") == "done"
    stored = groom_approval_for(path=_config(), work_item_id="li-epic")
    assert stored is not None
    assert stored.approver == "thewoolleyman"
    assert stored.route == "resolve-blocked:li-epic:ready ledger comment 41"


def test_a_filing_carrying_no_approval_evidence_is_refused_and_files_nothing() -> None:
    """The 2026-08-22 near-miss shape, as a regression.

    A filing call reaches the seam with nothing attributable behind it. It is
    refused, no slice is filed, and the original stays exactly where it was —
    so a refusal cannot leave the half-completed state (slices filed, original
    still open) that a partially-run filing would.
    """
    _seed_backlog_item(issue_id="li-epic")

    with pytest.raises(GroomApprovalRequiredError):
        _ = file_approved_slices(
            path=_config(),
            regroom_item_id="li-epic",
            local_repo=_LOCAL_REPO,
            approval=None,
            slices=[_factory_slice(title="unapproved slice")],
        )

    assert set(_all_items()) == {"li-epic"}
    assert _item_status(issue_id="li-epic") == "backlog"
    assert groom_approval_for(path=_config(), work_item_id="li-epic") is None


def test_a_filing_whose_approver_identity_is_empty_is_refused() -> None:
    """An unattributed record is refused as firmly as an absent one."""
    _seed_backlog_item(issue_id="li-epic")

    with pytest.raises(GroomApprovalRequiredError, match="names no approver identity"):
        _ = file_approved_slices(
            path=_config(),
            regroom_item_id="li-epic",
            local_repo=_LOCAL_REPO,
            approval=GroomApproval(approver="", route="resolve-blocked:li-epic:ready"),
            slices=[_factory_slice(title="unattributed slice")],
        )

    assert set(_all_items()) == {"li-epic"}
    assert _item_status(issue_id="li-epic") == "backlog"


# --------------------------------------------------------------------------
# Expected-error surface.
# --------------------------------------------------------------------------


def test_groom_refuses_a_non_backlog_target() -> None:
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
            labels=[],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )
    client.update_issue(issue_id="li-ready", status="ready")

    with pytest.raises(GroomTargetNotBacklogError) as excinfo:
        load_groom_context(path=_config(), item_id="li-ready")
    assert excinfo.value.item_id == "li-ready"


def test_groom_unknown_target_raises_not_found() -> None:
    with pytest.raises(WorkItemNotFoundError):
        load_groom_context(path=_config(), item_id="li-ghost")


# --------------------------------------------------------------------------
# Cross-repo filing (bd-ib-735bh2): one-slice/one-ledger model.
# --------------------------------------------------------------------------


def test_cross_repo_slice_not_filed_in_local_tenant() -> None:
    """A slice targeting a different repo must NOT be filed in the local tenant."""
    _seed_backlog_item(issue_id="li-epic")

    result = file_approved_slices(
        path=_config(),
        regroom_item_id="li-epic",
        local_repo=_LOCAL_REPO,
        approval=_APPROVAL,
        slices=[
            _factory_slice(title="local slice"),
            _cross_repo_slice(title="cross-repo slice"),
        ],
    )

    # Only the local slice is filed in the local ledger.
    assert len(result.filed_slice_ids) == 1
    items = _all_items()
    local_ids = [k for k in items if k != "li-epic"]
    assert len(local_ids) == 1
    assert _item_status(issue_id=local_ids[0]) == "ready"

    # The cross-repo slice is returned for external routing, not filed locally.
    assert len(result.cross_repo_slices) == 1
    assert isinstance(result.cross_repo_slices[0], CrossRepoSlice)
    assert result.cross_repo_slices[0].candidate.title == "cross-repo slice"
    assert result.cross_repo_slices[0].candidate.repo_target == _CROSS_REPO


def test_cross_repo_slice_carries_minted_id() -> None:
    """The returned CrossRepoSlice carries a non-empty minted id."""
    _seed_backlog_item(issue_id="li-epic")

    result = file_approved_slices(
        path=_config(),
        regroom_item_id="li-epic",
        local_repo=_LOCAL_REPO,
        approval=_APPROVAL,
        slices=[
            _factory_slice(title="local"),
            _cross_repo_slice(title="remote"),
        ],
    )

    assert result.cross_repo_slices[0].minted_id != ""


def test_local_slice_dep_on_cross_repo_blocker_uses_sibling_work_item_kind() -> None:
    """A local slice depending on a cross-repo blocker records sibling_work_item dep."""
    _seed_backlog_item(issue_id="li-epic")

    result = file_approved_slices(
        path=_config(),
        regroom_item_id="li-epic",
        local_repo=_LOCAL_REPO,
        approval=_APPROVAL,
        slices=[
            # Cross-repo blocker comes first (earlier layer).
            _cross_repo_slice(title="cross-repo blocker"),
            # Local slice depends on the cross-repo slice by draft-title handle.
            _factory_slice(title="local dependent", depends_on=("cross-repo blocker",)),
        ],
    )

    (local_id,) = result.filed_slice_ids
    cross_slice = result.cross_repo_slices[0]
    items = materialize_work_items(records=read_work_items(path=_config()))
    dependent = items[local_id]

    # The dep is sibling_work_item, not local, and references the cross-repo minted id.
    assert dependent.depends_on == (
        {
            "kind": "sibling_work_item",
            "repo": _CROSS_REPO,
            "work_item_id": cross_slice.minted_id,
        },
    )


def test_cross_repo_slice_still_regrooms_out_original() -> None:
    """Original backlog item is disposed even when some slices are cross-repo."""
    _seed_backlog_item(issue_id="li-epic")

    result = file_approved_slices(
        path=_config(),
        regroom_item_id="li-epic",
        local_repo=_LOCAL_REPO,
        approval=_APPROVAL,
        slices=[
            _factory_slice(title="local"),
            _cross_repo_slice(title="remote"),
        ],
    )

    assert result.regroomed_out is True
    assert _item_status(issue_id="li-epic") == "done"


def test_empty_repo_target_on_factory_slice_raises_draft_error() -> None:
    """A factory slice with an empty repo_target is a malformed draft."""
    _seed_backlog_item(issue_id="li-epic")

    with pytest.raises(GroomDraftError, match="empty repo_target"):
        file_approved_slices(
            path=_config(),
            regroom_item_id="li-epic",
            local_repo=_LOCAL_REPO,
            approval=_APPROVAL,
            slices=[
                CandidateSlice(
                    title="bad slice",
                    description="",
                    acceptance="done",
                    autonomy_tier="factory",
                    repo_target="",
                )
            ],
        )
