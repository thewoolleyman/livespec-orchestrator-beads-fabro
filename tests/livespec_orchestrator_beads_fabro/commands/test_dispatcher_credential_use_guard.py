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

HOW THESE CASES AVOID REAL TIME. The behaviour under test is a SHIPPED SHELL
SCRIPT comparing `date` against an absolute epoch, enforced against processes
this interpreter does not run. There is no clock to inject into `/bin/sh`, but
there is a `date` and a `sleep` the script finds on PATH, so every timing case
puts a controlled pair there: `date` reads a clock FILE and `sleep` advances it
at once. The deadline is then an instant on that file, the guard's signals land
on readings of it, and "the child stopped by the deadline" is read off the file
at the moment a deterministic event -- EOF on a pipe every process in the group
inherited -- says the group is gone. Cases that need no clock at all use an
epoch so far past or future that no host reading can matter.
"""

from __future__ import annotations

import contextlib
import os
import select
import signal
import subprocess
from collections.abc import Callable
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
# cases therefore measure termination RELATIVE TO THE ABSOLUTE EPOCH.
#
# `_SOON_SECONDS` must exceed the guard's own grace, or TERM would be due before
# the child has started and the case would measure process startup rather than
# the bound.
_SOON_SECONDS = GUARD_TERM_GRACE_SECONDS + 3

_SETTLE_SECONDS = 10
_CONTROLLED_EPOCH = 1_900_000_000
# Epochs no host clock can be near: a deadline that is always in the future (the
# year 2100) and one that has always passed (one second after 1970).
_FAR_FUTURE_EPOCH = 4_102_444_800
_LONG_PAST_EPOCH = 1


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
        env.pop(name, None)
    return env


def _run(
    *,
    tmp_path: Path,
    deadline: str | None,
    argv: list[str],
    timeout: float = _SETTLE_SECONDS,
    stdin_text: str | None = None,
    clock_bin: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the guard around `argv`, with the deadline supplied as the env var.

    With `clock_bin`, that directory leads PATH so the guard reads its `date`.
    """
    env = _hermetic_env()
    if deadline is not None:
        env[CREDENTIAL_USE_DEADLINE_ENV_VAR] = deadline
    if clock_bin is not None:
        env["PATH"] = f"{clock_bin}:{env.get('PATH', '')}"
    return subprocess.run(
        ["/bin/sh", str(_guard(tmp_path=tmp_path)), "--", *argv],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )


def _date_shim(*, bin_dir: Path, clock: Path) -> None:
    """A `date` that reads the clock file, with a fractional `%N` the guard can parse."""
    date_shim = bin_dir / "date"
    _ = date_shim.write_text(
        "#!/bin/sh\n"
        f'now="$(cat "{clock}")"\n'
        'case "$1" in\n'
        '    +%s.%N) awk -v n="$now" \'BEGIN{printf "%.9f\\n", n}\' ;;\n'
        '    +%s) awk -v n="$now" \'BEGIN{printf "%d\\n", n}\' ;;\n'
        '    *) printf "%s\\n" "$now" ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    date_shim.chmod(0o755)


def _fixed_clock(*, tmp_path: Path, epoch: int) -> Path:
    """A PATH directory whose `date` always reads `epoch`, for cases that never wait."""
    bin_dir = tmp_path / "fixed-clock-bin"
    bin_dir.mkdir()
    clock = tmp_path / "fixed-clock"
    _ = clock.write_text(f"{epoch}\n", encoding="utf-8")
    _date_shim(bin_dir=bin_dir, clock=clock)
    return bin_dir


def _controlled_clock(
    *, tmp_path: Path, armed: Path, release: Path, start: float
) -> tuple[Path, Path]:
    """Create the guard's `date`/`sleep` seam on a deterministic clock.

    The first fake sleep announces that the detached reaper is armed, then
    waits for the test's FIFO release. Only that first sleep reads the FIFO; later
    sleeps advance the clock immediately, so the instant the guard signals is a reading of this
    file rather than a measurement of host scheduling.
    """
    bin_dir = tmp_path / "controlled-clock-bin"
    bin_dir.mkdir()
    clock = tmp_path / "controlled-clock"
    _ = clock.write_text(f"{start}\n", encoding="utf-8")
    _date_shim(bin_dir=bin_dir, clock=clock)
    sleep_shim = bin_dir / "sleep"
    _ = sleep_shim.write_text(
        "#!/bin/sh\n"
        f'if [ ! -e "{armed}.once" ]; then\n'
        f'    : > "{armed}.once"\n'
        f'    printf armed > "{armed}"\n'
        f'    IFS= read -r _ < "{release}" || true\n'
        "fi\n"
        f'now="$(cat "{clock}")"\n'
        f'awk -v n="$now" -v d="$1" \'BEGIN{{printf "%.6f\\n", n+d}}\' > "{clock}.next"\n'
        f'mv "{clock}.next" "{clock}"\n',
        encoding="utf-8",
    )
    sleep_shim.chmod(0o755)
    return bin_dir, clock


def _close_guarded_fixture(
    *, guarded: subprocess.Popen[bytes], pid_file: Path, descriptors: tuple[int, ...]
) -> None:
    """Close this case's descriptors and stop either surviving fixture process."""
    for descriptor in descriptors:
        with contextlib.suppress(OSError):
            os.close(descriptor)
    with contextlib.suppress(ProcessLookupError):
        guarded.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        _ = guarded.wait(timeout=_SETTLE_SECONDS)
    with contextlib.suppress(FileNotFoundError, ProcessLookupError, ValueError):
        os.kill(int(pid_file.read_text(encoding="utf-8")), signal.SIGKILL)


def _term_resistant_child(*, pid_file: Path, ready: Path) -> str:
    """A child that ignores TERM from its first instruction and idles until killed."""
    return f"trap '' TERM; echo $$ > {pid_file}; echo ready > {ready}; exec /bin/sleep 600"


@dataclass
class _GuardedFixture:
    """A guarded child plus the descriptors and files the case rendezvouses on."""

    guarded: subprocess.Popen[bytes]
    pid_file: Path
    armed_fd: int
    ready_fd: int
    release_fd: int
    holder_read: int
    holder_write: int
    clock: Path
    deadline: int

    def descriptors(self) -> tuple[int, ...]:
        return (self.holder_write, self.holder_read, self.armed_fd, self.ready_fd, self.release_fd)


def _start_guarded_fixture(
    *,
    tmp_path: Path,
    child_script: Callable[[Path, Path], str] | None = None,
    start_fraction: float = 0.0,
) -> _GuardedFixture:
    """Start a guarded child with controlled-clock rendezvous.

    The clock starts `start_fraction` seconds into `_CONTROLLED_EPOCH` and the
    deadline is `_SOON_SECONDS` whole seconds after that epoch. `child_script`
    receives the pid file and the ready FIFO the child must write once it is set
    up, and defaults to a TERM-resistant idler.
    """
    pid_file = tmp_path / "pid"
    armed_fifo = tmp_path / "armed"
    ready_fifo = tmp_path / "ready"
    release_fifo = tmp_path / "release"
    os.mkfifo(armed_fifo)
    os.mkfifo(ready_fifo)
    os.mkfifo(release_fifo)
    # Read-write, not read-only: a FIFO with no writer is readable as EOF, so a
    # read end alone can report "nothing will ever arrive" before the reaper or
    # the child has opened its side. Holding a writer here makes the descriptor
    # readable only once an announcement has actually been written.
    armed_fd = os.open(armed_fifo, os.O_RDWR | os.O_NONBLOCK)
    ready_fd = os.open(ready_fifo, os.O_RDWR | os.O_NONBLOCK)
    release_fd = os.open(release_fifo, os.O_RDWR | os.O_NONBLOCK)
    bin_dir, clock = _controlled_clock(
        tmp_path=tmp_path,
        armed=armed_fifo,
        release=release_fifo,
        start=_CONTROLLED_EPOCH + start_fraction,
    )
    holder_read, holder_write = os.pipe()
    deadline = _CONTROLLED_EPOCH + _SOON_SECONDS
    env = _hermetic_env()
    env[CREDENTIAL_USE_DEADLINE_ENV_VAR] = str(deadline)
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    script = (
        child_script or (lambda pid, ready: _term_resistant_child(pid_file=pid, ready=ready))
    )(pid_file, ready_fifo)
    guarded = subprocess.Popen(
        ["/bin/sh", str(_guard(tmp_path=tmp_path)), "--", "/bin/sh", "-c", script],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        pass_fds=(holder_write,),
    )
    return _GuardedFixture(
        guarded=guarded,
        pid_file=pid_file,
        armed_fd=armed_fd,
        ready_fd=ready_fd,
        release_fd=release_fd,
        holder_read=holder_read,
        holder_write=holder_write,
        clock=clock,
        deadline=deadline,
    )


def _await_event(*, fd: int, expected: bytes, what: str) -> None:
    """Block until the FIFO `fd` delivers `expected`; the budget only bounds a hang.

    `fd` is opened read-write, so it holds its own writer and cannot report a
    pre-writer EOF: it becomes readable only when the announcement is written.
    """
    readable, _, _ = select.select([fd], [], [], _SETTLE_SECONDS)
    assert readable, f"{what} never arrived"
    assert os.read(fd, len(expected)) == expected


def _guarded_group_exit(
    *,
    tmp_path: Path,
    child_script: Callable[[Path, Path], str] | None = None,
    start_fraction: float = 0.0,
) -> tuple[int, float, int]:
    """Run the guard to the end of its group; return (guard status, clock reading, deadline).

    The reaper's FIFO announcement says it is armed and the child's says it has
    finished setting itself up; only then is the controlled clock released, so
    no signal can land on a child that has not yet installed its disposition.
    EOF on the pipe every group member inherited says the group is gone, and the
    clock reading at that event is the instant the guard's signals landed,
    because only the reaper's `sleep` advances it.
    """
    fixture = _start_guarded_fixture(
        tmp_path=tmp_path, child_script=child_script, start_fraction=start_fraction
    )
    try:
        _await_event(fd=fixture.armed_fd, expected=b"armed", what="the reaper's armed announcement")
        _await_event(fd=fixture.ready_fd, expected=b"ready\n", what="the child's readiness")
        # The release end stays open until cleanup: the reaper opens the FIFO
        # only AFTER announcing, and a FIFO with no open end discards the line
        # and blocks that open for good.
        os.write(fixture.release_fd, b"release\n")
        os.close(fixture.holder_write)
        fixture.holder_write = -1
        readable, _, _ = select.select([fixture.holder_read], [], [], _SETTLE_SECONDS)
        assert readable and os.read(fixture.holder_read, 1) == b"", (
            "the group stayed live past the deadline; "
            f"controlled clock is {fixture.clock.read_text(encoding='utf-8').strip()}"
        )
        status = fixture.guarded.wait(timeout=_SETTLE_SECONDS)
        return status, float(fixture.clock.read_text(encoding="utf-8").strip()), fixture.deadline
    finally:
        _close_guarded_fixture(
            guarded=fixture.guarded,
            pid_file=fixture.pid_file,
            descriptors=fixture.descriptors(),
        )


def test_a_sufficiently_fresh_deadline_lets_an_ordinary_command_finish(
    tmp_path: Path,
) -> None:
    """THE POSITIVE CONTROL: the guard is a bound, not a refusal.

    Without this case every other case here is satisfied by a guard that refuses
    unconditionally, which would make the normal workflow undispatchable while
    looking perfectly enforced.
    """
    marker = tmp_path / "ran"
    result = _run(
        tmp_path=tmp_path,
        deadline=str(_FAR_FUTURE_EPOCH),
        argv=["/bin/sh", "-c", f"printf done > {marker}; exit 7"],
    )

    assert marker.read_text(encoding="utf-8") == "done"
    # The wrapped command's own status passes through, so the guard is
    # transparent to a run that finishes inside its budget.
    assert result.returncode == 7


def test_a_running_child_stops_by_the_deadline_itself(tmp_path: Path) -> None:
    """Execution stops BY the absolute epoch, read off the guard's controlled clock.

    The assertion is NOT "the process is gone eventually" -- that is satisfied by
    a guard whose grace runs past the deadline, which would permit exactly the
    credential use the bound forbids. The clock only moves when the guard's
    reaper sleeps, so its reading at the moment the group is gone is the instant
    the guard's signal landed, and that instant must not be later than the
    deadline. A compliant child dies at the TERM, a grace before it.
    """
    pid_file = tmp_path / "pid"

    status, stopped_at, deadline = _guarded_group_exit(
        tmp_path=tmp_path,
        child_script=lambda pid,
        ready: f"echo $$ > {pid}; echo ready > {ready}; exec /bin/sleep 600",
    )

    assert stopped_at <= deadline
    # The TERM, not the KILL, is what ended it, so the grace is spent inside the
    # allowance and the clock never reached the deadline.
    assert stopped_at >= deadline - GUARD_TERM_GRACE_SECONDS - 1
    assert pid_file.exists(), "the child never started, so the bound stopped nothing"
    assert status != 0


def test_a_term_resistant_child_still_stops_by_the_deadline(tmp_path: Path) -> None:
    """TERM refusal buys no time at all, not even the escalation grace.

    The child traps TERM and idles, which is what an agent mid-turn with its own
    signal handling looks like. Because the guard lands TERM a grace BEFORE the
    deadline and KILL **at** it, refusing TERM costs the child its grace and
    nothing more: it must still stop by the same instant a compliant child
    would, and the clock reading shows the KILL, not the TERM, ended it.
    """
    status, stopped_at, deadline = _guarded_group_exit(tmp_path=tmp_path)

    assert stopped_at <= deadline, f"a TERM-resistant child outlived the deadline: {stopped_at}"
    assert stopped_at > deadline - 1, "the child ended at the TERM, so it was not TERM-resistant"
    assert status != 0


def test_a_credential_using_grandchild_stops_by_the_deadline_after_its_parent_exits(
    tmp_path: Path,
) -> None:
    """The ADAPTER PARENT EXITS and its child keeps the credential; both stop by the bound.

    This is the shape a guard that signals only its direct child gets wrong, and
    it is the shape that matters: the process still holding the credential after
    an adapter returns is the grandchild, not the adapter.

    THE WAIT IS LOAD-BEARING. The reaper is detached, so the wrapper returns as
    soon as the short-lived parent exits -- long before the deadline. Reading
    the clock at that moment would pass even if the grandchild then ran forever,
    which is exactly the vacuous shape this case must not have. So it reads the
    clock only once the group has emptied, and the pipe every member inherited
    cannot reach EOF while the grandchild is alive.
    """
    # The parent spawns a TERM-resistant long-running idler and exits IMMEDIATELY.
    status, stopped_at, deadline = _guarded_group_exit(
        tmp_path=tmp_path,
        child_script=lambda pid, ready: (
            f'/bin/sh -c \'trap "" TERM; echo $$ > {pid}; echo ready > {ready}; '
            "exec /bin/sleep 600' </dev/null >/dev/null 2>&1 & exit 0"
        ),
    )

    # The wrapper returned while the bound had not yet fallen.
    assert status == 0
    assert (
        stopped_at <= deadline
    ), f"a credential-using grandchild outlived the deadline: {stopped_at}"
    assert (
        stopped_at > deadline - 1
    ), "the grandchild ended before the KILL, so TERM was not refused"


def test_a_launch_after_the_deadline_is_refused_without_running_the_command(
    tmp_path: Path,
) -> None:
    """A LATE START never execs the agent, so queue delay counts against the bound.

    The marker file is the discriminator: a guard that refused only after
    running the command would still exit non-zero.
    """
    marker = tmp_path / "must-not-exist"
    result = _run(
        tmp_path=tmp_path,
        deadline=str(_LONG_PAST_EPOCH),
        argv=["/bin/sh", "-c", f"printf ran > {marker}"],
    )

    assert not marker.exists(), "the guard ran the command after the deadline had passed"
    assert result.returncode == GUARD_REFUSAL_EXIT_CODE
    assert "not reset by a retry" in result.stderr


def test_a_retried_launch_inherits_the_same_deadline_rather_than_a_fresh_budget(
    tmp_path: Path,
) -> None:
    """The bound is an INSTANT, so a second launch gets what is left, not a reset.

    Two launches against ONE deadline, with the deadline falling between them.
    The first finishes inside its budget; the second is refused. A guard
    measuring a duration per launch would admit both. The fall of the deadline
    is the test writing a later reading into the guard's clock file.
    """
    deadline = str(_CONTROLLED_EPOCH + _SOON_SECONDS)
    first_marker = tmp_path / "first"
    second_marker = tmp_path / "second"
    clock_bin = _fixed_clock(tmp_path=tmp_path, epoch=_CONTROLLED_EPOCH)
    clock = tmp_path / "fixed-clock"

    first = _run(
        tmp_path=tmp_path,
        deadline=deadline,
        argv=["/bin/sh", "-c", f"printf one > {first_marker}"],
        clock_bin=clock_bin,
    )
    _ = clock.write_text(f"{_CONTROLLED_EPOCH + _SOON_SECONDS + 1}\n", encoding="utf-8")
    second = _run(
        tmp_path=tmp_path,
        deadline=deadline,
        argv=["/bin/sh", "-c", f"printf two > {second_marker}"],
        clock_bin=clock_bin,
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
    env = _hermetic_env()
    env[CREDENTIAL_USE_DEADLINE_ENV_VAR] = str(_FAR_FUTURE_EPOCH)
    fresh = subprocess.run(
        ["/bin/sh", str(_guard(tmp_path=tmp_path)), "--check-start"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )

    env[CREDENTIAL_USE_DEADLINE_ENV_VAR] = str(_LONG_PAST_EPOCH)
    aged = subprocess.run(
        ["/bin/sh", str(_guard(tmp_path=tmp_path)), "--check-start"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )

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
    -- standing in for a dying host-side waiter -- before the controlled clock
    advances. The reaper's FIFO event then releases the clock, and EOF on the
    inherited holder pipe establishes that the child and reaper exited.
    """
    fixture = _start_guarded_fixture(tmp_path=tmp_path)
    try:
        _await_event(fd=fixture.armed_fd, expected=b"armed", what="the reaper's armed announcement")
        _await_event(fd=fixture.ready_fd, expected=b"ready\n", what="the child's readiness")
        fixture.guarded.send_signal(signal.SIGKILL)
        _ = fixture.guarded.wait(timeout=_SETTLE_SECONDS)
        # The release end stays open until cleanup: the reaper opens the FIFO
        # only AFTER announcing, and a FIFO with no open end discards the line
        # and blocks that open for good.
        os.write(fixture.release_fd, b"release\n")
        os.close(fixture.holder_write)
        fixture.holder_write = -1
        readable, _, _ = select.select([fixture.holder_read], [], [], _SETTLE_SECONDS)
        assert readable and os.read(fixture.holder_read, 1) == b"", (
            "the child stayed live after the waiter died; "
            f"controlled clock is {fixture.clock.read_text(encoding='utf-8').strip()}"
        )
        assert float(fixture.clock.read_text(encoding="utf-8").strip()) <= fixture.deadline
    finally:
        _close_guarded_fixture(
            guarded=fixture.guarded,
            pid_file=fixture.pid_file,
            descriptors=fixture.descriptors(),
        )


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
    result = _run(
        tmp_path=tmp_path,
        deadline=str(_FAR_FUTURE_EPOCH),
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

    The start is ALIGNED to a chosen fraction rather than left to chance,
    because an unaligned case passes roughly whenever the fraction happens to be
    small. The child ignores TERM so the KILL is what stops it, which is the arm
    the rounding affected.
    """
    # The clock STARTS at the chosen fraction of a second, so the alignment the
    # case needs is a value written into the clock file rather than a wait for
    # the host's clock to reach it. The child ignores TERM, so the KILL is what
    # stops it.
    status, stopped_at, deadline = _guarded_group_exit(
        tmp_path=tmp_path, start_fraction=start_fraction
    )

    assert (
        stopped_at <= deadline
    ), f"a start at .{int(start_fraction * 100)} killed {stopped_at - deadline:+.3f}s past the deadline"
    assert (
        stopped_at > deadline - 1
    ), "the child ended at the TERM, so the KILL arm was not measured"
    assert status != 0
