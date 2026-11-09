"""Scenario 285 (v290) — an exhausted implement hook refusal is attributable from the ledger.

`SPECIFICATION/contracts.md` "A refused commit's needs-human cause is attributable
from the ledger" and `SPECIFICATION/scenarios.md` "Scenario 285" (work-item
bd-ib-2h512). Seventeen runs in 48 hours ended at `implement_completion@2,
implement_hook_route@2`; ten of their needs-human causes said only `script exited
with status 1`, and the seven that named the exhausted budget omitted the failing
target. The cause the route writes at its exhausted-budget ending now names the
hook's recorded exit status and every failed target, carries one bounded failure
excerpt from the same recorded output, says the target is unknown and why when the
output names none, and never carries a sandbox environment-variable value.

The sub-scenarios execute the committed `implement_hook_route` script bytes in a
real clone whose pre-commit hook is a stub printing the check aggregate's shape.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_ROUTE = "implement_hook_route"

_EXHAUSTED = "LIVESPEC_IMPLEMENT_HOOK_REFUSED_BUDGET_EXHAUSTED"
_STAGE_CAUSE = "livespec-stage-cause"
_REENTRIES = "livespec-implement-hook-reentries"
_LIVE = "livespec-implement-live-commit"
_VERDICT = "livespec-implement-hook-verdict"
_PARTIAL_CAUSE = "stage: implement\ncause: LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS: stated incomplete\n"
_ERROR_LINE = (
    '_dispatcher_x.py:63:76 - error: Type of "x" is partially unknown (reportUnknownVariableType)'
)
_SECRET = "sk-live-0123456789abcdef"
_AUTH_JSON = '{"tokens": {"access_token": "' + _SECRET + '"}, "note": "multi word"}'
_AUTH_JSON_ESCAPED = json.dumps(_AUTH_JSON)[1:-1]


def _hook_script(*, body: str, status: int) -> str:
    return f"#!/bin/sh\ncat <<'LIVESPEC_HOOK_OUTPUT'\n{body}\nLIVESPEC_HOOK_OUTPUT\nexit {status}\n"


def _targets_block(*, targets: tuple[str, ...]) -> str:
    listed = "\n".join(f"  - {name}" for name in targets)
    return f"Failed targets ({len(targets)}):\n{listed}"


def _clone(*, tmp_path: Path, hook: str) -> Path:
    repo = tmp_path / "clone"
    repo.mkdir(parents=True)
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    hook_path = repo / ".git" / "hooks" / "pre-commit"
    _ = hook_path.write_text(hook, encoding="utf-8")
    hook_path.chmod(0o755)
    _ = (repo / "module.py").write_text("x = 1\n", encoding="utf-8")
    _ = subprocess.run(["git", "add", "module.py"], cwd=repo, check=True)
    _ = (repo / ".git" / _STAGE_CAUSE).write_text(_PARTIAL_CAUSE, encoding="utf-8")
    _ = (repo / ".git" / _REENTRIES).write_text("1\n", encoding="utf-8")
    return repo


def _route(
    *, repo: Path, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    script = dict(parsed.nodes.get(_ROUTE, {})).get("script", "exit 2")
    env = {**os.environ, **(extra_env or {})}
    return subprocess.run(
        ["sh", "-c", script], cwd=repo, check=False, capture_output=True, text=True, env=env
    )


def _child_environment() -> dict[str, str]:
    """Keep the real runner process outside this suite's Git and coverage state."""
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("GIT_", "COV_CORE_")) and name != "COVERAGE_PROCESS_START"
    }


def _cause(*, repo: Path) -> str:
    text = (repo / ".git" / _STAGE_CAUSE).read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.startswith("cause: ")]
    assert len(lines) == 1, text
    assert text.count("\n") == 2, f"the terminal reads one cause line: {text!r}"
    return lines[0]


def _exhausted(*, tmp_path: Path, body: str, status: int = 1) -> tuple[str, str]:
    repo = _clone(tmp_path=tmp_path, hook=_hook_script(body=body, status=status))
    result = _route(repo=repo)
    assert result.returncode != 0, result.stderr
    assert _EXHAUSTED in result.stderr
    return _cause(repo=repo), result.stderr


def test_the_cause_names_the_exit_status_and_every_failed_target_by_recipe_name(
    tmp_path: Path,
) -> None:
    body = f"::: just check-types\n{_ERROR_LINE}\n{_targets_block(targets=('check-types', 'check-lint'))}"

    cause, stderr = _exhausted(tmp_path=tmp_path, body=body, status=7)

    for text in (cause, stderr):
        assert "hook exit status: 7" in text
        assert "failed targets: check-types check-lint" in text


def test_the_cause_carries_the_first_failing_test_id_over_an_earlier_error_line(
    tmp_path: Path,
) -> None:
    body = "\n".join(
        [
            f"{_ERROR_LINE}",
            "FAILED tests/test_alpha.py::test_beta - AssertionError: nope",
            "FAILED tests/test_gamma.py::test_delta - AssertionError: no",
            _targets_block(targets=("check-tests",)),
        ]
    )

    cause, _ = _exhausted(tmp_path=tmp_path, body=body)

    assert "first failing test: tests/test_alpha.py::test_beta" in cause
    assert "test_delta" not in cause
    assert "AssertionError" not in cause


def test_the_cause_carries_the_first_error_line_when_no_test_id_is_reported(
    tmp_path: Path,
) -> None:
    body = f"::: just check-types\n{_ERROR_LINE}\n{_targets_block(targets=('check-types',))}"

    cause, _ = _exhausted(tmp_path=tmp_path, body=body)

    assert f"first error line: {_ERROR_LINE}" in cause
    assert "truncated" not in cause


def test_a_uutils_print_filter_keeps_spaces_in_the_error_excerpt(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tr = bin_dir / "tr"
    _ = tr.write_text(
        "#!/bin/sh\n"
        "if test \"$2\" = '[:print:]\\n'; then\n"
        "    exec /usr/bin/tr -cd '\\041-\\176\\n'\n"
        "fi\n"
        'exec /usr/bin/tr "$@"\n',
        encoding="utf-8",
    )
    tr.chmod(0o755)
    body = f"::: just check-types\n{_ERROR_LINE}\n{_targets_block(targets=('check-types',))}"
    repo = _clone(tmp_path=tmp_path / "clone", hook=_hook_script(body=body, status=1))

    result = _route(repo=repo, extra_env={"PATH": f"{bin_dir}:{os.environ['PATH']}"})

    assert result.returncode != 0, result.stderr
    assert f"first error line: {_ERROR_LINE}" in _cause(repo=repo)


def test_an_overlong_error_line_is_cut_to_200_characters_and_marked_truncated(
    tmp_path: Path,
) -> None:
    long_line = "error: " + "".join(f"{index % 10}" for index in range(400))
    body = f"{long_line}\n{_targets_block(targets=('check-types',))}"

    cause, _ = _exhausted(tmp_path=tmp_path, body=body)

    assert "first error line (truncated to 200 characters): " in cause
    assert long_line[:200] in cause
    assert long_line[:201] not in cause


def test_a_refusal_that_names_no_target_says_the_target_is_unknown_and_why(
    tmp_path: Path,
) -> None:
    cause, stderr = _exhausted(tmp_path=tmp_path, body=_ERROR_LINE)

    for text in (cause, stderr):
        assert (
            "failed targets: unknown, because the hook's recorded output names no failed target"
            in text
        )
        assert "hook exit status: 1" in text
    assert f"first error line: {_ERROR_LINE}" in cause


def test_a_refusal_with_no_recorded_output_says_the_output_is_absent(tmp_path: Path) -> None:
    repo = _clone(tmp_path=tmp_path, hook="#!/bin/sh\nexit 1\n")

    result = _route(repo=repo)

    assert result.returncode != 0, result.stderr
    cause = _cause(repo=repo)
    assert "failed targets: unknown, because the hook's recorded output is absent" in cause
    assert "hook exit status: 1" in cause


def test_a_refusal_whose_recorded_output_cannot_be_read_says_so(tmp_path: Path) -> None:
    repo = _clone(tmp_path=tmp_path, hook=_hook_script(body=_ERROR_LINE, status=1))
    (repo / ".git" / _VERDICT).mkdir()

    result = _route(repo=repo)

    assert result.returncode != 0, result.stderr
    cause = _cause(repo=repo)
    assert "failed targets: unknown, because the hook's recorded output could not be read" in cause


def test_an_excerpt_line_quoting_a_sandbox_credential_is_withheld_by_key_name(
    tmp_path: Path,
) -> None:
    for quoted in (_AUTH_JSON, _AUTH_JSON_ESCAPED):
        workdir = tmp_path / ("verbatim" if quoted == _AUTH_JSON else "escaped")
        body = "\n".join(
            [
                f"error: assertion repr printed {quoted}",
                _targets_block(targets=("check-tests",)),
            ]
        )
        repo = _clone(tmp_path=workdir, hook=_hook_script(body=body, status=1))

        result = _route(repo=repo, extra_env={"CODEX_AUTH_JSON": _AUTH_JSON})

        cause = _cause(repo=repo)
        assert result.returncode != 0, result.stderr
        for text in (cause, result.stderr):
            assert _SECRET not in text
            assert "failed targets: check-tests" in text
        assert (
            "an excerpt line was withheld because it contained the value of CODEX_AUTH_JSON"
            in cause
        )


def test_a_value_shorter_than_eight_characters_does_not_withhold_the_line(
    tmp_path: Path,
) -> None:
    body = f"error: short abc1234 appears\n{_targets_block(targets=('check-tests',))}"
    repo = _clone(tmp_path=tmp_path, hook=_hook_script(body=body, status=1))

    _ = _route(repo=repo, extra_env={"LIVESPEC_SHORT_VALUE": "abc1234"})

    assert "first error line: error: short abc1234 appears" in _cause(repo=repo)


def test_a_credential_value_starting_with_a_slash_is_withheld_by_key_name(
    tmp_path: Path,
) -> None:
    secret = "/leading-slash-secret-0123456789"
    body = f"error: assertion repr printed {secret}\n{_targets_block(targets=('check-tests',))}"
    repo = _clone(tmp_path=tmp_path, hook=_hook_script(body=body, status=1))

    result = _route(repo=repo, extra_env={"LIVESPEC_TEST_TOKEN": secret})

    cause = _cause(repo=repo)
    for text in (cause, result.stderr):
        assert secret not in text
    assert (
        "an excerpt line was withheld because it contained the value of LIVESPEC_TEST_TOKEN"
        in cause
    )


def test_a_path_variable_value_does_not_withhold_the_line(tmp_path: Path) -> None:
    home = "/home/livespec-test-user"
    body = f"error: cannot open {home}/file\n{_targets_block(targets=('check-tests',))}"
    repo = _clone(tmp_path=tmp_path, hook=_hook_script(body=body, status=1))

    _ = _route(repo=repo, extra_env={"HOME": home})

    assert f"first error line: error: cannot open {home}/file" in _cause(repo=repo)


def test_a_commit_run_refusal_is_attributed_from_its_recorded_brief(tmp_path: Path) -> None:
    repo = _clone(tmp_path=tmp_path, hook="#!/bin/sh\nexit 0\n")
    brief = (
        "failed\n"
        "failed targets: check-types check-lint\n\n"
        "Commit run abc, which the previous turn started through the commit runner and which "
        "was still running when that turn ended, ended FAILED with exit status 3; the "
        "repository commit hook ran, and no commit was made. Its own error lines (the tail of "
        "its recorded output at /x/abc.output):\n\n"
        f"{_ERROR_LINE}\nFailed targets (2):\n  - check-types\n  - check-lint\n"
    )
    _ = (repo / ".git" / _LIVE).write_text(brief, encoding="utf-8")

    result = _route(repo=repo)

    assert result.returncode != 0, result.stderr
    cause = _cause(repo=repo)
    assert "hook exit status: 3" in cause
    assert "failed targets: check-types check-lint" in cause
    assert f"first error line: {_ERROR_LINE}" in cause


def test_a_git_refusal_after_a_passing_hook_is_not_reported_as_a_hook_refusal(
    tmp_path: Path,
) -> None:
    """A terminal runner report preserves Git's refusal after the aggregate passed."""
    repo = _clone(tmp_path=tmp_path, hook="#!/bin/sh\nexit 0\n")
    runner = tmp_path / COMMIT_RUNNER_PROGRAM_FILENAME
    _ = runner.write_text(commit_runner_program_source(), encoding="utf-8")
    run_id = "commit-00000000000000000000000000000001"
    record = repo / ".git" / "livespec-commit-runs" / f"{run_id}.json"
    record.parent.mkdir()
    _ = record.write_text(
        json.dumps({"state": "failed", "exit_code": 1, "hook_ran": True}), encoding="utf-8"
    )
    refusal = "You asked to amend the most recent commit, but doing so would make it empty."
    _ = record.with_suffix(".output").write_text(
        "lefthook hook: pre-commit\nAll 94 targets passed\n" + refusal + "\n",
        encoding="utf-8",
    )

    waited = subprocess.run(
        [sys.executable, str(runner), "wait", run_id, "--timeout-seconds", "0"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=_child_environment(),
    )
    report = json.loads(waited.stdout)

    assert report["hook_passed"] is True
    assert report["git_refusal_line"] == refusal
    settle = subprocess.run(
        [
            sys.executable,
            str(runner),
            "settle",
            "--timeout-seconds",
            "0",
            "--brief-file",
            str(repo / ".git" / _LIVE),
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=_child_environment(),
    )
    assert settle.returncode == 0
    _ = (repo / ".git" / _REENTRIES).write_text("1\n", encoding="utf-8")

    result = _route(repo=repo)

    assert result.returncode != 0, result.stderr
    cause = _cause(repo=repo)
    assert refusal in cause
    assert "repository commit hook refused" not in cause


def test_a_passing_commit_after_a_passing_hook_carries_no_git_refusal_line(
    tmp_path: Path,
) -> None:
    """Git's refusal line belongs only to a non-zero commit; a commit that exited 0 has none."""
    hook = "#!/bin/sh\nprintf 'lefthook hook: pre-commit\\nAll 3 targets passed\\n'\nexit 0\n"
    repo = _clone(tmp_path=tmp_path, hook=hook)
    runner = tmp_path / COMMIT_RUNNER_PROGRAM_FILENAME
    _ = runner.write_text(commit_runner_program_source(), encoding="utf-8")
    commit = ["git", "commit", "-m", "feat: a passing commit"]
    environment = {
        **_child_environment(),
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }

    _ = subprocess.run(
        ["git", "commit", "--quiet", "-m", "chore: base"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=environment,
    )
    _ = (repo / "module.py").write_text("x = 2\n", encoding="utf-8")
    _ = subprocess.run(["git", "add", "module.py"], cwd=repo, check=True)

    started = subprocess.run(
        [sys.executable, str(runner), "start", "--", *commit],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    waited = subprocess.run(
        [
            sys.executable,
            str(runner),
            "wait",
            started.stdout.strip(),
            "--timeout-seconds",
            "60",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    report = json.loads(waited.stdout)

    assert report["state"] == "passed"
    assert report["hook_passed"] is True
    assert "git_refusal_line" not in report
    record = json.loads(
        (repo / ".git" / "livespec-commit-runs" / f"{started.stdout.strip()}.json").read_text(
            encoding="utf-8"
        )
    )
    assert "git_refusal_line" not in record


_RUFF_FINDING = "pretooluse_background_guard.py:283:89: E501 Line too long (95 > 88)"
_RUFF_OUTPUT = "\n".join(
    [
        _RUFF_FINDING,
        "    |",
        "282 |         log.error(",
        '283 |             "a message that runs past the configured line length limit ...",',
        "    |                                                                        ^^^ E501",
        "    |",
        "Found 1 error.",
    ]
)


def test_a_ruff_finding_line_is_the_first_error_line_over_a_context_line_quoting_error(
    tmp_path: Path,
) -> None:
    cause, stderr = _exhausted(tmp_path=tmp_path, body=_RUFF_OUTPUT)

    for text in (cause, stderr):
        assert (
            "failed targets: unknown, because the hook's recorded output names no failed target"
            in text
        )
    assert f"first error line: {_RUFF_FINDING}" in cause
    assert "282 |" not in cause


def test_a_ruff_finding_line_without_the_word_error_is_an_error_line(tmp_path: Path) -> None:
    body = "\n".join(["lefthook hook: pre-commit", _RUFF_FINDING, "    |"])

    cause, _ = _exhausted(tmp_path=tmp_path, body=body)

    assert f"first error line: {_RUFF_FINDING}" in cause


def test_a_numbered_source_context_line_is_never_an_error_line(tmp_path: Path) -> None:
    body = "\n".join(["    |", "282 |         log.error(", "283 |     value = 1"])

    cause, _ = _exhausted(tmp_path=tmp_path, body=body)

    assert "no failing test id or error line was found in the hook output" in cause
