"""Compose the refreshing-``gh`` helper bundle for the sandbox registry."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    GH_MINT_HELPER_RELPATH,
    GH_PUSH_HELPER_RELPATH,
    GH_WRAPPER_TAIL_RELPATH,
    gh_mint_helper_source,
    gh_wrapper_tail_source,
    github_auth_support_relpaths,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_push import PUSH_ORIGIN_SOURCE
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_model import Helper
from livespec_orchestrator_beads_fabro.commands._dispatcher_wip_capture import (
    WIP_CAPTURE_PROGRAM_FILENAME,
    wip_capture_program_source,
)

__all__: list[str] = ["gh_refresh_helpers"]

_EXECUTABLE = 0o755
_READABLE = 0o644
_GH_REFRESH_ROOT = "gh-refresh"


def _text(*, source: Callable[[], str]) -> Callable[[], bytes]:
    return lambda: source().encode("utf-8")


def _constant(*, text: str) -> Callable[[], bytes]:
    return lambda: text.encode("utf-8")


def _file(*, path: Path) -> Callable[[], bytes]:
    return path.read_bytes


def gh_refresh_helpers(*, scripts_root: Path) -> tuple[Helper, ...]:
    """The refreshing `gh` wrapper's fixed pieces and, file by file, its vendored support."""
    fixed = (
        Helper(
            name="gh-mint-helper",
            root=_GH_REFRESH_ROOT,
            path=GH_MINT_HELPER_RELPATH,
            mode=_EXECUTABLE,
            compose=_text(source=gh_mint_helper_source),
        ),
        Helper(
            name="gh-push-origin",
            root=_GH_REFRESH_ROOT,
            path=GH_PUSH_HELPER_RELPATH,
            mode=_EXECUTABLE,
            compose=_constant(text=PUSH_ORIGIN_SOURCE),
        ),
        Helper(
            name="gh-wip-capture",
            root=_GH_REFRESH_ROOT,
            path=f"bin/{WIP_CAPTURE_PROGRAM_FILENAME}",
            mode=_EXECUTABLE,
            compose=_text(source=wip_capture_program_source),
        ),
        Helper(
            name="gh-wrapper-tail",
            root=_GH_REFRESH_ROOT,
            path=GH_WRAPPER_TAIL_RELPATH,
            mode=_READABLE,
            compose=_text(source=gh_wrapper_tail_source),
        ),
    )
    support = tuple(
        Helper(
            name=f"gh-refresh-support/{relpath.as_posix()}",
            root=_GH_REFRESH_ROOT,
            path=relpath.as_posix(),
            mode=_READABLE,
            compose=_file(path=scripts_root / relpath),
        )
        for relpath in github_auth_support_relpaths(scripts_root=scripts_root)
    )
    return fixed + support
