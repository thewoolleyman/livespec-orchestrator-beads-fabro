"""Tests for the cross-repo manifest + dep-entry helpers."""

from pathlib import Path

import pytest
from livespec_impl_beads.commands import _cross_repo
from livespec_impl_beads.commands._cross_repo import (
    is_item_ready,
    load_manifest,
    parse_entry,
)
from livespec_impl_beads.types import WorkItem
from livespec_runtime.cross_repo.types import (
    BranchDependency,
    CrossRepoManifest,
    CrossRepoTarget,
    LocalDependency,
    PullRequestDependency,
    RefStatus,
    SiblingWorkItemDependency,
)


def _item(
    *,
    id_: str,
    status: str = "open",
    depends_on: tuple[object, ...] = (),
) -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status=status,  # type: ignore[arg-type]
        title=id_,
        description="d",
        origin="freeform",
        gap_id=None,
        priority=2,
        assignee=None,
        depends_on=depends_on,  # type: ignore[arg-type]
        captured_at="2026-05-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_load_manifest_returns_empty_when_file_absent(tmp_path: Path) -> None:
    manifest = load_manifest(project_root=tmp_path)
    assert manifest.targets == {}


def test_load_manifest_returns_empty_when_block_missing(tmp_path: Path) -> None:
    (tmp_path / ".livespec.jsonc").write_text(
        '{"template": "livespec"}',
        encoding="utf-8",
    )
    manifest = load_manifest(project_root=tmp_path)
    assert manifest.targets == {}


def test_load_manifest_parses_cross_repo_targets(tmp_path: Path) -> None:
    (tmp_path / ".livespec.jsonc").write_text(
        """
        {
          // sibling repos
          "cross_repo_targets": {
            "runtime": {
              "github_url": "https://github.com/thewoolleyman/livespec-runtime",
              "default_branch": "main"
            }
          }
        }
        """,
        encoding="utf-8",
    )
    manifest = load_manifest(project_root=tmp_path)
    assert "runtime" in manifest.targets
    target = manifest.targets["runtime"]
    assert target.github_url == "https://github.com/thewoolleyman/livespec-runtime"
    assert target.default_branch == "main"


def test_load_manifest_returns_empty_when_jsonc_malformed(tmp_path: Path) -> None:
    (tmp_path / ".livespec.jsonc").write_text("not valid {", encoding="utf-8")
    manifest = load_manifest(project_root=tmp_path)
    assert manifest.targets == {}


def test_load_manifest_returns_empty_when_root_not_object(tmp_path: Path) -> None:
    (tmp_path / ".livespec.jsonc").write_text("[1, 2, 3]", encoding="utf-8")
    manifest = load_manifest(project_root=tmp_path)
    assert manifest.targets == {}


def test_load_manifest_returns_empty_when_block_schema_invalid(tmp_path: Path) -> None:
    (tmp_path / ".livespec.jsonc").write_text(
        '{"cross_repo_targets": {"runtime": {}}}',
        encoding="utf-8",
    )
    manifest = load_manifest(project_root=tmp_path)
    assert manifest.targets == {}


def test_parse_entry_bare_string_to_local() -> None:
    entry = parse_entry(raw="li-x")
    assert isinstance(entry, LocalDependency)
    assert entry.work_item_id == "li-x"


def test_parse_entry_typed_local() -> None:
    entry = parse_entry(raw={"kind": "local", "work_item_id": "li-y"})
    assert isinstance(entry, LocalDependency)
    assert entry.work_item_id == "li-y"


def test_parse_entry_typed_pull_request() -> None:
    entry = parse_entry(raw={"kind": "pull_request", "repo": "runtime", "number": 42})
    assert isinstance(entry, PullRequestDependency)
    assert entry.number == 42


def test_parse_entry_typed_sibling_work_item() -> None:
    entry = parse_entry(
        raw={"kind": "sibling_work_item", "repo": "runtime", "work_item_id": "li-z"},
    )
    assert isinstance(entry, SiblingWorkItemDependency)


def test_parse_entry_typed_branch() -> None:
    entry = parse_entry(raw={"kind": "branch", "repo": "runtime", "name": "feat/x"})
    assert isinstance(entry, BranchDependency)


def test_parse_entry_unparseable_dict_returns_none() -> None:
    assert parse_entry(raw={"kind": "unknown_kind"}) is None


def test_parse_entry_non_str_non_dict_returns_none() -> None:
    assert parse_entry(raw=42) is None


def test_is_item_ready_open_with_no_deps() -> None:
    item = _item(id_="li-x")
    assert is_item_ready(item=item, index={"li-x": item}, manifest=CrossRepoManifest(targets={}))


def test_is_item_ready_closed_item_is_never_ready() -> None:
    item = _item(id_="li-x", status="closed")
    assert not is_item_ready(
        item=item, index={"li-x": item}, manifest=CrossRepoManifest(targets={})
    )


def test_is_item_ready_open_local_dep_blocks() -> None:
    blocker = _item(id_="li-blocker")
    blocked = _item(id_="li-blocked", depends_on=("li-blocker",))
    index = {item.id: item for item in (blocker, blocked)}
    assert not is_item_ready(item=blocked, index=index, manifest=CrossRepoManifest(targets={}))


def test_is_item_ready_closed_local_dep_does_not_block() -> None:
    blocker = _item(id_="li-done", status="closed")
    blocked = _item(id_="li-ready", depends_on=("li-done",))
    index = {item.id: item for item in (blocker, blocked)}
    assert is_item_ready(item=blocked, index=index, manifest=CrossRepoManifest(targets={}))


def test_is_item_ready_typed_local_dep_blocks_when_open() -> None:
    blocker = _item(id_="li-blocker")
    blocked = _item(
        id_="li-blocked",
        depends_on=({"kind": "local", "work_item_id": "li-blocker"},),
    )
    index = {item.id: item for item in (blocker, blocked)}
    assert not is_item_ready(item=blocked, index=index, manifest=CrossRepoManifest(targets={}))


def test_is_item_ready_typed_local_dep_passes_when_closed() -> None:
    blocker = _item(id_="li-done", status="closed")
    blocked = _item(
        id_="li-ready",
        depends_on=({"kind": "local", "work_item_id": "li-done"},),
    )
    index = {item.id: item for item in (blocker, blocked)}
    assert is_item_ready(item=blocked, index=index, manifest=CrossRepoManifest(targets={}))


def test_is_item_ready_unparseable_entry_blocks() -> None:
    item = _item(id_="li-x", depends_on=({"kind": "unknown"},))
    assert not is_item_ready(
        item=item, index={"li-x": item}, manifest=CrossRepoManifest(targets={})
    )


def test_is_item_ready_unknown_kind_with_empty_manifest_does_not_block() -> None:
    """Non-local kind whose `repo` is not in the manifest resolves to UNKNOWN."""
    entry = {"kind": "pull_request", "repo": "runtime", "number": 1}
    item = _item(id_="li-x", depends_on=(entry,))
    assert is_item_ready(
        item=item,
        index={"li-x": item},
        manifest=CrossRepoManifest(targets={}),
    )


def test_is_item_ready_open_pr_dep_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the manifest has the repo and the gh provider returns OPEN, exclude."""

    def _fake_pr_state(*, github_url: str, number: int) -> str | None:
        _ = github_url
        _ = number
        return "OPEN"

    from livespec_runtime.cross_repo.providers import github as gh

    monkeypatch.setattr(gh, "query_pull_request_state", _fake_pr_state)
    manifest = CrossRepoManifest(
        targets={
            "runtime": CrossRepoTarget(github_url="https://github.com/x/y"),
        },
    )
    entry = {"kind": "pull_request", "repo": "runtime", "number": 1}
    item = _item(id_="li-x", depends_on=(entry,))
    assert not is_item_ready(item=item, index={"li-x": item}, manifest=manifest)


def test_is_item_ready_merged_pr_dep_does_not_block(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_pr_state(*, github_url: str, number: int) -> str | None:
        _ = github_url
        _ = number
        return "MERGED"

    from livespec_runtime.cross_repo.providers import github as gh

    monkeypatch.setattr(gh, "query_pull_request_state", _fake_pr_state)
    manifest = CrossRepoManifest(
        targets={
            "runtime": CrossRepoTarget(github_url="https://github.com/x/y"),
        },
    )
    entry = {"kind": "pull_request", "repo": "runtime", "number": 1}
    item = _item(id_="li-x", depends_on=(entry,))
    assert is_item_ready(item=item, index={"li-x": item}, manifest=manifest)


def test_module_public_api() -> None:
    assert set(_cross_repo.__all__) == {"is_item_ready", "load_manifest", "parse_entry"}


def test_local_lookup_unknown_for_missing_id() -> None:
    """The local lookup returns UNKNOWN when an id is absent — covers the missing-id branch."""
    item = _item(id_="li-x", depends_on=({"kind": "local", "work_item_id": "li-absent"},))
    assert is_item_ready(item=item, index={"li-x": item}, manifest=CrossRepoManifest(targets={}))
    assert RefStatus.UNKNOWN.value == "unknown"
