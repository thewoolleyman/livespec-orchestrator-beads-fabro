"""Tests for the beads-private `work_item_merge_evidence` static check.

The check walks every materialized work-item from the store descriptor and
applies the merge-evidence rules (positive evidence for completed-style
resolutions, negative evidence for administrative closures, epics exempt
but child-closure-checked). Tests drive it hermetically through the
in-memory `FakeBeadsClient`: `LIVESPEC_BEADS_FAKE=1` flips the store onto
the fake, the singleton is reset per test, and the git-reachability seam is
monkeypatched so no real git invocation runs.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "work_item_merge_evidence.py"


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "work_item_merge_evidence_under_test", _CHECK_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The check imports `livespec_orchestrator_beads_fabro.*`; those resolve via the pytest
# pythonpath. Loading the module once at collection time is enough.
_CHECK = _load_check()

from livespec_orchestrator_beads_fabro.store import append_work_item  # noqa: E402
from livespec_orchestrator_beads_fabro.types import AuditRecord, StoreConfig, WorkItem  # noqa: E402


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.chdir(tmp_path)
    # Reset the store's process-singleton fake before and after each test.
    from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton

    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _audit(*, merge_sha: str = "sha-1") -> AuditRecord:
    return AuditRecord(
        verification_timestamp="2026-05-19T00:00:00Z",
        commits=("c",),
        files_changed=("f",),
        merge_sha=merge_sha,
    )


def _item(
    *,
    id_: str,
    type_: str = "task",
    status: str = "closed",
    resolution: str | None = "completed",
    audit: AuditRecord | None = None,
    depends_on: tuple[str, ...] = (),
) -> WorkItem:
    return WorkItem(
        id=id_,
        type=type_,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        title="t",
        description="d",
        origin="freeform",
        gap_id=None,
        priority=2,
        assignee=None,
        depends_on=depends_on,
        captured_at="2026-05-19T00:00:00Z",
        resolution=resolution,  # type: ignore[arg-type]
        reason="done",
        audit=audit,
        superseded_by=None,
    )


def _seed(item: WorkItem) -> None:
    append_work_item(path=_config(), item=item)


def _force_reachable(*, monkeypatch: pytest.MonkeyPatch, reachable: bool) -> None:
    monkeypatch.setattr(
        _CHECK,
        "_sha_reachable",
        lambda *, cwd, merge_sha, canonical_branch: reachable,  # noqa: ARG005
    )


# --------------------------------------------------------------------------
# Empty store + trivial pass.
# --------------------------------------------------------------------------


def test_empty_tenant_passes_trivially() -> None:
    assert _CHECK.main() == 0


def test_open_work_item_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_reachable(monkeypatch=monkeypatch, reachable=False)
    _seed(_item(id_="li-open", status="open", resolution=None))
    assert _CHECK.main() == 0


# --------------------------------------------------------------------------
# Positive evidence (completed / spec-revised / resolved-out-of-band).
# --------------------------------------------------------------------------


def test_completed_with_reachable_sha_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_reachable(monkeypatch=monkeypatch, reachable=True)
    _seed(_item(id_="li-done", resolution="completed", audit=_audit()))
    assert _CHECK.main() == 0


@pytest.mark.parametrize("resolution", ["completed", "spec-revised", "resolved-out-of-band"])
def test_positive_resolution_missing_audit_fails(
    monkeypatch: pytest.MonkeyPatch,
    resolution: str,
) -> None:
    _force_reachable(monkeypatch=monkeypatch, reachable=True)
    _seed(_item(id_="li-x", resolution=resolution, audit=None))
    assert _CHECK.main() == 1


def test_evidence_violation_empty_merge_sha(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The empty-merge_sha guard is unreachable through the store (which rejects
    an empty merge_sha on read), so it is exercised at the helper level with a
    hand-built audit record carrying an empty SHA.
    """
    _force_reachable(monkeypatch=monkeypatch, reachable=True)
    item = _item(id_="li-x", resolution="completed", audit=_audit(merge_sha=""))
    message = _CHECK._evidence_violation(  # noqa: SLF001
        cwd=tmp_path, item=item, canonical_branch="master"
    )
    assert message is not None
    assert "empty" in message


def test_completed_unreachable_sha_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_reachable(monkeypatch=monkeypatch, reachable=False)
    _seed(_item(id_="li-x", resolution="completed", audit=_audit()))
    assert _CHECK.main() == 1


# --------------------------------------------------------------------------
# Negative evidence (wontfix / duplicate / no-longer-applicable).
# --------------------------------------------------------------------------


@pytest.mark.parametrize("resolution", ["wontfix", "duplicate", "no-longer-applicable"])
def test_administrative_closure_without_audit_passes(resolution: str) -> None:
    _seed(_item(id_="li-admin", resolution=resolution, audit=None))
    assert _CHECK.main() == 0


def test_administrative_closure_with_audit_fails() -> None:
    _seed(_item(id_="li-admin", resolution="wontfix", audit=_audit()))
    assert _CHECK.main() == 1


# --------------------------------------------------------------------------
# Null resolution on a closed item.
# --------------------------------------------------------------------------


def test_closed_without_resolution_fails() -> None:
    _seed(_item(id_="li-x", resolution=None, audit=None))
    assert _CHECK.main() == 1


# --------------------------------------------------------------------------
# Epics — exempt from merge-evidence, child-closure checked instead.
# --------------------------------------------------------------------------


def test_epic_with_all_children_closed_passes() -> None:
    _seed(_item(id_="li-child", status="closed", resolution="wontfix", audit=None))
    _seed(
        _item(
            id_="li-epic",
            type_="epic",
            resolution=None,
            audit=None,
            depends_on=("li-child",),
        )
    )
    assert _CHECK.main() == 0


def test_epic_with_open_child_fails() -> None:
    _seed(_item(id_="li-child", status="open", resolution=None, audit=None))
    _seed(
        _item(
            id_="li-epic",
            type_="epic",
            resolution=None,
            audit=None,
            depends_on=("li-child",),
        )
    )
    assert _CHECK.main() == 1


def test_epic_with_missing_child_passes() -> None:
    """A child id with no matching record does not fail the epic check."""
    _seed(
        _item(
            id_="li-epic",
            type_="epic",
            resolution=None,
            audit=None,
            depends_on=("li-absent",),
        )
    )
    assert _CHECK.main() == 0


def test_epic_violation_skips_non_local_kind_child_entry() -> None:
    """A non-local-kind typed-dict child entry is skipped, not mis-flagged.

    The store materializes intra-tenant `blocks` edges as the v072 typed-dict
    `local` form; a non-`local` discriminator has no in-tenant child id to
    resolve, so the epic check skips it rather than flagging.
    """
    epic = WorkItem(
        id="li-epic",
        type="epic",
        status="closed",
        title="t",
        description="d",
        origin="freeform",
        gap_id=None,
        priority=2,
        assignee=None,
        depends_on=({"kind": "cross-repo", "ref": "sibling#li-x"},),
        captured_at="2026-05-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    assert _CHECK._epic_violation(item=epic, index={}) is None  # noqa: SLF001


def test_epic_violation_resolves_typed_dict_local_child() -> None:
    """The epic check resolves the child id from the v072 typed-dict `local` form.

    The store materializes intra-tenant `blocks` edges as
    `{"kind":"local","work_item_id":...}`; `_epic_violation` MUST extract the
    id from that shape (not only the legacy bare string) so a non-closed child
    still fails the closed-epic gate.
    """
    open_child = _item(id_="li-child", status="open", resolution=None, audit=None)
    epic = WorkItem(
        id="li-epic",
        type="epic",
        status="closed",
        title="t",
        description="d",
        origin="freeform",
        gap_id=None,
        priority=2,
        assignee=None,
        depends_on=({"kind": "local", "work_item_id": "li-child"},),
        captured_at="2026-05-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    index = {"li-child": open_child, "li-epic": epic}
    assert _CHECK._epic_violation(item=epic, index=index) is not None  # noqa: SLF001


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ("li-bare", "li-bare"),
        ({"kind": "local", "work_item_id": "li-typed"}, "li-typed"),
        ({"kind": "local", "work_item_id": 99}, None),
        ({"kind": "cross-repo", "ref": "sibling#li-x"}, None),
        (42, None),
    ],
)
def test_local_child_id_extraction(entry: object, expected: str | None) -> None:
    """`_local_child_id` accepts bare strings and typed-dict `local` entries.

    Non-local kinds, a non-string `work_item_id`, and non-str/non-dict
    entries all resolve to None (no in-tenant child to check).
    """
    assert _CHECK._local_child_id(entry=entry) == expected  # noqa: SLF001


def test_item_violation_unknown_resolution_falls_through(tmp_path: Path) -> None:
    """A resolution outside both evidence sets returns no violation (defensive).

    The `Resolution` enum partitions exactly into the require-evidence and
    negative-evidence sets, so this fall-through is unreachable for valid
    data; it is exercised here at the helper level with an off-enum value.
    """
    item = _item(id_="li-x", resolution="some-unmodelled-resolution", audit=None)
    message = _CHECK._item_violation(  # noqa: SLF001
        cwd=tmp_path, item=item, index={}, canonical_branch="master"
    )
    assert message is None


# --------------------------------------------------------------------------
# canonical_branch resolution + git seam.
# --------------------------------------------------------------------------


def test_resolve_canonical_branch_default_when_no_config(tmp_path: Path) -> None:
    assert _CHECK._resolve_canonical_branch(cwd=tmp_path) == "master"  # noqa: SLF001


def test_resolve_canonical_branch_from_config(tmp_path: Path) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-impl-beads": {"canonical_branch": "main"}}',
        encoding="utf-8",
    )
    assert _CHECK._resolve_canonical_branch(cwd=tmp_path) == "main"  # noqa: SLF001


def test_resolve_canonical_branch_malformed_config_defaults(tmp_path: Path) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text("{ not valid ", encoding="utf-8")
    assert _CHECK._resolve_canonical_branch(cwd=tmp_path) == "master"  # noqa: SLF001


def test_resolve_canonical_branch_non_object_root_defaults(tmp_path: Path) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text("[1, 2]", encoding="utf-8")
    assert _CHECK._resolve_canonical_branch(cwd=tmp_path) == "master"  # noqa: SLF001


def test_resolve_canonical_branch_non_dict_block_defaults(tmp_path: Path) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-impl-beads": "scalar"}', encoding="utf-8"
    )
    assert _CHECK._resolve_canonical_branch(cwd=tmp_path) == "master"  # noqa: SLF001


def test_resolve_canonical_branch_empty_value_defaults(tmp_path: Path) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-impl-beads": {"canonical_branch": ""}}', encoding="utf-8"
    )
    assert _CHECK._resolve_canonical_branch(cwd=tmp_path) == "master"  # noqa: SLF001


def test_git_ok_true_on_zero_exit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import subprocess

    def _fake_run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(_CHECK.subprocess, "run", _fake_run)
    assert _CHECK._git_ok(cwd=tmp_path, args=["cat-file", "-e", "sha"]) is True  # noqa: SLF001


def test_git_ok_false_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import subprocess

    def _fake_run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=argv, returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(_CHECK.subprocess, "run", _fake_run)
    assert _CHECK._git_ok(cwd=tmp_path, args=["cat-file", "-e", "sha"]) is False  # noqa: SLF001


def test_sha_reachable_false_when_cat_file_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        _CHECK,
        "_git_ok",
        lambda *, cwd, args: False,  # noqa: ARG005
    )
    assert (
        _CHECK._sha_reachable(cwd=tmp_path, merge_sha="sha", canonical_branch="master")  # noqa: SLF001
        is False
    )


def test_sha_reachable_true_when_both_git_calls_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        _CHECK,
        "_git_ok",
        lambda *, cwd, args: True,  # noqa: ARG005
    )
    assert (
        _CHECK._sha_reachable(cwd=tmp_path, merge_sha="sha", canonical_branch="master")  # noqa: SLF001
        is True
    )


def test_module_main_is_callable() -> None:
    assert callable(_CHECK.main)
