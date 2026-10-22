"""`pr_refresh` and `publish_draft` execute their declared check suite on both engines.

WHAT THIS BINDS, AND WHY IT IS THE SAME QUESTION ONE NODE OVER.
`test_workflow_janitor_check_suite_execution.py` established the renderer
compatibility claim for the `janitor` node: the pinned engine substitutes
`inputs.sandbox_check_suite` as raw text, while the Petri-era attractor
frontend shell-quotes the whole interpolated value as ONE word, so a bare
`$(...)` of it looks the suite's entire command line up as a command NAME.
The two refresh-era gates were left on the old form, and that is what this
module measures.

THE FAILURE THIS REPLACES IS A FALSE GREEN'S MIRROR -- A FALSE RED. Measured
2026-10-15 on hp-candidate run 01M50A81W7927JGTAHF7353DZS (plugin build
3a2a826a8ac4 = v0.201.0): `pr_refresh@1` rebased 157 commits cleanly and then
reported `bash: line 2: mise exec -- just check: command not found`, which the
refresh-repair brief recorded verbatim as its `failed-gate-targets`. The gate
never ran, so the run spent a fix round, a second janitor, a second
publish_draft, a second proof capture and a second review on a gate failure
that had not happened, and each such round consumes one of the two
refresh-repair attempts the budget allows.

WHY EVERY CASE EXECUTES RATHER THAN MATCHING TEXT. The thing under test is what
BASH DOES with the rendered bytes, and the two renderings differ only in
quoting -- a substring assertion over the script cannot tell a suite that RAN
from one whose command line was looked up as a name. So each case renders the
shipped `script` attribute both ways, stands a RECORDING stand-in in for the
repository's declared suite, and asserts on what that stand-in observed: its
own arguments, and the HEAD it saw. Only the engine's own template tokens are
substituted, because the engine owns that expansion rather than this
repository, and `sandbox_check_suite` is a per-repository DECLARATION -- so
standing a controlled command in for it stands in for the declaration, not for
the stage.

THE ENCLOSING RUN'S STATE IS NEVER TOUCHED. Each case builds its own bare
origin, clone and plugins root under `tmp_path`, and the stages resolve their
publication state inside THAT clone's `$GIT_DIR`. That matters more here than
elsewhere: `pr_refresh` runs the declared check suite -- this very suite -- as
its post-rebase gate, so a case writing state at a fixed shared path would
erase the live run's own refresh counters.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

_CHECK_SUITE_TOKEN = "{{ inputs.sandbox_check_suite }}"
_DEFAULT_BRANCH_TOKEN = "{{ inputs.default_branch }}"
_DEFAULT_BRANCH = "master"
_BRANCH = "feat/bd-ib-cwrllw"
_SHARED_FILE = "shared.txt"
_OWNED_FILE = "owned.txt"
_BRIEF_FILENAME = "livespec-refresh-repair-brief"
_FAILED_GATE_LABEL = "failed-gate-targets: "

# The two arguments the stand-in suite is given, and the separator it records
# them under. A declared suite is an ARGV rather than a program, so a renderer
# that collapses it to one word is invisible to a zero-argument stand-in: the
# whole point is that the arguments survive.
#
# THE FIRST ARGUMENT CONTAINS A SPACE DELIBERATELY. `dispatcher.janitor
# .check_suite` is declared as an argv and projected onto the workflow input by
# `_dispatcher_integration_projection._scalar`, which renders it with
# `shlex.join` -- so an element needing quoting reaches the stage SHELL-QUOTED
# even under the renderer that substitutes raw text. That is the element a gate
# which re-parses the joined text splits in two, and `|` is the separator that
# makes the split visible: a form that lost the quoting records `alpha|beta`
# rather than `alpha beta|gamma`.
_FIRST_ARGUMENT = "alpha beta"
_SECOND_ARGUMENT = "gamma"
_ARGUMENT_SEPARATOR = "|"

# What the stand-in suite writes on each stream. Both are asserted, because the
# brief is assembled from a `2>&1` capture and a redirection that lost one
# stream would still carry the other.
_STDOUT_MARKER = "LIVESPEC-DECLARED-SUITE-STDOUT"
_STDERR_MARKER = "LIVESPEC-DECLARED-SUITE-STDERR"

# The literal the measured defect produced in place of the suite's own output.
# Asserted ABSENT beside the positive marker assertions, because that string is
# what the false `failed-gate-targets` line carried on the live run.
_COMMAND_NOT_FOUND = "command not found"

# The coverage hooks an allowlisted spawn must scrub, so no child of this file
# self-instruments and races the concurrent coverage run.
_COVERAGE_ENV_PREFIXES = ("COVERAGE_PROCESS_START", "COV_CORE_")

# The two renderings, named so a failure reports which engine it modelled.
_RENDERINGS = (
    pytest.param(False, id="raw-text-substitution"),
    pytest.param(True, id="shell-quoted-one-word"),
)


def _fixture_git_env() -> dict[str, str]:
    """The fixture environment, coverage-scrubbed, with an explicit git identity.

    The identity is stated rather than inherited because the factory sandbox
    carries one that differs from a developer's, and a commit with no identity
    fails outright.
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


def _commit(*, cwd: Path, path: str, text: str, subject: str) -> str:
    """Write one file and commit it, returning the resulting head."""
    _ = _git("config", "user.email", "t@example.invalid", cwd=cwd)
    _ = _git("config", "user.name", "Test", cwd=cwd)
    _ = (cwd / path).write_text(text, encoding="utf-8")
    _ = _git("add", path, cwd=cwd)
    _ = _git("commit", "--quiet", "-m", subject, cwd=cwd)
    return _git("rev-parse", "HEAD", cwd=cwd).stdout.strip()


def _node_script(*, node: str, check_suite: str, shell_quoted_input: bool) -> str:
    """One shipped node's script with ONLY the engine's own two tokens bound.

    The bytes are read through `parse_dot_graph`, the same reader the
    Dispatcher's own graph consumers use, rather than retyped: a module
    carrying its own copy of the recipe would pass while the shipped stage did
    something else. `shell_quoted_input` is the renderer under test -- the
    Petri-era frontend quotes the interpolated value, the pinned engine does
    not.
    """
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes[node]["script"]
    assert script.count(_CHECK_SUITE_TOKEN) == 1, node
    rendered = shlex.quote(check_suite) if shell_quoted_input else check_suite
    return script.replace(_DEFAULT_BRANCH_TOKEN, _DEFAULT_BRANCH).replace(
        _CHECK_SUITE_TOKEN, rendered
    )


def _check_suite(*, root: Path, record: Path, status: int) -> Path:
    """A stand-in declared check suite that records how it was invoked.

    It writes its first two arguments and the HEAD it observed, so "ran with
    its arguments" and "ran against the rebased head" are separately
    assertable, then writes one marker on each stream and exits the status the
    case asked for.
    """
    quoted_record = shlex.quote(str(record))
    separator = shlex.quote(_ARGUMENT_SEPARATOR)
    lines = (
        "#!/usr/bin/env bash",
        f'printf "argv: %s%s%s\\n" "$1" {separator} "$2" > {quoted_record}',
        f'printf "head: %s\\n" "$(git rev-parse HEAD)" >> {quoted_record}',
        f'printf "%s\\n" {shlex.quote(_STDOUT_MARKER)}',
        f'printf "%s\\n" {shlex.quote(_STDERR_MARKER)} >&2',
        f"exit {status}",
        "",
    )
    path = root / "declared-check-suite"
    _ = path.write_text("\n".join(lines), encoding="utf-8")
    path.chmod(0o755)
    return path


def _declared_command_line(*, suite: Path) -> str:
    """The workflow-input value the Dispatcher would project for this declaration.

    `shlex.join`, because that is literally what the projection does to a
    declared argv -- so the text a case substitutes is the text a dispatch
    substitutes, quoting included, rather than a hand-spaced approximation that
    no declaration produces.
    """
    return shlex.join([str(suite), _FIRST_ARGUMENT, _SECOND_ARGUMENT])


def _expected_argv() -> str:
    return f"{_FIRST_ARGUMENT}{_ARGUMENT_SEPARATOR}{_SECOND_ARGUMENT}"


def _record_fields(*, record: Path) -> dict[str, str]:
    """The stand-in's observations as `label -> value`, asserted present as read.

    Present rather than defaulted: an absent record means the suite never ran
    at all, which is the measured defect itself, and that deserves its own
    message rather than a confusing lookup failure.
    """
    assert record.is_file(), "the declared check suite never ran"
    fields: dict[str, str] = {}
    for line in record.read_text(encoding="utf-8").splitlines():
        label, _, value = line.partition(": ")
        fields[label] = value
    return fields


@dataclass(frozen=True, kw_only=True)
class _World:
    """One case's throwaway world: a real bare origin, a real clone, real helpers."""

    origin: Path
    clone: Path
    plugins_root: Path

    def state_dir(self) -> Path:
        return self.clone / ".git" / PUBLICATION_STATE_GIT_PATH

    def state(self, *, name: str) -> str | None:
        path = self.state_dir() / name
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def head(self) -> str:
        return _git("rev-parse", "HEAD", cwd=self.clone).stdout.strip()

    def contains(self, *, ancestor: str) -> bool:
        probe = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, "HEAD"],
            cwd=self.clone,
            check=False,
            capture_output=True,
            text=True,
            env=_fixture_git_env(),
        )
        return probe.returncode == 0


_GH_UNARMED_STUB = """#!/bin/sh
# `pr_refresh` asks the forge whether the pull request carries an auto-merge
# request before it rebases, and fails closed when it cannot be asked. This
# module's subject is the declared-check-suite seam, not the arming, so the
# stub reports an UNARMED pull request and the disarm becomes a no-op. The
# real `gh` on PATH refuses without GitHub App credentials, which would stop
# the stage before it ever reached the suite. The arming arms themselves are
# driven in `test_scripted_refresh_execution`, against a forge stub that
# records the clone's head at each call.
echo null
"""


def _world(*, root: Path) -> _World:
    """An origin carrying the default branch, and a clone holding this run's work.

    The push program is written from its own source, so the lease `pr_refresh`
    performs is the lease the Dispatcher ships rather than one restated here.
    """
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
    _ = _commit(
        cwd=clone, path=_OWNED_FILE, text="this run's work\n", subject="feat: this run's work"
    )
    plugins_root = root / "plugins"
    plugins_root.mkdir()
    # The generated-record-file resolution rides the SAME prepare block as the
    # push program (bd-ib-ze7xxj), and a refreshing stage that cannot resolve it
    # fails closed before the repository-declared gate -- so a harness omitting
    # it would exercise that refusal on every case rather than the route under
    # test.
    _ = (plugins_root / RECORD_FILE_PROGRAM_FILENAME).write_text(
        record_file_program_source(), encoding="utf-8"
    )
    push_program = plugins_root / PUBLICATION_PUSH_PROGRAM_FILENAME
    _ = push_program.write_text(publication_push_program_source(), encoding="utf-8")
    push_program.chmod(0o700)
    bin_dir = root / "bin"
    bin_dir.mkdir()
    gh_stub = bin_dir / "gh"
    _ = gh_stub.write_text(_GH_UNARMED_STUB, encoding="utf-8")
    gh_stub.chmod(0o755)
    return _World(origin=origin, clone=clone, plugins_root=plugins_root)


def _stage_env(*, world: _World) -> dict[str, str]:
    """The stage's environment, EXPLICIT rather than inherited.

    Inherited `LIVESPEC_*` from the enclosing factory run could otherwise
    satisfy a guard a case meant to exercise -- `LIVESPEC_RESUME_PUBLISHED_HEAD`
    above all. The gh-refresh root names a directory holding no helper, so every
    push takes the inline fallback identically here and on a CI runner.
    """
    return {
        "PATH": f"{world.clone.parent / 'bin'}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(world.clone.parent / "home"),
        "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
        "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(world.clone.parent / "no-gh-refresh"),
        SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(world.plugins_root),
    }


def _published(*, world: _World, root: Path) -> str:
    """Publish this run's head and record the provenance `pr_refresh` demands.

    Running the plugin-cache gate's own body here also records this case's
    plugin pin, which is what makes the stage's later re-entry the ENFORCEMENT
    arm rather than a first recording.
    """
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_BRANCH}", cwd=world.clone)
    world.state_dir().mkdir(parents=True, exist_ok=True)
    _ = (world.state_dir() / PUBLISH_HEAD_STATE_FILENAME).write_text(world.head(), encoding="utf-8")
    gate_script = root / "install-plugin-gate.sh"
    _ = gate_script.write_text(plugin_cache_gate_script(), encoding="utf-8")
    _ = subprocess.run(
        ["bash", str(gate_script)],
        check=True,
        capture_output=True,
        text=True,
        env=_stage_env(world=world),
    )
    return world.head()


def _advance_default(*, world: _World) -> str:
    """Move origin's default branch through a SEPARATE clone.

    Separate so the case's own clone learns nothing about the movement until the
    stage's own fetch, which is the state a real dispatch is in when the default
    branch advances underneath it. The moved path is NOT the one this run
    touched, so the rebase applies cleanly and the gate is what decides.
    """
    mover = world.clone.parent / "mover"
    _ = _git("clone", "--quiet", str(world.origin), str(mover), cwd=world.clone.parent)
    advanced = _commit(cwd=mover, path=_SHARED_FILE, text="moved\n", subject="feat: advance")
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_DEFAULT_BRANCH}", cwd=mover)
    return advanced


def _refuse_every_push(*, world: _World) -> None:
    """Install a repository pre-push hook that refuses, as a red gate does.

    This repository's declared gate RUNS IN THE PRE-PUSH HOOK, so "the push was
    refused" reaches `publish_draft` as a failed push and nothing else, which is
    the arm whose gate check this module measures. The refusal text carries no
    authentication vocabulary, so the stage classifies it as a candidate gate
    rejection rather than as a credential failure.
    """
    hook = world.clone / ".git" / "hooks" / "pre-push"
    hook.parent.mkdir(parents=True, exist_ok=True)
    _ = hook.write_text(
        "#!/bin/sh\nprintf '%s\\n' 'the repository gate refused this head' >&2\nexit 1\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)


def _run(
    *,
    node: str,
    world: _World,
    check_suite: str,
    shell_quoted_input: bool,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            _node_script(node=node, check_suite=check_suite, shell_quoted_input=shell_quoted_input),
        ],
        cwd=world.clone,
        check=False,
        capture_output=True,
        text=True,
        env=_stage_env(world=world),
    )


@pytest.mark.parametrize("shell_quoted_input", _RENDERINGS)
def test_pr_refresh_runs_the_declared_suite_with_its_arguments_at_the_rebased_head(
    *,
    tmp_path: Path,
    shell_quoted_input: bool,
) -> None:
    """The post-rebase gate RUNS, with its arguments, against the head it gates.

    Three claims, each separately satisfiable while the requirement is unmet:
    the stand-in must have been executed at all (it records nothing otherwise),
    its arguments must have survived the rendering, and the HEAD it observed
    must be the REBASED one -- a gate that ran before the rebase would be
    grading a head that is never published.
    """
    world = _world(root=tmp_path)
    published = _published(world=world, root=tmp_path)
    advanced = _advance_default(world=world)
    record = tmp_path / "gate-record"
    suite = _check_suite(root=tmp_path, record=record, status=0)

    result = _run(
        node="pr_refresh",
        world=world,
        check_suite=_declared_command_line(suite=suite),
        shell_quoted_input=shell_quoted_input,
    )

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_REFRESH_CHANGED" in result.stderr
    observed = _record_fields(record=record)
    assert observed["argv"] == _expected_argv()
    rebased = world.head()
    assert rebased != published, "nothing was rebased, so the gate graded the old head"
    assert world.contains(ancestor=advanced), "the rebased head lacks the advanced default"
    assert observed["head"] == rebased


@pytest.mark.parametrize("shell_quoted_input", _RENDERINGS)
def test_publish_draft_runs_the_declared_suite_with_its_arguments_after_a_refused_push(
    *,
    tmp_path: Path,
    shell_quoted_input: bool,
) -> None:
    """A refused push consults the declared suite to tell a red gate from a dead origin.

    The discriminating assertion is the ABSENCE of the gate-rejected verdict
    beside the recorded invocation: a suite that exits zero means the refusal
    was NOT the repository's gate, so the stage must report the push failure
    instead. On the quoted rendering the unexecuted command line exited
    non-zero, which made every refused push look like a gate rejection and
    spent a refresh-repair round on it.
    """
    world = _world(root=tmp_path)
    _refuse_every_push(world=world)
    record = tmp_path / "gate-record"
    suite = _check_suite(root=tmp_path, record=record, status=0)

    result = _run(
        node="publish_draft",
        world=world,
        check_suite=_declared_command_line(suite=suite),
        shell_quoted_input=shell_quoted_input,
    )

    assert result.returncode != 0
    observed = _record_fields(record=record)
    assert observed["argv"] == _expected_argv()
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_FAILED" in result.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_GATE_REJECTED" not in result.stderr
    assert world.state(name=_BRIEF_FILENAME) is None


@pytest.mark.parametrize("shell_quoted_input", _RENDERINGS)
def test_a_failing_pr_refresh_suite_puts_its_own_output_in_the_repair_brief(
    *,
    tmp_path: Path,
    shell_quoted_input: bool,
) -> None:
    """The brief's `failed-gate-targets` carries the SUITE's output, not the shell's.

    This is the field a fix round reads to learn what to repair, and on the
    measured run it carried `command not found` -- a description of the stage's
    own invocation defect rather than of anything in the tree. Both of the
    stand-in's streams are asserted present, because the line is assembled from
    a `2>&1` capture.
    """
    world = _world(root=tmp_path)
    _ = _published(world=world, root=tmp_path)
    _ = _advance_default(world=world)
    record = tmp_path / "gate-record"
    suite = _check_suite(root=tmp_path, record=record, status=7)

    result = _run(
        node="pr_refresh",
        world=world,
        check_suite=_declared_command_line(suite=suite),
        shell_quoted_input=shell_quoted_input,
    )

    assert result.returncode == 1, result.stdout
    assert "LIVESPEC_REFRESH_REPAIR" in result.stderr
    brief = world.state(name=_BRIEF_FILENAME)
    assert brief is not None, "the stage recorded no refresh-repair brief"
    targets = [line for line in brief.splitlines() if line.startswith(_FAILED_GATE_LABEL)]
    assert len(targets) == 1, brief
    assert _STDOUT_MARKER in targets[0]
    assert _STDERR_MARKER in targets[0]
    assert _COMMAND_NOT_FOUND not in targets[0]
