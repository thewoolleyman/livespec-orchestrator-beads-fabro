"""The absolute credential-use deadline, enforced against REAL processes.

WHY THESE CASES SPAWN PROCESSES. The assertion under test is that dispatched
coding-agent execution CANNOT CONTINUE past the worker's absolute
credential-use deadline. A predicate returning False, or a mock recording that
`kill` was requested, is not evidence of that: the question is whether the
processes holding the credential are actually gone. So every case below renders
the SHIPPED guard script, runs it around a harmless real child, and then asks
the operating system whether that child still exists.

WHAT EACH CASE EXCLUDES, because a bound has several ways to be fake:

- A guard that refused everything would satisfy the termination cases and fail
  the POSITIVE COMPLETION case, where a sufficiently fresh deadline must let an
  ordinary command finish and pass its own exit status through.
- A guard that only checked at launch would pass the LATE START case and fail
  RUNNING TERMINATION, where the deadline falls while the child is mid-flight.
- A guard that killed only its direct child would pass running termination and
  fail the CREDENTIAL-USING CHILD case, where the adapter parent exits
  immediately and a grandchild keeps running -- which is exactly the shape that
  holds a credential after an adapter returns.
- A guard that sent TERM and assumed compliance would pass those and fail the
  TERM-RESISTANT case.
- A guard measuring a DURATION rather than an instant would pass everything
  above and fail RETRY WITH THE ORIGINAL EPOCH, which is the property that makes
  a retried or resumed launch inherit the remaining budget instead of a fresh
  one.
NOT YET COVERED HERE, and named so its absence is not mistaken for coverage:
an adapter that declares the deadline VARIABLE ITSELF. `render_adapter` places
env pairs ahead of the executable, so an adapter-declared
`LIVESPEC_CREDENTIAL_USE_DEADLINE_EPOCH` would override the projected value.
Refusing that at the render chokepoint is the remaining requirement; a case
setting unrelated variable names would NOT detect it, which is why none is
written here.

THE ARITHMETIC CASE IS NOT COSMETIC. The deadline is capped at the observed
expiry minus the documented margin, because time passes between the final
freshness measurement and the projection -- a bounded renewal request, a queue
wait, sandbox preparation. Anchoring on the projection instant alone stamps a
deadline the credential cannot cover whenever that delay is non-zero, which is
every real dispatch.

NO TEST HERE READS OR WAITS ON THE HOST'S CLOCK. The guard is a shell script that
asks `date` for the instant and `sleep` for the wait, so each case hands it a
`date` and a `sleep` shim over one simulated clock file. A verdict is then a
reading of that file, and every ordering the cases need -- the reaper is armed,
the child has trapped TERM, the wrapper has returned -- is an event the case
waits on: a written FIFO line, a closed descriptor, a child's exit. The only
wall-clock bounds left are hang guards on those waits, which never decide a
verdict.
"""

from __future__ import annotations

import contextlib
import os
import select
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    CREDENTIAL_EXPIRY_ENV_VAR,
    CREDENTIAL_REQUIRED_REMAINING_ENV_VAR,
    CREDENTIAL_USE_DEADLINE_ENV_VAR,
    GUARD_REFUSAL_EXIT_CODE,
    GUARD_TERM_GRACE_SECONDS,
    credential_use_deadline_epoch_capped,
    guard_script_text,
    guarded_acp_command,
)

# The guard spends its TERM grace INSIDE the allowance and hard-kills AT the
# deadline, so a child must stop BY the deadline -- not "eventually". These
# cases therefore read the guard's own simulated clock against the ABSOLUTE
# EPOCH, with no tolerance: the instant a signal fires is a fact about the
# guard's arithmetic, so a loaded host cannot make a correct guard read late.
#
# `_SOON_SECONDS` must exceed the guard's own grace, or TERM would be due before
# the child has started and the case would measure process startup rather than
# the bound.
_SOON_SECONDS = GUARD_TERM_GRACE_SECONDS + 3
_SETTLE_SECONDS = 10
# A liveness guard on a wait for a deterministic event, never a verdict.
_HANG_GUARD_SECONDS = 120
# An arbitrary whole epoch second for the simulated clock. Nothing reads the
# host's clock, so any value works; it is fixed so a failure message names the
# same instants on every run.
_CONTROLLED_EPOCH = 1_900_000_000

# The agents the guard wraps. Each records its pid and then announces on the
# ready FIFO, so a case releases the guard's clock only after the agent has
# installed whatever signal disposition the case is about.
_TERM_HONOURING_AGENT = "echo $$ > {pid}; echo ready > {ready}; exec /bin/sleep 600"
_TERM_RESISTANT_AGENT = "trap '' TERM; echo $$ > {pid}; echo ready > {ready}; exec /bin/sleep 600"
# The adapter parent hands the credential to a TERM-resistant grandchild and
# exits at once; the recorded pid is the grandchild's.
_ADAPTER_PARENT = (
    '/bin/sh -c \'trap "" TERM; echo $$ > {pid}; echo ready > {ready}; '
    "exec /bin/sleep 600' </dev/null >/dev/null 2>&1 &"
)


def _guard(*, tmp_path: Path) -> Path:
    """Render the SHIPPED guard script and make it executable."""
    script = tmp_path / "credential-use-guard.sh"
    _ = script.write_text(guard_script_text(), encoding="utf-8")
    script.chmod(0o755)
    return script


def _hermetic_env() -> dict[str, str]:
    """This process's environment with every credential-use projection removed.

    A factory stage runs this suite INSIDE a guarded launch, so its own process
    carries the deadline, the credential expiry and the required remaining
    lifetime that the Dispatcher projected for that node. Inherited, they make the
    start check grade the STAGE's credential against the STAGE's requirement, so
    a case's verdict depends on which node happens to run the suite: a `review_fix`
    stage requiring 7200 seconds refused the "fresh" one-hour case on 2026-10-10
    while the host and CI, which project nothing, passed it.
    """
    env = dict(os.environ)
    for name in (
        CREDENTIAL_USE_DEADLINE_ENV_VAR,
        CREDENTIAL_EXPIRY_ENV_VAR,
        CREDENTIAL_REQUIRED_REMAINING_ENV_VAR,
    ):
        _ = env.pop(name, None)
    return env


def _write_date_shim(*, bin_dir: Path, clock: Path) -> None:
    """A `date` that reads the simulated clock file in the two formats the guard asks for."""
    shim = bin_dir / "date"
    lines = [
        "#!/bin/sh",
        f'now="$(cat "{clock}")"',
        'case "$1" in',
        """    +%s.%N) awk -v n="$now" 'BEGIN{s=int(n); printf "%d.%09d\\n", s, (n-s)*1e9}' ;;""",
        """    *) awk -v n="$now" 'BEGIN{printf "%d\\n", int(n)}' ;;""",
        "esac",
    ]
    _ = shim.write_text("\n".join(lines) + "\n", encoding="utf-8")
    shim.chmod(0o755)


def _set_clock(*, clock: Path, to: float) -> None:
    """Move the simulated clock; the injected equivalent of waiting for an instant."""
    _ = clock.write_text(f"{to:.6f}\n", encoding="utf-8")


def _fixed_clock(*, tmp_path: Path, now: float) -> tuple[Path, Path]:
    """A `date` that reads a clock the case alone moves; `sleep` stays the host's.

    For cases whose verdict is made at ONE instant -- a launch admitted or
    refused -- so nothing about them waits for time to pass.
    """
    bin_dir = tmp_path / "fixed-clock-bin"
    bin_dir.mkdir()
    clock = tmp_path / "fixed-clock"
    _set_clock(clock=clock, to=now)
    _write_date_shim(bin_dir=bin_dir, clock=clock)
    return bin_dir, clock


def _controlled_clock(
    *, tmp_path: Path, start: float, armed: Path, release: Path
) -> tuple[Path, Path]:
    """Create the guard's `date`/`sleep` seam on a deterministic clock.

    `sleep N` adds N seconds to the clock and returns at once, so the instant the
    guard signals is a reading of the clock file rather than a measurement of host
    scheduling. The FIRST fake sleep announces that the detached reaper is armed
    on the `armed` FIFO and then holds the clock at a standstill until the case
    writes a line to the `release` FIFO; the case uses that standstill to arrange
    whatever must happen BEFORE any signal can fall.
    """
    bin_dir = tmp_path / "controlled-clock-bin"
    bin_dir.mkdir()
    clock = tmp_path / "controlled-clock"
    _set_clock(clock=clock, to=start)
    _write_date_shim(bin_dir=bin_dir, clock=clock)
    sleep_shim = bin_dir / "sleep"
    lines = [
        "#!/bin/sh",
        f'if [ ! -e "{armed}.once" ]; then',
        f'    : > "{armed}.once"',
        f'    printf armed > "{armed}"',
        f'    IFS= read -r _ < "{release}" || true',
        "fi",
        f'now="$(cat "{clock}")"',
        f'awk -v n="$now" -v d="$1" \'BEGIN{{printf "%.6f\\n", n+d}}\' > "{clock}.next"',
        f'mv "{clock}.next" "{clock}"',
    ]
    _ = sleep_shim.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sleep_shim.chmod(0o755)
    return bin_dir, clock


def _run(
    *,
    tmp_path: Path,
    deadline: str | None,
    argv: list[str],
    path_prefix: Path | None = None,
    stdin_text: str | None = None,
    timeout: float = _SETTLE_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """Run the guard around `argv`, with the deadline supplied as the env var."""
    env = _hermetic_env()
    if deadline is not None:
        env[CREDENTIAL_USE_DEADLINE_ENV_VAR] = deadline
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}:{env.get('PATH', '')}"
    return subprocess.run(
        ["/bin/sh", str(_guard(tmp_path=tmp_path)), "--", *argv],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )


@dataclass
class _Rig:
    """One guarded agent on the controlled clock, and every event a case waits on."""

    guarded: subprocess.Popen[bytes]
    pid_file: Path
    clock: Path
    deadline: int
    armed_fd: int
    ready_fd: int
    release_fd: int
    holder_read: int
    holder_write: int


def _start_rig(*, tmp_path: Path, start: float, agent: str) -> _Rig:
    """Start `agent` under the guard on the controlled clock, held at a standstill.

    Three FIFOs carry the rendezvous: `armed` (the reaper reached its first
    sleep), `ready` (the agent installed its disposition) and `release` (the case
    lets the clock move). A pipe whose write end every descendant inherits gives a
    fourth event: EOF on its read end means the whole process tree has exited.
    """
    pid_file = tmp_path / "pid"
    armed_fifo = tmp_path / "armed"
    ready_fifo = tmp_path / "ready"
    release_fifo = tmp_path / "release"
    for fifo in (armed_fifo, ready_fifo, release_fifo):
        os.mkfifo(fifo)
    armed_fd = os.open(armed_fifo, os.O_RDONLY | os.O_NONBLOCK)
    ready_fd = os.open(ready_fifo, os.O_RDONLY | os.O_NONBLOCK)
    release_fd = os.open(release_fifo, os.O_RDWR | os.O_NONBLOCK)
    bin_dir, clock = _controlled_clock(
        tmp_path=tmp_path, start=start, armed=armed_fifo, release=release_fifo
    )
    holder_read, holder_write = os.pipe()
    deadline = _CONTROLLED_EPOCH + _SOON_SECONDS
    env = _hermetic_env()
    env[CREDENTIAL_USE_DEADLINE_ENV_VAR] = str(deadline)
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    guarded = subprocess.Popen(
        [
            "/bin/sh",
            str(_guard(tmp_path=tmp_path)),
            "--",
            "/bin/sh",
            "-c",
            agent.format(pid=pid_file, ready=ready_fifo),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        pass_fds=(holder_write,),
        start_new_session=True,
    )
    return _Rig(
        guarded=guarded,
        pid_file=pid_file,
        clock=clock,
        deadline=deadline,
        armed_fd=armed_fd,
        ready_fd=ready_fd,
        release_fd=release_fd,
        holder_read=holder_read,
        holder_write=holder_write,
    )


def _await_event(*, fd: int, expected: bytes, what: str) -> None:
    """Wait for `expected` on a FIFO; the bound is a hang guard, not a verdict."""
    readable, _, _ = select.select([fd], [], [], _HANG_GUARD_SECONDS)
    assert readable, what
    assert os.read(fd, len(expected)) == expected


def _await_armed_and_ready(*, rig: _Rig) -> None:
    """Both events that must precede the clock moving: reaper armed, agent configured."""
    _await_event(fd=rig.armed_fd, expected=b"armed", what="the reaper never announced it was armed")
    _await_event(
        fd=rig.ready_fd, expected=b"ready\n", what="the agent never announced it was ready"
    )


def _release_clock(*, rig: _Rig) -> None:
    """Let the reaper's first sleep return, which starts simulated time moving."""
    _ = os.write(rig.release_fd, b"release\n")


def _await_tree_exit(*, rig: _Rig, what: str) -> None:
    """Wait for every process that inherited the holder pipe to exit.

    Closing this side's copy of the write end first leaves only descendants
    holding it, so EOF on the read end is the event "the whole tree is gone".
    """
    os.close(rig.holder_write)
    rig.holder_write = -1
    readable, _, _ = select.select([rig.holder_read], [], [], _HANG_GUARD_SECONDS)
    assert readable and os.read(rig.holder_read, 1) == b"", what


def _clock_reading(*, rig: _Rig) -> float:
    return float(rig.clock.read_text(encoding="utf-8").strip())


def _agent_pid(*, rig: _Rig) -> int:
    return int(rig.pid_file.read_text(encoding="utf-8").strip())


def _executing(*, pid: int) -> bool:
    """True while `pid` exists and is not a zombie -- a zombie holds no credential."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return False
    return raw[raw.rfind(")") + 2 :].split()[0] != "Z"


def test_a_missing_process_is_not_executing() -> None:
    """A vanished pid holds no credential, so the liveness reading is false."""
    assert not _executing(pid=999_999_999)


def _close_rig(*, rig: _Rig) -> None:
    """Close this case's descriptors and stop every process the case started.

    The guard, its detached reaper and the shims share the guard's own session;
    the agent leads a session of its own. Signalling both groups is what keeps a
    failed case from leaving a reaper polling on a shim clock after pytest exits.
    """
    for descriptor in (
        rig.armed_fd,
        rig.ready_fd,
        rig.release_fd,
        rig.holder_read,
        rig.holder_write,
    ):
        with contextlib.suppress(OSError):
            os.close(descriptor)
    with contextlib.suppress(OSError):
        os.killpg(rig.guarded.pid, signal.SIGKILL)
    with contextlib.suppress(OSError, ValueError):
        agent_group = os.getpgid(_agent_pid(rig=rig))
        if agent_group != os.getpgrp():
            os.killpg(agent_group, signal.SIGKILL)
    with contextlib.suppress(subprocess.TimeoutExpired):
        _ = rig.guarded.wait(timeout=_SETTLE_SECONDS)


@pytest.mark.parametrize(
    ("agent_group", "own_group", "expected_kills"),
    [
        (303, 404, [(101, signal.SIGKILL), (303, signal.SIGKILL)]),
        (404, 404, [(101, signal.SIGKILL)]),
    ],
)
def test_cleanup_kills_only_an_agent_group_other_than_its_own(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    agent_group: int,
    own_group: int,
    expected_kills: list[tuple[int, signal.Signals]],
) -> None:
    """Cleanup reaches a separate agent session but never signals this test's group."""

    class _Guarded:
        pid = 101

        @staticmethod
        def wait(*, timeout: float) -> None:
            assert timeout == _SETTLE_SECONDS

    pid_file = tmp_path / "pid"
    _ = pid_file.write_text("202\n", encoding="utf-8")
    closed = tuple(os.open(os.devnull, os.O_RDONLY) for _ in range(5))
    killed: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(os, "getpgid", lambda pid: agent_group if pid == 202 else 0)
    monkeypatch.setattr(os, "getpgrp", lambda: own_group)
    monkeypatch.setattr(os, "killpg", lambda group, sig: killed.append((group, sig)))
    rig = _Rig(
        guarded=_Guarded(),  # type: ignore[arg-type]
        pid_file=pid_file,
        clock=tmp_path / "clock",
        deadline=0,
        armed_fd=closed[0],
        ready_fd=closed[1],
        release_fd=closed[2],
        holder_read=closed[3],
        holder_write=closed[4],
    )

    _close_rig(rig=rig)

    assert killed == expected_kills


def test_a_sufficiently_fresh_deadline_lets_an_ordinary_command_finish(
    tmp_path: Path,
) -> None:
    """THE POSITIVE CONTROL: the guard is a bound, not a refusal.

    Without this case every other case here is satisfied by a guard that refuses
    unconditionally, which would make the normal workflow undispatchable while
    looking perfectly enforced.
    """
    marker = tmp_path / "ran"
    bin_dir, _ = _fixed_clock(tmp_path=tmp_path, now=float(_CONTROLLED_EPOCH))
    result = _run(
        tmp_path=tmp_path,
        deadline=str(_CONTROLLED_EPOCH + 3600),
        argv=["/bin/sh", "-c", f"printf done > {marker}; exit 7"],
        path_prefix=bin_dir,
    )

    assert marker.read_text(encoding="utf-8") == "done"
    # The wrapped command's own status passes through, so the guard is
    # transparent to a run that finishes inside its budget.
    assert result.returncode == 7


def test_a_running_child_stops_by_the_deadline_itself(tmp_path: Path) -> None:
    """Execution stops BY the absolute epoch, read off the guard's own clock.

    The assertion is NOT "the process is gone eventually" -- that is satisfied by
    a guard whose grace runs past the deadline, which would permit exactly the
    credential use the bound forbids. The child is a real process that honours
    TERM, so the signal that stops it is the guard's TERM, and the simulated clock
    says when the guard sent it: inside the grace before the deadline, never after.
    """
    rig = _start_rig(tmp_path=tmp_path, start=float(_CONTROLLED_EPOCH), agent=_TERM_HONOURING_AGENT)
    try:
        _await_armed_and_ready(rig=rig)
        assert _clock_reading(rig=rig) == float(_CONTROLLED_EPOCH)
        _release_clock(rig=rig)

        status = rig.guarded.wait(timeout=_HANG_GUARD_SECONDS)

        stopped_at = _clock_reading(rig=rig)
        assert status == 128 + signal.SIGTERM
        assert (
            rig.deadline - GUARD_TERM_GRACE_SECONDS <= stopped_at <= rig.deadline
        ), f"the child was signalled {stopped_at - rig.deadline:+.3f}s from the deadline"
    finally:
        _close_rig(rig=rig)


def test_a_term_resistant_child_still_stops_by_the_deadline(tmp_path: Path) -> None:
    """TERM refusal buys no time at all, not even the escalation grace.

    The child traps TERM, which is what an agent mid-turn with its own signal
    handling looks like. Because the guard lands TERM a grace BEFORE the deadline
    and KILL **at** it, refusing TERM costs the child its grace and nothing more:
    it must still stop by the same instant a compliant child would.

    The clock is held until the child has announced that its trap is installed.
    Without that ordering a loaded host can deliver the TERM before the shell has
    run `trap`, and the agent dies by TERM (exit 143) instead of by the KILL the
    case is about.
    """
    rig = _start_rig(tmp_path=tmp_path, start=float(_CONTROLLED_EPOCH), agent=_TERM_RESISTANT_AGENT)
    try:
        _await_armed_and_ready(rig=rig)
        _release_clock(rig=rig)

        status = rig.guarded.wait(timeout=_HANG_GUARD_SECONDS)

        killed_at = _clock_reading(rig=rig)
        assert status == 128 + signal.SIGKILL
        assert (
            rig.deadline - 1 < killed_at <= rig.deadline
        ), f"a TERM-resistant child was killed {killed_at - rig.deadline:+.3f}s from the deadline"
    finally:
        _close_rig(rig=rig)


def test_a_credential_using_grandchild_stops_by_the_deadline_after_its_parent_exits(
    tmp_path: Path,
) -> None:
    """The ADAPTER PARENT EXITS and its child keeps the credential; both stop by the bound.

    This is the shape a guard that signals only its direct child gets wrong, and
    it is the shape that matters: the process still holding the credential after
    an adapter returns is the grandchild, not the adapter.

    THE HOLD IS LOAD-BEARING. The reaper is detached, so the wrapper returns as
    soon as the short-lived parent exits. The guard's clock is HELD until the
    wrapper has returned, so by construction no signal has been sent when the
    parent exits; only then is the clock released, and the case asks whether the
    TERM-resistant grandchild is gone and when the KILL that stopped it fired.
    """
    rig = _start_rig(tmp_path=tmp_path, start=float(_CONTROLLED_EPOCH), agent=_ADAPTER_PARENT)
    try:
        _await_armed_and_ready(rig=rig)
        # The wrapper has returned, the grandchild runs on, and the bound has not
        # yet fallen: the guard's clock has not moved.
        assert rig.guarded.wait(timeout=_HANG_GUARD_SECONDS) == 0
        grandchild = _agent_pid(rig=rig)
        assert _executing(pid=grandchild)
        assert _clock_reading(rig=rig) == float(_CONTROLLED_EPOCH)

        _release_clock(rig=rig)
        _await_tree_exit(rig=rig, what="the credential-using grandchild was never stopped")

        killed_at = _clock_reading(rig=rig)
        assert (
            rig.deadline - 1 < killed_at <= rig.deadline
        ), f"a credential-using grandchild was killed {killed_at - rig.deadline:+.3f}s from the deadline"
    finally:
        _close_rig(rig=rig)


def test_a_launch_after_the_deadline_is_refused_without_running_the_command(
    tmp_path: Path,
) -> None:
    """A LATE START never execs the agent, so queue delay counts against the bound.

    The marker file is the discriminator: a guard that refused only after
    running the command would still exit non-zero.
    """
    marker = tmp_path / "must-not-exist"
    bin_dir, _ = _fixed_clock(tmp_path=tmp_path, now=float(_CONTROLLED_EPOCH))
    result = _run(
        tmp_path=tmp_path,
        deadline=str(_CONTROLLED_EPOCH - 60),
        argv=["/bin/sh", "-c", f"printf ran > {marker}"],
        path_prefix=bin_dir,
    )

    assert not marker.exists(), "the guard ran the command after the deadline had passed"
    assert result.returncode == GUARD_REFUSAL_EXIT_CODE
    assert "not reset by a retry" in result.stderr


def test_a_retried_launch_inherits_the_same_deadline_rather_than_a_fresh_budget(
    tmp_path: Path,
) -> None:
    """The bound is an INSTANT, so a second launch gets what is left, not a reset.

    Two launches against ONE deadline, with the deadline falling between them: the
    case moves the injected clock past it. The first finishes inside its budget;
    the second is refused. A guard measuring a duration per launch would admit
    both.
    """
    deadline = str(_CONTROLLED_EPOCH + _SOON_SECONDS)
    first_marker = tmp_path / "first"
    second_marker = tmp_path / "second"
    bin_dir, clock = _fixed_clock(tmp_path=tmp_path, now=float(_CONTROLLED_EPOCH))

    first = _run(
        tmp_path=tmp_path,
        deadline=deadline,
        argv=["/bin/sh", "-c", f"printf one > {first_marker}"],
        path_prefix=bin_dir,
    )
    _set_clock(clock=clock, to=float(_CONTROLLED_EPOCH + _SOON_SECONDS + 1))
    second = _run(
        tmp_path=tmp_path,
        deadline=deadline,
        argv=["/bin/sh", "-c", f"printf two > {second_marker}"],
        path_prefix=bin_dir,
    )

    assert first.returncode == 0
    assert first_marker.read_text(encoding="utf-8") == "one"
    assert second.returncode == GUARD_REFUSAL_EXIT_CODE
    assert not second_marker.exists(), "the retry was granted a fresh budget"


@pytest.mark.parametrize(
    ("deadline", "needle"),
    [
        pytest.param(None, "is not set", id="absent"),
        pytest.param("not-an-epoch", "not an epoch second", id="unparseable"),
        pytest.param("", "is not set", id="empty"),
    ],
)
def test_a_deadline_the_guard_cannot_read_refuses_rather_than_running(
    tmp_path: Path, deadline: str | None, needle: str
) -> None:
    """FAIL CLOSED. A guard that ran when blinded would be decoration.

    Each arm names what it could not read, because "refused" alone does not tell
    an operator whether the projection is missing or malformed.
    """
    marker = tmp_path / "must-not-exist"
    result = _run(
        tmp_path=tmp_path,
        deadline=deadline,
        argv=["/bin/sh", "-c", f"printf ran > {marker}"],
    )

    assert not marker.exists()
    assert result.returncode == GUARD_REFUSAL_EXIT_CODE
    assert needle in result.stderr


def test_the_start_check_reports_remaining_budget_without_running_anything(
    tmp_path: Path,
) -> None:
    """The QUEUE/PREPARATION-AGING check a prepare step runs before any agent node.

    Separate from the wrapping mode because it has to answer before there is a
    command to wrap: a credential that aged below its remaining worker lifetime
    while the run sat queued must refuse at startup, not mid-turn.
    """
    bin_dir, _ = _fixed_clock(tmp_path=tmp_path, now=float(_CONTROLLED_EPOCH))
    env = _hermetic_env()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

    def check_start(*, deadline: int) -> subprocess.CompletedProcess[str]:
        env[CREDENTIAL_USE_DEADLINE_ENV_VAR] = str(deadline)
        return subprocess.run(
            ["/bin/sh", str(_guard(tmp_path=tmp_path)), "--check-start"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            check=False,
        )

    fresh = check_start(deadline=_CONTROLLED_EPOCH + 3600)
    aged = check_start(deadline=_CONTROLLED_EPOCH - 1)

    assert fresh.returncode == 0
    assert "budget remain" in fresh.stdout
    assert aged.returncode == GUARD_REFUSAL_EXIT_CODE


def test_the_deadline_is_capped_at_the_observed_expiry_minus_the_margin() -> None:
    """The projection delay must not stamp a deadline the credential cannot cover.

    The allowance here is deliberately LARGER than the credential's remaining
    life, which is the case the cap exists for: anchoring on the projection
    instant alone would authorise work past the token's own expiry.
    """
    expiry = 1_000_000
    margin = 3_600

    capped = credential_use_deadline_epoch_capped(
        projected_epoch=900_000,
        allowance_seconds=500_000,
        credential_expiry_epoch=expiry,
        margin_seconds=margin,
    )

    assert capped == expiry - margin


def test_the_allowance_binds_when_it_is_the_earlier_bound() -> None:
    """The control for the cap: the allowance is not always the loser.

    Without this, "capped at expiry minus margin" is equally consistent with a
    derivation that ignores the allowance entirely.
    """
    projected = 900_000

    bound = credential_use_deadline_epoch_capped(
        projected_epoch=projected,
        allowance_seconds=1_000,
        credential_expiry_epoch=10_000_000,
        margin_seconds=3_600,
    )

    assert bound == projected + 1_000


def test_the_margin_is_never_spent_as_execution_time() -> None:
    """The margin stays headroom between the deadline and the expiry.

    Asserted as a RELATION to the expiry rather than against a number, because
    the claim is that the gap exists at all -- which is what `required_seconds`
    promises when it adds the margin on top of the allowance rather than inside
    it.
    """
    expiry = 2_000_000
    margin = 3_600

    deadline = credential_use_deadline_epoch_capped(
        projected_epoch=1_000_000,
        allowance_seconds=10_000_000,
        credential_expiry_epoch=expiry,
        margin_seconds=margin,
    )

    assert expiry - deadline == margin


def test_every_launch_route_is_wrapped_through_one_argv_transform() -> None:
    """A literal `acp.command` is guarded by the same transform as a built-in.

    The routes differ only in how the argv was produced, so the guard attaches to
    the ARGV rather than to an adapter identity: a per-adapter guard would leave
    the literal route -- the one a repository writes by hand -- unbounded.
    """
    literal = guarded_acp_command(argv=["/usr/local/bin/my-agent", "--acp"])
    builtin = guarded_acp_command(argv=["npx", "-y", "@zed-industries/claude-code-acp"])

    for wrapped, original in (
        (literal, ["/usr/local/bin/my-agent", "--acp"]),
        (builtin, ["npx", "-y", "@zed-industries/claude-code-acp"]),
    ):
        assert wrapped[0] == "/bin/sh"
        assert wrapped[-len(original) :] == original
        assert "--" in wrapped


def test_losing_the_waiting_process_does_not_disarm_the_bound(
    tmp_path: Path,
) -> None:
    """The host-independence property, read from the guard's injected clock.

    The reaper lives in the sandbox beside the child, so losing the process that
    is WAITING does not extend anything. Here the waiter is killed deliberately
    -- standing in for a dying host-side waiter -- while the guard's clock is
    HELD, so the waiter is provably gone before any signal falls. The reaper's
    armed event releases nothing by itself: the case moves the clock only after
    the waiter has exited, and EOF on the inherited holder pipe then establishes
    that the child and reaper exited, the child by a KILL that fires by the
    deadline.
    """
    rig = _start_rig(tmp_path=tmp_path, start=float(_CONTROLLED_EPOCH), agent=_TERM_RESISTANT_AGENT)
    try:
        _await_armed_and_ready(rig=rig)
        agent = _agent_pid(rig=rig)

        rig.guarded.send_signal(signal.SIGKILL)
        _ = rig.guarded.wait(timeout=_HANG_GUARD_SECONDS)
        assert _executing(pid=agent)
        assert _clock_reading(rig=rig) == float(_CONTROLLED_EPOCH)

        _release_clock(rig=rig)
        _await_tree_exit(rig=rig, what="the agent stayed live after the waiter died")

        killed_at = _clock_reading(rig=rig)
        assert (
            rig.deadline - 1 < killed_at <= rig.deadline
        ), f"the agent was killed {killed_at - rig.deadline:+.3f}s from the deadline after the waiter died"
    finally:
        _close_rig(rig=rig)


def test_a_bidirectional_protocol_session_survives_the_guard(tmp_path: Path) -> None:
    """ACP is bidirectional stdio, so the guard must be transparent to it.

    THE DEFECT THIS CATCHES IS INVISIBLE TO EVERY OTHER CASE HERE. POSIX hands
    an ASYNCHRONOUS command in a non-interactive shell its stdin from
    /dev/null unless the redirection is written out, and the guard runs the
    agent asynchronously so it can arm a reaper beside it. Without an explicit
    redirection the agent read EOF on its first protocol request: it still
    started, still produced output and still exited 0, so a marker-file or
    exit-status assertion passed while every real session was dead on arrival.

    MULTIPLE TURNS are exchanged, not one. A one-shot initial read passes even
    when only the first buffered line survives, and an ACP session is a
    conversation -- the failure that matters is the second request never
    arriving.
    """
    requests = "first-request\nsecond-request\nthird-request\n"
    bin_dir, _ = _fixed_clock(tmp_path=tmp_path, now=float(_CONTROLLED_EPOCH))
    result = _run(
        tmp_path=tmp_path,
        deadline=str(_CONTROLLED_EPOCH + 3600),
        path_prefix=bin_dir,
        argv=[
            "python3",
            "-c",
            # Echo each request back as a response, exactly as a protocol peer
            # would, until stdin closes.
            "import sys\n"
            "for line in sys.stdin:\n"
            "    sys.stdout.write('response:' + line.strip() + '\\n')\n"
            "    sys.stdout.flush()\n",
        ],
        stdin_text=requests,
        # The deadline is an hour away, so nothing here is timing-sensitive; the
        # budget only bounds a hung guard. The default settle budget was exceeded
        # by interpreter startup alone on a loaded factory sandbox (run
        # 01M4Q7GCZQBG, 2026-10-12), failing a case that measures stdin, not time.
        timeout=60,
    )

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "response:first-request",
        "response:second-request",
        "response:third-request",
    ]


@pytest.mark.parametrize("start_fraction", [0.65, 0.95])
def test_a_fractional_start_still_stops_by_the_absolute_epoch(
    tmp_path: Path, start_fraction: float
) -> None:
    """A guard entered PART-WAY THROUGH A SECOND must not kill late.

    The measured defect this pins: `date +%s` floors the current instant, so a
    guard starting at epoch+0.65 credited itself the remainder of that second
    and landed its KILL at deadline+0.65. That is systematic rounding, not
    scheduler jitter -- it reproduces at the same offset every run -- and a
    deadline that is late by construction is not a deadline.

    The guard runs on a simulated clock started at the chosen fraction, so the
    instant its KILL fires is read off the clock its own arithmetic advanced. On
    that clock the flooring defect fires at deadline+0.05 or +0.15, past the
    deadline, and the fixed arithmetic fires inside the last second before it,
    whatever the host's load.

    The agent is a real process that ignores TERM, so the KILL is what stops
    it: the arm the rounding affected.
    """
    rig = _start_rig(
        tmp_path=tmp_path,
        start=_CONTROLLED_EPOCH + start_fraction,
        agent=_TERM_RESISTANT_AGENT,
    )
    try:
        _await_armed_and_ready(rig=rig)
        _release_clock(rig=rig)

        status = rig.guarded.wait(timeout=_HANG_GUARD_SECONDS)

        killed_at = _clock_reading(rig=rig)
        assert status == 128 + signal.SIGKILL
        assert (
            rig.deadline - 1 < killed_at <= rig.deadline
        ), f"a start at .{int(start_fraction * 100)} killed {killed_at - rig.deadline:+.3f}s from the deadline"
    finally:
        _close_rig(rig=rig)
