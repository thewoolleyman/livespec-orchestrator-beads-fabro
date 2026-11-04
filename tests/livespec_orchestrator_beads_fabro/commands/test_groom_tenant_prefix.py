"""The id prefix a cross-repo groom slice's target tenant mints.

The prefix is read off the target clone's own configuration, and a target that
yields none is refused rather than papered over with the local prefix, which
would reproduce the id the target tenant rejects.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._groom_tenant_prefix import target_tenant_prefix
from livespec_orchestrator_beads_fabro.errors import GroomDraftError
from livespec_orchestrator_beads_fabro.types import StoreConfig


def _project(
    *, tmp_path: Path, clone_config: dict[str, object] | None, cloned: bool
) -> StoreConfig:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {"cross_repo_targets": {"target": {"github_url": "https://github.com/x/target"}}}
        ),
        encoding="utf-8",
    )
    if cloned:
        clone = tmp_path / "target"
        clone.mkdir()
        if clone_config is not None:
            _ = (clone / ".livespec.jsonc").write_text(json.dumps(clone_config), encoding="utf-8")
    return StoreConfig(
        tenant="own",
        prefix="own",
        server_user="own",
        database="own",
        bd_path="bd",
        repo_root=repo,
        fake=True,
    )


def test_the_prefix_is_the_one_the_target_clone_declares(tmp_path: Path) -> None:
    config = _project(
        tmp_path=tmp_path,
        clone_config={"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "tg"}}},
        cloned=True,
    )

    assert target_tenant_prefix(path=config, repo="target") == "tg"


@pytest.mark.parametrize(
    ("clone_config", "cloned"),
    [
        (None, True),
        ({"livespec-orchestrator-beads-fabro": {"connection": {"prefix": ""}}}, True),
        (None, False),
    ],
)
def test_a_target_yielding_no_prefix_is_refused_by_name(
    *, tmp_path: Path, clone_config: dict[str, object] | None, cloned: bool
) -> None:
    config = _project(tmp_path=tmp_path, clone_config=clone_config, cloned=cloned)

    with pytest.raises(GroomDraftError, match="'target'"):
        _ = target_tenant_prefix(path=config, repo="target")


def test_an_unconfigured_target_is_refused_by_name(tmp_path: Path) -> None:
    config = _project(tmp_path=tmp_path, clone_config=None, cloned=False)

    with pytest.raises(GroomDraftError, match="'elsewhere'"):
        _ = target_tenant_prefix(path=config, repo="elsewhere")
