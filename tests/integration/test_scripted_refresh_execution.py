"""Run the `pr_refresh` stage's OWN script bytes against real Git and a real remote.

WHY THIS FILE EXISTS, AND WHY IT IS NOT A DECLARATION TEST.
`test_scripted_publication_stages.py` grades which KIND of stage publishes, which
is a property of the committed payload. `test_scripted_publication_execution.py`
grades what the `pr` node DOES. Neither reaches `pr_refresh`, and `pr_refresh` is
the one stage the ratified clause grants a REWRITING capability: it rebases the
publish branch and pushes it under a lease. Every guard around that capability --
the recorded-versus-remote ownership test, the non-numeric-counter fail-closed,
the three-refresh bound, the conflict abort, the post-rebase gate, and the lease
itself -- is shell, and a substring assertion cannot tell a guard that RUNS from
one that is dead code behind an earlier `exit`.

So each control below executes the shipped bytes and then asserts what happened
to a REAL remote.

THE SCRIPT BYTES ARE READ THROUGH THE CANONICAL PARSER, NEVER RETYPED, with
`parse_dot_graph` -- the same reader the Dispatcher's own graph consumers use. A
test carrying its own copy of the recipe would pass while the shipped stage did
something else, which is the specific failure this work-item's recovery review
called out.

WHAT IS SIMULATED, AND WHY EACH SUBSTITUTION IS SAFE.

- `{{ inputs.default_branch }}` and `{{ inputs.sandbox_check_suite }}` are
  substituted here because the pinned ENGINE owns that templating, not this
  repository. The check suite is a per-repository DECLARATION -- an arbitrary
  command the governed repo names -- so standing a controlled script in for it
  is standing in for the declaration, not for the stage. Nothing else in the
  bytes is touched, and in particular the fetch, the `ls-remote`, the rebase, the
  plugin gate and the leased push all run for real.
- ORIGIN IS A REAL LOCAL BARE REPOSITORY and the clone is a real `git clone` of
  it, because the questions are about refs: whether the branch moved, whether a
  lease rejects, whether anything was pushed at all. A double cannot answer any
  of those, and the claim this file exists to establish is precisely that the
  shell reaches the right ref operations.
- THE THREE MATERIALIZED HELPERS ARE THE PRODUCTION ONES. The plugin-cache gate,
  the exact-head push program and (for the state filenames) the publication-state
  module are imported and written from their own sources, so the lease the push
  performs is the lease the Dispatcher ships rather than one restated here.

THE ENCLOSING RUN'S STATE IS NEVER TOUCHED. Each control builds its own
throwaway origin, clone and plugins root under `tmp_path`, and the stage resolves
its state directory inside THAT clone's `$GIT_DIR`. This matters more here than
anywhere else in the tree: `pr_refresh` runs `sandbox_check_suite` -- this very
suite -- as its post-rebase gate, in the same sandbox, AFTER establishing its
provenance. A control writing state at a fixed shared path would erase the live
refresh counter of the stage running it, letting the next refresh restart at one
and evade the three-refresh bound.
`test_the_refresh_execution_boundary_leaves_enclosing_run_state_intact` is the
regression control for that property.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import render_run_config_overlay
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    PLUGIN_GATE_PROGRAM_FILENAME,
    plugin_cache_gate_script,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    PUBLICATION_PUSH_PROGRAM_FILENAME,
    publication_push_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_state import (
    PUBLICATION_STATE_GIT_PATH,
    PUBLISH_HEAD_STATE_FILENAME,
    REFRESH_CHANGED_STATE_FILENAME,
    REFRESH_COUNT_STATE_FILENAME,
    publication_state_filenames,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import resume_checkout_for
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IMPLEMENT_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

_BRANCH = "feat/bd-ib-c3txja"
_DEFAULT_BRANCH = "master"
# The file the publish branch owns. A conflict is arranged by moving the DEFAULT
# branch's copy of this same path, which is the real shape of the conflict the
# stage must abort rather than resolve.
_OWNED_FILE = "owned.txt"
_SHARED_FILE = "shared.txt"


# The coverage hooks an allowlisted spawn must scrub, so no child of this file
# self-instruments and races the concurrent coverage run. Git itself ignores
# them, but the fixture git calls below are the only place in this module that
# inherits the parent environment at all, and the obligation is on the FILE.
_COVERAGE_ENV_PREFIXES = ("COVERAGE_PROCESS_START", "COV_CORE_")


def _fixture_git_env() -> dict[str, str]:
    """The fixture environment, coverage-scrubbed, with an explicit git identity.

    The identity is stated rather than inherited because a control must not
    depend on whatever `user.name` the executing machine carries -- the factory
    sandbox carries one that differs from a developer's, and a commit with no
    identity at all fails outright.
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
        env=_fixture_git_env(),
    )


def _refresh_script(*, check_suite: str) -> str:
    """The shipped `pr_refresh` node's script, with only the engine's own tokens bound."""
    graph = parse_dot_graph(text=_IMPLEMENT_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script = graph.nodes["pr_refresh"]["script"]
    return script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH).replace(
        "{{ inputs.sandbox_check_suite }}", check_suite
    )


@dataclass(frozen=True, kw_only=True)
class _Refresh:
    """One control's throwaway world: a real origin, a real clone, real helpers."""

    origin: Path
    clone: Path
    plugins_root: Path
    gate_script: Path

    def state_dir(self) -> Path:
        return self.clone / ".git" / PUBLICATION_STATE_GIT_PATH

    def remote_head(self, *, ref: str) -> str:
        """Origin's own answer for one ref, or the empty string when it holds none."""
        listed = subprocess.run(
            ["git", "ls-remote", "--heads", str(self.origin), f"refs/heads/{ref}"],
            check=True,
            capture_output=True,
            text=True,
            env=_fixture_git_env(),
        )
        return listed.stdout.split("\t")[0] if listed.stdout.strip() else ""

    def local_head(self) -> str:
        return _git("rev-parse", "HEAD", cwd=self.clone).stdout.strip()

    def state(self, *, name: str) -> str | None:
        path = self.state_dir() / name
        return path.read_text(encoding="utf-8") if path.is_file() else None


def _commit(*, cwd: Path, path: str, text: str, subject: str) -> str:
    """Write one file and commit it, returning the resulting head.

    Every fixture mutation in this module is this shape, and `git commit`
    refuses outright without an identity, so the `config` pair rides here rather
    than being remembered at each site.
    """
    _ = _git("config", "user.email", "t@example.invalid", cwd=cwd)
    _ = _git("config", "user.name", "Test", cwd=cwd)
    _ = (cwd / path).write_text(text, encoding="utf-8")
    _ = _git("add", path, cwd=cwd)
    _ = _git("commit", "--quiet", "-m", subject, cwd=cwd)
    return _git("rev-parse", "HEAD", cwd=cwd).stdout.strip()


def _origin_with_default(*, root: Path) -> Path:
    """A bare origin whose default branch carries the shared file."""
    origin = root / "origin.git"
    _ = origin.mkdir(parents=True)
    _ = _git("init", "--bare", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=origin)
    seed = root / "seed"
    _ = seed.mkdir()
    _ = _git("init", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=seed)
    _ = _commit(cwd=seed, path=_SHARED_FILE, text="base\n", subject="chore: seed")
    _ = _git("push", "--quiet", str(origin), f"HEAD:refs/heads/{_DEFAULT_BRANCH}", cwd=seed)
    return origin


def _materialized_plugins_root(*, root: Path) -> Path:
    """The sandbox plugins root, carrying the two PRODUCTION helpers.

    The push program is written from its own source and the gate from its own
    prepare-step body, so the lease the stage performs is the lease the
    Dispatcher ships rather than one restated here.
    """
    plugins_root = root / "plugins"
    _ = plugins_root.mkdir()
    push_program = plugins_root / PUBLICATION_PUSH_PROGRAM_FILENAME
    _ = push_program.write_text(publication_push_program_source(), encoding="utf-8")
    push_program.chmod(0o700)
    gate_script = root / "install-plugin-gate.sh"
    _ = gate_script.write_text(plugin_cache_gate_script(), encoding="utf-8")
    return plugins_root


def _build(*, root: Path) -> _Refresh:
    """An origin carrying `master` and the publish branch, and a clone on the branch.

    The clone's HEAD is the publish branch's tip and origin's copy of that branch
    is the same object, so the recorded provenance written below is TRUE -- which
    is what makes every departure a control arranges the one thing under test.

    Running the gate's own body here also records this control's plugin pin,
    which is what makes the stage's later re-entry the ENFORCEMENT arm rather
    than a first recording.
    """
    origin = _origin_with_default(root=root)
    clone = root / "clone"
    _ = _git("clone", "--quiet", str(origin), str(clone), cwd=root)
    _ = _commit(
        cwd=clone, path=_OWNED_FILE, text="this run's work\n", subject="feat: this run's work"
    )
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=clone)
    gate_script = root / "install-plugin-gate.sh"
    box = _Refresh(
        origin=origin,
        clone=clone,
        plugins_root=_materialized_plugins_root(root=root),
        gate_script=gate_script,
    )
    box.state_dir().mkdir(parents=True)
    _ = (box.state_dir() / PUBLISH_HEAD_STATE_FILENAME).write_text(
        box.local_head(), encoding="utf-8"
    )
    _ = subprocess.run(
        ["bash", str(gate_script)],
        check=True,
        capture_output=True,
        text=True,
        env=_env(box=box),
    )
    return box


def _env(*, box: _Refresh, extra: dict[str, str] | None = None) -> dict[str, str]:
    """The child environment, EXPLICIT rather than inherited.

    The subprocess-spawn allowlist requires it, and it also keeps a control
    honest: an inherited `LIVESPEC_*` from the enclosing factory run could
    satisfy a guard the control meant to exercise -- `LIVESPEC_RESUME_PUBLISHED_
    HEAD` above all, which is the fallback the no-provenance control asserts.
    """
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(box.clone.parent / "home"),
        "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
        SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(box.plugins_root),
    }
    return env if extra is None else {**env, **extra}


def _advance_default(*, box: _Refresh, path: str = _SHARED_FILE, text: str = "moved\n") -> str:
    """Move origin's default branch, as another merge to it would.

    Performed through a SEPARATE clone so the control's own clone learns nothing
    about the movement until the stage's own fetch -- which is the state a real
    dispatch is in when the default branch advances underneath it.
    """
    mover = box.clone.parent / f"mover-{path}-{len(text)}"
    _ = _git("clone", "--quiet", str(box.origin), str(mover), cwd=box.clone.parent)
    advanced = _commit(cwd=mover, path=path, text=text, subject=f"feat: advance {path}")
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_DEFAULT_BRANCH}", cwd=mover)
    return advanced


def _branch_clone(*, box: _Refresh, name: str) -> Path:
    """A second clone sitting on the publish branch, for a control that moves it."""
    other = box.clone.parent / name
    _ = _git("clone", "--quiet", str(box.origin), str(other), cwd=box.clone.parent)
    _ = _git("checkout", "--quiet", "-B", _BRANCH, f"origin/{_BRANCH}", cwd=other)
    return other


_PASSING_GATE = "true"
_FAILING_GATE = "false"


def _run(
    *,
    box: _Refresh,
    check_suite: str = _PASSING_GATE,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", _refresh_script(check_suite=check_suite)],
        cwd=box.clone,
        capture_output=True,
        text=True,
        check=False,
        env=_env(box=box, extra=extra_env),
    )


def test_an_advanced_default_is_rebased_gated_and_republished_under_a_lease(
    tmp_path: Path,
) -> None:
    """The one path that REWRITES, end to end, asserted on origin's own refs.

    Four things have to hold together and each is separately satisfiable while
    the requirement is unmet: origin's publish branch must now carry the rebased
    head, that head must contain the advanced default, the recorded provenance
    must have been rewritten to it (or the NEXT refresh refuses its own push as
    foreign), and the changed marker must be set (or `pr_refresh_head` routes a
    rebased head to `pr` on proof of the old one).
    """
    box = _build(root=tmp_path)
    before = box.remote_head(ref=_BRANCH)
    advanced = _advance_default(box=box)

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_REFRESH_CHANGED" in result.stderr
    republished = box.remote_head(ref=_BRANCH)
    assert republished != before, "origin still carries the pre-rebase head"
    assert republished == box.local_head()
    contains = subprocess.run(
        ["git", "merge-base", "--is-ancestor", advanced, republished],
        cwd=box.clone,
        check=False,
        capture_output=True,
        text=True,
        env=_fixture_git_env(),
    )
    assert contains.returncode == 0, "the republished head does not contain the advanced default"
    assert box.state(name=PUBLISH_HEAD_STATE_FILENAME) == f"{republished}\n"
    assert box.state(name=REFRESH_COUNT_STATE_FILENAME) == "1\n"
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) == ""


def test_an_unchanged_default_owes_no_rebase_and_pushes_nothing(tmp_path: Path) -> None:
    """The common path: the publish head already contains the default, so stop.

    Asserted on the ABSENCE of the changed marker as well as on the sentinel,
    because `pr_refresh_head` reads only the marker -- a stage that reported
    unchanged while leaving a marker behind would still route to `proof_capture`.
    """
    box = _build(root=tmp_path)
    before = box.remote_head(ref=_BRANCH)

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_REFRESH_UNCHANGED" in result.stderr
    assert box.remote_head(ref=_BRANCH) == before
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None
    assert box.state(name=REFRESH_COUNT_STATE_FILENAME) is None


def test_a_foreign_remote_publish_head_is_refused_before_any_rewrite(tmp_path: Path) -> None:
    """A publish branch someone else moved is not this run's to lease over.

    The default branch is advanced TOO, so the stage would otherwise have real
    work to do: without that, a build whose ownership test never ran would exit
    on the unchanged arm and look identical to one that refused.
    """
    box = _build(root=tmp_path)
    foreign = _branch_clone(box=box, name="foreign")
    _ = _commit(
        cwd=foreign, path="foreign.txt", text="not this run\n", subject="feat: a foreign change"
    )
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=foreign)
    _ = _advance_default(box=box)
    foreign_head = box.remote_head(ref=_BRANCH)

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_REFRESH_FOREIGN_HEAD" in result.stderr
    assert box.remote_head(ref=_BRANCH) == foreign_head, "the foreign head was overwritten"
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None


def test_an_absent_remote_publish_ref_is_refused(tmp_path: Path) -> None:
    """A branch origin no longer carries is not recreated from a local tree.

    The sentinel asserted is the FETCH's -- `LIVESPEC_PR_REFRESH_ORIGIN_
    UNOBSERVABLE` -- rather than the dedicated remote-ref-unknown one, because
    the fetch names both refs and fails first. That attribution imprecision was
    raised as an ADVISORY finding on this work-item and was not accepted, so the
    control asserts what the shipped stage DOES rather than what a reworded
    version would; the load-bearing half either way is that it fails closed and
    rewrites nothing.
    """
    box = _build(root=tmp_path)
    _ = _git("push", "--quiet", "origin", "--delete", f"refs/heads/{_BRANCH}", cwd=box.clone)

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_REFRESH_ORIGIN_UNOBSERVABLE" in result.stderr
    assert box.remote_head(ref=_BRANCH) == "", "a deleted publish branch was recreated"


def test_a_run_with_no_recorded_provenance_refuses_before_touching_any_ref(
    tmp_path: Path,
) -> None:
    """With nothing recorded and no validated resume head, there is nothing to own."""
    box = _build(root=tmp_path)
    (box.state_dir() / PUBLISH_HEAD_STATE_FILENAME).unlink()
    before = box.remote_head(ref=_BRANCH)
    _ = _advance_default(box=box)

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_REFRESH_NO_PROVENANCE" in result.stderr
    assert box.remote_head(ref=_BRANCH) == before


@pytest.mark.parametrize("advance_default", [False, True])
def test_a_validated_resume_head_supplies_the_provenance_the_record_lacks(
    *,
    tmp_path: Path,
    advance_default: bool,
) -> None:
    """Resume through the Dispatcher's checkout and environment, with no saved head.

    The old control supplied the fallback variable by hand, so it passed while
    every real resume failed. Start this clone on the default branch instead,
    execute the rendered prepare step, and give the stage only the environment
    the overlay actually emits. Both refresh outcomes must accept that provenance.
    """
    box = _build(root=tmp_path)
    recorded = box.local_head()
    (box.state_dir() / PUBLISH_HEAD_STATE_FILENAME).unlink()
    if advance_default:
        _ = _advance_default(box=box)
    _ = _git("checkout", "--detach", "origin/master", cwd=box.clone)
    assert box.local_head() != recorded
    overlay = render_run_config_overlay(
        committed_text='[workflow]\ngraph = "workflow.fabro"\n[run.environment]\nid = "sandbox"\n',
        workflow_dir=tmp_path,
        token="",
        github_token="",
        siblings=None,
        resume_checkout=resume_checkout_for(
            args=argparse.Namespace(resume_head=recorded),
            branch=_BRANCH,
        ),
    )
    assert overlay is not None
    parsed = tomli.loads(overlay)
    overlay_env = parsed["environments"]["sandbox"]["env"]
    [checkout_step] = [
        step["script"]
        for step in parsed["run"]["prepare"]["steps"]
        if "git checkout --detach" in step["script"]
    ]
    prepared = subprocess.run(
        ["bash", "-c", checkout_step],
        cwd=box.clone,
        check=False,
        capture_output=True,
        text=True,
        env=_env(box=box, extra=overlay_env),
    )
    assert prepared.returncode == 0, prepared.stderr
    assert box.local_head() == recorded
    assert box.state(name=PUBLISH_HEAD_STATE_FILENAME) is None
    assert box.remote_head(ref=_BRANCH) == recorded

    result = _run(box=box, extra_env=overlay_env)

    assert result.returncode == 0, result.stderr
    outcome = "CHANGED" if advance_default else "UNCHANGED"
    assert f"LIVESPEC_PR_REFRESH_{outcome}" in result.stderr
    assert "LIVESPEC_PR_REFRESH_NO_PROVENANCE" not in result.stderr
    assert box.remote_head(ref=_BRANCH) == box.local_head()


def test_a_conflicting_rebase_is_aborted_with_no_side_chosen(tmp_path: Path) -> None:
    """A conflict preserves the run tree; it does not pick a winner.

    Three instruments, because "it exited 1" is cheap. The rebase must be ABORTED
    (no in-progress rebase directory left, which would wedge every later stage),
    HEAD must be back at the head this run published, and the conflicted file
    must carry no merge markers -- the shape a build that resolved by taking one
    side would leave.

    SINCE v134 THE SENTINEL IS THE REPAIR ONE rather than
    `LIVESPEC_PR_REFRESH_CONFLICT`: a conflicted refresh now restores its
    published head and routes to the `fix` node, and that fail-closed sentinel is
    reached only once the two-round repair budget is spent. Every property this
    case was written for is unchanged and is exactly what the repair depends on --
    the abort, the restored head and the unresolved file -- so all three are
    asserted as before. The repair's own accounting is bound in
    `test_workflow_refresh_repair_scenario176.py`.
    """
    box = _build(root=tmp_path)
    published = _commit(
        cwd=box.clone,
        path=_SHARED_FILE,
        text="this run's edit\n",
        subject="feat: edit the shared file",
    )
    _ = _git("push", "--quiet", "--force", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=box.clone)
    _ = (box.state_dir() / PUBLISH_HEAD_STATE_FILENAME).write_text(published, encoding="utf-8")
    _ = _advance_default(box=box, text="a conflicting default edit\n")

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_REFRESH_REPAIR" in result.stderr
    assert box.local_head() == published, "the aborted rebase left HEAD somewhere else"
    assert not (box.clone / ".git" / "rebase-merge").exists()
    assert not (box.clone / ".git" / "rebase-apply").exists()
    assert "<<<<<<<" not in (box.clone / _SHARED_FILE).read_text(encoding="utf-8")
    assert box.remote_head(ref=_BRANCH) == published
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None


def test_a_failing_post_rebase_gate_pushes_nothing(tmp_path: Path) -> None:
    """The gate is a PRECONDITION of the push, not a report alongside it.

    The rebase has already happened when the gate runs, so the discriminating
    assertion is about ORIGIN: a build that pushed first and gated afterwards
    would leave the rebased head published and exit non-zero all the same.
    """
    box = _build(root=tmp_path)
    before = box.remote_head(ref=_BRANCH)
    _ = _advance_default(box=box)

    result = _run(box=box, check_suite=_FAILING_GATE)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_REFRESH_REPAIR" in result.stderr
    assert box.remote_head(ref=_BRANCH) == before, "a failed gate still published"
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None
    assert box.state(name=PUBLISH_HEAD_STATE_FILENAME) == before
    # The refresh COUNT does move, and that is v134's own requirement rather than
    # a relaxation of this case: the bound counts each visit that refreshed onto
    # an advanced default whether the refresh succeeded or routed to repair, so a
    # repaired refresh that left the counter alone would let a run alternate
    # repair and refresh past the bound forever.
    assert box.state(name=REFRESH_COUNT_STATE_FILENAME) == "1\n"


def test_a_remote_moving_after_observation_is_rejected_by_the_lease(tmp_path: Path) -> None:
    """The lease is what makes the one rewriting capability safe, so it is driven.

    The expected object is read BEFORE the rebase and the gate, so a check suite
    that moves origin's publish branch reproduces exactly the window the lease
    exists to close -- without needing to interleave two processes. A bare force
    push, or a lease carrying an empty expected object, would succeed here.
    """
    box = _build(root=tmp_path)
    mover = _branch_clone(box=box, name="lease-mover")
    late = _commit(
        cwd=mover, path="late.txt", text="landed mid-gate\n", subject="feat: land mid-gate"
    )
    racing_gate = box.clone.parent / "racing-gate.sh"
    _ = racing_gate.write_text(
        f'git -C "{mover}" push --quiet origin "HEAD:refs/heads/{_BRANCH}"\n',
        encoding="utf-8",
    )
    _ = _advance_default(box=box)

    result = _run(box=box, check_suite=f'bash "{racing_gate}"')

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_REFRESH_LEASE_FAILED" in result.stderr
    assert box.remote_head(ref=_BRANCH) == late
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None
    assert box.state(name=REFRESH_COUNT_STATE_FILENAME) is None


def test_a_non_numeric_refresh_counter_fails_closed(tmp_path: Path) -> None:
    """A counter nothing can compare cannot bound anything, so it refuses.

    This is the arm the node's own comment calls out as the natural coding
    error: `test "$count" -ge 3` returns 2 on a non-numeric value, which an `if`
    reads as "below the bound" -- so the plausible spelling of this guard lets a
    corrupt counter refresh forever. The control is therefore the push NOT
    happening, not merely a non-zero exit.
    """
    box = _build(root=tmp_path)
    before = box.remote_head(ref=_BRANCH)
    _ = (box.state_dir() / REFRESH_COUNT_STATE_FILENAME).write_text("many", encoding="utf-8")
    _ = _advance_default(box=box)

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_REFRESH_COUNT_UNREADABLE" in result.stderr
    assert box.remote_head(ref=_BRANCH) == before
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None


def test_the_three_refresh_bound_stops_a_fourth_refresh(tmp_path: Path) -> None:
    """Three completed refreshes is the bound, so the fourth does not rewrite.

    The control is the pair: at two the same world refreshes, at three it
    refuses. Asserting only the refusal would pass for a build that refuses
    every refresh, and asserting only the success would pass for an unbounded
    one.
    """
    bounded = _build(root=tmp_path / "bounded")
    _ = (bounded.state_dir() / REFRESH_COUNT_STATE_FILENAME).write_text("3", encoding="utf-8")
    at_bound_before = bounded.remote_head(ref=_BRANCH)
    _ = _advance_default(box=bounded)

    refused = _run(box=bounded)

    assert refused.returncode == 1, refused.stdout
    assert "LIVESPEC_PR_REFRESH_NON_CONVERGED" in refused.stderr
    assert bounded.remote_head(ref=_BRANCH) == at_bound_before
    assert bounded.state(name=REFRESH_COUNT_STATE_FILENAME) == "3"

    below = _build(root=tmp_path / "below")
    _ = (below.state_dir() / REFRESH_COUNT_STATE_FILENAME).write_text("2", encoding="utf-8")
    _ = _advance_default(box=below)

    allowed = _run(box=below)

    assert allowed.returncode == 0, allowed.stderr
    assert "LIVESPEC_PR_REFRESH_CHANGED" in allowed.stderr
    assert below.state(name=REFRESH_COUNT_STATE_FILENAME) == "3\n"


def test_a_stale_changed_marker_is_cleared_at_every_entry(tmp_path: Path) -> None:
    """A marker from an earlier refresh must not route an unchanged head onward.

    The node's own comment names this: `pr_refresh_head` reads only the marker,
    so a marker left behind by a previous refresh of the SAME run would send an
    unchanged head back through capture forever.
    """
    box = _build(root=tmp_path)
    _ = (box.state_dir() / REFRESH_CHANGED_STATE_FILENAME).write_text("stale", encoding="utf-8")

    result = _run(box=box)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_REFRESH_UNCHANGED" in result.stderr
    assert box.state(name=REFRESH_CHANGED_STATE_FILENAME) is None


def test_an_absent_exact_head_push_program_fails_closed(tmp_path: Path) -> None:
    """Without the materialized helper no rewrite can be PROVEN to carry a lease.

    The stage must not fall back to an inline push, so the assertion is that
    origin is untouched after a run that had real work to do and a passing gate.
    """
    box = _build(root=tmp_path)
    before = box.remote_head(ref=_BRANCH)
    (box.plugins_root / PUBLICATION_PUSH_PROGRAM_FILENAME).unlink()
    _ = _advance_default(box=box)

    result = _run(box=box)

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_PR_REFRESH_PUSH_PROGRAM_ABSENT" in result.stderr
    assert box.remote_head(ref=_BRANCH) == before


def test_the_refresh_execution_boundary_leaves_enclosing_run_state_intact(
    tmp_path: Path,
) -> None:
    """Executing the refresh here cannot touch the publication state of a real run.

    THE REGRESSION CONTROL FOR THIS FILE'S OWN SAFETY, and it matters more for
    this node than for any other: `pr_refresh` runs `sandbox_check_suite` -- this
    suite -- as its post-rebase gate, in the same sandbox, AFTER establishing its
    provenance and while its refresh counter stands. A control that wrote
    publication state at a fixed shared path would erase that live counter
    mid-gate and let the next refresh restart at one, evading the three-refresh
    bound; on a gate failure it would also drop the published-head marker.
    Anchoring state to each control's own `$GIT_DIR` makes that impossible by
    construction, and this control is what proves the construction holds.

    THE SHARED-PATH LEG IS A BEFORE/AFTER COMPARISON, NOT AN ABSENCE CHECK, and
    the difference decides whether this control measures anything. Asserting
    those paths are ABSENT grades the ambient machine: a leftover from any
    earlier build fails the control while saying nothing about the boundary, and
    a clean machine passes it just as uninformatively. Comparing each path's
    bytes before against after is what actually asks whether EXECUTING THE STAGE
    touched it.

    BOTH A SUCCEEDING AND A FAILING ARM are run, because a gate failure is
    exactly when the original finding lost state.
    """
    enclosing = tmp_path / "enclosing" / ".git" / PUBLICATION_STATE_GIT_PATH
    enclosing.mkdir(parents=True)
    sentinels = {name: f"enclosing-run-{name}" for name in publication_state_filenames()}
    for name, text in sentinels.items():
        _ = (enclosing / name).write_text(text, encoding="utf-8")
    assert sentinels, "the state filename set must not be empty"

    def shared_state() -> dict[str, str | None]:
        """Each fixed shared path's bytes, or `None` where it does not exist."""
        snapshot: dict[str, str | None] = {}
        for name in publication_state_filenames():
            path = Path(os.sep) / "tmp" / name
            snapshot[name] = path.read_text(encoding="utf-8") if path.is_file() else None
        return snapshot

    before = shared_state()
    passing_box = _build(root=tmp_path / "passing")
    failing_box = _build(root=tmp_path / "failing")
    _ = _advance_default(box=passing_box)
    _ = _advance_default(box=failing_box)
    passing = _run(box=passing_box)
    failing = _run(box=failing_box, check_suite=_FAILING_GATE)

    assert passing.returncode == 0, passing.stderr
    assert failing.returncode == 1, failing.stdout
    for name, text in sentinels.items():
        path = enclosing / name
        assert path.is_file(), f"{name} was removed by a refresh execution control"
        assert path.read_text(encoding="utf-8") == text, name
    assert shared_state() == before, "a refresh execution control touched a fixed shared path"
    # The POSITIVE half: each control's own state resolved inside its own
    # `$GIT_DIR`, which is the mechanism that makes the two legs above hold. The
    # passing arm wrote a counter there and the failing arm did not, so the one
    # directory carries both answers.
    assert passing_box.state(name=REFRESH_COUNT_STATE_FILENAME) == "1\n"
    # Both boxes now record a refresh, because v134 counts the repaired visit
    # too; what this case grades is that each recorded it in its OWN clone, which
    # is the boundary under test.
    assert failing_box.state(name=REFRESH_COUNT_STATE_FILENAME) == "1\n"


def test_the_executed_bytes_are_the_committed_bytes(tmp_path: Path) -> None:
    """The substitutions stand in for the ENGINE and touch nothing else.

    Without this, every control above is equally consistent with a harness that
    rewrote the recipe into something easier to pass. Three assertions, because
    each covers a different way the extraction could drift: the executed text
    must be the committed `script` attribute apart from the two engine tokens,
    those tokens must have been present to substitute, and no other `{{ ... }}`
    may survive into the bytes a control runs.
    """
    graph = parse_dot_graph(text=_IMPLEMENT_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    committed = graph.nodes["pr_refresh"]["script"]
    assert "{{ inputs.default_branch }}" in committed
    assert "{{ inputs.sandbox_check_suite }}" in committed
    executed = _refresh_script(check_suite=_PASSING_GATE)
    assert "{{" not in executed
    assert executed == committed.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH).replace(
        "{{ inputs.sandbox_check_suite }}", _PASSING_GATE
    )
    # And the one program the stage re-enters is the production one, written from
    # its own source rather than restated: a control whose push helper was a
    # local stand-in would prove nothing about the shipped lease.
    box = _build(root=tmp_path)
    assert (box.plugins_root / PUBLICATION_PUSH_PROGRAM_FILENAME).read_text(
        encoding="utf-8"
    ) == publication_push_program_source()
    assert (box.plugins_root / PLUGIN_GATE_PROGRAM_FILENAME).is_file()
    assert sys.executable, "the control needs an interpreter to have resolved"
