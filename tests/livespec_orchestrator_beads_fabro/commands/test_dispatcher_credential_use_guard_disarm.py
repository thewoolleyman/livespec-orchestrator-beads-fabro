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
import ctypes
import fcntl
import os
import select
import signal
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    CREDENTIAL_USE_DEADLINE_ENV_VAR,
    guard_script_text,
)

# The scale that makes the defect matter. The repository's resolved allowance is
# roughly 7.43 days, so this is the real order of magnitude rather than a number
# chosen to make a test convenient: at this distance an armed reaper outlives
# every process identifier it holds.
_WEEK_SECONDS = 7 * 24 * 60 * 60

# An epoch no host clock is near (the year 2100). The case needs a deadline far
# enough away that an armed reaper outlives every identifier it holds, and a
# constant says that without reading the host clock.
_FAR_FUTURE_EPOCH = 4_102_444_800

# prctl(2) option that makes this process the adoptive parent of its orphaned
# descendants, so their exit statuses are collected here instead of by whatever
# the sandbox runs as process 1.
_PR_SET_CHILD_SUBREAPER = 36

# The failure bound on waiting for the reaper to NOTICE a finished group. It
# polls, so disarming is not instantaneous, and the wait ends on the reaper's
# exit rather than on this number; the number only keeps a reaper that never
# disarms from hanging the suite. It must stay far below the deadline above, or
# the case could pass against a reaper that merely slept.
_DISARM_SETTLE_SECONDS = 60.0

# Where the holder pipe's write end is placed. The guard shell uses descriptor 3
# for its own stdin duplicate, so the inherited descriptor must not collide.
_HOLDER_FD_FLOOR = 100

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


class _HolderPipe:
    """A pipe whose write end every process the guard launches inherits.

    The guard shell, the adapter, any descendant and the DETACHED reaper all
    hold a copy of the write end, because none of them closes descriptors it
    did not open. Once this side has sealed its own copy, the read end reaches
    EOF exactly when the last of them has exited. That is the event the reaper's
    disarm is observed through: it is not this interpreter's child, so there is
    no handle to wait on and no clock to inject, but it cannot leave the process
    table without releasing its copy.
    """

    def __init__(self) -> None:
        self.read_fd, write_fd = os.pipe()
        self.write_fd: int | None = fcntl.fcntl(write_fd, fcntl.F_DUPFD, _HOLDER_FD_FLOOR)
        os.close(write_fd)

    def seal(self) -> None:
        """Drop this side's own copy of the write end, once the launch is done."""
        if self.write_fd is not None:
            os.close(self.write_fd)
            self.write_fd = None

    def all_holders_gone(self, *, budget_seconds: float) -> bool:
        """Block until every holder has exited; the budget only bounds a wait that never ends."""
        readable, _, _ = select.select([self.read_fd], [], [], budget_seconds)
        return bool(readable)

    def holders(self) -> list[str]:
        """Describe every OTHER process holding a descriptor on this pipe.

        Read from `/proc` by the pipe's inode, so a wait that never reaches EOF
        can say which process kept it open and what state it was in.
        """
        needle = f"pipe:[{os.fstat(self.read_fd).st_ino}]"
        found: list[str] = []
        for entry in Path("/proc").iterdir():
            # A process may exit between the listing and any read of it, and
            # that is the answer this scan wants: it no longer holds anything.
            with contextlib.suppress(OSError):
                held = [fd.name for fd in (entry / "fd").iterdir() if str(fd.readlink()) == needle]
                if held and entry.name.isdigit() and entry.name != str(os.getpid()):
                    stat = (entry / "stat").read_text(encoding="utf-8")
                    command = (entry / "cmdline").read_bytes().replace(b"\0", b" ")
                    found.append(
                        f"pid {entry.name} state {stat.rpartition(') ')[2][:1]} "
                        f"fds {','.join(held)} command {command.decode(errors='replace').strip()!r}"
                    )
        return found

    def close(self) -> None:
        self.seal()
        os.close(self.read_fd)


@contextmanager
def _holder_pipe() -> Iterator[_HolderPipe]:
    pipe = _HolderPipe()
    try:
        yield pipe
    finally:
        pipe.close()


def _launch_guarded(
    *, guard: Path, command: list[str], holders: _HolderPipe
) -> subprocess.CompletedProcess[str]:
    """Run the SHIPPED guard around `command`, handing every descendant the holder pipe."""
    assert holders.write_fd is not None
    result = subprocess.run(
        ["/bin/sh", str(guard), "--", *command],
        capture_output=True,
        text=True,
        timeout=_LAUNCH_TIMEOUT_SECONDS,
        env=_env_with(deadline=_FAR_FUTURE_EPOCH),
        pass_fds=(holders.write_fd,),
        check=False,
    )
    holders.seal()
    return result


def test_process_scan_tolerates_a_process_disappearing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A vanished proc entry must not hide a later, still-running owned process."""
    guard = tmp_path / "unique-guard.sh"
    matching = tmp_path / "123"
    unrelated = tmp_path / "456"
    matching.mkdir()
    unrelated.mkdir()
    (matching / "cmdline").write_bytes(b"/bin/sh\0" + str(guard).encode() + b"\0")
    (unrelated / "cmdline").write_bytes(b"/bin/sh\0unrelated.sh\0")
    # The numeric entry has vanished after listing; the nonnumeric entry is
    # deliberately unreadable too, but must be skipped before any read.
    entries = [tmp_path / "789", tmp_path / "self", unrelated, matching]
    monkeypatch.setattr(Path, "iterdir", lambda _path: iter(entries))

    assert _processes_naming(guard=guard) == [123]


@contextmanager
def _adopting_orphans() -> Iterator[None]:
    """Make this process the parent of every orphan the guarded launch leaves.

    An orphaned descendant that is killed stays a zombie until its parent
    collects it, and its parent is whatever runs as process 1 in the sandbox.
    A process 1 that never collects (a bare `tail -f /dev/null` in a container
    job) leaves the zombie in the guard's process group forever, so the reaper
    keeps seeing a member and stays armed. Adopting the orphans lets the case
    collect the one it kills, so the group empties for real.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    assert libc.prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) == 0, os.strerror(ctypes.get_errno())
    try:
        yield
    finally:
        _ = libc.prctl(_PR_SET_CHILD_SUBREAPER, 0, 0, 0, 0)


def _collect(*, pid: int) -> None:
    """Collect a killed child's exit status; a pid that is not ours has none to collect."""
    with contextlib.suppress(ChildProcessError):
        _ = os.waitpid(pid, 0)


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
        for pid in (*extra_pids, *_processes_naming(guard=guard)):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGKILL)
            _collect(pid=pid)


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
    with _owned_processes(guard=guard), _holder_pipe() as holders:
        result = _launch_guarded(
            guard=guard, command=["/bin/sh", "-c", f"printf done > {marker}"], holders=holders
        )

        # The positive control rides along: a far-future deadline is a bound,
        # not a refusal, so the ordinary command must actually have run.
        assert result.returncode == 0, result.stderr
        assert marker.read_text(encoding="utf-8") == "done"

        disarmed = holders.all_holders_gone(budget_seconds=_DISARM_SETTLE_SECONDS)
        stragglers = _processes_naming(guard=guard)
        assert disarmed and stragglers == [], (
            "a reaper is still armed after the guarded group finished; it holds "
            f"a recyclable process-group id for up to {_WEEK_SECONDS}s "
            f"(pids {stragglers}); holders of the pipe: {holders.holders()}"
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
    # The adapter records its child's PID synchronously before returning, so
    # observing ownership does not depend on when the descendant is scheduled.
    adapter = (
        "sleep 600 >/dev/null 2>&1 </dev/null & child=$!; "
        f"printf '%s' \"$child\" > {pid_file}; exit 0"
    )
    with _owned_processes(guard=guard) as owned, _adopting_orphans(), _holder_pipe() as holders:
        result = _launch_guarded(guard=guard, command=["/bin/sh", "-c", adapter], holders=holders)
        assert result.returncode == 0, result.stderr

        assert pid_file.exists(), "the descendant never recorded its pid"
        descendant = int(pid_file.read_text(encoding="utf-8").strip())
        owned.append(descendant)

        # The adapter has returned, so the guard shell is gone. Anything still
        # naming the guard is the reaper -- and it MUST still be there, because
        # the descendant keeps the group alive.
        reapers = _processes_naming(guard=guard)
        assert reapers != [], (
            "the reaper disarmed while a descendant of the guarded group was "
            "still executing, so that descendant is now unbounded"
        )
        # The reaper is an orphan this case adopted: it exits on its own below,
        # and its status is collected with the descendant's.
        owned.extend(reapers)

        # Release the group, and the reaper must now disarm: its lifetime is
        # tied to the group emptying, in that order, which is the event this
        # case ends on rather than any interval.
        os.kill(descendant, signal.SIGKILL)
        _collect(pid=descendant)
        assert holders.all_holders_gone(budget_seconds=_DISARM_SETTLE_SECONDS), (
            "the reaper stayed armed after the last descendant of the group exited; "
            f"holders of the pipe: {holders.holders()}"
        )


def test_the_holder_report_names_a_process_that_keeps_the_pipe_open() -> None:
    """The failure message must say WHICH process held the pipe, not merely that one did."""
    with _holder_pipe() as holders:
        assert holders.write_fd is not None
        assert holders.holders() == []
        holder = subprocess.Popen(["/bin/sleep", "600"], pass_fds=(holders.write_fd,))
        try:
            holders.seal()
            report = holders.holders()
        finally:
            holder.kill()
            _ = holder.wait()

    assert len(report) == 1
    assert report[0].startswith(f"pid {holder.pid} state ")
    assert "'/bin/sleep 600'" in report[0]
