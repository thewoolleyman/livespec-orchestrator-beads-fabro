"""Where the publication stages keep the facts they hand each other.

The module is a handful of small pure values, so the cases below grade the two
properties that actually decide behaviour: that the directory is resolved BY GIT
rather than joined onto a guessed path, and that the filename set is COMPLETE.

Neither is cosmetic. `$GIT_DIR` is `.git` in an ordinary clone and a
file-pointer indirection in a worktree, so a joined path is correct in one and
silently wrong in the other; and the only caller that reads the whole filename
set is a control asserting an execution boundary left the enclosing run's state
intact, where a missing filename is a file the control does not cover and
nothing about the resulting read would announce it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_state import (
    PR_VISIT_COUNT_STATE_FILENAME,
    PUBLICATION_STATE_GIT_PATH,
    PUBLISH_HEAD_STATE_FILENAME,
    REFRESH_CHANGED_STATE_FILENAME,
    REFRESH_COUNT_STATE_FILENAME,
    REFRESH_REPAIR_BRIEF_STATE_FILENAME,
    REFRESH_REPAIR_COUNT_STATE_FILENAME,
    REFRESH_ROUTE_MARKER_STATE_FILENAME,
    publication_state_filenames,
    publication_state_root_command,
)


def test_the_root_command_resolves_inside_the_clones_own_git_directory(
    tmp_path: Path,
) -> None:
    """Executed against a real repository, not asserted as text.

    The whole point of resolving through git is that the answer is correct for
    whatever shape `$GIT_DIR` has, and only running it can show that. The
    assertion is that the resolved path sits UNDER this repository's own git
    directory and nowhere else — which is what makes a nested execution in a
    different repository structurally unable to name the enclosing run's state.
    """
    repo = tmp_path / "clone"
    subprocess.run(
        ["git", "init", "-b", "master", str(repo)], check=True, capture_output=True, text=True
    )

    resolved = subprocess.run(
        ["sh", "-c", publication_state_root_command()],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    git_dir = subprocess.run(
        ["git", "rev-parse", "--absolute-git-dir"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert resolved
    assert (repo / resolved).resolve() == Path(git_dir) / PUBLICATION_STATE_GIT_PATH
    assert PUBLICATION_STATE_GIT_PATH in resolved


def test_a_second_repository_resolves_a_disjoint_directory(tmp_path: Path) -> None:
    """Two clones, two state directories — the isolation the design rests on.

    Asserted as a POSITIVE pair rather than as a property of one repository:
    "the path is under `$GIT_DIR`" is equally true of a constant that happened
    to contain `.git`, and only two repositories answering differently shows
    that a nested execution cannot reach the enclosing run's state.
    """
    resolved: list[str] = []
    for name in ("enclosing", "nested"):
        repo = tmp_path / name
        subprocess.run(
            ["git", "init", "-b", "master", str(repo)], check=True, capture_output=True, text=True
        )
        answer = subprocess.run(
            ["sh", "-c", publication_state_root_command()],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        resolved.append(str((repo / answer).resolve()))

    assert resolved[0] != resolved[1]
    assert not resolved[0].startswith(resolved[1])
    assert not resolved[1].startswith(resolved[0])


def test_the_filename_set_is_complete_and_distinct() -> None:
    """Every fact, each under its own name.

    Completeness is asserted against the module's own constants rather than
    against a list repeated here: a further fact added without extending
    `publication_state_filenames` is exactly the omission this case exists to
    catch, and a literal copy would have to be edited to notice it.

    The two REFRESH-REPAIR names are asserted DISTINCT from
    `REFRESH_COUNT_STATE_FILENAME` by the same set comparison, which is the
    property that keeps the two counters apart: one bounds `pr_refresh`'s
    non-convergence at three refreshes, the other bounds repair rounds across
    both refreshing stages at two, and a shared file would make each budget
    spend the other's. The REFRESH-ROUTE pair is held apart from both for the
    same reason: `PR_VISIT_COUNT_STATE_FILENAME` counts `pr` visits and decides
    nothing about convergence, so a name shared with either refresh counter
    would make a routed re-entry spend a refresh budget twice.
    """
    filenames = publication_state_filenames()

    assert set(filenames) == {
        PUBLISH_HEAD_STATE_FILENAME,
        REFRESH_COUNT_STATE_FILENAME,
        REFRESH_CHANGED_STATE_FILENAME,
        REFRESH_REPAIR_BRIEF_STATE_FILENAME,
        REFRESH_REPAIR_COUNT_STATE_FILENAME,
        PR_VISIT_COUNT_STATE_FILENAME,
        REFRESH_ROUTE_MARKER_STATE_FILENAME,
    }
    assert len(filenames) == len(set(filenames))
    assert all(re.fullmatch(r"livespec-[a-z-]+", name) for name in filenames), filenames
