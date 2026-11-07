"""Render Petri's explicit remote target for an origin-proven source launch."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._fabro_client import (
    fabro_uses_workflow_package,
)

__all__: list[str] = ["explicit_source_target_argv"]

_GITHUB_REPOSITORY_PARTS = 2


def explicit_source_target_argv(
    *,
    argv: list[str],
    fabro_version: str | None,
    origin_url: str,
    origin_ref: str,
    resume_branch: str | None,
) -> list[str]:
    """Target the proved origin branch so Petri need not push the local source branch.

    An older Fabro client and an origin the Dispatcher cannot identify as GitHub
    retain the existing local-source behavior.  A normal Git push is not
    changed: the target applies only to this Fabro launch.
    """
    repository = _github_repository(origin=origin_url)
    if not fabro_uses_workflow_package(version=fabro_version) or repository is None:
        return argv
    branch = resume_branch if resume_branch is not None else origin_ref.removeprefix("origin/")
    target = f"{repository}@{branch}"
    try:
        position = argv.index("--server")
    except ValueError:
        position = len(argv)
    return [*argv[:position], "--target", target, *argv[position:]]


def _github_repository(*, origin: str) -> str | None:
    """Return an ``owner/repository`` identity from a supported GitHub origin."""
    trimmed = origin.strip().rstrip("/").removesuffix(".git")
    if trimmed.startswith("git@github.com:"):
        path = trimmed.removeprefix("git@github.com:")
    elif "github.com/" in trimmed:
        path = trimmed.split("github.com/", maxsplit=1)[1]
    else:
        return None
    parts = path.split("/")
    if len(parts) != _GITHUB_REPOSITORY_PARTS or not all(parts):
        return None
    return "/".join(parts)
