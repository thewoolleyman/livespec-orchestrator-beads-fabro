"""The materialized sandbox commit runner, exercised in-process with no real process.

Work-item `bd-ib-atyefi`; `SPECIFICATION/contracts.md` "A commit leg completes
past one tool call" and Scenario 179. The program is stdlib-only source the
prepare step writes into the sandbox, so these cases load that exact source into
a fresh namespace and replace its `subprocess` module and process table with
fakes: `check-tests-no-subprocess-spawn` forbids a real spawn, and the item's
rider (coordinator ruling R18) chose that route over an allowlist entry. What
they pin is the clause's own vocabulary -- `running` until the commit's own
process records a verdict, `no-verdict` for a commit ended by a signal or a run
whose processes are gone, a refused start that names the running run, and no
start of a commit that skips its hooks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    REPORT_EXIT_CODE_KEY,
    REPORT_HEAD_KEY,
    REPORT_HOOK_RAN_KEY,
    REPORT_OUTPUT_TAIL_KEY,
    REPORT_RUN_ID_KEY,
    REPORT_STATE_KEY,
    commit_runner_prepare_steps_block,
    commit_runner_program_path_expansion,
    commit_runner_program_source,
)

_RUN_ID = "commit-00000000000000000000000000000001"


@dataclass
class _FakeSubprocess:
    """The slice of `subprocess` the program uses, recording every call."""

    returncode: int = 0
    runs: list[list[str]] = field(default_factory=list)
    popens: list[list[str]] = field(default_factory=list)
    DEVNULL: int = -3
    STDOUT: int = -2

    def run(self, command: list[str], **kwargs: Any) -> SimpleNamespace:
        self.runs.append(command)
        stdout = kwargs["stdout"]
        _ = stdout.write(
            "│ lefthook v1.13.6  hook: pre-commit │\nFailed targets (1):\n  - check-types\n"
        )
        return SimpleNamespace(returncode=self.returncode)

    def Popen(self, command: list[str], **kwargs: Any) -> SimpleNamespace:  # noqa: N802
        assert kwargs["start_new_session"] is True
        assert kwargs["stdin"] == self.DEVNULL
        self.popens.append(command)
        return SimpleNamespace(pid=4242)


def _program(tmp_path: Path, fake: _FakeSubprocess | None = None) -> dict[str, Any]:
    """The runner's exact source, loaded with its git and process access faked."""
    namespace: dict[str, Any] = {"__name__": "livespec_commit_runner_under_test"}
    code = compile(
        commit_runner_program_source(),
        str(tmp_path / COMMIT_RUNNER_PROGRAM_FILENAME),
        "exec",
    )
    exec(code, namespace)  # noqa: S102 — the materialized program's exact source, in-process
    runs = tmp_path / "runs"
    answers: dict[tuple[str, ...], str] = {
        ("rev-parse", "--git-path", "livespec-commit-runs"): str(runs),
        ("rev-parse", "--show-toplevel"): str(tmp_path),
        ("rev-parse", "HEAD"): "0123abc",
    }

    def git_output(*argv: str) -> str:
        return answers[argv]

    namespace["git_output"] = git_output
    namespace["subprocess"] = fake or _FakeSubprocess()
    return namespace


def _record(tmp_path: Path, run_id: str, record: dict[str, object], pid: int | None) -> Path:
    path = tmp_path / "runs" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(record), encoding="utf-8")
    if pid is not None:
        _ = path.with_suffix(".pid").write_text(f"{pid}\n", encoding="utf-8")
    return path


def _proc_entry(proc: Path, pid: int, state: str, group: int) -> None:
    (proc / str(pid)).mkdir(parents=True)
    _ = (proc / str(pid) / "stat").write_text(
        f"{pid} (git commit) {state} 1 {group} {group} 0", encoding="utf-8"
    )


def _alive(group: int) -> bool:
    return group == 4242


def _gone(group: int) -> bool:
    del group
    return False


def _last_report(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_the_source_and_prepare_step_carry_no_template_opener_and_no_privileged_write() -> None:
    """The overlay passes through a template engine and the sandbox user may not be root."""
    source = commit_runner_program_source()
    block = commit_runner_prepare_steps_block()

    for opener in ("{" + "{", "{" + "%", "{" + "#"):
        assert opener not in source
        assert opener not in block
    assert "\nLIVESPEC_COMMIT_RUNNER\n" not in source
    assert "[[run.prepare.steps]]" in block
    assert commit_runner_program_path_expansion().endswith("/livespec-commit-runner.py")
    assert "/usr/local/bin" not in block
    assert "__HOOK_BANNER__" not in source
    assert "--no-verify" not in source.replace('"--no-verify"', "")


def test_the_report_keys_the_dispatcher_reads_are_the_ones_the_program_prints(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The JSON keys are the contract between the sandbox and Dispatcher halves."""
    program = _program(tmp_path)
    path = _record(tmp_path, _RUN_ID, {"state": "passed", "exit_code": 0, "head": "0123abc"}, None)
    _ = path.with_suffix(".output").write_text("line one\nline two\n", encoding="utf-8")

    assert program["wait"](_RUN_ID, 0) == 0
    report = _last_report(capsys)

    assert report == {
        REPORT_RUN_ID_KEY: _RUN_ID,
        REPORT_STATE_KEY: "passed",
        REPORT_EXIT_CODE_KEY: 0,
        REPORT_HEAD_KEY: "0123abc",
        REPORT_HOOK_RAN_KEY: False,
        REPORT_OUTPUT_TAIL_KEY: "line one\nline two",
    }


def test_a_running_commit_is_reported_running_when_the_bound_expires(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A live run's wait returns `running` and nothing else once its bound is spent."""
    program = _program(tmp_path)
    program["group_alive"] = _alive
    _ = _record(tmp_path, _RUN_ID, {"state": "running"}, 4242)

    assert program["wait"](_RUN_ID, 0) == 0

    assert _last_report(capsys) == {REPORT_RUN_ID_KEY: _RUN_ID, REPORT_STATE_KEY: "running"}


def test_a_running_record_whose_processes_are_gone_reads_as_no_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario 179: a commit run no longer running without a recorded status is not a commit."""
    program = _program(tmp_path)
    program["group_alive"] = _gone
    _ = _record(tmp_path, _RUN_ID, {"state": "running"}, 4242)

    _ = program["wait"](_RUN_ID, 30)
    report = _last_report(capsys)

    assert report[REPORT_STATE_KEY] == "no-verdict"
    assert report[REPORT_EXIT_CODE_KEY] is None


def test_a_running_record_still_in_its_launch_window_reads_as_running(tmp_path: Path) -> None:
    """Before the pid file exists the worker is starting, not gone."""
    program = _program(tmp_path)
    path = _record(tmp_path, _RUN_ID, {"state": "running"}, None)

    assert program["current_state"](path, {"state": "running"}) == "running"
    assert program["current_state"](path, {"state": 7}) == "no-verdict"


def test_group_liveness_reads_the_process_table_and_ignores_zombies(tmp_path: Path) -> None:
    """Any non-zombie process of the run's session group keeps the run alive."""
    program = _program(tmp_path)
    proc = tmp_path / "proc"
    _proc_entry(proc, 4242, "Z", 4242)
    (proc / "self").mkdir()
    (proc / "999").mkdir()

    assert program["group_alive"](4242, str(proc)) is False

    _proc_entry(proc, 4250, "S", 4242)

    assert program["group_alive"](4242, str(proc)) is True
    assert program["group_alive"](7, str(proc)) is False


def test_group_liveness_without_a_process_table_asks_the_kernel(tmp_path: Path) -> None:
    """With no `/proc`, signal 0 to the group is the probe."""
    program = _program(tmp_path)
    calls: list[tuple[int, int]] = []

    def killpg(group: int, signal: int) -> None:
        calls.append((group, signal))
        if group != 4242:
            raise ProcessLookupError

    def isdir(path: str) -> bool:
        del path
        return False

    program["os"] = SimpleNamespace(path=SimpleNamespace(isdir=isdir), killpg=killpg)

    assert program["group_alive"](4242, "/no-proc") is True
    assert program["group_alive"](4243, "/no-proc") is False
    assert calls == [(4242, 0), (4243, 0)]


def test_a_second_start_while_one_is_running_is_refused_naming_the_running_run(
    tmp_path: Path,
) -> None:
    """Scenario 179: the runner refuses the start and names the running commit run."""
    fake = _FakeSubprocess()
    program = _program(tmp_path, fake)
    program["group_alive"] = _alive
    _ = _record(tmp_path, _RUN_ID, {"state": "running"}, 4242)
    _ = (tmp_path / "runs" / "unreadable.json").write_text("[not a record", encoding="utf-8")

    with pytest.raises(program["RunnerRefusal"], match=_RUN_ID):
        program["start"](["git", "commit", "-m", "next"], "/runner.py")
    assert fake.popens == []


def test_a_start_launches_the_commit_unchanged_in_its_own_session_and_prints_its_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The run is recorded, the worker is launched detached, and start does not wait."""
    fake = _FakeSubprocess()
    program = _program(tmp_path, fake)
    command = ["mise", "exec", "--", "git", "commit", "--amend", "--no-edit"]
    _ = _record(tmp_path, "commit-finished", {"state": "failed", "exit_code": 1}, None)

    assert program["start"](command, "/runner.py") == 0
    run_id = capsys.readouterr().out.strip()
    record = json.loads((tmp_path / "runs" / f"{run_id}.json").read_text(encoding="utf-8"))

    assert record == {"state": "running", "command": command, "root": str(tmp_path)}
    assert fake.popens[0][1:] == ["/runner.py", "worker", run_id]
    assert (tmp_path / "runs" / f"{run_id}.pid").read_text(encoding="utf-8") == "4242\n"


@pytest.mark.parametrize(
    "command",
    [
        ["git", "commit", "--no-verify", "-m", "x"],
        ["git", "commit", "-anm", "x"],
        ["mise", "exec", "--", "git", "commit", "-n"],
        ["git", "commit", "--no-verif", "-m", "x"],
        ["git", "commit", "--no-v"],
    ],
)
def test_a_start_that_would_skip_the_hooks_is_refused(tmp_path: Path, command: list[str]) -> None:
    """The runner never passes `--no-verify` and never starts a commit that skips hooks."""
    program = _program(tmp_path)

    with pytest.raises(program["RunnerRefusal"], match="skips its hooks"):
        program["start"](command, "/runner.py")


@pytest.mark.parametrize(
    "arguments",
    [
        ["-m", "fix -n handling"],
        ["-am", "no"],
        ["-m"],
        ["--amend", "--", "-n"],
        ["-S"],
        ["-uno", "-m", "x"],
        ["--no-edit", "--amend"],
    ],
)
def test_a_value_that_merely_contains_n_does_not_read_as_skipping_hooks(
    tmp_path: Path, arguments: list[str]
) -> None:
    """A message value, a bundle ending in a value option, or a pathspec is not `-n`."""
    program = _program(tmp_path)

    assert program["skips_hooks"](arguments) is False


def test_a_start_of_anything_but_a_git_commit_is_refused(tmp_path: Path) -> None:
    """The runner starts commits, never an arbitrary command."""
    program = _program(tmp_path)

    with pytest.raises(program["RunnerRefusal"], match="ordinary `git commit`"):
        program["start"](["git", "push"], "/runner.py")


def test_the_worker_records_the_commit_s_own_exit_status_and_head(tmp_path: Path) -> None:
    """`passed` carries the resulting HEAD; `failed` carries the refusal's status."""
    passing = _FakeSubprocess(returncode=0)
    program = _program(tmp_path, passing)
    path = _record(tmp_path, _RUN_ID, {"state": "running", "command": ["git", "commit"]}, 1)

    assert program["worker"](_RUN_ID) == 0
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "state": "passed",
        "exit_code": 0,
        "head": "0123abc",
        "hook_ran": True,
    }
    assert path.with_suffix(".pid").read_text(encoding="utf-8").strip().isdigit()

    refusing = _FakeSubprocess(returncode=1)
    program = _program(tmp_path, refusing)
    _ = _record(tmp_path, _RUN_ID, {"state": "running", "command": ["git", "commit"]}, 1)

    _ = program["worker"](_RUN_ID)

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "state": "failed",
        "exit_code": 1,
        "hook_ran": True,
    }
    assert "check-types" in path.with_suffix(".output").read_text(encoding="utf-8")


def test_a_commit_ended_by_a_signal_records_no_verdict(tmp_path: Path) -> None:
    """Scenario 179: a commit process ended by a signal is not a failed commit."""
    program = _program(tmp_path, _FakeSubprocess(returncode=-15))
    path = _record(tmp_path, _RUN_ID, {"state": "running", "command": ["git", "commit"]}, 1)

    assert program["worker"](_RUN_ID) == 1

    assert json.loads(path.read_text(encoding="utf-8")) == {"state": "no-verdict", "signal": 15}


def test_main_routes_operations_and_reports_refusals_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`start --` strips the separator; an unknown run is a refusal with exit status 2."""
    fake = _FakeSubprocess(returncode=0)
    program = _program(tmp_path, fake)

    assert program["main"](["start", "--", "git", "commit", "-m", "x"], "/runner.py") == 0
    run_id = capsys.readouterr().out.strip()
    assert json.loads((tmp_path / "runs" / f"{run_id}.json").read_text(encoding="utf-8"))[
        "command"
    ] == ["git", "commit", "-m", "x"]

    assert program["main"](["wait", "commit-missing", "--timeout-seconds", "0"], "/r.py") == 2
    assert "no commit run commit-missing" in capsys.readouterr().err

    _ = _record(tmp_path, "commit-w", {"state": "running", "command": ["git", "commit"]}, None)
    assert program["main"](["worker", "commit-w"], "/runner.py") == 0


def test_a_commit_that_passed_while_the_wait_looked_is_reported_passed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The worker writes its verdict and then exits, so a gone group is re-read first."""
    program = _program(tmp_path)
    path = _record(tmp_path, _RUN_ID, {"state": "running"}, 4242)
    stale = {"state": "running"}

    def gone_after_verdict(group: int) -> bool:
        del group
        _ = path.write_text(
            json.dumps({"state": "passed", "exit_code": 0, "head": "0123abc", "hook_ran": True}),
            encoding="utf-8",
        )
        return False

    program["group_alive"] = gone_after_verdict

    assert program["report"](_RUN_ID, path, stale) == 0
    report = _last_report(capsys)

    assert report[REPORT_STATE_KEY] == "passed"
    assert report[REPORT_HEAD_KEY] == "0123abc"
    assert report[REPORT_HOOK_RAN_KEY] is True


_OTHER_RUN_ID = "commit-00000000000000000000000000000002"
_HOOK_REFUSAL_OUTPUT = (
    "│ lefthook v1.13.6  hook: pre-commit │\r\n"
    "::: just check-types\r\n"
    "module.py:3:1 - error: Type of x is partially unknown\r\n"
    "Failed targets (2):\r\n"
    "  - check-types\r\n"
    "  - check-lint\r\n"
    "error: Recipe check-pre-commit failed with exit code 1\r\n"
)


def _settle_program(tmp_path: Path) -> dict[str, Any]:
    program = _program(tmp_path)
    assert "settle" in program
    return program


def _alive_once_then(path: Path, verdict: dict[str, object]) -> Any:
    """A liveness probe that sees the run live at entry, then records `verdict` and exits."""
    calls: list[int] = []

    def probe(group: int) -> bool:
        del group
        calls.append(1)
        if len(calls) == 1:
            return True
        _ = path.write_text(json.dumps(verdict), encoding="utf-8")
        return False

    return probe


def test_settle_with_no_live_commit_run_removes_a_stale_brief_and_prints_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A turn that ended with every commit run terminal leaves no live-commit brief."""
    program = _settle_program(tmp_path)
    brief = tmp_path / "brief"
    _ = brief.write_text("passed\nstale\n", encoding="utf-8")
    _ = _record(tmp_path, _RUN_ID, {"state": "passed", "exit_code": 0, "head": "0123abc"}, None)

    assert program["settle"](30, str(brief)) == 0

    assert not brief.exists()
    assert capsys.readouterr().out == ""


def test_settle_waits_for_the_live_run_and_a_passed_verdict_is_briefed_with_its_head(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The turn ended mid-commit; the run waits, and the commit it finds PASSED is named."""
    program = _settle_program(tmp_path)
    path = _record(tmp_path, _RUN_ID, {"state": "running"}, 4242)
    program["group_alive"] = _alive_once_then(
        path, {"state": "passed", "exit_code": 0, "head": "0123abc", "hook_ran": True}
    )
    brief = tmp_path / "brief"

    assert program["settle"](30, str(brief)) == 0

    lines = brief.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "passed"
    assert _RUN_ID in "\n".join(lines[1:])
    assert "0123abc" in "\n".join(lines[1:])
    assert json.loads(capsys.readouterr().out) == {
        "settled": [{REPORT_RUN_ID_KEY: _RUN_ID, REPORT_STATE_KEY: "passed"}]
    }


def test_settle_briefs_a_failed_run_with_its_failed_targets_and_error_lines(
    tmp_path: Path,
) -> None:
    """A failed commit run is named, with the hook's failed targets from its FULL output."""
    program = _settle_program(tmp_path)
    path = _record(tmp_path, _RUN_ID, {"state": "running"}, 4242)
    _ = path.with_suffix(".output").write_text(
        "scrolled-off first line\n" * 100 + _HOOK_REFUSAL_OUTPUT, encoding="utf-8"
    )
    program["group_alive"] = _alive_once_then(
        path, {"state": "failed", "exit_code": 1, "hook_ran": True}
    )
    brief = tmp_path / "brief"

    assert program["settle"](30, str(brief)) == 0

    lines = brief.read_text(encoding="utf-8").splitlines()
    body = "\n".join(lines[1:])
    assert lines[0] == "failed"
    assert _RUN_ID in body
    assert "failed targets: check-types check-lint" in body
    assert "module.py:3:1 - error: Type of x is partially unknown" in body


def test_settle_briefs_a_run_that_ended_without_a_verdict_as_having_made_no_commit(
    tmp_path: Path,
) -> None:
    """A run whose processes are gone with no recorded status made no commit."""
    program = _settle_program(tmp_path)
    program["group_alive"] = _gone
    _ = _record(tmp_path, _RUN_ID, {"state": "running"}, 4242)
    brief = tmp_path / "brief"

    assert program["settle"](30, str(brief)) == 0

    lines = brief.read_text(encoding="utf-8").splitlines()
    body = "\n".join(lines[1:])
    assert lines[0] == "no-verdict"
    assert _RUN_ID in body
    assert "ended without a verdict" in body
    assert "no commit was made" in body


def test_settle_reports_running_when_the_bound_expires_and_the_worst_run_leads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run still live at the bound is `running`, and it outranks a passed sibling."""
    program = _settle_program(tmp_path)
    program["group_alive"] = _alive
    _ = _record(tmp_path, _OTHER_RUN_ID, {"state": "running"}, 4242)
    brief = tmp_path / "brief"

    assert program["settle"](0, str(brief)) == 0

    lines = brief.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "running"
    assert _OTHER_RUN_ID in "\n".join(lines[1:])
    assert json.loads(capsys.readouterr().out)["settled"][0][REPORT_STATE_KEY] == "running"


def test_main_routes_the_settle_operation_with_its_bound_and_brief_file(
    tmp_path: Path,
) -> None:
    """`settle --timeout-seconds N --brief-file F` is a parseable operation of the runner."""
    program = _settle_program(tmp_path)
    brief = tmp_path / "brief"

    assert (
        program["main"](["settle", "--timeout-seconds", "0", "--brief-file", str(brief)], "/r.py")
        == 0
    )
