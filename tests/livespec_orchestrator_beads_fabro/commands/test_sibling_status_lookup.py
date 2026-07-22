"""Unit tests for `make_sibling_status_lookup` (qiqz6b Part B).

The lookup is the orchestrator-side injection that lets a CLOSED cross-repo
sibling stop blocking a work-item while OPEN and unresolvable siblings still
fail closed. These tests exercise the resolver directly with a monkeypatched
fleet manifest + `load_items` (no real beads tenant), asserting BOTH happy
paths (done/closed -> CLOSED, other -> OPEN) and — the load-bearing invariant —
every unresolvable path resolving to `UNKNOWN` (fail-closed), so the disposition
cannot silently flip to fail-open.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _sibling_status_lookup as sut
from livespec_orchestrator_beads_fabro.commands._sibling_status_lookup import (
    make_sibling_status_lookup,
)
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError
from livespec_orchestrator_beads_fabro.types import WorkItem
from livespec_runtime.cross_repo.types import RefStatus

_SIBLING_REPO = "sibling-repo"
_MANIFEST = '{"owner": "someowner", "fleet": [{"repo": "sibling-repo"}]}'


def _item(*, id_: str, status: str) -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status=status,  # type: ignore[arg-type]
        title=id_,
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-05-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _project_root(*, tmp_path: Path, make_clone_dir: bool) -> Path:
    """Return a project root whose PARENT-DIR peer is the sibling clone.

    `make_sibling_status_lookup` derives the sibling clone as
    `project_root.parent / <repo>`, so the sibling clone lands at
    `tmp_path / _SIBLING_REPO`.
    """
    project_root = tmp_path / "orchestrator"
    project_root.mkdir()
    if make_clone_dir:
        (tmp_path / _SIBLING_REPO).mkdir()
    return project_root


def _install_fleet(
    *,
    monkeypatch: pytest.MonkeyPatch,
    manifest_text: str | None,
    items: list[WorkItem],
) -> None:
    def _fetch() -> str | None:
        return manifest_text

    def _load(**_kwargs: object) -> list[WorkItem]:
        return list(items)

    monkeypatch.setattr(sut, "fetch_fleet_manifest_text", _fetch)
    monkeypatch.setattr(sut, "load_items", _load)


def test_done_sibling_resolves_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = _project_root(tmp_path=tmp_path, make_clone_dir=True)
    _install_fleet(
        monkeypatch=monkeypatch, manifest_text=_MANIFEST, items=[_item(id_="sib-1", status="done")]
    )
    lookup = make_sibling_status_lookup(project_root=project_root)
    assert lookup(_SIBLING_REPO, "sib-1") == RefStatus.CLOSED


def test_native_closed_sibling_resolves_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The beads-native `closed` status also maps to CLOSED (belt-and-suspenders
    # for any pre-normalization raw path).
    project_root = _project_root(tmp_path=tmp_path, make_clone_dir=True)
    _install_fleet(
        monkeypatch=monkeypatch,
        manifest_text=_MANIFEST,
        items=[_item(id_="sib-1", status="closed")],
    )
    lookup = make_sibling_status_lookup(project_root=project_root)
    assert lookup(_SIBLING_REPO, "sib-1") == RefStatus.CLOSED


def test_open_sibling_resolves_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = _project_root(tmp_path=tmp_path, make_clone_dir=True)
    _install_fleet(
        monkeypatch=monkeypatch, manifest_text=_MANIFEST, items=[_item(id_="sib-1", status="ready")]
    )
    lookup = make_sibling_status_lookup(project_root=project_root)
    assert lookup(_SIBLING_REPO, "sib-1") == RefStatus.OPEN


def test_missing_clone_dir_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = _project_root(tmp_path=tmp_path, make_clone_dir=False)
    _install_fleet(
        monkeypatch=monkeypatch, manifest_text=_MANIFEST, items=[_item(id_="sib-1", status="done")]
    )
    lookup = make_sibling_status_lookup(project_root=project_root)
    assert lookup(_SIBLING_REPO, "sib-1") == RefStatus.UNKNOWN


def test_load_items_raising_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = _project_root(tmp_path=tmp_path, make_clone_dir=True)

    def _fetch() -> str | None:
        return _MANIFEST

    def _load(**_kwargs: object) -> list[WorkItem]:
        raise BeadsConnectionError(detail="unreachable sibling tenant")

    monkeypatch.setattr(sut, "fetch_fleet_manifest_text", _fetch)
    monkeypatch.setattr(sut, "load_items", _load)
    lookup = make_sibling_status_lookup(project_root=project_root)
    assert lookup(_SIBLING_REPO, "sib-1") == RefStatus.UNKNOWN


def test_item_absent_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = _project_root(tmp_path=tmp_path, make_clone_dir=True)
    _install_fleet(
        monkeypatch=monkeypatch, manifest_text=_MANIFEST, items=[_item(id_="other", status="done")]
    )
    lookup = make_sibling_status_lookup(project_root=project_root)
    assert lookup(_SIBLING_REPO, "sib-1") == RefStatus.UNKNOWN


def test_repo_not_fleet_member_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = _project_root(tmp_path=tmp_path, make_clone_dir=True)
    _install_fleet(
        monkeypatch=monkeypatch, manifest_text=_MANIFEST, items=[_item(id_="sib-1", status="done")]
    )
    lookup = make_sibling_status_lookup(project_root=project_root)
    assert lookup("not-a-fleet-member", "sib-1") == RefStatus.UNKNOWN


def test_unfetchable_manifest_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = _project_root(tmp_path=tmp_path, make_clone_dir=True)
    _install_fleet(
        monkeypatch=monkeypatch, manifest_text=None, items=[_item(id_="sib-1", status="done")]
    )
    lookup = make_sibling_status_lookup(project_root=project_root)
    assert lookup(_SIBLING_REPO, "sib-1") == RefStatus.UNKNOWN


def test_malformed_manifest_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = _project_root(tmp_path=tmp_path, make_clone_dir=True)
    _install_fleet(
        monkeypatch=monkeypatch,
        manifest_text="{ this is not valid manifest jsonc",
        items=[_item(id_="sib-1", status="done")],
    )
    lookup = make_sibling_status_lookup(project_root=project_root)
    assert lookup(_SIBLING_REPO, "sib-1") == RefStatus.UNKNOWN


def test_sibling_tenant_read_once_across_lookups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = _project_root(tmp_path=tmp_path, make_clone_dir=True)
    load_calls = {"count": 0}

    def _fetch() -> str | None:
        return _MANIFEST

    def _load(**_kwargs: object) -> list[WorkItem]:
        load_calls["count"] += 1
        return [_item(id_="sib-1", status="done"), _item(id_="sib-2", status="ready")]

    monkeypatch.setattr(sut, "fetch_fleet_manifest_text", _fetch)
    monkeypatch.setattr(sut, "load_items", _load)
    lookup = make_sibling_status_lookup(project_root=project_root)
    first = lookup(_SIBLING_REPO, "sib-1")
    second = lookup(_SIBLING_REPO, "sib-2")
    # Both resolutions read the sibling tenant exactly once (per-repo memo).
    assert load_calls["count"] == 1
    assert first == RefStatus.CLOSED
    assert second == RefStatus.OPEN
