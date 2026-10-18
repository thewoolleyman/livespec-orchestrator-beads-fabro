"""Binds `SPECIFICATION/scenarios.md` "Scenario 179 — A sandbox commit whose hook
outlasts one tool call completes with the hook's own verdict", and with it the
commit-leg-completion paragraph of `SPECIFICATION/contracts.md`.

EVERY CASE EXECUTES THE MATERIALIZED PROGRAM against a real local repository
with real hooks installed. Reading its text cannot establish any of the four
sub-scenarios: whether an identity comes back BEFORE a hook finishes, whether a
bounded wait actually returns inside its bound, whether a signal death reports
`no-verdict` rather than a pass, and whether a second start is refused are all
properties of a running process and of files that process writes.

THE SLOW-HOOK FIXTURES ARE THE POINT, not incidental cost. A hook that outlasts
its caller is the whole condition under test, so the cases that assert
detachment install a hook that sleeps far longer than the bound they then pass
to `wait`, and each of them stops its run before returning rather than leaving a
detached session behind.

TWO CONTROLS, because three of these assertions could otherwise be satisfied by
an instrument that cannot return the other answer. The refusal case runs the
SAME refused commit in the FOREGROUND first and compares exit statuses, so the
reported status is measured against git's own rather than against a number this
test chose. The hook-parity case runs a foreground commit and a runner commit
through the same four installed hooks and compares the two recorded sets, so a
runner that silently skipped a hook fails instead of reporting a clean pass.
"""

from __future__ import annotations

import os
import stat
import subprocess
import time
from pathlib import Path

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    plugin_cache_gate_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_commit_runner import (
    SANDBOX_COMMIT_RUNNER_FILENAME,
    sandbox_commit_runner_path_expansion,
    sandbox_commit_runner_prepare_steps_block,
    sandbox_commit_runner_source,
)

_OUTPUT_SEPARATOR = "--- final output lines ---"
# Scrubbed from every child environment so a spawned process does not
# self-instrument and race this suite's own coverage run.
_COVERAGE_ENV_PREFIXES = ("COVERAGE_PROCESS_START", "COV_CORE_")
# Generous against a loaded host: every case that reads a terminal state passes
# this as its bound, and every hook under test finishes in well under it.
_TERMINAL_BOUND_SECONDS = "180"
# The bound the two detachment cases pass. Small enough that a `wait` which
# ignored it would be caught by the elapsed-time assertion.
_SHORT_BOUND_SECONDS = "2"
# The elapsed ceiling a `_SHORT_BOUND_SECONDS` wait is held to. Far above the
# bound so ordinary scheduling noise cannot fail it, and far below the hook
# sleeps so a wait that blocked to completion could not pass.
_SHORT_WAIT_CEILING_SECONDS = 25.0
_HOOK_PARITY_NAMES = ("pre-commit", "prepare-commit-msg", "commit-msg", "post-commit")


def _child_env() -> dict[str, str]:
    """The environment every child here runs under, coverage-scrubbed."""
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(_COVERAGE_ENV_PREFIXES)
    }


def _git(*, repo: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """One fixture git command, raising its own captured stderr on failure.

    `check=True` rather than a hand-rolled branch: every call here is fixture
    setup that must succeed, so a tolerated-failure arm would be a branch no
    case takes — which this tier's per-file coverage gate reads exactly as it
    reads a never-taken branch in the product.
    """
    return subprocess.run(
        ["git", *argv], cwd=repo, check=True, text=True, capture_output=True, env=_child_env()
    )


def _runner(*, root: Path) -> Path:
    """The runner exactly as the prepare step materializes it: its bytes, executable."""
    path = root / SANDBOX_COMMIT_RUNNER_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(sandbox_commit_runner_source(), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _repository(*, root: Path) -> Path:
    """A clone with one commit on `master`, ready for a second one."""
    root.mkdir(parents=True)
    work = root / "clone"
    _ = _git(repo=root, argv=["init", "-b", "master", str(work)])
    _ = _git(repo=work, argv=["config", "user.name", "Sandbox Commit Runner Test"])
    _ = _git(repo=work, argv=["config", "user.email", "commit-runner@example.com"])
    _ = (work / "base.txt").write_text("base\n", encoding="utf-8")
    _ = _git(repo=work, argv=["add", "base.txt"])
    _ = _git(repo=work, argv=["commit", "-m", "base"])
    return work


def _hook(*, repo: Path, name: str, body: str) -> None:
    path = repo / ".git" / "hooks" / name
    _ = path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _stage(*, repo: Path, name: str) -> None:
    _ = (repo / name).write_text(f"{name}\n", encoding="utf-8")
    _ = _git(repo=repo, argv=["add", name])


def _invoke(*, program: Path, repo: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(program), *argv],
        cwd=repo,
        check=False,
        text=True,
        capture_output=True,
        env=_child_env(),
    )


def _start(*, program: Path, repo: Path, commit: list[str]) -> str:
    started = _invoke(program=program, repo=repo, argv=["start", "--", *commit])
    assert started.returncode == 0, started.stderr
    return started.stdout.strip()


def _report(*, completed: subprocess.CompletedProcess[str]) -> dict[str, str]:
    """The `key: value` head of a report, parsed; the output tail is dropped.

    Every line above the separator is a `key: value` pair by construction, so
    this needs no filtering arm — which keeps it free of a branch no case takes.
    """
    head = completed.stdout.split(_OUTPUT_SEPARATOR, 1)[0]
    parsed: dict[str, str] = {}
    for line in head.splitlines():
        key, value = line.split(": ", 1)
        parsed[key] = value
    return parsed


def _head(*, repo: Path) -> str:
    return _git(repo=repo, argv=["rev-parse", "HEAD"]).stdout.strip()


def _sleeping_hook(*, marker_dir: Path, seconds: int) -> str:
    """A `pre-commit` that announces it started, then outlasts any bound here."""
    return (
        "#!/bin/sh\n"
        f'printf started > "{marker_dir}/started"\n'
        f"sleep {seconds}\n"
        f'printf finished > "{marker_dir}/finished"\n'
    )


def test_starting_a_commit_returns_an_identity_before_its_hook_finishes(
    tmp_path: Path,
) -> None:
    """Assertion 1: the identity comes back while the hook is still executing."""
    repo = _repository(root=tmp_path / "detach")
    program = _runner(root=tmp_path / "plugins")
    markers = tmp_path / "markers"
    markers.mkdir()
    _hook(repo=repo, name="pre-commit", body=_sleeping_hook(marker_dir=markers, seconds=90))
    _stage(repo=repo, name="detached.txt")
    base = _head(repo=repo)

    run_id = _start(program=program, repo=repo, commit=["git", "commit", "-m", "detached"])
    # The hook is forked by `git commit`, so give it a moment to reach its own
    # first line. The hook then sleeps for 90 seconds, which is the margin that
    # makes the two absences below mean what they say.
    time.sleep(3.0)
    status = _invoke(program=program, repo=repo, argv=["status", run_id])

    assert run_id, "start printed no commit run identity"
    assert (markers / "started").is_file(), "the commit hook never started"
    assert not (markers / "finished").is_file(), "the commit hook had already finished"
    assert _report(completed=status)["state"] == "running"
    assert _head(repo=repo) == base

    _ = _invoke(program=program, repo=repo, argv=["stop", run_id])


def test_a_bounded_wait_on_a_running_hook_returns_running_inside_its_bound(
    tmp_path: Path,
) -> None:
    """Assertion 2: the wait honours the caller's bound in seconds."""
    repo = _repository(root=tmp_path / "bounded")
    program = _runner(root=tmp_path / "plugins")
    markers = tmp_path / "markers"
    markers.mkdir()
    _hook(repo=repo, name="pre-commit", body=_sleeping_hook(marker_dir=markers, seconds=90))
    _stage(repo=repo, name="bounded.txt")
    run_id = _start(program=program, repo=repo, commit=["git", "commit", "-m", "bounded"])

    before = time.monotonic()
    waited = _invoke(program=program, repo=repo, argv=["wait", run_id, _SHORT_BOUND_SECONDS])
    elapsed = time.monotonic() - before
    after = _invoke(program=program, repo=repo, argv=["status", run_id])

    assert _report(completed=waited)["state"] == "running"
    assert elapsed < _SHORT_WAIT_CEILING_SECONDS, f"the wait blocked for {elapsed:.1f}s"
    # The wait only reads the run directory, so the run it returned on is
    # untouched and still running afterwards.
    assert _report(completed=after)["state"] == "running"

    _ = _invoke(program=program, repo=repo, argv=["stop", run_id])


def test_a_later_wait_reports_passed_with_status_zero_and_the_resulting_head(
    tmp_path: Path,
) -> None:
    """Assertion 3: the same run, waited on again, carries its verdict and commit id."""
    repo = _repository(root=tmp_path / "passed")
    program = _runner(root=tmp_path / "plugins")
    markers = tmp_path / "markers"
    markers.mkdir()
    _hook(repo=repo, name="pre-commit", body=_sleeping_hook(marker_dir=markers, seconds=8))
    _stage(repo=repo, name="passed.txt")
    base = _head(repo=repo)
    run_id = _start(program=program, repo=repo, commit=["git", "commit", "-m", "passed"])

    early = _invoke(program=program, repo=repo, argv=["wait", run_id, _SHORT_BOUND_SECONDS])
    late = _invoke(program=program, repo=repo, argv=["wait", run_id, _TERMINAL_BOUND_SECONDS])
    report = _report(completed=late)

    assert _report(completed=early)["state"] == "running"
    assert report["state"] == "passed"
    assert report["exit_status"] == "0"
    assert report["head"] == _head(repo=repo)
    assert report["head"] != base
    assert late.returncode == 0, late.stderr


def test_a_commit_completed_through_the_runner_carries_every_hook_written_trailer(
    tmp_path: Path,
) -> None:
    """Assertion 4: the message the hook rewrote is the message the commit carries."""
    repo = _repository(root=tmp_path / "trailers")
    program = _runner(root=tmp_path / "plugins")
    _hook(
        repo=repo,
        name="commit-msg",
        body=(
            "#!/bin/sh\n"
            'printf "\\nHook-Written-Trailer: first\\n" >> "$1"\n'
            'printf "Hook-Written-Second: second\\n" >> "$1"\n'
        ),
    )
    _stage(repo=repo, name="trailers.txt")
    run_id = _start(program=program, repo=repo, commit=["git", "commit", "-m", "trailers"])

    waited = _invoke(program=program, repo=repo, argv=["wait", run_id, _TERMINAL_BOUND_SECONDS])
    message = _git(repo=repo, argv=["log", "-1", "--format=%B"]).stdout

    assert _report(completed=waited)["state"] == "passed", waited.stdout
    assert "Hook-Written-Trailer: first" in message
    assert "Hook-Written-Second: second" in message


def test_a_hook_refusal_reports_failed_with_the_commit_status_and_leaves_head(
    tmp_path: Path,
) -> None:
    """Assertion 5: measured against the FOREGROUND commit's own exit status.

    The foreground control is what makes the reported status evidence rather
    than a number this test picked: it establishes what git itself exits with
    for this refusal, so a runner that invented its own status fails here.
    """
    repo = _repository(root=tmp_path / "refused")
    program = _runner(root=tmp_path / "plugins")
    _hook(repo=repo, name="pre-commit", body="#!/bin/sh\necho refusing this commit >&2\nexit 3\n")
    _stage(repo=repo, name="refused.txt")
    base = _head(repo=repo)

    foreground = subprocess.run(
        ["git", "commit", "-m", "refused"],
        cwd=repo,
        check=False,
        text=True,
        capture_output=True,
        env=_child_env(),
    )
    run_id = _start(program=program, repo=repo, commit=["git", "commit", "-m", "refused"])
    waited = _invoke(program=program, repo=repo, argv=["wait", run_id, _TERMINAL_BOUND_SECONDS])
    report = _report(completed=waited)

    assert foreground.returncode != 0, foreground.stdout
    assert report["state"] == "failed"
    assert report["exit_status"] == str(foreground.returncode)
    assert waited.returncode == foreground.returncode
    assert _head(repo=repo) == base
    assert "refusing this commit" in waited.stdout


def test_a_commit_run_ended_by_a_signal_reports_no_verdict_and_never_passed(
    tmp_path: Path,
) -> None:
    """Assertion 6: a signal death is not a verdict, and must never read as one.

    The hook signals its own parent, which IS the `git commit` process, so the
    commit is ended by a signal before it exits on its own — the condition the
    assertion names, produced deterministically rather than by racing a kill.
    """
    repo = _repository(root=tmp_path / "signalled")
    program = _runner(root=tmp_path / "plugins")
    _hook(repo=repo, name="pre-commit", body='#!/bin/sh\nkill -TERM "$PPID"\nsleep 30\n')
    _stage(repo=repo, name="signalled.txt")
    base = _head(repo=repo)
    run_id = _start(program=program, repo=repo, commit=["git", "commit", "-m", "signalled"])

    waited = _invoke(program=program, repo=repo, argv=["wait", run_id, _TERMINAL_BOUND_SECONDS])
    again = _invoke(program=program, repo=repo, argv=["status", run_id])

    assert _report(completed=waited)["state"] == "no-verdict", waited.stdout
    assert _report(completed=again)["state"] == "no-verdict"
    assert waited.returncode != 0
    assert _head(repo=repo) == base


def test_a_second_start_while_one_is_running_is_refused_naming_the_running_run(
    tmp_path: Path,
) -> None:
    """Assertion 7: two hook runs never execute concurrently in one sandbox."""
    repo = _repository(root=tmp_path / "busy")
    program = _runner(root=tmp_path / "plugins")
    markers = tmp_path / "markers"
    markers.mkdir()
    _hook(repo=repo, name="pre-commit", body=_sleeping_hook(marker_dir=markers, seconds=90))
    _stage(repo=repo, name="first.txt")
    run_id = _start(program=program, repo=repo, commit=["git", "commit", "-m", "first"])

    second = _invoke(
        program=program, repo=repo, argv=["start", "--", "git", "commit", "-m", "second"]
    )

    assert second.returncode != 0
    assert run_id in second.stderr
    assert "still running" in second.stderr
    assert not second.stdout.strip(), "a refused start must mint no second identity"

    _ = _invoke(program=program, repo=repo, argv=["stop", run_id])


def test_the_runner_executes_every_hook_a_foreground_commit_executes(
    tmp_path: Path,
) -> None:
    """Assertion 8: the two recorded hook sets are compared, not assumed.

    The foreground leg is the positive control. Without it an empty recorded
    set would read identically for "the runner skipped every hook" and "the
    fixture never installed any", which is the shape of probe that reports a
    clean pass over a question it could not answer.
    """
    repo = _repository(root=tmp_path / "parity")
    program = _runner(root=tmp_path / "plugins")
    ledger = tmp_path / "hooks-fired.log"
    for name in _HOOK_PARITY_NAMES:
        _hook(repo=repo, name=name, body=f'#!/bin/sh\nprintf "{name}\\n" >> "{ledger}"\n')

    _stage(repo=repo, name="foreground.txt")
    _ = _git(repo=repo, argv=["commit", "-m", "foreground"])
    foreground_fired = sorted(set(ledger.read_text(encoding="utf-8").split()))
    _ = ledger.write_text("", encoding="utf-8")

    _stage(repo=repo, name="through-runner.txt")
    run_id = _start(program=program, repo=repo, commit=["git", "commit", "-m", "through-runner"])
    waited = _invoke(program=program, repo=repo, argv=["wait", run_id, _TERMINAL_BOUND_SECONDS])
    runner_fired = sorted(set(ledger.read_text(encoding="utf-8").split()))

    assert _report(completed=waited)["state"] == "passed", waited.stdout
    assert foreground_fired == sorted(_HOOK_PARITY_NAMES)
    assert runner_fired == foreground_fired


def test_the_prepare_pass_materializes_the_runner_below_the_sandbox_plugins_root() -> None:
    """The runner has to BE in the sandbox before the first agent turn runs.

    A one-shot heredoc cannot be re-entered, so the program lands on disk at
    prepare time and rides the same block the publication helpers ride — all of
    them below one root, so a sandbox given a subset fails closed at a stage
    whose refusal would otherwise name the wrong seam.
    """
    source = sandbox_commit_runner_source()
    path = sandbox_commit_runner_path_expansion()
    block = sandbox_commit_runner_prepare_steps_block()

    assert block, "the runner renders no prepare step, so no sandbox would carry it"
    parsed = tomli.loads(block)
    [step] = parsed["run"]["prepare"]["steps"]
    script = step["script"]
    assert source.startswith("#!/bin/sh\n")
    assert "--no-verify" not in source
    assert "LIVESPEC_CHECK_SKIP" not in source
    assert path.endswith(f"/{SANDBOX_COMMIT_RUNNER_FILENAME}")
    assert f"cat > \"{path}\" <<'LIVESPEC_SANDBOX_COMMIT_RUNNER'" in script
    assert source in script
    assert f'chmod 700 "{path}"' in script
    assert block in plugin_cache_gate_prepare_steps_block()
