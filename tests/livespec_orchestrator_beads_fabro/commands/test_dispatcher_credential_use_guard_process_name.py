"""A process NAME must not be able to disarm the credential-use guard.

THE DEFECT THIS COVERS, and why it is an enforcement bypass rather than a
cosmetic parsing slip. The guard decides whether a process group is still its
own by reading `/proc/<pid>/stat` -- field 5 for the group id, field 22 for the
leader's start-time incarnation. Those fields sit behind the `comm` field, which
is the process name in parentheses, and `comm` MAY ITSELF CONTAIN `') '`: it is
operator-supplied text, truncated to fifteen bytes, and a process may rewrite it
during its own lifetime.

The first implementation stripped the prefix with `${line#*') '}` -- SHORTEST
prefix removal, which stops at the FIRST `') '` -- while its own comment claimed
it parsed after the FINAL one. For a leader named `agent) worker` the stat line
reads `<pid> (agent) worker) S 1 <pgid> ...`, so the shortest-prefix strip leaves
`worker) S 1 <pgid> ...` and every column behind it shifts by two. Measured on a
synthetic line: the group id reads `1` and the start time reads `0` instead of
the real `1234` and `987654`.

WHAT THAT COSTS, in the direction that matters. `group_is_ours` compares the
shifted start time against the recorded one, sees a mismatch, and concludes the
group is no longer the guard's -- so the reaper DISARMS and the agent keeps
running past the absolute deadline. An independent control measured a heartbeat
continuing 4.693 seconds beyond the deadline with a renamed leader, while the
same case with an ordinary name stopped 0.995 seconds BEFORE it. A guard that
can be switched off by choosing a process name is not a bound.

HOW THE NAME IS SET HERE, WITHOUT SPAWNING PYTHON. `comm` defaults to the
basename of the executed program, so copying `/bin/sh` to a file literally named
`agent) worker` is enough -- no `prctl` call and no Python child, which the
repository's `tests_no_subprocess_spawn` guard would flag. The copy is a plain
shell, so it can run the same heartbeat loop the sibling guard suite uses.

THE INSTRUMENT IS THE HEARTBEAT, not process existence. A stopped-but-unreaped
process writes nothing, so the last timestamp in the beat file is the last moment
the child actually executed -- and a zombie holds no credential. Asking only
whether a pid exists cannot tell the two apart.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    CREDENTIAL_USE_DEADLINE_ENV_VAR,
    GUARD_TERM_GRACE_SECONDS,
    guard_script_text,
)

# The adversarial name. `comm` is capped at fifteen bytes, so this must fit to
# survive the kernel's truncation -- thirteen characters, and it carries the
# `') '` sequence that defeats a shortest-prefix strip.
_HOSTILE_NAME = "agent) worker"

# An ordinary name, as the CONTROL. Without it a passing hostile case could be
# explained by the harness rather than by the parse.
_ORDINARY_NAME = "agentworker"

# Must exceed the guard's own TERM grace, or TERM would be due before the child
# had started and the case would be measuring process startup.
_SOON_SECONDS = GUARD_TERM_GRACE_SECONDS + 4

# Signal-delivery slack only. The guard floors a fractional measurement, so its
# KILL is due at or BEFORE the epoch by construction; this covers the scheduling
# delay between the signal and the child stopping. Never widen it to make a late
# kill pass -- that is precisely the defect being measured.
_HARD_TOLERANCE_SECONDS = 0.5
_SETTLE_SECONDS = 40
_POLL_SECONDS = 0.2

# The real process table. Named so the scan below can be pointed at a synthetic
# one in the case that covers its unreadable-entry arm.
_PROC = Path("/proc")


def _guard_script(*, tmp_path: Path) -> Path:
    """Render the SHIPPED guard at a path unique to this test."""
    script = tmp_path / "credential-use-guard.sh"
    _ = script.write_text(guard_script_text(), encoding="utf-8")
    script.chmod(0o755)
    return script


def _shell_named(*, tmp_path: Path, name: str) -> Path:
    """A real shell whose `comm` is `name`, via the basename the kernel records."""
    target = tmp_path / name
    _ = shutil.copy("/bin/sh", target)
    target.chmod(0o755)
    return target


def _processes_naming(*, guard: Path, root: Path = _PROC) -> list[int]:
    """PIDs whose command line names THIS test's guard script.

    Read-only and incapable of over-matching: `guard` lives under this test's
    own `tmp_path`, so no process outside this case can carry it.

    `root` is the process table to scan and defaults to the real one. It is a
    parameter so the unreadable-entry arm below can be exercised against a
    SYNTHETIC table: against `/proc` that arm fires only when a process happens
    to exit between the listing and the read, which is a race no case can
    schedule, and polling until the race lands buys a flake rather than a
    guarantee.
    """
    needle = str(guard).encode()
    found: list[int] = []
    for entry in root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes()
        except OSError:
            # The process exited between the listing and the read, which is the
            # answer this scan wants anyway.
            continue
        if needle in cmdline:
            found.append(int(entry.name))
    return found


@contextmanager
def _owned_processes(*, guard: Path, pid_file: Path) -> Iterator[None]:
    """Reap everything THIS case started, on every exit path including failure.

    THE CHILD'S PID IS READ HERE, IN THE CLEANUP, rather than registered by the
    case after its launch returns. Against the UNFIXED guard the hostile case
    does not merely fail an assertion -- the child never stops, so the launch
    raises `TimeoutExpired` and any registration step placed after it is never
    reached. An earlier draft registered the pid that way and leaked a live
    heartbeat child on exactly the run the case exists to produce.

    The group is signalled before the pid, because the child under measurement
    is a group leader created by the guard's `setsid` and may have descendants
    of its own. Both are this case's own processes, and the guard-named scan
    matches only this case's unique `tmp_path`.
    """
    try:
        yield
    finally:
        # No `pid_file.exists()` pre-check: `FileNotFoundError` IS an `OSError`,
        # so the suppression below already covers the case where the child never
        # got far enough to record a pid. A pre-check would also be a race of its
        # own, since the file can appear between the test and the read.
        with contextlib.suppress(ValueError, OSError):
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(pid, signal.SIGKILL)
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGKILL)
        for resident in _processes_naming(guard=guard):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(resident, signal.SIGKILL)


def _last_beat(*, beat_file: Path) -> float:
    """The last instant the child was observed EXECUTING."""
    beats = [
        line.strip() for line in beat_file.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert beats, "the child never recorded a heartbeat, so nothing was measured"
    return float(beats[-1])


def _stop_instant_under_guard(*, tmp_path: Path, name: str) -> tuple[float, int]:
    """Run a heartbeat child named `name` under the guard; return its last beat.

    Returns the last instant the child executed, and the absolute deadline it
    was launched against, so the caller compares the two directly.
    """
    guard = _guard_script(tmp_path=tmp_path)
    shell = _shell_named(tmp_path=tmp_path, name=name)
    beat_file = tmp_path / "beats"
    pid_file = tmp_path / "pid"
    deadline = int(time.time()) + _SOON_SECONDS
    env = dict(os.environ)
    env[CREDENTIAL_USE_DEADLINE_ENV_VAR] = str(deadline)

    with _owned_processes(guard=guard, pid_file=pid_file):
        result = subprocess.run(
            [
                "/bin/sh",
                str(guard),
                "--",
                str(shell),
                "-c",
                f"echo $$ > {pid_file}; while : ; do date +%s.%N >> {beat_file}; sleep 0.2; done",
            ],
            capture_output=True,
            text=True,
            timeout=_SETTLE_SECONDS,
            env=env,
            check=False,
        )
        # The guard returns when the child stops. A child still running here
        # would have tripped the launch timeout above instead -- which is itself
        # the defective behaviour, reported by the cases below as a child that
        # never stopped rather than as a harness fault.
        assert result.returncode != 0 or beat_file.exists(), result.stderr
        return _last_beat(beat_file=beat_file), deadline


def test_an_ordinary_leader_name_stops_by_the_deadline(tmp_path: Path) -> None:
    """THE CONTROL: with an unremarkable name the bound already held.

    This is what makes the hostile case below evidence about the PARSE rather
    than about the harness: both cases run the same guard, the same heartbeat
    and the same deadline, and differ only in the leader's `comm`.
    """
    last_beat, deadline = _stop_instant_under_guard(tmp_path=tmp_path, name=_ORDINARY_NAME)
    assert (
        last_beat <= deadline + _HARD_TOLERANCE_SECONDS
    ), f"the child was still executing {last_beat - deadline:.3f}s past the deadline"


def test_a_leader_name_containing_the_stat_delimiter_still_stops(
    tmp_path: Path,
) -> None:
    """A leader named `agent) worker` must NOT escape the absolute deadline.

    The name puts `') '` inside `comm`, which is exactly what a shortest-prefix
    strip mistakes for the end of that field. Under the defective parse the
    group id and the leader incarnation both read as other columns, the ownership
    test concludes the group is not the guard's, the reaper disarms, and the
    child runs on. The assertion is therefore about WHEN THE CHILD STOPPED
    EXECUTING, measured against the absolute epoch -- not about whether the
    reaper happened to still be resident.
    """
    last_beat, deadline = _stop_instant_under_guard(tmp_path=tmp_path, name=_HOSTILE_NAME)
    assert last_beat <= deadline + _HARD_TOLERANCE_SECONDS, (
        f"a leader named {_HOSTILE_NAME!r} kept executing "
        f"{last_beat - deadline:.3f}s past the absolute deadline, so a process "
        "name disarmed the guard"
    )


def test_the_process_scan_skips_entries_it_cannot_read(tmp_path: Path) -> None:
    """The reaping scan must skip an unreadable entry rather than raise.

    WHY THIS IS NOT MERELY A COVERAGE ERRAND. The scan runs inside
    `_owned_processes`' `finally`, so an exception escaping it would replace the
    real assertion failure of whichever case is failing with a cleanup error,
    AND abandon the live heartbeat child that case started -- the precise leak
    the context manager exists to prevent.

    The table is SYNTHETIC because the arm is unreachable on demand against the
    real one: there, an entry becomes unreadable only when its process exits
    between the listing and the read. A directory named `cmdline` raises
    `IsADirectoryError`, an `OSError`, with no race to schedule.
    """
    guard = tmp_path / "credential-use-guard.sh"
    root = tmp_path / "proc"
    # A non-numeric entry, as the real table carries (`self`, `net`).
    (root / "self").mkdir(parents=True)
    # A numeric entry whose `cmdline` cannot be read.
    (root / "41" / "cmdline").mkdir(parents=True)
    # One that genuinely names the guard.
    (root / "42").mkdir()
    _ = (root / "42" / "cmdline").write_bytes(f"/bin/sh\0{guard}\0".encode())
    # And one that does not, so a match is discriminating rather than universal.
    (root / "43").mkdir()
    _ = (root / "43" / "cmdline").write_bytes(b"/bin/sh\0-c\0true\0")

    assert _processes_naming(guard=guard, root=root) == [42]
