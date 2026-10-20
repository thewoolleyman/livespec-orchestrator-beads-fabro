"""The dispatcher sandbox-image inventory uses the dispatch resolution seams."""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_images import (
    BuildRoot,
    sandbox_images,
)

_IMAGE = "ghcr.io/example/sandbox:committed"
_CONFIGURED = "ghcr.io/example/sandbox:configured"


def _workflow(*, path: Path, image: str = _IMAGE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        '[workflow]\ngraph = "workflow.fabro"\n'
        '\n[run.environment]\nid = "sandbox"\n'
        '\n[environments.sandbox]\nprovider = "docker"\n'
        f'\n[environments.sandbox.image]\ndocker = "{image}"\n',
        encoding="utf-8",
    )


def _config(*, repo: Path, factory: dict[str, object], image: str | None) -> None:
    dispatcher: dict[str, object] = {"factories": {"factory": factory}}
    if image is not None:
        dispatcher["fabro_sandbox_image"] = image
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )


def test_inventory_reports_the_same_three_source_arms_a_dispatch_uses(tmp_path: Path) -> None:
    """Catalog, configured, and bundled pins retain their source evidence."""
    catalog_repo = tmp_path / "catalog"
    configured_repo = tmp_path / "configured"
    bundled_repo = tmp_path / "bundled"
    for repo in (catalog_repo, configured_repo, bundled_repo):
        repo.mkdir()
    _config(repo=catalog_repo, factory={"environment": "catalog-env"}, image=_CONFIGURED)
    _config(repo=configured_repo, factory={}, image=_CONFIGURED)
    _config(repo=bundled_repo, factory={}, image=None)
    _workflow(
        path=catalog_repo / ".fabro/workflows/implement-work-item/workflow.toml",
        image="ghcr.io/example/sandbox:target",
    )
    bundle = tmp_path / "build"
    _workflow(path=bundle / ".fabro/workflows/implement-work-item/workflow.toml")

    entries = sandbox_images(
        factory="factory",
        builds=(
            BuildRoot(repository=catalog_repo, root=bundle, kind="registered_install"),
            BuildRoot(repository=configured_repo, root=bundle, kind="cache_lease"),
            BuildRoot(repository=bundled_repo, root=bundle, kind="payload"),
        ),
    )

    assert [entry.record() for entry in entries] == [
        {
            "repository": str(catalog_repo),
            "build": str(bundle),
            "build_kind": "registered_install",
            "source": "catalog_environment",
            "environment_id": "catalog-env",
            "image": None,
            "path": None,
        },
        {
            "repository": str(configured_repo),
            "build": str(bundle),
            "build_kind": "cache_lease",
            "source": "dispatcher.fabro_sandbox_image",
            "environment_id": None,
            "image": _CONFIGURED,
            "path": None,
        },
        {
            "repository": str(bundled_repo),
            "build": str(bundle),
            "build_kind": "payload",
            "source": "committed_run_config",
            "environment_id": None,
            "image": _IMAGE,
            "path": str(bundle / ".fabro/workflows/implement-work-item/workflow.toml"),
        },
    ]
