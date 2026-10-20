"""Tests for resolving a reference's named repository to a clone and a connection.

The two answers this step owns are asserted SEPARATELY, because getting one right
and the other wrong is the failure the module exists to prevent: the clone every
adapter runs its subprocess from, and the tenant connection whose `repo_root`
pins the directory `bd` itself runs in.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import (
    ResultRepository,
    resolve_result_repository,
    result_store_config,
)

_CONNECTION = {"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}


def _project(*, tmp_path: Path, targets: dict[str, object] | None = None) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    config: dict[str, object] = dict(_CONNECTION)
    if targets is not None:
        config["cross_repo_targets"] = targets
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    return repo


def test_the_projects_own_directory_name_resolves_to_the_project_root(tmp_path: Path) -> None:
    """The manifest names siblings and never the project, so the name is the slug.

    Without this arm the commonest result either caller tracks — a target in its
    own repository — would be unresolvable, and the clause puts an unresolvable
    repository in the unobservable set.
    """
    repo = _project(tmp_path=tmp_path)
    assert resolve_result_repository(project_root=repo, name="repo") == ResultRepository(
        name="repo", clone=repo
    )


def test_a_name_absent_from_the_manifest_does_not_resolve(tmp_path: Path) -> None:
    repo = _project(tmp_path=tmp_path)
    assert resolve_result_repository(project_root=repo, name="livespec-overseer") is None


def test_a_configured_absolute_clone_resolves_to_itself(tmp_path: Path) -> None:
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    repo = _project(
        tmp_path=tmp_path,
        targets={
            "sibling": {
                "github_url": "https://github.com/thewoolleyman/sibling",
                "local_clone": str(sibling),
            }
        },
    )
    resolved = resolve_result_repository(project_root=repo, name="sibling")
    assert resolved is not None
    assert resolved.clone == sibling


def test_a_configured_relative_clone_resolves_under_the_project_root(tmp_path: Path) -> None:
    repo = _project(
        tmp_path=tmp_path,
        targets={
            "nested": {
                "github_url": "https://github.com/thewoolleyman/nested",
                "local_clone": "vendor/nested",
            }
        },
    )
    (repo / "vendor" / "nested").mkdir(parents=True)
    resolved = resolve_result_repository(project_root=repo, name="nested")
    assert resolved is not None
    assert resolved.clone == repo / "vendor" / "nested"


def test_a_target_declaring_no_clone_resolves_to_a_parent_dir_peer(tmp_path: Path) -> None:
    """The same convention this repository's sibling resolution already reads."""
    peer = tmp_path / "peer"
    peer.mkdir()
    repo = _project(
        tmp_path=tmp_path,
        targets={"peer": {"github_url": "https://github.com/thewoolleyman/peer"}},
    )
    resolved = resolve_result_repository(project_root=repo, name="peer")
    assert resolved is not None
    assert resolved.clone == peer


def test_a_configured_clone_that_is_not_a_directory_does_not_resolve(tmp_path: Path) -> None:
    """A sibling that has never been cloned on this host is unresolved, not resolved.

    Returning the path anyway would hand every adapter a working directory that is
    not a repository, and the read failure that followed would read as a forge or
    ledger fault rather than as the missing clone it is.
    """
    repo = _project(
        tmp_path=tmp_path,
        targets={
            "uncloned": {
                "github_url": "https://github.com/thewoolleyman/uncloned",
                "local_clone": str(tmp_path / "never-cloned"),
            }
        },
    )
    assert resolve_result_repository(project_root=repo, name="uncloned") is None


def test_the_connection_is_resolved_from_the_target_repositorys_own_clone(
    tmp_path: Path,
) -> None:
    """`repo_root` is the clone, which is the directory `bd` then runs in.

    This is the cross-tenant execution requirement, asserted where it is decided:
    `bd` resolves its connection from the current directory's `.beads/config.yaml`
    rather than from any resolved object, so a connection built from the invoking
    project would read the wrong tenant however correct the descriptor looked.
    """
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    _ = (sibling / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "sib", "tenant": "sib"}
                }
            }
        ),
        encoding="utf-8",
    )
    config = result_store_config(repository=ResultRepository(name="sibling", clone=sibling))
    assert config is not None
    assert config.repo_root == sibling
    assert config.prefix == "sib"
    assert config.tenant == "sib"


def test_an_unreadable_target_configuration_yields_no_connection(tmp_path: Path) -> None:
    """A repository whose configuration declares no create-prefix is unreadable.

    The refusal is a VALUE rather than the exception the resolver raises, because
    the clause makes this an unobservable read and an exception would have to be
    caught outside this tree's one permitted effect boundary.
    """
    broken = tmp_path / "broken"
    broken.mkdir()
    _ = (broken / ".livespec.jsonc").write_text("{}", encoding="utf-8")
    assert result_store_config(repository=ResultRepository(name="broken", clone=broken)) is None


def _checkout_with_primary_path(*, tmp_path: Path, checkout_name: str, primary: Path) -> Path:
    checkout = tmp_path / checkout_name
    checkout.mkdir()
    _ = subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    _ = subprocess.run(
        ["git", "-C", str(checkout), "config", "livespec.primaryPath", str(primary)], check=True
    )
    return checkout


def test_a_worktree_named_after_its_branch_resolves_its_repository_by_primary_path(
    tmp_path: Path,
) -> None:
    """A worktree under `~/.worktrees/<repo>/<branch>` is named after its branch.

    Matching only the checkout directory's name made every same-repository result
    unobservable from such a worktree, which turned bd-ib-qnmxzm's post-merge
    janitor and every worktree pre-push red on 2026-10-12. The primary checkout's
    path is in the shared git config every worktree of it reads.
    """
    checkout = _checkout_with_primary_path(
        tmp_path=tmp_path,
        checkout_name="janitor-bd-ib-qnmxzm",
        primary=tmp_path / "livespec-orchestrator-beads-fabro",
    )
    assert resolve_result_repository(
        project_root=checkout, name="livespec-orchestrator-beads-fabro"
    ) == ResultRepository(name="livespec-orchestrator-beads-fabro", clone=checkout)


def test_legacy_self_repository_identities_resolve_to_the_invoking_checkout(
    tmp_path: Path,
) -> None:
    """Stored absolute and owner-qualified self identities remain observable."""
    primary = tmp_path / "livespec-orchestrator-beads-fabro"
    primary.mkdir()
    checkout = _checkout_with_primary_path(
        tmp_path=tmp_path,
        checkout_name="factory-sandbox",
        primary=primary,
    )
    _ = subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "config",
            "remote.origin.url",
            "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git",
        ],
        check=True,
    )

    for name in (
        str(checkout),
        str(primary),
        "thewoolleyman/livespec-orchestrator-beads-fabro",
    ):
        assert resolve_result_repository(project_root=checkout, name=name) == ResultRepository(
            name=name,
            clone=checkout,
        )


def test_a_name_matching_neither_the_checkout_nor_the_primary_path_does_not_resolve(
    tmp_path: Path,
) -> None:
    checkout = _checkout_with_primary_path(
        tmp_path=tmp_path,
        checkout_name="janitor-bd-ib-qnmxzm",
        primary=tmp_path / "livespec-orchestrator-beads-fabro",
    )
    assert resolve_result_repository(project_root=checkout, name="livespec-overseer") is None


@pytest.mark.parametrize(
    ("origin", "resolves"),
    [
        ("https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro", True),
        ("https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git", True),
        ("git@github.com:thewoolleyman/livespec-orchestrator-beads-fabro.git", True),
        ("ssh://git@host/thewoolleyman/livespec-orchestrator-beads-fabro.git/", True),
        ("/clones/livespec-orchestrator-beads-fabro", True),
        ("https://github.com/thewoolleyman/livespec-overseer.git", False),
        ("", False),
        (None, False),
    ],
)
def test_the_origin_remotes_repository_name_resolves_a_differently_named_checkout(
    *, tmp_path: Path, origin: str | None, resolves: bool
) -> None:
    """A clone directory can be named after neither the repository nor a branch.

    The two identities this module already read cannot see such a checkout: the
    directory name is unrelated to the repository, and a clone made by a sandbox
    carries no `livespec.primaryPath` naming a primary checkout. Petri's sandbox
    clones this repository into `/workspace`, so every same-repository result was
    unobservable in a Petri-era dispatch (bd-ib-wehfpc) while the pinned engine's
    `/data/projects/<repo>` checkout matched by name and stayed green.

    The origin remote's own repository name is read from local git configuration,
    so it costs no network access, and it identifies the repository across each
    URL spelling a clone can carry. A checkout whose origin names a DIFFERENT
    repository, or names nothing at all, must still not invent an identity.
    """
    checkout = tmp_path / "workspace"
    checkout.mkdir()
    _ = subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    if origin is not None:
        _ = subprocess.run(
            ["git", "-C", str(checkout), "config", "remote.origin.url", origin], check=True
        )
    unset = subprocess.run(
        ["git", "-C", str(checkout), "config", "--get", "livespec.primaryPath"],
        capture_output=True,
        check=False,
    )
    assert unset.returncode == 1
    name = "livespec-orchestrator-beads-fabro"
    expected = ResultRepository(name=name, clone=checkout) if resolves else None
    assert resolve_result_repository(project_root=checkout, name=name) == expected
