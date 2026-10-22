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

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_carry_forward_program import (
    CARRY_FORWARD_PROGRAM_FILENAME,
    carry_forward_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    plugin_cache_gate_script,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    PUBLICATION_PUSH_PROGRAM_FILENAME,
    publication_push_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_state import (
    PUBLICATION_STATE_GIT_PATH,
    PUBLISH_HEAD_STATE_FILENAME,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_regeneration import (
    RECORD_FILE_PROGRAM_FILENAME,
    record_file_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    PUBLISH_HEAD_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
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
    (cwd / path).parent.mkdir(parents=True, exist_ok=True)
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
    mover = world.clone.parent / f"mover-{path.replace(chr(47), chr(45))}"
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


def _materialized_push_program(*, root: Path) -> Path:
    """A sandbox plugins root carrying the PRODUCTION exact-head push helper.

    Written from its own source rather than restated here, so the lease a
    republication performs is the lease the Dispatcher ships. The root reaches
    the stage through the env var the stage itself resolves.
    """
    plugins_root = root / "plugins"
    plugins_root.mkdir(parents=True, exist_ok=True)
    # The generated-record-file resolution rides the SAME prepare block as the
    # push program (bd-ib-ze7xxj), and a refreshing stage that cannot resolve it
    # fails closed before the repository-declared gate -- so a harness omitting
    # it would exercise that refusal on every case rather than the route under
    # test.
    _ = (plugins_root / RECORD_FILE_PROGRAM_FILENAME).write_text(
        record_file_program_source(), encoding="utf-8"
    )
    program = plugins_root / PUBLICATION_PUSH_PROGRAM_FILENAME
    _ = program.write_text(publication_push_program_source(), encoding="utf-8")
    program.chmod(0o700)
    return plugins_root


def _blob_identity(*, world: _World, head: str, path: str) -> str:
    """The blob one path carries at one commit, asked of git rather than of the tree.

    The decision's own measure of "the tree the proof observed is unchanged" is
    per-path rather than whole-tree, and it has to be: a refresh onto an
    advanced default branch brings that branch's own paths in, so the root tree
    differs on every refresh that did anything at all.
    """
    return _git("rev-parse", f"{head}:{path}", cwd=world.clone).stdout.strip()


def _ancestor_of(*, world: _World, earlier: str, later: str) -> bool:
    """Whether one commit is contained in another, asked of git rather than inferred."""
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", earlier, later],
            cwd=world.clone,
            check=False,
            capture_output=True,
            text=True,
            env=_fixture_env(),
        ).returncode
        == 0
    )


def test_a_review_fix_republish_drops_the_empties_above_the_published_tip(
    tmp_path: Path,
) -> None:
    """The preserve_remote_ancestry MERGE path, which no rebase flag can reach.

    On re-entry — every accepted review fix re-earns a green janitor and
    re-enters this stage — origin's publish tip is an ancestor of this run's
    HEAD, so the stage MERGES the current default tip rather than rebasing, to
    retain the already-published ancestry and keep the push fast-forward. A
    merge drops nothing, so the empty commits the engine minted since the last
    publication survive it: the flags that fix the first publication leave this
    path exactly as it was.

    THE PUBLISHED TIP IS ASSERTED STILL CONTAINED, which is what keeps this a
    repair of the merge path rather than its replacement. A stage that reached
    for the whole-branch rebase instead would publish a head with no empty
    commits and pass a weaker assertion, while having rewritten a tip the forge
    is already serving and a reviewer has already read.

    AND THE EXACT-HEAD PUSH HELPER IS WITHHELD, deliberately, as the instrument
    that proves the push stayed a FAST-FORWARD. Both a fast-forward and a lease
    move the ref to the same sha, so nothing in the final refs tells them apart;
    with no helper materialized, a stage that tried to lease fails closed before
    pushing anything.
    """
    world = _petri_run(root=tmp_path)
    _ = _advance_default(world=world)

    first = _run_publish_draft(world=world)
    assert first.returncode == 0, first.stderr
    published_first = world.remote_head(ref=_BRANCH)
    assert _published_empties(world=world) == []

    # The rest of the run, as the engine leaves it: a checkpoint per node, an
    # accepted review fix, and another checkpoint.
    _ = _checkpoint(cwd=world.clone, subject="fabro(run): proof_capture (succeeded)")
    _ = _commit(
        cwd=world.clone, path=_OWNED_FILE, text="the reviewer's fix\n", subject="fix: review fix"
    )
    _ = _checkpoint(cwd=world.clone, subject="fabro(run): janitor (succeeded)")
    assert (
        len(_commits_that_started_empty(world=world, base=published_first, head="HEAD")) == 2
    ), "the fixture carries no empty commits above the published tip"
    _ = _advance_default(world=world, path="second.txt", text="moved again\n")

    result = _run_publish_draft(world=world)

    assert result.returncode == 0, result.stderr
    assert _published_empties(world=world) == []
    republished = world.remote_head(ref=_BRANCH)
    assert republished == world.head()
    assert republished != published_first
    assert _ancestor_of(
        world=world, earlier=published_first, later=republished
    ), "the already-published tip was rewritten rather than preserved"
    assert world.state(name=PUBLISH_HEAD_STATE_FILENAME) == f"{republished}\n"
    assert (
        _git("show", f"{republished}:{_OWNED_FILE}", cwd=world.clone).stdout
        == "the reviewer's fix\n"
    )


def _anchored_run(*, root: Path) -> tuple[_World, str]:
    """A run whose ALREADY-PUBLISHED tip itself carries empty checkpoint commits.

    The shape a PR-anchored resume of pull request 3113 or 3114 reaches: that
    branch was published by a run of the pre-repair build, so the empties are
    inside the published ancestry rather than above it, and dropping them is a
    rewrite of a ref the forge is already serving. The resuming run's HEAD
    descends from that tip, so the stage reads it as its own and takes the
    preserve path.
    """
    world = _world(root=root)
    _ = _checkpoint(cwd=world.clone, subject="fabro(prior): dod_gate (succeeded)")
    _ = _commit(
        cwd=world.clone,
        path=_OWNED_FILE,
        text="work the prior run published\n",
        subject="feat: work",
    )
    _ = _checkpoint(cwd=world.clone, subject="fabro(prior): janitor (succeeded)")
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=world.clone)
    published = world.head()
    (world.clone / ".git" / PUBLICATION_STATE_GIT_PATH).mkdir(parents=True, exist_ok=True)
    _ = (world.state_dir() / PUBLISH_HEAD_STATE_FILENAME).write_text(
        f"{published}\n", encoding="utf-8"
    )
    _ = _checkpoint(cwd=world.clone, subject="fabro(resume): implement (succeeded)")
    _ = _commit(
        cwd=world.clone, path=_OWNED_FILE, text="the resumed run's work\n", subject="feat: resumed"
    )
    return world, published


def test_a_published_tip_carrying_empties_is_rewritten_under_an_explicit_lease(
    tmp_path: Path,
) -> None:
    """The arm the preserve path cannot serve, and the reason the lease exists.

    When the empties sit INSIDE the published ancestry — a resume anchored on a
    pull request the pre-repair build published, which is exactly pull requests
    3113 and 3114 — no amount of dropping above that tip reaches them, so
    preserving the ancestry and dropping the empties are incompatible. The
    guarantee wins: the stage refreshes onto the default tip, drops every empty
    commit, and republishes under an EXPLICIT lease against the tip it observed.

    THE TIP IS THIS RUN'S OWN BY MEASUREMENT, not by assumption, which is what
    keeps this narrow. The arm is reachable only where the observed tip is an
    ANCESTOR of this run's HEAD, so the history being rewritten is history this
    run contains; a foreign tip still fails closed on the unchanged sentinel.

    FOUR INSTRUMENTS, because "no empty commit" alone is satisfied by a stage
    that published nothing. The published branch must carry the resumed work,
    the record must name the republished head (or `pr` compares the pull
    request against a head nothing published), the old tip must NOT be
    contained — that is the rewrite, and its absence would mean the empties
    survived — and the stage must say on its own transcript which tip it leased
    against, so the rewrite is readable rather than inferred from a moved ref.
    """
    world, published = _anchored_run(root=tmp_path)
    assert (
        len(
            _commits_that_started_empty(
                world=world, base=f"origin/{_DEFAULT_BRANCH}", head=published
            )
        )
        == 2
    ), "the fixture's published tip carries no empty commits"
    plugins_root = _materialized_push_program(root=tmp_path)

    result = _run_publish_draft(
        world=world, extra_env={SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(plugins_root)}
    )

    assert result.returncode == 0, result.stderr
    assert _published_empties(world=world) == []
    republished = world.remote_head(ref=_BRANCH)
    assert republished == world.head()
    assert not _ancestor_of(world=world, earlier=published, later=republished)
    assert world.state(name=PUBLISH_HEAD_STATE_FILENAME) == f"{republished}\n"
    assert (
        _git("show", f"{republished}:{_OWNED_FILE}", cwd=world.clone).stdout
        == "the resumed run's work\n"
    )
    assert published in result.stderr


def test_a_published_tip_carrying_empties_fails_closed_without_the_lease_helper(
    tmp_path: Path,
) -> None:
    """The control that makes the arm above a LEASE rather than a bare force.

    Without this case, "the branch was republished without its empty commits"
    is equally consistent with a stage that force-pushed, which is the one
    thing the ratified clause forbids of a publication rewrite. The helper is
    the only route to an expected-object push, so withholding it must stop the
    stage before it writes anything — and origin's publish branch is asserted
    UNMOVED, because a refusal issued after the push would leave the same
    sentinel on stderr and a rewritten ref behind it.
    """
    world, published = _anchored_run(root=tmp_path)

    result = _run_publish_draft(
        world=world,
        extra_env={SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(tmp_path / "absent-plugins")},
    )

    assert result.returncode != 0, result.stdout
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_PROGRAM_ABSENT" in result.stderr
    assert world.remote_head(ref=_BRANCH) == published


# The four decision inputs `pr_refresh` records beside its changed marker, and
# that `pr_refresh_head` hands the carry-forward program. Spelled as LITERALS
# here because the package exports no names for them: a Red's test bytes are
# fixed across its Red-to-Green pair, so a top-level import of a name that does
# not exist would make the Red a collection error, which proves the name absent
# and nothing about the behaviour.
_PREVIOUS_HEAD_FILENAME = "livespec-pr-refresh-previous-head"
_PREVIOUS_BASE_FILENAME = "livespec-pr-refresh-previous-base"
_NEW_BASE_FILENAME = "livespec-pr-refresh-new-base"
_NEW_HEAD_FILENAME = "livespec-pr-refresh-new-head"

# The inert class the carry-forward decision derives from `plan/`, and the spec
# root the world declares. `SPEC` rather than this repository's own
# `SPECIFICATION`, so the classes derived from the declaration can only be right
# by having been READ.
_INERT_PATH = "plan/topic/note.md"
_SPEC_ROOT = "SPEC"

# The `gh` a `pr_refresh` needs: it reads whether the pull request carries an
# auto-merge request before it rebases (v145) and fails closed when it cannot.
# `null` is the state these cases are about -- the disarm itself is driven in
# `test_scripted_refresh_execution.py`.
_UNARMED_GH_LINES = ("#!/bin/sh", "printf 'null\\n'", "")

# The `gh` the DECISION needs: the pull request's comments going in, and the
# record it posts coming back out, captured so the verdict is read off the
# durable artifact rather than off stderr alone.
_DECISION_GH_LINES = (
    "#!/usr/bin/env python3",
    "import os, pathlib, sys",
    "argv = sys.argv[1:]",
    "if argv[:2] == ['pr', 'view']:",
    "    sys.stdout.write(pathlib.Path(os.environ['GH_COMMENTS']).read_text())",
    "    raise SystemExit(0)",
    "if argv[:2] == ['pr', 'comment']:",
    "    body = argv[argv.index('--body-file') + 1]",
    "    out = pathlib.Path(os.environ['GH_POSTED'])",
    "    target = out / (str(len(list(out.iterdir()))) + '.md')",
    "    target.write_text(pathlib.Path(body).read_text())",
    "    sys.stdout.write('https://forge.invalid/pull/3116#issuecomment-1\\n')",
    "    raise SystemExit(0)",
    "sys.stderr.write('unexpected gh invocation: ' + repr(argv))",
    "raise SystemExit(2)",
    "",
)


def _published_run(*, root: Path) -> tuple[_World, str]:
    """A run whose publish branch is already published, with empties above it.

    The state a `pr_refresh` is entered in: `publish_draft` pushed a head, and
    the engine has checkpointed once per node since -- `proof_capture` and
    `proof_verify` -- so HEAD carries empty commits the published tip does not.
    That is the shape whose empties `pr_refresh` is the only stage positioned to
    drop, because publication has already happened by the time they exist.

    The world also declares a spec root and carries an inert-classed path, so
    the SAME fixture can be handed to the carry-forward decision.
    """
    world = _world(root=root)
    _ = _commit(
        cwd=world.clone,
        path=".livespec.jsonc",
        text='{\n  // a comment\n  "spec_root": "' + _SPEC_ROOT + '"\n}\n',
        subject="chore: declare the spec root",
    )
    _ = _commit(
        cwd=world.clone, path=_OWNED_FILE, text="this run's work\n", subject="feat: the run's work"
    )
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=world.clone)
    published = world.head()
    world.state_dir().mkdir(parents=True, exist_ok=True)
    _ = (world.state_dir() / PUBLISH_HEAD_STATE_FILENAME).write_text(
        f"{published}\n", encoding="utf-8"
    )
    _ = _checkpoint(cwd=world.clone, subject="fabro(run): proof_capture (succeeded)")
    _ = _checkpoint(cwd=world.clone, subject="fabro(run): proof_verify (succeeded)")
    return world, published


def _refresh_plugins_root(*, root: Path) -> Path:
    """The sandbox plugins root `pr_refresh` resolves, carrying both helpers.

    The exact-head push program AND the plugin-cache gate, each written from its
    own production source. The gate's own prepare-step body is RUN here, which
    records this case's plugin pin -- so the stage's later re-entry is the
    ENFORCEMENT arm rather than a first recording, and a gate that refused would
    stop the refresh before its push.
    """
    plugins_root = _materialized_push_program(root=root)
    gate_script = root / "install-plugin-gate.sh"
    _ = gate_script.write_text(plugin_cache_gate_script(), encoding="utf-8")
    _ = subprocess.run(
        ["bash", str(gate_script)],
        check=True,
        capture_output=True,
        text=True,
        env={
            **_fixture_env(),
            SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(plugins_root),
            "HOME": str(root / "home"),
        },
    )
    return plugins_root


def _run_pr_refresh(*, world: _World, plugins_root: Path) -> subprocess.CompletedProcess[str]:
    """Execute the shipped `pr_refresh` bytes in this world's clone."""
    bin_dir = world.clone.parent / "refresh-bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    _ = gh.write_text("\n".join(_UNARMED_GH_LINES), encoding="utf-8")
    gh.chmod(0o755)
    return subprocess.run(
        ["bash", "-c", _node_script(node="pr_refresh", check_suite="true")],
        cwd=world.clone,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{bin_dir}:/usr/local/bin:/usr/bin:/bin",
            "HOME": str(world.clone.parent / "home"),
            "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
            "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(world.clone.parent / "no-gh-refresh"),
            SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(plugins_root),
        },
    )


def _verified_record(*, world: _World, head: str) -> str:
    """One `verified` Proof of Done record the carry-forward decision can read.

    Its single reproduction step is a direct read of the one path the ITEM
    changed, with the read identity taken from the working tree AFTER the
    refresh -- which is the comparison the decision makes, so taking it any
    earlier would assert against a file the stage had already re-materialized.
    """
    identity = _git("hash-object", "--no-filters", _OWNED_FILE, cwd=world.clone).stdout.strip()
    return "\n".join(
        [
            "Proof of Done — verified — run run-1 — 2026-10-16T00:00:00Z",
            "",
            f"{PUBLISH_HEAD_LABEL}: {head}",
            "Working directory: .",
            f"Read: {_OWNED_FILE} {identity}",
            "",
            "## Assertion 1 — the owned file says what it says.",
            "",
            f"1. Run `cat {_OWNED_FILE}`.",
            "",
            "```",
            "this run's work",
            "```",
            "",
        ]
    )


def _run_carry_forward_decision(
    *, world: _World, root: Path, record: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run the decision program as `pr_refresh_head` runs it, over the refresh's own state.

    The four inputs are READ OFF the state files `pr_refresh` wrote rather than
    recomputed here: the claim is about the decision the stage's own refresh
    leads to, and a test that supplied its own heads would be grading a refresh
    it had described rather than the one that happened.
    """
    program = root / CARRY_FORWARD_PROGRAM_FILENAME
    _ = program.write_text(carry_forward_program_source(), encoding="utf-8")
    bin_dir = root / "decision-bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    _ = gh.write_text("\n".join(_DECISION_GH_LINES), encoding="utf-8")
    gh.chmod(0o755)
    comments = root / "comments.json"
    _ = comments.write_text(json.dumps({"comments": [{"url": "u", "body": record}]}), "utf-8")
    posted_dir = root / "posted"
    posted_dir.mkdir(exist_ok=True)
    inputs = {
        "--previous-head": _PREVIOUS_HEAD_FILENAME,
        "--previous-base": _PREVIOUS_BASE_FILENAME,
        "--new-base": _NEW_BASE_FILENAME,
        "--new-head": _NEW_HEAD_FILENAME,
    }
    argv: list[str] = [
        sys.executable,
        str(program),
        "--pull-request",
        "3116",
        "--default-branch",
        _DEFAULT_BRANCH,
    ]
    for flag, filename in inputs.items():
        recorded = world.state(name=filename)
        assert recorded is not None, f"pr_refresh recorded no {filename}"
        argv.extend([flag, recorded.strip()])
    result = subprocess.run(
        argv,
        cwd=world.clone,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{bin_dir}:/usr/local/bin:/usr/bin:/bin",
            "HOME": str(root / "home"),
            "GH_COMMENTS": str(comments),
            "GH_POSTED": str(posted_dir),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        },
    )
    return result, [path.read_text(encoding="utf-8") for path in sorted(posted_dir.iterdir())]


def test_pr_refresh_republishes_without_the_empty_commits_it_inherited(
    tmp_path: Path,
) -> None:
    """The third refresh site, and the only one positioned to reach these empties.

    By the time `pr_refresh` runs, the branch has been published and the engine
    has checkpointed once per node since — so the empties above the published
    tip exist only after publication, and no earlier stage can drop them. This
    stage's rebase is the one that can, and it is already a REWRITING stage: it
    republishes under an explicit lease, so dropping the empties costs it no new
    capability.

    FIVE INSTRUMENTS. The published branch must carry no empty commit and must
    still carry the run's work; origin's publish branch must be what the clone
    now holds; the publication record must be rewritten to it, or the NEXT
    refresh refuses its own push as foreign; and the changed marker must be set,
    or `pr_refresh_head` routes a rewritten head to `pr` on proof of the old one.
    """
    world, published = _published_run(root=tmp_path)
    plugins_root = _refresh_plugins_root(root=tmp_path)
    assert (
        len(_commits_that_started_empty(world=world, base=published, head="HEAD")) == 2
    ), "the fixture carries no empty commits above the published tip"
    advanced = _advance_default(world=world, path=_INERT_PATH, text="a plan note\n")

    result = _run_pr_refresh(world=world, plugins_root=plugins_root)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_REFRESH_CHANGED" in result.stderr
    assert _published_empties(world=world) == []
    republished = world.remote_head(ref=_BRANCH)
    assert republished == world.head()
    assert republished != published
    assert (
        _git("show", f"{republished}:{_OWNED_FILE}", cwd=world.clone).stdout == "this run's work\n"
    )
    assert world.state(name=PUBLISH_HEAD_STATE_FILENAME) == f"{republished}\n"
    assert _ancestor_of(world=world, earlier=advanced, later=republished)


def test_a_refresh_that_only_dropped_empty_commits_carries_the_proof_forward(
    tmp_path: Path,
) -> None:
    """The rewritten head is still the tree the proof was verified on.

    Dropping the empties makes the refresh REWRITE every commit of the run,
    which is exactly the shape a carry-forward decision could mistake for new
    work: the head differs, the previous published head is no longer contained,
    and nothing about the shas says the tree is unchanged. The decision has to
    reach `carried_forward` anyway, from the readings rather than the shas — the
    patch identity of the item's own diff, the blob of every observed path, the
    recorded read identity against the new working tree, and the replay.

    THE DECISION RUNS OVER THE REFRESH'S OWN STATE FILES, not over heads this
    case computed, so the claim is about the refresh that happened. Each half of
    the premise is asserted independently of the verdict, because "it carried
    forward" over work that had genuinely changed would be the wrong answer
    reached for the wrong reason: the republished branch carries no empty
    commit, the path the proof observed carries the same blob it did at the
    verified head, and the verified head is no longer contained -- which is the
    rewrite, and without it there would be nothing for the decision to survive.

    THE PREMISE IS PER-PATH AND NOT WHOLE-TREE, which is not a weakening. A
    refresh onto an advanced default branch brings that branch's own paths into
    the tree, so the root tree differs on every refresh that did anything; the
    question the decision answers is whether the incoming commits could have
    affected what the proof OBSERVED, and the observed path's blob is that
    question's own instrument.
    """
    world, published = _published_run(root=tmp_path)
    plugins_root = _refresh_plugins_root(root=tmp_path)
    _ = _advance_default(world=world, path=_INERT_PATH, text="a plan note\n")

    refresh = _run_pr_refresh(world=world, plugins_root=plugins_root)
    assert refresh.returncode == 0, refresh.stderr
    assert _published_empties(world=world) == []
    republished = world.head()
    assert _blob_identity(world=world, head=published, path=_OWNED_FILE) == _blob_identity(
        world=world, head=republished, path=_OWNED_FILE
    ), "the refresh changed the observed path, so this is not the drop-only case"
    assert not _ancestor_of(world=world, earlier=published, later=republished)

    decision, posted = _run_carry_forward_decision(
        world=world, root=tmp_path, record=_verified_record(world=world, head=published)
    )

    assert decision.returncode == 0, decision.stderr
    assert "LIVESPEC_CARRY_FORWARD_CARRIED" in decision.stderr
    assert len(posted) == 1
    assert "Decision: carried_forward" in posted[0]
    assert f"{PUBLISH_HEAD_LABEL}: {republished}" in posted[0]
