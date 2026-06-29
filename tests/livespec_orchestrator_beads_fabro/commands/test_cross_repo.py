"""Tests for the cross-repo manifest + dep-entry helpers.

The readiness predicate (`is_item_ready`), the canonical ranking key
(`ready_sort_key`), and the sibling-lookup helpers RELOCATED to the shared
`livespec_runtime.work_items.lifecycle` module (vendored; covered by its own
upstream tests). What remains in `_cross_repo` — and is exercised here — is
the `.livespec.jsonc` manifest loader and the raw-entry parser.
"""

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _cross_repo
from livespec_orchestrator_beads_fabro.commands._cross_repo import load_manifest, parse_entry
from livespec_runtime.cross_repo.types import (
    BranchDependency,
    LocalDependency,
    PullRequestDependency,
    SiblingWorkItemDependency,
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


def test_module_public_api() -> None:
    assert set(_cross_repo.__all__) == {
        "load_manifest",
        "parse_entry",
    }
