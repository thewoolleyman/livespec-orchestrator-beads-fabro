"""No engine checkpoint commit that started empty reaches the published branch.

Binds work-item ``bd-ib-myvlbl`` against ``SPECIFICATION/contracts.md``
section "Self-contained plugin dispatch" -- which governs the refresh rebase
both publishing stages perform -- and ``SPECIFICATION/scenarios.md`` Scenario
178, whose carry-forward decision has to survive the rewrite, and Scenario 184,
whose arming is what the empty commits were defeating.

WHY THIS FILE EXISTS. The Petri-era engine commits every checkpoint with
``--allow-empty`` (``fabro-petri/src/checkpoint.rs``), so a run branch gains one
commit per node whether or not that node changed anything. Measured 2026-10-16:
pull request 3114 carried 101 such commits out of 107 and pull request 3113
carried 272 out of 279, and GitHub refused BOTH at the rebase-merge arm with
"This branch can't be rebased". The old-engine fork patch that skipped empty
checkpoints was dropped in the Petri carrier rebuild, and the maintainer chose
to work the hazard around in this repository's own workflow rather than patch
the fork again.

WHY THE FLAGS ARE WHAT THEY ARE, MEASURED RATHER THAN ASSUMED. On git 2.43.0
and 2.51.0 alike a plain ``git rebase`` KEEPS a commit that started empty, and
so does ``--empty=drop`` -- that option governs commits that BECOME empty, not
ones that arrived that way. Only ``--no-keep-empty`` drops them, and only
``--force-rebase`` makes a rebase act at all when the upstream has not moved,
which is the ordinary case for a first publication taken minutes after the
clone. Both halves are therefore load-bearing and each is separately
satisfiable while the requirement is unmet, which is why the cases below assert
on the COMMITS of the published branch rather than on the flags.

WHY EVERY CASE EXECUTES THE SHIPPED BYTES AGAINST A REAL ORIGIN. The refresh is
shell, and the whole question is what git did to a ref: whether a commit
survived, whether the published tip moved, whether a push was a fast-forward or
a lease. A substring assertion on the committed ``script`` attribute cannot tell
a flag that REACHES git from one sitting behind an earlier ``exit``, and no
Python entry point exists for a node's script. So each case parses the script
out of the committed graph with the canonical reader, binds only the two tokens
the ENGINE owns, and runs it under ``bash`` in a real clone of a real bare
origin.

THE EMPTINESS TEST IS ``git diff-tree`` PER COMMIT AND NOT A COMMIT COUNT. A
count falls to the same trap in both directions: a rebase that dropped the
empties and gained an incoming commit reports the same total as one that kept
them, and the published branch legitimately carries a different number of
commits per case. ``_commits_that_started_empty`` asks each commit whether its
own tree differs from its parent's, which is the property the flag is about.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_state import (
    PUBLICATION_STATE_GIT_PATH,
    PUBLISH_HEAD_STATE_FILENAME,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GRAPH_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

_DEFAULT_BRANCH = "master"
_BRANCH = "feat/bd-ib-myvlbl"
# The path the run owns and the path the default branch moves. They are distinct
# so an advancing default applies cleanly: a conflict would take the
# refresh-repair route and never reach the push these cases assert on.
_OWNED_FILE = "owned.txt"
_SHARED_FILE = "shared.txt"

_COVERAGE_ENV_PREFIXES = ("COVERAGE_PROCESS_START", "COV_CORE_")

# The forge double's body, as LINES rather than one concatenated literal: this
# repository bans implicit string concatenation, and a shell program assembled
# by `+` is one missing newline away from running a different command. `pr list`
# deliberately prints NOTHING, which routes the stage onto `pr create`, whose
# printed URL it reads the number out of.
_GH_DOUBLE_LINES = (
    "#!/bin/sh",
    'if test "$1 $2" = "pr create"; then',
    "    printf '%s\\n' 'https://example.invalid/o/r/pull/3115'",
    "fi",
    "exit 0",
    "",
)


def _fixture_env() -> dict[str, str]:
    """The fixture git environment, coverage-scrubbed, with an explicit identity.

    The identity is STATED rather than inherited because the factory sandbox
    carries one that differs from a developer's, and a commit with no identity
    at all fails outright. The scrub is the obligation every allowlisted spawn
    in this tree carries: a self-instrumenting child races the concurrent
    coverage run.
    """
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(_COVERAGE_ENV_PREFIXES)
    }
    return {**env, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@example.invalid"}


def _git(*argv: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=_fixture_env(),
    )


def _commit(*, cwd: Path, path: str, text: str, subject: str) -> str:
    """Write one file and commit it, returning the resulting head."""
    _ = _git("config", "user.email", "t@example.invalid", cwd=cwd)
    _ = _git("config", "user.name", "Test", cwd=cwd)
    _ = (cwd / path).write_text(text, encoding="utf-8")
    _ = _git("add", path, cwd=cwd)
    _ = _git("commit", "--quiet", "-m", subject, cwd=cwd)
    return _git("rev-parse", "HEAD", cwd=cwd).stdout.strip()


def _checkpoint(*, cwd: Path, subject: str) -> str:
    """One engine checkpoint commit over an unchanged tree.

    This is the Petri-era engine's own shape: `git commit --allow-empty` after
    every node, which is why a run branch gains one of these per node whether
    the node wrote anything or not.
    """
    _ = _git("config", "user.email", "t@example.invalid", cwd=cwd)
    _ = _git("config", "user.name", "Test", cwd=cwd)
    _ = _git("commit", "--quiet", "--allow-empty", "-m", subject, cwd=cwd)
    return _git("rev-parse", "HEAD", cwd=cwd).stdout.strip()


@dataclass(frozen=True, kw_only=True)
class _World:
    """One case's throwaway world: a real bare origin and a real clone on a run branch."""

    origin: Path
    clone: Path
    forge_bin: Path

    def state_dir(self) -> Path:
        return self.clone / ".git" / PUBLICATION_STATE_GIT_PATH

    def state(self, *, name: str) -> str | None:
        path = self.state_dir() / name
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def head(self) -> str:
        return _git("rev-parse", "HEAD", cwd=self.clone).stdout.strip()

    def remote_head(self, *, ref: str) -> str:
        """Origin's own answer for one ref, or the empty string when it holds none."""
        listed = subprocess.run(
            ["git", "ls-remote", "--heads", str(self.origin), f"refs/heads/{ref}"],
            check=True,
            capture_output=True,
            text=True,
            env=_fixture_env(),
        )
        return listed.stdout.split("\t")[0] if listed.stdout.strip() else ""


def _forge_bin(*, root: Path) -> Path:
    """A `gh` on PATH answering the two calls a succeeding publication makes."""
    bin_dir = root / "forge-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    gh = bin_dir / "gh"
    _ = gh.write_text("\n".join(_GH_DOUBLE_LINES), encoding="utf-8")
    gh.chmod(0o755)
    return bin_dir


def _world(*, root: Path) -> _World:
    """An origin carrying the default branch, and a clone on this run's own branch."""
    origin = root / "origin.git"
    origin.mkdir(parents=True)
    _ = _git("init", "--bare", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=origin)
    seed = root / "seed"
    seed.mkdir()
    _ = _git("init", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=seed)
    _ = _commit(cwd=seed, path=_SHARED_FILE, text="base\n", subject="chore: seed")
    _ = _git("push", "--quiet", str(origin), f"HEAD:refs/heads/{_DEFAULT_BRANCH}", cwd=seed)
    clone = root / "clone"
    _ = _git("clone", "--quiet", str(origin), str(clone), cwd=root)
    _ = _git("switch", "--quiet", "-c", "fabro/run/test", cwd=clone)
    return _World(origin=origin, clone=clone, forge_bin=_forge_bin(root=root))


def _petri_run(*, root: Path) -> _World:
    """A run branch shaped as the Petri-era engine leaves it.

    One commit of real work with a checkpoint commit on either side of it, which
    is the ordinary shape: the engine checkpoints after EVERY node, so the
    empties bracket the work rather than trailing it. Bracketing matters,
    because a rebase that dropped only the trailing empties would leave the
    branch looking shorter while still carrying the ones GitHub refuses.
    """
    world = _world(root=root)
    _ = _checkpoint(cwd=world.clone, subject="fabro(run): dod_gate (succeeded)")
    _ = _commit(
        cwd=world.clone, path=_OWNED_FILE, text="this run's work\n", subject="feat: the run's work"
    )
    _ = _checkpoint(cwd=world.clone, subject="fabro(run): janitor (succeeded)")
    return world


def _advance_default(*, world: _World, path: str = _SHARED_FILE, text: str = "moved\n") -> str:
    """Move origin's default branch through a SEPARATE clone.

    Separate so this case's own clone learns nothing about the movement until
    the stage's own fetch, which is the state a real dispatch is in when the
    default branch advances underneath it.
    """
    mover = world.clone.parent / f"mover-{path}"
    _ = _git("clone", "--quiet", str(world.origin), str(mover), cwd=world.clone.parent)
    advanced = _commit(cwd=mover, path=path, text=text, subject=f"feat: advance {path}")
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_DEFAULT_BRANCH}", cwd=mover)
    return advanced


def _node_script(*, node: str, check_suite: str) -> str:
    """The shipped node's script, with only the engine's own two tokens bound.

    Read through `parse_dot_graph`, the same reader the Dispatcher's own graph
    consumers use, so a case cannot pass against a recipe this repository does
    not ship. The check suite is a per-repository DECLARATION, so standing a
    controlled command in for it stands in for the declaration and not for the
    stage.
    """
    graph = parse_dot_graph(text=_GRAPH_PATH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes[node]["script"]
    return script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH).replace(
        "{{ inputs.sandbox_check_suite }}", check_suite
    )


def _run_publish_draft(
    *, world: _World, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Execute the shipped `publish_draft` bytes in this world's clone.

    The environment is EXPLICIT rather than inherited, for the two reasons every
    stage-driving module here gives: the subprocess-spawn discipline requires
    it, and an inherited `LIVESPEC_*` from the enclosing factory run could
    satisfy a guard the case meant to exercise -- `LIVESPEC_RESUME_PUBLISHED_
    HEAD` above all. The gh-refresh root deliberately names a directory holding
    no helper, so every case takes the inline push fallback identically here and
    on a CI runner.
    """
    env = {
        "PATH": f"{world.forge_bin}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(world.clone.parent / "home"),
        "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
        "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(world.clone.parent / "no-gh-refresh"),
    }
    return subprocess.run(
        ["bash", "-c", _node_script(node="publish_draft", check_suite="true")],
        cwd=world.clone,
        capture_output=True,
        text=True,
        check=False,
        env=env if extra_env is None else {**env, **extra_env},
    )


def _commits_that_started_empty(*, world: _World, base: str, head: str) -> list[str]:
    """Every non-merge commit of `base..head` whose tree equals its parent's.

    Asked of each commit rather than inferred from a count, for the reason the
    module docstring gives: a count cannot tell a dropped empty from an
    incoming commit that replaced it.
    """
    listed = _git("rev-list", "--no-merges", f"{base}..{head}", cwd=world.clone).stdout.split()
    empty: list[str] = []
    for commit in listed:
        touched = _git(
            "diff-tree", "--no-commit-id", "--name-only", "-r", commit, cwd=world.clone
        ).stdout.strip()
        if not touched:
            empty.append(commit)
    return empty


def _published_empties(*, world: _World) -> list[str]:
    """The empty commits the PUBLISHED branch carries above the default branch.

    Read from origin's own ref rather than from the clone's HEAD: the claim is
    about what GitHub would be asked to rebase-merge, and a stage that rewrote
    its working branch without pushing it would satisfy a HEAD-side assertion
    while the pull request carried every empty commit it started with.
    """
    published = world.remote_head(ref=_BRANCH)
    assert published, "origin carries no publish branch, so nothing was published"
    _ = _git("fetch", "--quiet", "origin", _DEFAULT_BRANCH, cwd=world.clone)
    base = _git(
        "merge-base", published, f"origin/{_DEFAULT_BRANCH}", cwd=world.clone
    ).stdout.strip()
    return _commits_that_started_empty(world=world, base=base, head=published)


def test_a_first_publication_drops_the_engine_s_empty_checkpoint_commits(
    tmp_path: Path,
) -> None:
    """The ordinary first publication: an advanced default, and no empty survives.

    FOUR INSTRUMENTS, because "no empty commit" alone is satisfied by a stage
    that published nothing at all. The run's real work must still be on the
    published branch, the published tip must be what the clone now holds, the
    publication record must name that tip (or `pr` compares the pull request
    against a head nothing published), and the branch must contain the advanced
    default -- which is the refresh this stage existed for before any of this.

    The fixture's empties BRACKET the work rather than trailing it, so a rebase
    that dropped only what came after the last real commit cannot pass.
    """
    world = _petri_run(root=tmp_path)
    before = _commits_that_started_empty(world=world, base=f"origin/{_DEFAULT_BRANCH}", head="HEAD")
    assert len(before) == 2, "the fixture does not carry the engine's empty commits"
    advanced = _advance_default(world=world)

    result = _run_publish_draft(world=world)

    assert result.returncode == 0, result.stderr
    assert _published_empties(world=world) == []
    published = world.remote_head(ref=_BRANCH)
    assert published == world.head()
    assert world.state(name=PUBLISH_HEAD_STATE_FILENAME) == f"{published}\n"
    assert _git("show", f"{published}:{_OWNED_FILE}", cwd=world.clone).stdout == "this run's work\n"
    contains = subprocess.run(
        ["git", "merge-base", "--is-ancestor", advanced, published],
        cwd=world.clone,
        check=False,
        capture_output=True,
        text=True,
        env=_fixture_env(),
    )
    assert contains.returncode == 0, "the published head does not contain the advanced default"


def test_an_unmoved_default_branch_still_drops_the_empty_checkpoint_commits(
    tmp_path: Path,
) -> None:
    """The arm `--no-keep-empty` alone cannot reach, and the common case.

    A rebase onto an upstream the branch already contains is a NO-OP unless
    `--force-rebase` is passed, so without it this publication keeps every
    empty commit the engine minted -- and a first publication taken minutes
    after the clone is exactly the dispatch whose default branch has not moved.
    Without this case, "the empties are dropped" is evidence only about a
    repository whose default branch happened to advance mid-run.

    The default branch is asserted UNMOVED rather than merely left alone, since
    a fixture that had advanced it would pass through the case above's arm and
    report this one green.
    """
    world = _petri_run(root=tmp_path)
    _ = _git("fetch", "--quiet", "origin", _DEFAULT_BRANCH, cwd=world.clone)
    base = _git("rev-parse", f"origin/{_DEFAULT_BRANCH}", cwd=world.clone).stdout.strip()
    assert (
        _git("merge-base", "HEAD", f"origin/{_DEFAULT_BRANCH}", cwd=world.clone).stdout.strip()
        == base
    ), "the fixture's default branch has advanced, so this is not the unmoved arm"

    result = _run_publish_draft(world=world)

    assert result.returncode == 0, result.stderr
    assert _published_empties(world=world) == []
    published = world.remote_head(ref=_BRANCH)
    assert published == world.head()
    assert _git("show", f"{published}:{_OWNED_FILE}", cwd=world.clone).stdout == "this run's work\n"
