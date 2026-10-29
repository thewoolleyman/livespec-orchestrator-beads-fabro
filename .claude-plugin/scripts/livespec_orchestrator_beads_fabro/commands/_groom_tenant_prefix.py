"""The id prefix a cross-repo groom slice's target tenant mints and accepts.

A beads tenant enforces its own create-prefix on every id filed into it, so a
cross-repo slice minted with the LOCAL tenant's prefix can never be filed in
the tenant it exists for. The target's prefix is read off the target
repository's own configuration — never tabulated — by the same resolution the
carrier tenancy uses. A target that does not resolve to a clone on this host, or
whose clone declares no prefix, has no id this seam can mint honestly, so it is
an expected authoring error rather than a reason to fall back to the local
prefix (which would reproduce the unfilable id).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_result_repository import (
    resolve_result_repository,
    result_store_config,
)
from livespec_orchestrator_beads_fabro.errors import GroomDraftError

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "target_tenant_prefix",
]


def target_tenant_prefix(*, path: StoreConfig, repo: str) -> str:
    """Return the create-prefix of `repo`'s own tenant, or refuse the draft."""
    project_root = path.repo_root if path.repo_root is not None else Path.cwd()
    repository = resolve_result_repository(project_root=project_root, name=repo)
    resolved = None if repository is None else result_store_config(repository=repository)
    if resolved is None or resolved.prefix == "":
        raise GroomDraftError(
            detail=(
                f"cross-repo slice target {repo!r} resolves to no tenant with an id prefix: "
                f"it must be a configured cross_repo_targets entry whose clone exists on "
                f"this host and declares its tenant connection"
            )
        )
    return resolved.prefix
