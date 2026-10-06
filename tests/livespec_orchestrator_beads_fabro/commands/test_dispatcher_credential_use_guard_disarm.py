"""The guard's reaper must DISARM once the group it bounds has finished.

WHY THIS IS A SEPARATE CONCERN FROM "the deadline is enforced", and why it is a
correctness defect rather than tidiness. The reaper deliberately outlives the
guard shell: the adapter is frequently not the process holding the credential, so
cancelling the reaper when the direct child exits left a credential-using
grandchild unbounded. The first draft bought that guarantee by never cancelling
at all -- the reaper slept to the absolute deadline and then signalled the group
unconditionally.

At the scale this mechanism actually runs at, that is a hazard. The resolved
allowance for this repository is roughly seven days, so a one-second command
left a kill armed against a NUMERIC process-group identifier for a week. PIDs
and PGIDs are recyclable, and inside a long-lived sandbox that identifier is
reused by ordinary work -- the janitor, a check suite, a git invocation. The
reaper would then signal a group it never launched, with no record connecting
the two.

WHAT THE RESOLUTION HAS TO SATISFY, in both directions. A finished group must
disarm, so no recyclable identifier stays armed. A descendant that outlives the
adapter must stay bounded, because that is the case the never-cancel design was
adopted for. And the decision to SIGNAL must rest on evidence that the group is
still the one this guard launched -- polling a bare numeric identifier narrows
the exposure but proves no ownership, since the group can empty and the number
be reused between two polls.

HOW AN ARMED REAPER IS OBSERVED HERE, which is the whole reason these cases can
tell the designs apart. The reaper is a subshell of the guard shell, so it
inherits the guard shell's command line -- and that command line names THIS
test's guard script, which lives at a unique `tmp_path`. A read-only `/proc`
scan for that unique path therefore counts exactly the guard shell plus its
reaper and can match nothing else on the machine.

EVERY CASE CLEANS UP ONLY WHAT IT STARTED, AND IT DOES SO EVEN WHEN IT FAILS.
That is load-bearing rather than hygiene: against the UNFIXED guard the first
case fails by design, and without cleanup around the launch itself a failing run
would leak exactly the week-long reaper the case exists to report. The cleanup
matches on this test's own unique guard path and on pids this test recorded, so
it can never reach an unrelated process.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    CREDENTIAL_USE_DEADLINE_ENV_VAR,
    guard_script_text,
)

# The scale that makes the defect matter. The repository's resolved allowance is
# roughly 7.43 days, so this is the real order of magnitude rather than a number
# chosen to make a test convenient: at this distance an armed reaper outlives
# every process identifier it holds.
_WEEK_SECONDS = 7 * 24 * 60 * 60

# How long the reaper may take to NOTICE a finished group. It polls, so disarming
# is not instantaneous; this bounds the poll interval rather than granting the
# reaper a grace. It must stay far below the deadline above, or the case could
# pass against a reaper that merely slept.
_DISARM_SETTLE_SECONDS = 20.0

# How long a descendant must be observed still holding the group open. Short on
# purpose: the question is whether the reaper is resident at all, not how long.
_ARMED_OBSERVATION_SECONDS = 3.0

_POLL_SECONDS = 0.2
_LAUNCH_TIMEOUT_SECONDS = 60


def _guard_script(*, tmp_path: Path) -> Path:
    """Render the SHIPPED guard at a path unique to this test."""
    script = tmp_path / "credential-use-guard.sh"
    _ = script.write_text(guard_script_text(), encoding="utf-8")
    script.chmod(0o755)
    return script


def _env_with(*, deadline: int) -> dict[str, str]:
    env = dict(os.environ)
    env[CREDENTIAL_USE_DEADLINE_ENV_VAR] = str(deadline)
    return env


def _processes_naming(*, guard: Path) -> list[int]:
    """PIDs whose command line names THIS test's guard script.

    Read-only, and it cannot over-match: `guard` is under the test's own
    `tmp_path`, so no process outside this case can carry it. After the guard
    shell has exited, anything still listed here is the detached reaper.
    """
    needle = str(guard).encode()
    found: list[int] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes()
        except OSError:
            # The process exited between listing and reading, which is the
            # answer this scan wants anyway.
            continue
        if needle in cmdline:
            found.append(int(entry.name))
    return found


def _await_no_guard_process(*, guard: Path, budget_seconds: float) -> list[int]:
    """Poll until no process names the guard, returning whatever still does."""
    deadline = time.monotonic() + budget_seconds
    remaining = _processes_naming(guard=guard)
    while remaining and time.monotonic() < deadline:
        time.sleep(_POLL_SECONDS)
        remaining = _processes_naming(guard=guard)
    return remaining


@contextmanager
def _owned_processes(*, guard: Path) -> Iterator[list[int]]:
    """Reap everything THIS case started, on every exit path including failure.

    Wraps the LAUNCH as well as the assertions. A launch that raises -- the
    descendant case times out against a guard whose stdio it inherits -- would
    otherwise skip cleanup entirely and leave both the stray child and the
    week-long reaper resident.

    `extra_pids` is for processes the case recorded itself; the guard-named scan
    covers the guard shell and its reaper. Both are this case's own.
    """
    extra_pids: list[int] = []
    try:
        yield extra_pids
    finally:
        for pid in extra_pids:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGKILL)
        for pid in _processes_naming(guard=guard):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGKILL)


def test_a_finished_group_disarms_rather_than_arming_a_multi_day_kill(
    tmp_path: Path,
) -> None:
    """A quick command must leave NO reaper armed against a recyclable id.

    THE ASSERTION IS ABOUT WHAT SURVIVES, not about the command's own result.
    The wrapped command finishes in milliseconds and its group is then empty, so
    the process-group identifier the reaper holds is immediately reusable. A
    reaper still resident after that is one that will signal whatever inherits
    the number a week from now.
    """
    guard = _guard_script(tmp_path=tmp_path)
    marker = tmp_path / "ran"
    with _owned_processes(guard=guard):
        result = subprocess.run(
            ["/bin/sh", str(guard), "--", "/bin/sh", "-c", f"printf done > {marker}"],
            capture_output=True,
            text=True,
            timeout=_LAUNCH_TIMEOUT_SECONDS,
            env=_env_with(deadline=int(time.time()) + _WEEK_SECONDS),
            check=False,
        )

        # The positive control rides along: a far-future deadline is a bound,
        # not a refusal, so the ordinary command must actually have run.
        assert result.returncode == 0, result.stderr
        assert marker.read_text(encoding="utf-8") == "done"

        stragglers = _await_no_guard_process(guard=guard, budget_seconds=_DISARM_SETTLE_SECONDS)
        assert stragglers == [], (
            "a reaper is still armed after the guarded group finished; it holds "
            f"a recyclable process-group id for up to {_WEEK_SECONDS}s "
            f"(pids {stragglers})"
        )


def test_a_surviving_descendant_keeps_the_reaper_armed(tmp_path: Path) -> None:
    """THE COUNTER-CONTROL: disarming must not weaken the real enforcement.

    Without this case the test above is satisfied by deleting the reaper
    outright, which is the defect the never-cancel design was adopted to fix: the
    adapter exits while a credential-using grandchild keeps running, and nothing
    would then bound it. Here the adapter exits IMMEDIATELY and leaves a harmless
    descendant executing, so the group is still occupied -- and the reaper must
    still be resident, because the identifier is still ours and the deadline has
    not arrived.

    THE DESCENDANT'S STDIO IS REDIRECTED, and that is required rather than
    tidy. It inherits the guard shell's stdout and stderr, which here are
    `subprocess.run`'s capture pipes; a descendant holding them open keeps
    `run` reading until its timeout even though the adapter exited promptly, so
    the case would fail on a launch timeout and never reach its assertion.
    """
    guard = _guard_script(tmp_path=tmp_path)
    pid_file = tmp_path / "descendant.pid"
    # Stands in for an adapter that spawns a worker and returns. The descendant
    # is a plain sleep -- harmless -- and it holds the group open. Its stdio
    # goes to /dev/null so it does not hold the launch's capture pipes open.
    adapter = (
        f"/bin/sh -c 'echo $$ > {pid_file}; exec sleep 600' " ">/dev/null 2>&1 </dev/null & exit 0"
    )
    with _owned_processes(guard=guard) as owned:
        result = subprocess.run(
            ["/bin/sh", str(guard), "--", "/bin/sh", "-c", adapter],
            capture_output=True,
            text=True,
            timeout=_LAUNCH_TIMEOUT_SECONDS,
            env=_env_with(deadline=int(time.time()) + _WEEK_SECONDS),
            check=False,
        )
        assert result.returncode == 0, result.stderr

        settle = time.monotonic() + 10
        while not pid_file.exists() and time.monotonic() < settle:
            time.sleep(_POLL_SECONDS)
        assert pid_file.exists(), "the descendant never recorded its pid"
        owned.append(int(pid_file.read_text(encoding="utf-8").strip()))

        # The adapter has returned, so the guard shell is gone. Anything still
        # naming the guard is the reaper -- and it MUST still be there, because
        # the descendant keeps the group alive.
        armed = _await_no_guard_process(guard=guard, budget_seconds=_ARMED_OBSERVATION_SECONDS)
        assert armed != [], (
            "the reaper disarmed while a descendant of the guarded group was "
            "still executing, so that descendant is now unbounded"
        )
