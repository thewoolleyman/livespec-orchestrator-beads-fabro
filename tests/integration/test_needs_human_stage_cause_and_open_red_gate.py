"""The `needs_human` terminal reports the FAILING STAGE's cause, not a guess at the tree.

WHAT THIS BINDS. Work-item `bd-ib-rv7g4z` against `SPECIFICATION/scenarios.md`
"Scenario 103 — A needs-human outcome terminates the run and routes the
decision to the ledger". The terminal resolves its reason in order: a
stage-written needs-human reason, else the cause the failing stage recorded,
else an open Red commit at the branch head, else a generic line. Two of those
four arms were wrong at once on run 01M51D4RYHCB, and each was wrong in the
direction that reads as a real finding.

THE MEASURED INCIDENT. `pr_refresh` failed with
`LIVESPEC_PR_REFRESH_ORIGIN_UNOBSERVABLE` because the pull request had already
auto-merged and its branch was deleted; `refresh_repair` then reported
`LIVESPEC_REFRESH_REPAIR_ABSENT` and said in as many words that it was "routing
to needs_human with that stage own cause" — but NOTHING carried that cause, so
the terminal fell through to the open-Red arm and reported "open Red commit
40f8db0e at the branch head". That reason was wrong twice over. It was not the
cause, and the Red was not open in any sense a human can act on: the head
commit changed only `.fabro` workflow files plus one test file, which
`red_green_replay` exempts from the Green stamp altogether, so a Red trailer
with no Green is the NORMAL shape of such a commit rather than a half-authored
pair.

WHY THE SCRIPT BYTES ARE EXECUTED RATHER THAN MATCHED. Every arm under test is
SHELL inside a DOT attribute, and a substring assertion cannot tell a
precedence arm that RUNS from one sitting behind an earlier `elif`. So each
case extracts the shipped node's own script through the canonical parser —
never retyped — and runs it by `sh` in a throwaway clone with a real bare
origin and real commits.

EVERY CASE CARRIES THE CONTROL THAT MAKES ITS ASSERTION EVIDENCE. "The terminal
named the stage" is satisfied just as well by a terminal that no longer knows
how to report an open Red at all, so each case also runs the SAME fixture with
only the thing under test withheld and asserts the other answer appears. That
is the whole reason the open-Red clause is asserted PRESENT in half the cases
below: the defect is a reason that fires too often, and the cheapest wrong fix
is one that never fires.

THE ENCLOSING RUN'S STATE IS NEVER TOUCHED. Each case builds its own origin and
clone under `tmp_path`, and the terminal resolves its artifacts inside THAT
clone's `$GIT_DIR`, so a nested execution is structurally unable to name the
live run's own files.
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

_TERMINAL = "needs_human"
_REFRESH_CLASSIFIER = "refresh_repair"
_DEFAULT_BRANCH = "master"
_PUBLISH_BRANCH = "feat/bd-ib-rv7g4z"

# A run id the terminal accepts: its uniqueness filter refuses anything
# carrying a character outside `[0-9A-Za-z]`, so a hyphenated id would take the
# no-run-id arm and preserve nothing.
_RUN = "01M51D4RYHCBTESTFIXTURE00"

_OPERATOR_NAME = "Test"
_OPERATOR_EMAIL = "t@example.invalid"

_COVERAGE_ENV_PREFIXES = ("COVERAGE_PROCESS_START", "COV_CORE_")

# The trailer keys the commit-refuse hook writes. An OPEN Red carries the first
# and not the second.
_RED_TRAILER = "TDD-Red-Test-File-Checksum: sha256:0f0f"
_OPEN_RED_MESSAGE = f"fix(factory): the staged test\n\n{_RED_TRAILER}\n"

# The two needles the open-Red reason owes an operator, spelled apart because
# the sha alone appears in any git output and says nothing about the shape of
# the tree.
_OPEN_RED_CLAUSE = "open Red commit"
_HALF_PAIR_CLAUSE = "half authored"
_GENERIC_REASON = "loop cannot auto-resolve this work-item"

# The artifact a failing stage records its own cause in, resolved through
# `git rev-parse --git-path` exactly as the needs-human reason file beside it
# is. Spelled as a LITERAL here, because the name lives inside a shell string
# in the graph that no import can reach.
_STAGE_CAUSE_GIT_PATH = "livespec-stage-cause"

# A product implementation path under this repository's own declared source
# tree, and the cause line the measured incident's `pr_refresh` printed.
_PRODUCT_IMPL_PATH = (
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_fixture_probe.py"
)
_PR_REFRESH_STAGE = "pr_refresh"
_PR_REFRESH_CAUSE = (
    "LIVESPEC_PR_REFRESH_ORIGIN_UNOBSERVABLE: origin could not be fetched, so neither "
    "the authoritative default branch nor the remote publish head can be observed; "
    "holding rather than proceeding blinded"
)


def _graph_text() -> str:
    return _GRAPH_PATH.read_text(encoding="utf-8")


def _node_script(*, node: str) -> str:
    """One shipped node's own script bytes, with the engine's tokens bound.

    The tokens are the pinned engine's own expansion and a per-repository
    DECLARATION; binding them stands in for the engine and the declaration,
    never for the node. `sandbox_check_suite` resolves to `true` because no
    case below reaches a gate — every one of them fails before any rebase.
    """
    graph = parse_dot_graph(text=_graph_text())
    assert not isinstance(graph, str), graph
    script: str = graph.nodes[node]["script"]
    return script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH).replace(
        "{{ inputs.sandbox_check_suite }}", "true"
    )


def _terminal_script() -> str:
    """The shipped terminal's own script bytes, with the one engine token bound."""
    return _node_script(node=_TERMINAL)


def _fixture_env() -> dict[str, str]:
    """The fixture git environment, coverage-scrubbed, with an explicit identity."""
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(_COVERAGE_ENV_PREFIXES)
    }
    return {**env, "GIT_AUTHOR_NAME": _OPERATOR_NAME, "GIT_AUTHOR_EMAIL": _OPERATOR_EMAIL}


def _git(*argv: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=_fixture_env(),
    )


@dataclass(frozen=True, kw_only=True)
class _World:
    """One case's throwaway world: a real bare origin, a real clone, a real head."""

    origin: Path
    clone: Path
    head: str

    def git_path(self, *, name: str) -> Path:
        resolved = Path(_git("rev-parse", "--git-path", name, cwd=self.clone).stdout.strip())
        return resolved if resolved.is_absolute() else self.clone / resolved


def _world(*, root: Path, changed: dict[str, str], message: str) -> _World:
    """A clone whose HEAD commit carries `message` and changes exactly `changed`.

    The head commit is the subject of every open-Red reading, so the paths it
    touches are the fixture's only real variable: the terminal has to tell a
    half-authored product change from a commit `red_green_replay` never asked
    for a Green stamp on, and nothing but those paths distinguishes them.
    """
    origin = root / "origin.git"
    origin.mkdir(parents=True)
    _ = _git("init", "--bare", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=origin)
    clone = root / "clone"
    clone.mkdir()
    _ = _git("init", "--quiet", f"--initial-branch={_DEFAULT_BRANCH}", cwd=clone)
    _ = _git("config", "user.email", _OPERATOR_EMAIL, cwd=clone)
    _ = _git("config", "user.name", _OPERATOR_NAME, cwd=clone)
    _ = _git("config", "commit.gpgsign", "false", cwd=clone)
    _ = (clone / "seed.txt").write_text("seed\n", encoding="utf-8")
    _ = _git("add", "seed.txt", cwd=clone)
    _ = _git("commit", "--quiet", "-m", "chore: seed", cwd=clone)
    _ = _git("remote", "add", "origin", str(origin), cwd=clone)
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_DEFAULT_BRANCH}", cwd=clone)
    for path, text in changed.items():
        target = clone / path
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(text, encoding="utf-8")
        _ = _git("add", path, cwd=clone)
    subprocess.run(
        ["git", "commit", "--quiet", "-F", "-"],
        cwd=str(clone),
        check=True,
        text=True,
        capture_output=True,
        input=message,
        env=_fixture_env(),
    )
    return _World(
        origin=origin,
        clone=clone,
        head=_git("rev-parse", "--short", "HEAD", cwd=clone).stdout.strip(),
    )


def _run_terminal(*, world: _World) -> str:
    """The shipped terminal's real stderr, run in this world's clone.

    The environment is EXPLICIT rather than inherited: an inherited
    `LIVESPEC_*` or a `GITHUB_APP_ID` from the enclosing factory run would
    otherwise reach a guard this case never meant to exercise.
    """
    completed = subprocess.run(
        ["sh", "-c", _terminal_script()],
        cwd=str(world.clone),
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(world.clone.parent / "home"),
            "LIVESPEC_GIT_AUTHOR_NAME": _OPERATOR_NAME,
            "LIVESPEC_GIT_AUTHOR_EMAIL": _OPERATOR_EMAIL,
            "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(world.clone.parent / "no-gh-refresh"),
        },
        check=False,
        text=True,
        capture_output=True,
        input=f"{_RUN}\n",
    )
    assert completed.returncode == 1, completed.stderr
    return completed.stderr


def _record_stage_cause(*, world: _World, stage: str, cause: str) -> None:
    """Record a failing stage's own cause, in the shape a failing stage writes."""
    _ = world.git_path(name=_STAGE_CAUSE_GIT_PATH).write_text(
        f"stage: {stage}\ncause: {cause}\n", encoding="utf-8"
    )


def test_a_recorded_stage_cause_outranks_the_open_red_commit_reason(tmp_path: Path) -> None:
    """The terminal names the stage that failed and its cause line, not the tree.

    This is the first half of the measured incident: a stage HAD diagnosed its
    own fault and the terminal reported a guess about the branch head instead.
    The head here carries a genuine open Red over a product implementation
    path, so the open-Red arm is REACHABLE and the case is about which of two
    available answers the terminal gives — which is exactly what the control
    below establishes, by withholding the record and nothing else and watching
    the open-Red reason appear in its place.
    """
    world = _world(
        root=tmp_path / "recorded",
        changed={_PRODUCT_IMPL_PATH: "the half-authored product edit\n"},
        message=_OPEN_RED_MESSAGE,
    )
    _record_stage_cause(world=world, stage=_PR_REFRESH_STAGE, cause=_PR_REFRESH_CAUSE)
    control = _world(
        root=tmp_path / "control",
        changed={_PRODUCT_IMPL_PATH: "the half-authored product edit\n"},
        message=_OPEN_RED_MESSAGE,
    )

    stderr = _run_terminal(world=world)
    control_stderr = _run_terminal(world=control)

    assert f"stage {_PR_REFRESH_STAGE} failed: {_PR_REFRESH_CAUSE}" in stderr
    assert _OPEN_RED_CLAUSE not in stderr
    assert _GENERIC_REASON not in stderr
    assert f"{_OPEN_RED_CLAUSE} {control.head}" in control_stderr
    assert _HALF_PAIR_CLAUSE in control_stderr


def _run_node(*, world: _World, node: str) -> subprocess.CompletedProcess[str]:
    """Execute one shipped node's bytes in this world's clone, environment EXPLICIT.

    Explicit because the subprocess-spawn allowlist requires it and because an
    inherited `LIVESPEC_*` from the enclosing factory run could otherwise
    satisfy a guard the case meant to exercise. The gh-refresh root names a
    directory holding no helper, so the push helper's inline fallback is taken
    identically here and on a CI runner that carries no production helper.
    """
    return subprocess.run(
        ["sh", "-c", _node_script(node=node)],
        cwd=str(world.clone),
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(world.clone.parent / "home"),
            "LIVESPEC_PUBLISH_BRANCH": _PUBLISH_BRANCH,
            "LIVESPEC_GIT_AUTHOR_NAME": _OPERATOR_NAME,
            "LIVESPEC_GIT_AUTHOR_EMAIL": _OPERATOR_EMAIL,
            "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(world.clone.parent / "no-gh-refresh"),
        },
        check=False,
        text=True,
        capture_output=True,
        input=f"{_RUN}\n",
    )


def _merged_and_deleted_publication(*, root: Path) -> _World:
    """The measured state: this run published, the pull request merged, the branch is gone.

    `pr_refresh` establishes its pre-refresh head from the run's own
    publication record and then asks origin for both the default branch and
    the publish branch in ONE fetch. Deleting the publish branch — which is
    what the forge does the moment auto-merge lands — makes that fetch fail
    outright, which is how a finished publication reaches the stage as
    `LIVESPEC_PR_REFRESH_ORIGIN_UNOBSERVABLE`. Nothing is stood in: the branch
    is really published and really deleted, so the stage meets the real
    failure rather than a stand-in for one.
    """
    world = _world(
        root=root,
        changed={_PRODUCT_IMPL_PATH: "the half-authored product edit\n"},
        message=_OPEN_RED_MESSAGE,
    )
    _ = _git("push", "--quiet", "origin", f"HEAD:refs/heads/{_PUBLISH_BRANCH}", cwd=world.clone)
    published = _git("rev-parse", "HEAD", cwd=world.clone).stdout.strip()
    state = world.git_path(name=PUBLICATION_STATE_GIT_PATH)
    state.mkdir(parents=True, exist_ok=True)
    _ = (state / PUBLISH_HEAD_STATE_FILENAME).write_text(published, encoding="utf-8")
    _ = _git(
        "push", "--quiet", "origin", "--delete", f"refs/heads/{_PUBLISH_BRANCH}", cwd=world.clone
    )
    return world


def test_a_failed_pr_refresh_carries_its_own_cause_through_the_classifier_to_the_terminal(
    tmp_path: Path,
) -> None:
    """END TO END across the seam the defect sat in: stage, classifier, terminal.

    No layer can establish this alone, which is why the three are composed
    here rather than asserted apart. The classifier ALREADY said it routes
    "to needs_human with that stage own cause", so a reading of its text
    proves nothing; and the terminal's precedence, proved by the case above,
    is satisfied by a record no stage ever writes. What was missing is the
    carry, and only running the shipped bytes of all three in one clone can
    show it.

    THE CONTROL IS THE SAME COMPOSITION WITH ONLY THE RECORD REMOVED, taken
    after `pr_refresh` has really failed, so the world is identical in every
    other respect. It is load-bearing twice: it proves the open-Red arm was
    REACHABLE here — this head really does carry Red trailers over a product
    implementation path, which is exactly the shape the measured incident
    reported — and it therefore proves the cause DISPLACED that reason rather
    than the terminal having forgotten how to give it.
    """
    world = _merged_and_deleted_publication(root=tmp_path / "carried")
    control = _merged_and_deleted_publication(root=tmp_path / "control")

    refresh = _run_node(world=world, node="pr_refresh")
    classifier = _run_node(world=world, node=_REFRESH_CLASSIFIER)
    stderr = _run_terminal(world=world)
    control_refresh = _run_node(world=control, node="pr_refresh")
    control.git_path(name=_STAGE_CAUSE_GIT_PATH).unlink(missing_ok=True)
    control_stderr = _run_terminal(world=control)

    assert refresh.returncode != 0, refresh.stdout
    assert "LIVESPEC_PR_REFRESH_ORIGIN_UNOBSERVABLE" in refresh.stderr
    assert classifier.returncode != 0, classifier.stdout
    assert "LIVESPEC_REFRESH_REPAIR_ABSENT" in classifier.stderr
    assert f"stage {_PR_REFRESH_STAGE} failed: LIVESPEC_PR_REFRESH_ORIGIN_UNOBSERVABLE" in stderr
    assert _OPEN_RED_CLAUSE not in stderr
    assert control_refresh.returncode != 0, control_refresh.stdout
    assert f"{_OPEN_RED_CLAUSE} {control.head}" in control_stderr


def test_an_open_red_reason_requires_a_py_path_in_the_head_commit(tmp_path: Path) -> None:
    """Red trailers alone are not the open-Red trigger; a changed `.py` is half of it.

    `red_green_replay` buckets PRODUCT IMPLEMENTATION by `.py` suffix, so a
    commit carrying no `.py` at all can never owe a Green stamp and its
    trailer shape is complete rather than half authored. A terminal that read
    the trailers alone therefore reported a half-authored pair on a commit
    master CI had correctly passed.

    THE CONTROL IS THE SAME TRAILERS OVER A PRODUCT `.py`, and it is what
    keeps the narrowing honest: a terminal that had simply stopped reporting
    open Reds would satisfy the first assertion and lose the diagnosis
    bd-ib-qhv7qs added. The generic reason is asserted BY NAME on the narrowed
    leg, because "the open-Red clause is absent" is equally true of a terminal
    that printed nothing at all.
    """
    narrowed = _world(
        root=tmp_path / "narrowed",
        changed={"docs/note.md": "a documentation-only change\n"},
        message=_OPEN_RED_MESSAGE,
    )
    control = _world(
        root=tmp_path / "control",
        changed={_PRODUCT_IMPL_PATH: "the half-authored product edit\n"},
        message=_OPEN_RED_MESSAGE,
    )

    stderr = _run_terminal(world=narrowed)
    control_stderr = _run_terminal(world=control)

    assert _OPEN_RED_CLAUSE not in stderr
    assert _HALF_PAIR_CLAUSE not in stderr
    assert _GENERIC_REASON in stderr
    assert f"{_OPEN_RED_CLAUSE} {control.head}" in control_stderr
    assert _HALF_PAIR_CLAUSE in control_stderr


def test_a_non_py_implementation_beside_its_test_claims_no_open_red(tmp_path: Path) -> None:
    """The measured shape of master 1d7c6d14: `.fabro` implementation plus its test.

    `red_green_replay`'s impl bucket is `.py`-only, so a Green amend that
    stages a `workflow.fabro` beside its test takes the gate's silent-pass
    branch and is never stamped `TDD-Green-Verified-At`. Red trailers with no
    Green are therefore that commit's CONFORMING shape — master CI passes it —
    and the terminal reported it as a half-authored pair blocking the loop.

    THE TEST FILE IS WHAT MAKES THIS A SEPARATE CASE from the narrowing above.
    Such a commit DOES carry a `.py`; it is simply not a product one, so a
    reading that merely counted `.py` paths would pass the previous case and
    still fire on every `.fabro` pair this repository authors. The control is
    the SAME three paths with one product `.py` added, which is a genuinely
    half-authored commit and must still be reported — without it, "no open Red"
    is equally consistent with a terminal that ignores the head commit
    entirely.
    """
    exempt = {
        ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro": "the graph edit\n",
        "tests/integration/test_slice.py": "def test_slice() -> None:\n    pass\n",
    }
    world = _world(root=tmp_path / "exempt", changed=exempt, message=_OPEN_RED_MESSAGE)
    control = _world(
        root=tmp_path / "control",
        changed={**exempt, _PRODUCT_IMPL_PATH: "the half-authored product edit\n"},
        message=_OPEN_RED_MESSAGE,
    )

    stderr = _run_terminal(world=world)
    control_stderr = _run_terminal(world=control)

    assert _OPEN_RED_CLAUSE not in stderr
    assert _HALF_PAIR_CLAUSE not in stderr
    assert _GENERIC_REASON in stderr
    assert f"{_OPEN_RED_CLAUSE} {control.head}" in control_stderr
    assert _HALF_PAIR_CLAUSE in control_stderr
