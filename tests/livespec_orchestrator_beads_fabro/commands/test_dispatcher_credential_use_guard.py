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
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
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

# SIGNAL-DELIVERY SLACK ONLY, deliberately tight. The guard floors a FRACTIONAL
# measurement of the remaining budget, so its KILL is due at or BEFORE the epoch
# by construction; this covers only the scheduling delay between the signal and
# the child stopping. It is NOT a grace, and it must never be widened to make a
# late kill pass -- an earlier draft of this module allowed 2.5 seconds and
# would have accepted the measured deadline+0.65 rounding defect as healthy.
_HARD_TOLERANCE_SECONDS = 0.5
_SETTLE_SECONDS = 10


def _guard(*, tmp_path: Path) -> Path:
    """Render the SHIPPED guard script and make it executable."""
    script = tmp_path / "credential-use-guard.sh"
    _ = script.write_text(guard_script_text(), encoding="utf-8")
    script.chmod(0o755)
    return script


def _run(
    *,
    tmp_path: Path,
    deadline: str | None,
    argv: list[str],
    timeout: float = _SETTLE_SECONDS,
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the guard around `argv`, with the deadline supplied as the env var."""
    env = dict(os.environ)
    env.pop(CREDENTIAL_USE_DEADLINE_ENV_VAR, None)
    if deadline is not None:
        env[CREDENTIAL_USE_DEADLINE_ENV_VAR] = deadline
    return subprocess.run(
        ["/bin/sh", str(_guard(tmp_path=tmp_path)), "--", *argv],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )


def _heartbeat_argv(*, beat_file: Path, pid_file: Path) -> list[str]:
    """A harmless child that stamps the clock continuously while it executes.

    The heartbeat is the instrument that separates EXECUTING from merely
    EXISTING: a stopped-but-unreaped process writes nothing, so the last
    timestamp in this file is the last moment the child actually ran. Asking
    only whether a pid exists cannot tell a zombie from a live agent, and a
    zombie holds no credential.
    """
    return [
        "/bin/sh",
        "-c",
        f"echo $$ > {pid_file}; while : ; do date +%s.%N >> {beat_file}; sleep 0.2; done",
    ]


def _last_beat(*, beat_file: Path) -> float:
    """The last instant the child was observed executing."""
    beats = [
        line.strip() for line in beat_file.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert beats, "the child never recorded a heartbeat, so nothing was measured"
    return float(beats[-1])


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
    """Execution stops BY the absolute epoch, measured from the child's own clock.

    The assertion is NOT "the process is gone eventually" -- that is satisfied by
    a guard whose grace runs past the deadline, which would permit exactly the
    credential use the bound forbids. The child stamps the clock while it runs,
    so the LAST heartbeat is the last instant it executed, and that instant must
    not be later than the deadline plus scheduling slack.
    """
    beat_file = tmp_path / "beats"
    pid_file = tmp_path / "pid"
    deadline = int(time.time()) + _SOON_SECONDS

    result = _run(
        tmp_path=tmp_path,
        deadline=str(deadline),
        argv=_heartbeat_argv(beat_file=beat_file, pid_file=pid_file),
        timeout=_SOON_SECONDS + _SETTLE_SECONDS,
    )

    last = _last_beat(beat_file=beat_file)
    assert (
        last <= deadline + _HARD_TOLERANCE_SECONDS
    ), f"the child was still executing {last - deadline:.2f}s after the deadline"
    # And it genuinely ran, so the bound is what stopped it rather than a
    # command that never started.
    assert last > deadline - _SOON_SECONDS
    assert result.returncode != 0


def test_a_term_resistant_child_still_stops_by_the_deadline(tmp_path: Path) -> None:
    """TERM refusal buys no time at all, not even the escalation grace.

    The child traps TERM and keeps stamping the clock, which is what an agent
    mid-turn with its own signal handling looks like. Because the guard lands
    TERM a grace BEFORE the deadline and KILL **at** it, refusing TERM costs the
    child its grace and nothing more: it must still stop by the same instant a
    compliant child would.
    """
    beat_file = tmp_path / "beats"
    pid_file = tmp_path / "pid"
    deadline = int(time.time()) + _SOON_SECONDS

    result = _run(
        tmp_path=tmp_path,
        deadline=str(deadline),
        argv=[
            "/bin/sh",
            "-c",
            f"trap '' TERM; echo $$ > {pid_file}; "
            f"while : ; do date +%s.%N >> {beat_file}; sleep 0.2; done",
        ],
        timeout=_SOON_SECONDS + _SETTLE_SECONDS,
    )

    last = _last_beat(beat_file=beat_file)
    assert (
        last <= deadline + _HARD_TOLERANCE_SECONDS
    ), f"a TERM-resistant child executed {last - deadline:.2f}s past the deadline"
    assert result.returncode != 0


def test_a_credential_using_grandchild_stops_by_the_deadline_after_its_parent_exits(
    tmp_path: Path,
) -> None:
    """The ADAPTER PARENT EXITS and its child keeps the credential; both stop by the bound.

    This is the shape a guard that signals only its direct child gets wrong, and
    it is the shape that matters: the process still holding the credential after
    an adapter returns is the grandchild, not the adapter.

    THE WAIT IS LOAD-BEARING. The reaper is detached, so the wrapper returns as
    soon as the short-lived parent exits -- long before the deadline. Reading the
    heartbeat at that moment would pass even if the grandchild then ran forever,
    which is exactly the vacuous shape this case must not have. So it sleeps
    PAST the absolute deadline first, and only then asks when the grandchild
    last executed.
    """
    beat_file = tmp_path / "beats"
    pgid_file = tmp_path / "pgid"
    deadline = int(time.time()) + _SOON_SECONDS

    result = _run(
        tmp_path=tmp_path,
        deadline=str(deadline),
        # The parent records the process group it owns, spawns a long-running
        # stamper, and exits IMMEDIATELY.
        argv=[
            "/bin/sh",
            "-c",
            f"ps -o pgid= -p $$ | tr -d ' ' > {pgid_file}; "
            f"/bin/sh -c 'while : ; do date +%s.%N >> {beat_file}; sleep 0.2; done' & exit 0",
        ],
        timeout=_SETTLE_SECONDS,
    )

    # The wrapper has already returned; the bound has not yet fallen.
    assert result.returncode == 0
    assert time.time() < deadline, "the parent did not exit before the deadline"

    # Wait THROUGH the deadline, then read when the grandchild last ran.
    time.sleep((deadline - time.time()) + _HARD_TOLERANCE_SECONDS + 1.0)

    last = _last_beat(beat_file=beat_file)
    try:
        assert (
            last <= deadline + _HARD_TOLERANCE_SECONDS
        ), f"a credential-using grandchild executed {last - deadline:+.3f}s past the deadline"
    finally:
        # Own what we spawned: never leak a stamper into the rest of the suite.
        # Own what we spawned. Every failure mode here is suppressed together --
        # an unwritten file, an unparseable pgid, a group already gone -- because
        # this is cleanup running inside a `finally`, and a cleanup that raised
        # would replace the real assertion failure with its own.
        with contextlib.suppress(OSError, ValueError):
            os.killpg(int(pgid_file.read_text(encoding="utf-8").strip()), signal.SIGKILL)


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
    env = dict(os.environ)
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
    """The host-independence property, read locally and against the epoch.

    The reaper lives in the sandbox beside the child, so losing the process that
    is WAITING does not extend anything. Here the waiter is killed deliberately
    -- standing in for a dying host-side waiter -- and the child must still stop
    by the same instant.
    """
    beat_file = tmp_path / "beats"
    pid_file = tmp_path / "pid"
    deadline = int(time.time()) + _SOON_SECONDS
    env = dict(os.environ)
    env[CREDENTIAL_USE_DEADLINE_ENV_VAR] = str(deadline)

    guarded = subprocess.Popen(
        [
            "/bin/sh",
            str(_guard(tmp_path=tmp_path)),
            "--",
            *_heartbeat_argv(beat_file=beat_file, pid_file=pid_file),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    settle = time.time() + 10
    while time.time() < settle and not beat_file.exists():
        time.sleep(0.1)

    guarded.send_signal(signal.SIGKILL)
    _ = guarded.wait(timeout=10)

    time.sleep(_SOON_SECONDS + _HARD_TOLERANCE_SECONDS + 2)

    last = _last_beat(beat_file=beat_file)
    assert (
        last <= deadline + _HARD_TOLERANCE_SECONDS
    ), f"the agent executed {last - deadline:.2f}s past the deadline after the waiter died"


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
    beat_file = tmp_path / "beats"
    while not (start_fraction <= (time.time() % 1) <= start_fraction + 0.08):
        time.sleep(0.005)
    deadline = int(time.time()) + _SOON_SECONDS

    result = _run(
        tmp_path=tmp_path,
        deadline=str(deadline),
        argv=[
            "python3",
            "-c",
            "import signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            f"handle = open({str(beat_file)!r}, 'a')\n"
            "while True:\n"
            "    handle.write('%.6f\\n' % time.time())\n"
            "    handle.flush()\n"
            "    time.sleep(0.05)\n",
        ],
        timeout=_SOON_SECONDS + _SETTLE_SECONDS,
    )

    last = _last_beat(beat_file=beat_file)
    assert (
        last <= deadline + _HARD_TOLERANCE_SECONDS
    ), f"a start at .{int(start_fraction * 100)} killed {last - deadline:+.3f}s past the deadline"
    assert result.returncode != 0
