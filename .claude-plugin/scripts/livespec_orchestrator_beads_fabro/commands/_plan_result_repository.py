"""Resolving a result reference's named repository to a clone and a connection.

The shared-authoritative-result-reader clause of `SPECIFICATION/contracts.md`
requires two things of this step, and they are easy to confuse: reads MUST use
the named repository's configuration and credential seam, and cross-tenant
commands MUST execute FROM that target repository. The first is about which
`.livespec.jsonc` and which tenant credentials answer, the second is about the
working directory the subprocess runs in — and a reader that got the first right
and the second wrong would read the correct configuration while asking the wrong
forge repository, which is the wrong-population trap this repository's own
verification discipline catalogues.

So both answers come from ONE resolution. `ResultRepository.clone` is the
directory every adapter passes as the runner's `cwd`, and `result_store_config`
derives the tenant connection from that same directory, which is what pins
`StoreConfig.repo_root` and therefore the directory `bd` itself runs in — per
this repository's own rule that `bd` resolves its connection from the current
directory's `.beads/config.yaml` rather than from any resolved object.

WHY THE PROJECT HAS THREE CANONICAL IDENTITIES AND NOT ONE. The manifest names
siblings and never the project itself, so a reference to the repository the
reader is running in would otherwise be unresolvable — and the delivery and
deadline callers' commonest result is a target in their own repository. The name
is matched against the project root's directory name, which is the same slug the
manifest keys siblings by, against the basename of the checkout's
`livespec.primaryPath`, and against the repository name its origin remote URL
carries. Each later identity answers a checkout the earlier ones cannot see. A
worktree under `~/.worktrees/<repo>/<branch>` is named after its BRANCH, so the
directory name alone made every same-repository result unobservable there
(bd-ib-bqmrvq); the primary checkout's path lives in the shared git config every
worktree of it reads. A clone a sandbox makes is named after neither — Petri
clones this repository into `/workspace` and sets no `livespec.primaryPath`, so
those two identities left every same-repository result unobservable in a
Petri-era dispatch while the pinned engine's `/data/projects/<repo>` checkout
matched by name and stayed green (bd-ib-wehfpc). The origin remote's repository
name is the identity a clone carries however its directory is named, and it is
read from LOCAL git configuration, so recognising the project costs no network
access and no forge credential.

WHY EVERY IDENTITY RESOLVES TO THE INVOKING CHECKOUT. These three are readings of
ONE repository identity rather than three repositories, so each resolves to the
project root — the directory whose configuration and credential seam the reads
then use. An identity that resolved to the primary checkout or to the origin's
canonical path would send a sandbox's reads at a directory that need not exist
on the host running them.

WHY AN UNRESOLVABLE NAME IS A VALUE AND NOT AN EXCEPTION. The clause puts
"missing repository-resolution failures" in the `unobservable` set, so the
reader has to turn this into an observation; an exception would have to be caught
outside this tree's one permitted effect boundary.

WHY THE CLONE MUST BE A DIRECTORY THAT EXISTS. A configured sibling that has
never been cloned on this host resolves to a path, and every adapter handed one
would run its subprocess in a directory that is not a repository — producing a
read failure whose cause reads as a forge or ledger fault rather than as the
missing clone it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._cross_repo import load_manifest
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._session_wait_gate import (
    resolve_primary_repository,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCredentialMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "ResultRepository",
    "resolve_result_repository",
    "result_store_config",
]

# The EXPECTED-error surface resolving ONE repository's connection descriptor can
# raise: an unreadable or prefix-less `.livespec.jsonc`, and the absent tenant
# secret. Each is an unobservable read rather than a bug, so each is captured
# here instead of escaping as a traceback about the file it was about to name.
_CONFIG_ERRORS: tuple[type[Exception], ...] = (
    LivespecConfigUnreadableError,
    ConnectionPrefixMissingError,
    BeadsCredentialMissingError,
)
_OWNER_REPOSITORY_PARTS = 2


@dataclass(frozen=True, kw_only=True)
class ResultRepository:
    """One named repository, resolved to the clone every read of it runs from."""

    name: str
    clone: Path


def resolve_result_repository(*, project_root: Path, name: str) -> ResultRepository | None:
    """Resolve one canonical repository identity, or `None` when it does not resolve.

    The project's own directory name, the basename of its `livespec.primaryPath`,
    or the repository name its origin remote URL carries resolves to the project
    root. Every other
    name must be a key in the project's configured `cross_repo_targets` block AND
    resolve to a directory that exists on this host.
    """
    primary = resolve_primary_repository(repository=project_root)
    if name in (project_root.name, primary.name):
        return ResultRepository(name=name, clone=project_root)
    if _is_self_repository_path(name=name, project_root=project_root, primary=primary):
        return ResultRepository(name=name, clone=project_root)
    if name in _origin_repository_identities(project_root=project_root):
        return ResultRepository(name=name, clone=project_root)
    target = load_manifest(project_root=project_root).targets.get(name)
    if target is None:
        return None
    clone = _clone(project_root=project_root, name=name, local_clone=target.local_clone)
    if not clone.is_dir():
        return None
    return ResultRepository(name=name, clone=clone)


def result_store_config(*, repository: ResultRepository) -> StoreConfig | None:
    """The named repository's own tenant connection, or `None` when unreadable.

    Resolved from the repository's clone rather than from the invoking project, so
    `StoreConfig.repo_root` pins the directory `bd` runs in to the target
    repository — the clause's cross-tenant execution requirement, enforced where
    the connection is built rather than re-asserted at each ledger adapter.
    """
    resolved = attempt(
        action=lambda: store_config(repo=repository.clone), exceptions=_CONFIG_ERRORS
    )
    if isinstance(resolved, AttemptFailure):
        return None
    return resolved


def _is_self_repository_path(*, name: str, project_root: Path, primary: Path) -> bool:
    """Whether an absolute legacy identity names this checkout or its primary."""
    candidate = Path(name)
    return candidate.is_absolute() and candidate.resolve() in (
        project_root.resolve(),
        primary.resolve(),
    )


def _origin_repository_identities(*, project_root: Path) -> tuple[str, ...]:
    """The repository name this checkout's origin remote URL carries, when it has one.

    Taken from the URL's last path segment with any `.git` suffix removed, which
    is the component every spelling a clone's origin can carry agrees on — HTTPS,
    the scp-like SSH form, an `ssh://` URL, and a local path alike. A checkout
    with no origin, or one whose git configuration cannot be read, has NO such
    identity rather than a wrong one: the caller's next step is the sibling
    manifest, and inventing a name here would resolve another repository's result
    to this checkout.
    """
    result = ShellCommandRunner().run(
        argv=["git", "-C", str(project_root), "config", "--get", "remote.origin.url"],
        cwd=project_root,
        timeout_seconds=5.0,
    )
    if result.exit_code != 0:
        return ()
    url = result.stdout.strip().rstrip("/").removesuffix(".git")
    bare = url.rsplit("/", 1)[-1]
    if not bare:
        return ()
    path = url.partition("://")[2].partition("/")[2]
    if not path and ":" in url and not url.startswith("/"):
        path = url.rsplit(":", 1)[-1]
    owner_and_repository = path if len(path.split("/")) == _OWNER_REPOSITORY_PARTS else ""
    return tuple(identity for identity in (bare, owner_and_repository) if identity)


def _clone(*, project_root: Path, name: str, local_clone: Path | None) -> Path:
    """The clone a configured target names, by the manifest's own path conventions.

    A relative `local_clone` is resolved against the project root and an absent
    one against the project's PARENT, which is how this repository's sibling
    resolution already reads the same manifest: sibling clones are parent-dir
    peers of the orchestrator's own checkout.
    """
    if local_clone is None:
        return project_root.parent / name
    if local_clone.is_absolute():
        return local_clone
    return project_root / local_clone
