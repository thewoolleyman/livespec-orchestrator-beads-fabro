"""A commit inside an implement, fix or review_fix turn takes the affected-tests gate.

The pre-commit hook reads the turn's stage from `LIVESPEC_AUTHORING_TURN`, which the
detached commit runner sets. These cases run the real hook script in a throwaway
repository against a fake `just` and `uv` that record what the hook asks for, so the
hook's routing is read from the recipes it calls rather than from a whole check run.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PRE_COMMIT = _REPO_ROOT / "dev-tooling" / "just-check-pre-commit.sh"
_CHECK_CHANGED = _REPO_ROOT / "dev-tooling" / "just-check-changed.sh"
_WORKFLOW = ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_WIDGET = ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/widget.py"
_AGGREGATE = "check-skipping check-codex-skill-picker"
_RED_MODE = (
    "check-skipping check-coverage check-per-file-coverage check-check-coverage-incremental"
    " check-codex-skill-picker"
)


def _run(*, argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, check=False)


def _git(*, repo: Path, arguments: list[str]) -> None:
    done = _run(argv=["git", *arguments], cwd=repo, env=os.environ.copy())
    assert done.returncode == 0, done.stderr


def _write_tool(*, directory: Path, name: str, body: str) -> None:
    path = directory / name
    _ = path.write_text(body, encoding="utf-8")
    _ = path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _repository(*, tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    """A repository with one baseline commit, and an environment whose tools are fakes."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo=repo, arguments=["init", "--quiet"])
    _git(repo=repo, arguments=["config", "user.name", "Test User"])
    _git(repo=repo, arguments=["config", "user.email", "test@example.invalid"])
    source = repo / _WIDGET
    source.parent.mkdir(parents=True)
    _ = source.write_text("VALUE = 0\n", encoding="utf-8")
    _git(repo=repo, arguments=["add", "."])
    _git(repo=repo, arguments=["commit", "--quiet", "-m", "baseline"])

    tools = tmp_path / "bin"
    tools.mkdir()
    log = tmp_path / "tools.log"
    _write_tool(
        directory=tools,
        name="uv",
        body=(
            "#!/usr/bin/env bash\n"
            'printf \'uv %s\\n\' "$*" >> "$FAKE_LOG"\n'
            "case \"$*\" in *'pre_commit_delegate run'*) exit 75 ;; esac\n"
            'exit "${FAKE_UV_STATUS:-0}"\n'
        ),
    )
    _write_tool(
        directory=tools,
        name="just",
        body=(
            "#!/usr/bin/env bash\n"
            'printf \'%s\\n\' "$*" >> "$FAKE_LOG"\n'
            'if [[ "$*" == check-changed ]]; then exit "${FAKE_CHANGED_STATUS:-0}"; fi\n'
            'if [[ "$*" == check-pre-commit-doc-only ]]; then exit "${FAKE_DOC_ONLY_STATUS:-0}"; fi\n'
            'if [[ "$*" == check-staged-precheck ]]; then exit "${FAKE_PRECHECK_STATUS:-0}"; fi\n'
        ),
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"LIVESPEC_AUTHORING_TURN", "LIVESPEC_AGENT_STAGE", "LIVESPEC_GATE_CONTEXT"}
    }
    environment["PATH"] = f"{tools}{os.pathsep}{environment['PATH']}"
    environment["FAKE_LOG"] = str(log)
    return repo, environment, log


def _stage(*, repo: Path, path: str, text: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(text, encoding="utf-8")
    _git(repo=repo, arguments=["add", path])


def _hook(
    *, tmp_path: Path, staged: dict[str, str], extra: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    repo, environment, log = _repository(tmp_path=tmp_path)
    for path, text in staged.items():
        _stage(repo=repo, path=path, text=text)
    done = _run(argv=["bash", str(_PRE_COMMIT)], cwd=repo, env={**environment, **extra})
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return done, [line for line in lines if not line.startswith("uv ")]


@pytest.mark.parametrize("stage", ["implement", "fix", "review_fix"])
def test_an_authoring_turn_commit_runs_the_affected_tests_gate_and_not_the_aggregate(
    *, tmp_path: Path, stage: str
) -> None:
    """The staged pre-check runs, then `just check-changed`, and the aggregate does not."""
    done, calls = _hook(
        tmp_path=tmp_path, staged={_WIDGET: "VALUE = 1\n"}, extra={"LIVESPEC_AUTHORING_TURN": stage}
    )

    assert done.returncode == 0, done.stderr
    assert calls == ["check-staged-precheck", "check-changed"]


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"LIVESPEC_AGENT_STAGE": "fix"},
        {"LIVESPEC_AUTHORING_TURN": "janitor"},
        {"LIVESPEC_AUTHORING_TURN": "implement_extra"},
    ],
)
def test_a_commit_outside_an_authoring_turn_keeps_the_full_aggregate(
    *, tmp_path: Path, extra: dict[str, str]
) -> None:
    """Only the commit runner's authoring-turn marker selects the gate; the guard variable does not."""
    done, calls = _hook(tmp_path=tmp_path, staged={_WIDGET: "VALUE = 1\n"}, extra=extra)

    assert done.returncode == 0, done.stderr
    assert calls == [_AGGREGATE]


def test_a_change_the_gate_cannot_scope_falls_back_to_the_full_aggregate(*, tmp_path: Path) -> None:
    """Exit 75 from the gate is not a refusal: the same commit then runs the aggregate."""
    done, calls = _hook(
        tmp_path=tmp_path,
        staged={_WIDGET: "VALUE = 1\n"},
        extra={"LIVESPEC_AUTHORING_TURN": "fix", "FAKE_CHANGED_STATUS": "75"},
    )

    assert done.returncode == 0, done.stderr
    assert calls == ["check-staged-precheck", "check-changed", _AGGREGATE]
    assert "running the full check aggregate" in done.stdout


def test_the_gates_refusal_refuses_the_commit_without_running_the_aggregate(
    *, tmp_path: Path
) -> None:
    """A failing test or an uncovered line is the gate's own verdict and ends the hook."""
    done, calls = _hook(
        tmp_path=tmp_path,
        staged={_WIDGET: "VALUE = 1\n"},
        extra={"LIVESPEC_AUTHORING_TURN": "review_fix", "FAKE_CHANGED_STATUS": "2"},
    )

    assert done.returncode == 2
    assert calls == ["check-staged-precheck", "check-changed"]
    assert "affected-tests gate refused the commit" in done.stderr


def test_a_failing_staged_precheck_refuses_before_the_gate_runs(*, tmp_path: Path) -> None:
    """Lint and type errors in the staged files are reported before any test runs."""
    done, calls = _hook(
        tmp_path=tmp_path,
        staged={_WIDGET: "VALUE = 1\n"},
        extra={"LIVESPEC_AUTHORING_TURN": "fix", "FAKE_PRECHECK_STATUS": "1"},
    )

    assert done.returncode == 1
    assert calls == ["check-staged-precheck"]


def test_a_red_commit_keeps_its_fast_path_in_an_authoring_turn(*, tmp_path: Path) -> None:
    """A staged test alone is a Red commit: it must fail, so no gate may demand it pass."""
    done, calls = _hook(
        tmp_path=tmp_path,
        staged={"tests/test_widget.py": "def test_widget() -> None:\n    assert False\n"},
        extra={"LIVESPEC_AUTHORING_TURN": "implement"},
    )

    assert done.returncode == 0, done.stderr
    assert calls == [_RED_MODE]


def test_a_workflow_graph_change_runs_the_doc_only_gates_then_the_graph_reading_tests(
    *, tmp_path: Path
) -> None:
    """A graph edit stages no `.py`, so the doc-only gates run and then the affected-tests gate."""
    done, calls = _hook(
        tmp_path=tmp_path,
        staged={_WORKFLOW: "digraph { }\n"},
        extra={"LIVESPEC_AUTHORING_TURN": "fix"},
    )

    assert done.returncode == 0, done.stderr
    assert calls == ["check-pre-commit-doc-only", "check-changed"]


def test_a_workflow_graph_change_the_doc_only_gates_refuse_runs_no_tests(*, tmp_path: Path) -> None:
    """The graph-validity gates still bind a graph edit made inside a turn."""
    done, calls = _hook(
        tmp_path=tmp_path,
        staged={_WORKFLOW: "digraph { }\n"},
        extra={"LIVESPEC_AUTHORING_TURN": "fix", "FAKE_DOC_ONLY_STATUS": "1"},
    )

    assert done.returncode == 1
    assert calls == ["check-pre-commit-doc-only"]


def test_a_commit_staging_no_python_and_no_graph_keeps_the_doc_only_path(*, tmp_path: Path) -> None:
    """Nothing to scope tests to: the existing doc-only gates are the commit's gate."""
    done, calls = _hook(
        tmp_path=tmp_path,
        staged={"README.md": "notes\n"},
        extra={"LIVESPEC_AUTHORING_TURN": "fix"},
    )

    assert done.returncode == 0, done.stderr
    assert calls == ["check-pre-commit-doc-only"]


def test_a_merge_in_progress_is_graded_by_the_full_aggregate(*, tmp_path: Path) -> None:
    """A merge commit stages the merged tree, which no scoped gate speaks for."""
    repo, environment, log = _repository(tmp_path=tmp_path)
    _stage(repo=repo, path=_WIDGET, text="VALUE = 1\n")
    head = _run(argv=["git", "rev-parse", "HEAD"], cwd=repo, env=environment).stdout.strip()
    _ = (repo / ".git" / "MERGE_HEAD").write_text(f"{head}\n", encoding="utf-8")

    done = _run(
        argv=["bash", str(_PRE_COMMIT)],
        cwd=repo,
        env={**environment, "LIVESPEC_AUTHORING_TURN": "fix"},
    )

    assert done.returncode == 0, done.stderr
    assert "check-changed" not in log.read_text(encoding="utf-8")


def test_the_check_changed_recipe_runs_the_selection_and_passes_its_status_through(
    *, tmp_path: Path
) -> None:
    """The hook reads 75 from `just check-changed`, so the script must not swallow it."""
    repo, environment, log = _repository(tmp_path=tmp_path)

    done = _run(
        argv=["bash", str(_CHECK_CHANGED)], cwd=repo, env={**environment, "FAKE_UV_STATUS": "75"}
    )

    assert done.returncode == 75
    assert log.read_text(encoding="utf-8").splitlines() == [
        "uv run python dev-tooling/checks/_affected_tests_selection.py"
    ]
