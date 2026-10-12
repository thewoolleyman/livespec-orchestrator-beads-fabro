"""Materialize the exact-object leased publication push `pr_refresh` performs.

WHY A MATERIALIZED PROGRAM RATHER THAN SHELL IN THE NODE. The ratified clause
grants `pr_refresh` ONE rewriting capability and bounds it tightly: "a rewrite
MUST use an explicit lease against the recorded remote head of this run's own
publish branch", and "MUST NOT use bare force, `--no-verify`, or rewrite
another ref". Those are three separate properties, and a `git push` assembled
inline in a node's `script` attribute puts all three one typo away from being
lost -- a `--force` that should have been `--force-with-lease=`, a refspec that
should have named one branch, an expected object that arrived empty and turned
the lease into a no-op.

So the push is a PROGRAM with exactly one exec, and the program validates its
own arguments before reaching it: two arguments or nothing, a non-empty branch,
and an expected object that is a full forty-character lowercase sha. The last
check is the load-bearing one, because `--force-with-lease=<ref>:` with an
EMPTY expected object is accepted by git and means "the ref does not exist" --
so an empty value does not fail, it silently becomes a different and much
weaker assertion.

The program is materialized below the sandbox plugins root at prepare time, the
way `_dispatcher_plugin_cache_gate` already materializes its gate, and the node
fails closed on its absence rather than falling back to an inline push.
"""

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
    """A quoted-heredoc prepare step that installs the executable helper.

    The delimiter is QUOTED so the shell expands nothing inside the program:
    its own body carries `$#`, `$1` and `${#expected}`, every one of which an
    unquoted heredoc would substitute away before the file was written.
    """
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
        "\n# --- Dispatcher-materialized exact-object publication push: the ONE\n"
        "# --- rewriting capability the refresh stage is granted ---\n"
        "[[run.prepare.steps]]\n"
        f"script = {json.dumps(script)}\n"
    )
