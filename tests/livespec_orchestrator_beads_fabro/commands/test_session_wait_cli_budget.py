"""The host wait command spends ONE deadline on freezing and on waiting.

Scenario 156 binds every observation, transport operation and the final return
of a wait to the one deadline it was armed with. The CLI freezes each named
pane's identity before it hands the targets to the wait, and that initial
observation is not exempt: measured against the real `session_wait.main` with
default seams, a 0.1s requested deadline against a peer that accepted
`agent.get` and never answered took 5.01s, because the freeze used its own
default socket timeout before the wait's clock had started.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _session_wait_cli, session_wait
from livespec_orchestrator_beads_fabro.commands._session_wait_pane import freeze_pane_target
from livespec_orchestrator_beads_fabro.commands._session_wait_records import (
    process_generation_token,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_routing import (
    default_wait_launcher,
    observe_wait_target,
)

_PEER_RECEIVE_BYTES = 65536
# Far above any budget these tests request, so a peer that has not answered by
# then has hung for the purposes of every assertion below.
_NEVER_SECONDS = 3600.0


_PEER_REPLY = (
    json.dumps({"id": "livespec-session-wait", "result": {"agent": {"terminal_id": "t-peer"}}})
    + "\n"
).encode("utf-8")


def _answer_after(
    *,
    connection: socket.socket,
    received: list[bytes],
    stop: threading.Event,
    reply_after_seconds: float,
) -> None:
    """Record one request, then reply only once the delay has passed."""
    with suppress(OSError):
        connection.settimeout(1.0)
        received.append(connection.recv(_PEER_RECEIVE_BYTES))
        if not stop.wait(timeout=reply_after_seconds):
            connection.sendall(_PEER_REPLY)


def _serve(
    *,
    listener: socket.socket,
    held: list[socket.socket],
    received: list[bytes],
    stop: threading.Event,
    reply_after_seconds: float,
) -> None:
    while not stop.is_set():
        try:
            connection, _ = listener.accept()
        except OSError:
            continue
        held.append(connection)
        threading.Thread(
            target=_answer_after,
            kwargs={
                "connection": connection,
                "received": received,
                "stop": stop,
                "reply_after_seconds": reply_after_seconds,
            },
            daemon=True,
        ).start()


@contextmanager
def _identity_peer(*, socket_path: Path, reply_after_seconds: float) -> Iterator[list[bytes]]:
    """A unix socket that answers `agent.get` only after a fixed delay.

    Disclosed as a CONTROLLED PEER rather than presented as a server: a healthy
    Herdr server cannot be asked to answer slowly or never, and what is under
    test is how the CLI's budget treats a slow first identity observation. The
    reply, when it comes, is a well-formed agent record carrying a terminal id,
    so a freeze that receives it in time identifies the pane. Each connection
    is held OPEN until it is answered — closing it would end the read with an
    empty buffer, which is a reply rather than a hang.

    Every request received is recorded and yielded, so a test can assert that
    only a read-only `agent.get` reached the target.
    """
    received: list[bytes] = []
    held: list[socket.socket] = []
    stop = threading.Event()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(8)
    listener.settimeout(0.05)
    worker = threading.Thread(
        target=_serve,
        kwargs={
            "listener": listener,
            "held": held,
            "received": received,
            "stop": stop,
            "reply_after_seconds": reply_after_seconds,
        },
        daemon=True,
    )
    worker.start()
    try:
        yield received
    finally:
        stop.set()
        worker.join(timeout=30.0)
        for connection in held:
            connection.close()
        listener.close()


@dataclass(kw_only=True)
class _FreezeRecorder:
    """The REAL identity freeze, keeping the budget each call was GRANTED.

    The granted budget is the decision under test, and it is observable nowhere
    else. A duration measured around the command renders a verdict on what the
    HOST did with that budget, which is why the bound it needed carried 1.5
    seconds of slack and why it failed on a loaded factory; the number the CLI
    hands each freeze is the thing the clause is about, and it cannot be moved
    by load.

    The discrimination is unchanged and sharper. Measured before the fix, a
    0.1s request took 5.01s because the freeze spent its own default socket
    timeout — a build that did that again records 5.0 against a 0.3s deadline
    here, every run. And a build giving each freeze a FRESH budget records the
    full deadline twice, which no shared budget can produce.

    Every bound asserted against these values is one-sided in the safe
    direction: the remaining budget only ever SHRINKS as a host slows down, so
    load can make an assertion pass more comfortably and never less.
    """

    budgets: list[float] = field(default_factory=list)

    def freeze(self, *, socket_path: Path, pane_id: str, timeout_seconds: float) -> object:
        self.budgets.append(timeout_seconds)
        return freeze_pane_target(
            socket_path=socket_path,
            pane_id=pane_id,
            timeout_seconds=timeout_seconds,
        )


def _recorded_freeze(*, monkeypatch: pytest.MonkeyPatch) -> _FreezeRecorder:
    """Put the recorder in the CLI's own freeze seam for one case."""
    recorder = _FreezeRecorder()
    monkeypatch.setattr(_session_wait_cli, "freeze_pane_target", recorder.freeze)
    return recorder


def _own_root(*, repository: Path) -> Path:
    return repository


def _seams() -> session_wait.SessionWaitCliSeams:
    """The default seams, except that the repository is the test's own root."""
    return session_wait.SessionWaitCliSeams(
        primary_repository=_own_root,
        launcher=default_wait_launcher,
        observe_target=observe_wait_target,
        process_generation=process_generation_token,
        wall_clock=time.time,
    )


def _wait_argv(*, repository: Path, deadline_seconds: float, panes: list[Path]) -> list[str]:
    argv = [
        "wait",
        "--repo",
        str(repository),
        "--session-id",
        "budget-session",
        "--wait-id",
        "budget-wait",
        "--deadline-seconds",
        str(deadline_seconds),
    ]
    for index, socket_path in enumerate(panes):
        argv += ["--pane", str(socket_path), f"w1:p{index + 1}"]
    return argv


def test_a_hung_first_identity_observation_is_refused_inside_the_deadline(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pane whose identity never arrives is refused within the request.

    The refusal itself is kept — a pane the server cannot identify is a
    precondition failure of the request, never an armed target — but it has to
    be bounded by the deadline the caller asked for rather than by the freeze's
    own default socket timeout. The GRANTED budget is what says so; see
    `_FreezeRecorder` for why that is the instrument and a measured duration
    is not.
    """
    socket_path = tmp_path / "hung.sock"
    deadline_seconds = 0.3
    recorder = _recorded_freeze(monkeypatch=monkeypatch)
    with (
        _identity_peer(socket_path=socket_path, reply_after_seconds=_NEVER_SECONDS) as received,
        pytest.raises(ValueError, match="not identifiable"),
    ):
        _ = session_wait.main(
            argv=_wait_argv(
                repository=tmp_path,
                deadline_seconds=deadline_seconds,
                panes=[socket_path],
            ),
            seams=_seams(),
        )
    assert len(recorder.budgets) == 1, f"one pane was frozen, not {len(recorder.budgets)}"
    assert (
        recorder.budgets[0] <= deadline_seconds
    ), f"the freeze was granted {recorder.budgets[0]}s against a {deadline_seconds}s deadline"
    # The freeze SPENT that budget on a real read rather than being handed a
    # zero one, which is what makes the bound above a bound on work done.
    assert [json.loads(request)["method"] for request in received] == ["agent.get"]


def test_slow_identity_observations_share_one_budget_with_the_wait(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two slow freezes and the wait itself spend ONE deadline, not three.

    Each peer answers after most of the deadline. A CLI that gave every freeze
    its own budget would identify both panes and then start a full-length wait,
    returning after roughly three deadlines; with one shared budget the second
    freeze cannot outlast what remains.

    The SECOND granted budget is what distinguishes those two worlds, and it
    distinguishes them without a verdict on the host: a shared budget cannot
    grant the second freeze more than the deadline minus what the first one
    spent, while a per-freeze budget grants it the whole deadline again.
    """
    deadline_seconds = 2.0
    reply_after_seconds = 1.6
    first, second = tmp_path / "first.sock", tmp_path / "second.sock"
    recorder = _recorded_freeze(monkeypatch=monkeypatch)
    with (
        _identity_peer(socket_path=first, reply_after_seconds=reply_after_seconds),
        _identity_peer(socket_path=second, reply_after_seconds=reply_after_seconds),
        suppress(ValueError),
    ):
        _ = session_wait.main(
            argv=_wait_argv(
                repository=tmp_path,
                deadline_seconds=deadline_seconds,
                panes=[first, second],
            ),
            seams=_seams(),
        )
    assert len(recorder.budgets) == 2, f"two panes were frozen, not {len(recorder.budgets)}"
    granted_first, granted_second = recorder.budgets
    assert granted_first <= deadline_seconds
    assert granted_second < granted_first
    assert granted_second <= deadline_seconds - reply_after_seconds, (
        f"the second freeze was granted {granted_second}s after the first spent"
        f" {reply_after_seconds}s of a {deadline_seconds}s deadline"
    )
