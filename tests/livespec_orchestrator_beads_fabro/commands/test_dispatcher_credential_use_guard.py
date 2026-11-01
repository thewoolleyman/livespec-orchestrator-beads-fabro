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
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from collections.abc import Callable
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

# NO HOST-CLOCK TOLERANCE REMAINS. Every termination case below runs the guard
# on the CONTROLLED CLOCK (`_controlled_clock`), so the instant a signal fires is
# read off the clock the guard's own arithmetic advanced. A host-clock heartbeat
# with a +0.5 s slack cannot tell a late KILL from a loaded host delivering a
# correct one late: measured 2026-11-01 at load ~60, a correct guard's child was
# read executing +0.735 s, +1.36 s and +2.90 s past the deadline. That slack
# was never widened to pass a late kill; it was retired in favour of a reading
# that has no slack at all.
_SETTLE_SECONDS = 10
# Ample for the guard's simulated-time loop, which spawns a few short processes
# per controlled-clock step; it never decides a verdict.
_CONTROLLED_CLOCK_HANG_GUARD_SECONDS = 120


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
    path_prefix: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the guard around `argv`, with the deadline supplied as the env var.

    `path_prefix` puts a directory first on the guard's PATH, which is how a case
    hands the guard a controlled `date` and `sleep` in place of the host's.
    """
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
        deadline=str(int(time.time()) + 3600),
        argv=["/bin/sh", "-c", f"printf done > {marker}; exit 7"],
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
    TERM, so the signal that stops it is the guard's TERM, and the controlled
    clock says when the guard sent it: by the deadline, never after.
    """
    bin_dir, clock = _controlled_clock(tmp_path=tmp_path, start=float(_CONTROLLED_EPOCH))
    deadline = _CONTROLLED_EPOCH + _SOON_SECONDS

    result = _run(
        tmp_path=tmp_path,
        deadline=str(deadline),
        argv=["/bin/sh", "-c", "exec /bin/sleep 600"],
        timeout=_CONTROLLED_CLOCK_HANG_GUARD_SECONDS,
        path_prefix=bin_dir,
    )

    stopped_at = float(clock.read_text(encoding="utf-8"))
    assert result.returncode == 128 + signal.SIGTERM, result.stderr
    assert (
        stopped_at <= deadline
    ), f"the child was signalled {stopped_at - deadline:+.3f}s past the deadline"


def test_a_term_resistant_child_still_stops_by_the_deadline(tmp_path: Path) -> None:
    """TERM refusal buys no time at all, not even the escalation grace.

    The child traps TERM and keeps stamping the clock, which is what an agent
    mid-turn with its own signal handling looks like. Because the guard lands
    TERM a grace BEFORE the deadline and KILL **at** it, refusing TERM costs the
    child its grace and nothing more: it must still stop by the same instant a
    compliant child would.

    The guard runs on the CONTROLLED CLOCK (see `_controlled_clock` below), so
    the instant its KILL fires is read off the clock its own arithmetic
    advanced, not off a host stopwatch. Measured 2026-11-01 at load ~70: a
    host-clock heartbeat read a correct guard's TERM-resistant child executing
    +1.36 s past the deadline against a +0.5 s allowance, which is delivery
    latency, not a late KILL. The child is a real process that ignores TERM, so
    only the KILL stops it, and the KILL must fire by the deadline.
    """
    trapped = tmp_path / "term-is-ignored"
    bin_dir, clock = _controlled_clock(
        tmp_path=tmp_path, start=float(_CONTROLLED_EPOCH), hold=trapped
    )
    deadline = _CONTROLLED_EPOCH + _SOON_SECONDS

    result = _run(
        tmp_path=tmp_path,
        deadline=str(deadline),
        # Absolute paths, so the child runs on the HOST's clock and only the
        # guard reads the controlled one. The ignored TERM survives the exec.
        argv=_term_ignoring_agent(trapped=trapped),
        timeout=_CONTROLLED_CLOCK_HANG_GUARD_SECONDS,
        path_prefix=bin_dir,
    )

    killed_at = float(clock.read_text(encoding="utf-8"))
    assert result.returncode == 128 + signal.SIGKILL, result.stderr
    assert (
        killed_at <= deadline
    ), f"a TERM-resistant child was killed {killed_at - deadline:+.3f}s past the deadline"


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
    hold = tmp_path / "release-the-clock"
    bin_dir, clock = _controlled_clock(tmp_path=tmp_path, start=float(_CONTROLLED_EPOCH), hold=hold)
    deadline = _CONTROLLED_EPOCH + _SOON_SECONDS
    grandchild_pid = tmp_path / "grandchild-pid"
    parent = tmp_path / "parent.sh"
    _ = parent.write_text(
        f"/bin/sh -c 'trap \"\" TERM; echo $$ > {grandchild_pid}; exec /bin/sleep 600' </dev/null >/dev/null 2>&1 &\n"
        f"while [ ! -s {grandchild_pid} ]; do /bin/sleep 0.05; done\n"
        "exit 0\n",
        encoding="utf-8",
    )

    result = _run(
        tmp_path=tmp_path,
        deadline=str(deadline),
        argv=["/bin/sh", str(parent)],
        timeout=_CONTROLLED_CLOCK_HANG_GUARD_SECONDS,
        path_prefix=bin_dir,
    )
    pid = int(grandchild_pid.read_text(encoding="utf-8").strip())
    try:
        # The wrapper has returned, the grandchild runs on, and the bound has not
        # yet fallen: the guard's clock has not moved.
        assert result.returncode == 0, result.stderr
        assert _executing(pid=pid)
        assert float(clock.read_text(encoding="utf-8")) == float(_CONTROLLED_EPOCH)

        _ = hold.write_text("", encoding="utf-8")

        assert _stops(pid=pid), "the credential-using grandchild was never stopped"
        killed_at = float(clock.read_text(encoding="utf-8"))
        assert (
            deadline - 1 < killed_at <= deadline
        ), f"a credential-using grandchild was killed {killed_at - deadline:+.3f}s from the deadline"
    finally:
        # Own what we spawned: never leak a sleeper into the rest of the suite.
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGKILL)
        _ = hold.write_text("", encoding="utf-8")


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
        deadline=str(int(time.time()) - 60),
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
    measuring a duration per launch would admit both.
    """
    deadline = str(int(time.time()) + _SOON_SECONDS)
    first_marker = tmp_path / "first"
    second_marker = tmp_path / "second"

    first = _run(
        tmp_path=tmp_path,
        deadline=deadline,
        argv=["/bin/sh", "-c", f"printf one > {first_marker}"],
    )
    time.sleep(_SOON_SECONDS + 1)
    second = _run(
        tmp_path=tmp_path,
        deadline=deadline,
        argv=["/bin/sh", "-c", f"printf two > {second_marker}"],
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
    env[CREDENTIAL_USE_DEADLINE_ENV_VAR] = str(int(time.time()) + 3600)
    fresh = subprocess.run(
        ["/bin/sh", str(_guard(tmp_path=tmp_path)), "--check-start"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )

    env[CREDENTIAL_USE_DEADLINE_ENV_VAR] = str(int(time.time()) - 1)
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
    """The host-independence property, read against the guard's own epoch.

    The reaper lives in the sandbox beside the child, so losing the process that
    is WAITING does not extend anything. Here the waiter is killed deliberately
    -- standing in for a dying host-side waiter -- while the guard's clock is
    HELD, so the waiter is provably gone before any signal falls. The clock is
    then released, and the TERM-resistant child must still be stopped, by a KILL
    that fires by the deadline.
    """
    hold = tmp_path / "release-the-clock"
    bin_dir, clock = _controlled_clock(tmp_path=tmp_path, start=float(_CONTROLLED_EPOCH), hold=hold)
    deadline = _CONTROLLED_EPOCH + _SOON_SECONDS
    pid_file = tmp_path / "pid"
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
            f"trap '' TERM; echo $$ > {pid_file}; exec /bin/sleep 600",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert _appears(path=pid_file), "the guarded child never started"
        pid = int(pid_file.read_text(encoding="utf-8").strip())

        guarded.send_signal(signal.SIGKILL)
        _ = guarded.wait(timeout=_CONTROLLED_CLOCK_HANG_GUARD_SECONDS)
        assert _executing(pid=pid)
        _ = hold.write_text("", encoding="utf-8")

        assert _stops(pid=pid), "the agent was never stopped after the waiter died"
        killed_at = float(clock.read_text(encoding="utf-8"))
        assert (
            deadline - 1 < killed_at <= deadline
        ), f"the agent was killed {killed_at - deadline:+.3f}s from the deadline after the waiter died"
    finally:
        _ = hold.write_text("", encoding="utf-8")
        with contextlib.suppress(OSError, ValueError):
            os.kill(int(pid_file.read_text(encoding="utf-8").strip()), signal.SIGKILL)


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
        deadline=str(int(time.time()) + 3600),
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


# An arbitrary whole epoch second for the controlled clock. Nothing reads the
# host's clock in the case below, so any value works; it is fixed so a failure
# message names the same instants on every run.
_CONTROLLED_EPOCH = 1_900_000_000


def _term_ignoring_agent(*, trapped: Path) -> list[str]:
    """An agent that ignores TERM, and says so only once the trap is installed.

    The guard's clock is held on `trapped`, so no signal can fall before the
    trap exists. Without that ordering a loaded host can deliver the TERM
    before the shell has run `trap`, and the agent dies by TERM (exit 143)
    instead of by the KILL the case is about: measured 2026-11-01 at load ~58,
    in a diagnostic full suite.
    """
    return ["/bin/sh", "-c", f"trap '' TERM; : > {trapped}; exec /bin/sleep 600"]


def _controlled_clock(
    *, tmp_path: Path, start: float, hold: Path | None = None
) -> tuple[Path, Path]:
    """A `date` and a `sleep` that read and advance one simulated clock file.

    `sleep N` adds N seconds to the clock and returns at once, and `date` reads
    it back in the two formats the guard asks for. A guard run on these two
    makes every scheduling decision against simulated time, so the instant its
    KILL fires is a computed fact about its arithmetic rather than a reading of
    how quickly a loaded host delivered it.

    With `hold`, every simulated `sleep` first waits in real time until that
    file exists. A case uses it to put the guard's clock at a standstill while
    it arranges something that must happen BEFORE any signal can fall -- the
    adapter parent exiting, the waiter dying -- and then releases it.
    """
    bin_dir = tmp_path / "controlled-clock-bin"
    bin_dir.mkdir()
    clock = tmp_path / "controlled-clock"
    _ = clock.write_text(f"{start:.6f}\n", encoding="utf-8")
    date_shim = bin_dir / "date"
    _ = date_shim.write_text(
        "#!/bin/sh\n"
        f'now="$(cat {clock})"\n'
        'case "$1" in\n'
        """    +%s.%N) awk -v n="$now" 'BEGIN{s=int(n); printf "%d.%09d\\n", s, (n-s)*1e9}' ;;\n"""
        """    *) awk -v n="$now" 'BEGIN{printf "%d\\n", int(n)}' ;;\n"""
        "esac\n",
        encoding="utf-8",
    )
    sleep_shim = bin_dir / "sleep"
    _ = sleep_shim.write_text(
        "#!/bin/sh\n"
        + (f"while [ ! -e {hold} ]; do /bin/sleep 0.05; done\n" if hold is not None else "")
        + f'now="$(cat {clock})"\n'
        f"""awk -v n="$now" -v d="$1" 'BEGIN{{printf "%.6f\\n", n+d}}' > {clock}.next\n"""
        f"mv {clock}.next {clock}\n",
        encoding="utf-8",
    )
    date_shim.chmod(0o755)
    sleep_shim.chmod(0o755)
    return bin_dir, clock


def _executing(*, pid: int) -> bool:
    """True while `pid` exists and is not a zombie -- a zombie holds no credential."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return False
    return raw[raw.rfind(")") + 2 :].split()[0] != "Z"


def _eventually(
    *, condition: Callable[[], bool], guard_seconds: float = _CONTROLLED_CLOCK_HANG_GUARD_SECONDS
) -> bool:
    """Whether `condition` holds within the hang guard; the bound under test is read elsewhere."""
    give_up = time.monotonic() + guard_seconds
    while not condition():
        if time.monotonic() >= give_up:
            return False
        time.sleep(0.05)
    return True


def _stops(*, pid: int) -> bool:
    """Whether `pid` stops executing within the hang guard."""
    return _eventually(condition=lambda: not _executing(pid=pid))


def _appears(*, path: Path) -> bool:
    """Whether `path` gains content within the hang guard."""
    return _eventually(
        condition=lambda: path.exists() and path.read_text(encoding="utf-8").strip() != ""
    )


def test_the_hang_guard_reports_a_condition_that_never_holds() -> None:
    """A hung guard is reported as a failed wait, never as a hang of the suite."""
    assert not _eventually(condition=lambda: False, guard_seconds=0.0)


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

    The guard runs on a CONTROLLED CLOCK started at the chosen fraction, so the
    instant its KILL fires is read off the clock its own arithmetic advanced.
    A stopwatch on the host cannot tell that rounding apart from a kill a
    loaded host merely delivered late: measured 2026-10-31 at load ~100, a
    correct guard's kill landed +0.735 s past the deadline against a +0.5 s
    allowance. On the controlled clock the flooring defect fires at
    deadline+0.05 or +0.15, past the deadline, and the fixed arithmetic fires
    inside the last second before it, whatever the host's load.

    The agent is a real process that ignores TERM, so the KILL is what stops
    it: the arm the rounding affected.
    """
    trapped = tmp_path / "term-is-ignored"
    bin_dir, clock = _controlled_clock(
        tmp_path=tmp_path, start=_CONTROLLED_EPOCH + start_fraction, hold=trapped
    )
    deadline = _CONTROLLED_EPOCH + _SOON_SECONDS

    result = _run(
        tmp_path=tmp_path,
        deadline=str(deadline),
        # Absolute paths, so the agent runs on the HOST's clock and only the
        # guard reads the controlled one. The ignored TERM survives the exec.
        argv=_term_ignoring_agent(trapped=trapped),
        # A hang guard only: the guard's sleeps return at once, so it ends on
        # its own KILL long before this.
        timeout=_CONTROLLED_CLOCK_HANG_GUARD_SECONDS,
        path_prefix=bin_dir,
    )

    killed_at = float(clock.read_text(encoding="utf-8"))
    assert result.returncode == 128 + signal.SIGKILL, result.stderr
    assert (
        deadline - 1 < killed_at <= deadline
    ), f"a start at .{int(start_fraction * 100)} killed {killed_at - deadline:+.3f}s from the deadline"
