"""Materialize the exact-object leased publication push used by `pr_refresh`."""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

__all__: list[str] = [
    "PUBLICATION_PUSH_PROGRAM_FILENAME",
    "publication_push_program_path_expansion",
    "publication_push_program_prepare_steps_block",
    "publication_push_program_source",
]

PUBLICATION_PUSH_PROGRAM_FILENAME = "livespec-push-exact-head"

_PROGRAM_SOURCE = """#!/bin/sh
set -eu
if test "$#" -ne 2; then
    echo 'livespec exact-head push: expected <branch> <expected-object>' >&2
    exit 2
fi
branch=$1
expected=$2
if test -z "$branch"; then
    echo 'livespec exact-head push: branch is empty' >&2
    exit 2
fi
if test "${#expected}" -ne 40; then
    echo 'livespec exact-head push: expected object is not a full lowercase sha' >&2
    exit 2
fi
case "$expected" in
    *[!0-9a-f]*)
        echo 'livespec exact-head push: expected object is not a full lowercase sha' >&2
        exit 2
        ;;
esac
exec git push --force-with-lease="refs/heads/$branch:$expected" origin "HEAD:refs/heads/$branch"
"""


def publication_push_program_source() -> str:
    """The sandbox helper's exact bytes; its one push pins the expected object."""
    return _PROGRAM_SOURCE


def publication_push_program_path_expansion() -> str:
    """The path both the prepare step and `pr_refresh` resolve."""
    return f"{sandbox_plugins_root_expansion()}/{PUBLICATION_PUSH_PROGRAM_FILENAME}"


def publication_push_program_prepare_steps_block() -> str:
    """A quoted-heredoc prepare step that installs the executable helper."""
    root = sandbox_plugins_root_expansion()
    path = f"{root}/{PUBLICATION_PUSH_PROGRAM_FILENAME}"
    script = (
        f'set -eu\nmkdir -p "{root}"\n'
        f"cat > \"{path}\" <<'LIVESPEC_PUBLICATION_PUSH_PROGRAM'\n"
        f"{publication_push_program_source()}"
        "LIVESPEC_PUBLICATION_PUSH_PROGRAM\n"
        f'chmod 700 "{path}"'
    )
    return (
        "\n# --- Dispatcher-materialized exact-object publication push ---\n"
        "[[run.prepare.steps]]\n"
        f"script = {json.dumps(script)}\n"
    )
