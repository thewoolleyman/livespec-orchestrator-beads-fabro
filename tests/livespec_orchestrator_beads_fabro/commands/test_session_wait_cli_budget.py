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
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import session_wait
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
# Slack for interpreter, thread and socket overhead on a loaded host. It is an
# order of magnitude below the five-second default the freeze used to spend, so
# a freeze that escaped the budget cannot pass inside it.
_SLACK_SECONDS = 1.5


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
    *, tmp_path: Path
) -> None:
    """A pane whose identity never arrives is refused within the request.

    The refusal itself is kept — a pane the server cannot identify is a
    precondition failure of the request, never an armed target — but it has to
    arrive inside the deadline the caller asked for rather than after the
    freeze's own default socket timeout.
    """
    socket_path = tmp_path / "hung.sock"
    deadline_seconds = 0.3
    with _identity_peer(socket_path=socket_path, reply_after_seconds=_NEVER_SECONDS) as received:
        started = time.monotonic()
        with pytest.raises(ValueError, match="not identifiable"):
            _ = session_wait.main(
                argv=_wait_argv(
                    repository=tmp_path,
                    deadline_seconds=deadline_seconds,
                    panes=[socket_path],
                ),
                seams=_seams(),
            )
        elapsed = time.monotonic() - started
    assert (
        elapsed < deadline_seconds + _SLACK_SECONDS
    ), f"identity refusal took {elapsed:.2f}s against a {deadline_seconds}s deadline"
    assert [json.loads(request)["method"] for request in received] == ["agent.get"]


def test_slow_identity_observations_share_one_budget_with_the_wait(*, tmp_path: Path) -> None:
    """Two slow freezes and the wait itself spend ONE deadline, not three.

    Each peer answers after most of the deadline. A CLI that gave every freeze
    its own budget would identify both panes and then start a full-length wait,
    returning after roughly three deadlines; with one shared budget the second
    freeze cannot outlast what remains, so the command ends near ONE deadline,
    either refusing the second pane or reporting the wait's expiry.
    """
    deadline_seconds = 2.0
    reply_after_seconds = 1.6
    first, second = tmp_path / "first.sock", tmp_path / "second.sock"
    with (
        _identity_peer(socket_path=first, reply_after_seconds=reply_after_seconds),
        _identity_peer(socket_path=second, reply_after_seconds=reply_after_seconds),
    ):
        started = time.monotonic()
        with suppress(ValueError):
            _ = session_wait.main(
                argv=_wait_argv(
                    repository=tmp_path,
                    deadline_seconds=deadline_seconds,
                    panes=[first, second],
                ),
                seams=_seams(),
            )
        elapsed = time.monotonic() - started
    assert (
        elapsed < deadline_seconds + _SLACK_SECONDS
    ), f"two freezes and a wait took {elapsed:.2f}s against one {deadline_seconds}s deadline"
