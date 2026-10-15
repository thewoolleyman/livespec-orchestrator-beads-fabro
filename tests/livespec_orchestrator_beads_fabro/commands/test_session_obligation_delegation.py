"""The real dispatched and delegated targets one registration boundary attaches.

Scenario 160 asks for an authorized detached dispatch whose launch intent is
"recorded before the effect and attached to the actual gate identity", and for
a crash between those two writes to be reconciled "with the stable operation
identity" without duplicating the effect. These cases drive the boundary the
product actually calls, against a real detached-gate directory and a real unix
socket peer, so what is measured is the attachment of an identity some other
process owns rather than one a fixture handed in.

The crash is reproduced the way it happens: a first registration whose target
cannot yet be observed leaves a recorded obligation with no attachment, and the
ORDINARY retry is what completes it.
"""

from __future__ import annotations

import itertools
import json
import shutil
import socket
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._session_obligation_coverage import (
    COVERAGE_UNMONITORED,
    COVERAGE_VERIFIED,
    DIAGNOSTIC_OWNER_ABSENT,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_delegation import (
    gate_launch_observer,
    pane_launch_observer,
    register_launch,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_host import (
    coverage_declaration_path,
    host_coverage_reading,
    obligation_store_root,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_launch import (
    DIAGNOSTIC_TARGET_UNOBSERVED,
    LAUNCH_ATTACHMENT_PENDING,
    LAUNCH_PROTECTED,
    LAUNCH_UNMONITORED,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_reconcile import (
    RECONCILE_ALREADY_ATTACHED,
    RECONCILE_ATTACHED,
    RECONCILE_EFFECT_UNOBSERVABLE,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_records import (
    LaunchAuthority,
    LaunchIntent,
    LaunchTarget,
    obligation_record_path,
    read_obligation_record,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GATE_TARGET_KIND,
    PANE_TARGET_KIND,
)

_OPERATION = "op-zejlae-1"
_SUN_PATH_LIMIT = 107

_SOUND_DECLARATION: dict[str, object] = {
    "max_observation_interval_seconds": 15.0,
    "proof_artifact": "livespec-overseer-consumer@0.1.0",
    "recovery_route": "overseer-supervised-service",
    "runtime": "codex",
    "runtime_version": "0.60.0",
    "service_generation": "7",
    "service_identity": "livespec-overseer-consumer.service",
    "takeover_budget_seconds": 20.0,
    "terminal_backend": "herdr",
    "terminal_instance": "w1:pF",
    "terminal_version": "0.9.3",
}


def _declare_coverage(*, primary: Path) -> None:
    path = coverage_declaration_path(primary=primary)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(_SOUND_DECLARATION), encoding="utf-8")


def _intent(*, primary: Path, operation_id: str = _OPERATION) -> LaunchIntent:
    return LaunchIntent(
        operation_id=operation_id,
        authority=LaunchAuthority(
            session_id="session-d",
            repository=primary,
            invoker="role:coordinator",
            scope="plan:agent-session-stall-prevention",
        ),
        required_result_identity="item_status bd-ib-zejlae status closed",
        result_epoch=4,
        original_deadline="2026-10-15T12:00:00Z",
    )


def _start_gate(*, gate_store_root: Path, run_id: str) -> None:
    run_dir = gate_store_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _ = (run_dir / "started_at").write_text("20261015T090000Z\n", encoding="utf-8")


def _answer_once(*, connection: socket.socket, reply: bytes) -> None:
    with suppress(OSError), connection:
        connection.settimeout(5.0)
        _ = connection.recv(65536)
        connection.sendall(reply)


@contextmanager
def _herdr_peer(*, terminal_id: str) -> Iterator[Path]:
    """A unix socket answering `agent.get` with one agent record.

    It owns a SHORT root of its own rather than binding under `tmp_path`, for
    the `sun_path` reason `test_session_wait_pane` records: under `pytest -n`
    the temporary prefix gains a worker segment and a longer path overflows
    the 107-byte limit, which `just check` runs into and a serial run does not.
    """
    directory = Path(tempfile.mkdtemp(prefix="livespec-oblig-"))
    socket_path = directory / "h.sock"
    assert len(str(socket_path)) <= _SUN_PATH_LIMIT
    reply = (
        json.dumps({"id": "test", "result": {"agent": {"terminal_id": terminal_id}}}).encode(
            "utf-8"
        )
        + b"\n"
    )
    stop = threading.Event()
    served = itertools.count()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(8)
    listener.settimeout(0.05)

    def serve() -> None:
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except OSError:
                continue
            _ = next(served)
            threading.Thread(
                target=_answer_once,
                kwargs={"connection": connection, "reply": reply},
                daemon=True,
            ).start()

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    try:
        yield socket_path
    finally:
        stop.set()
        worker.join(timeout=30.0)
        listener.close()
        shutil.rmtree(directory, ignore_errors=True)


class _RecordingObserver:
    """An observation that records every call and answers with a fixed target.

    It is the control for both directions of the refusal: the uncovered case
    asserts it was NEVER called, which only means something beside a covered
    case proving the same instrument IS reached and counted.
    """

    def __init__(self, *, target: LaunchTarget | None) -> None:
        self.target = target
        self.calls: list[str] = []

    def __call__(self, *, operation_id: str) -> LaunchTarget | None:
        self.calls.append(operation_id)
        return self.target


def test_an_undeclared_host_refuses_the_launch_and_observes_nothing(tmp_path: Path) -> None:
    """The uncovered refusal writes no obligation and takes no observation."""
    gate_store_root = tmp_path / "gate-runs"
    _start_gate(gate_store_root=gate_store_root, run_id="g-1")
    observer = _RecordingObserver(target=LaunchTarget(kind="gate", identity="gate:g-1"))

    outcome = register_launch(
        intent=_intent(primary=tmp_path),
        coverage=host_coverage_reading(path=coverage_declaration_path(primary=tmp_path)),
        obligation_store_root=obligation_store_root(primary=tmp_path),
        observe=observer,
        now=100.0,
    )

    assert (outcome.state, outcome.coverage_state) == (LAUNCH_UNMONITORED, COVERAGE_UNMONITORED)
    assert outcome.diagnostic == DIAGNOSTIC_OWNER_ABSENT
    assert outcome.protected is False
    assert observer.calls == []
    assert not obligation_store_root(primary=tmp_path).exists()


def test_a_covered_launch_observes_its_target_exactly_once(tmp_path: Path) -> None:
    """The positive control: one registration spends one observation."""
    _declare_coverage(primary=tmp_path)
    observer = _RecordingObserver(target=LaunchTarget(kind="gate", identity="gate:g-1"))

    outcome = register_launch(
        intent=_intent(primary=tmp_path),
        coverage=host_coverage_reading(path=coverage_declaration_path(primary=tmp_path)),
        obligation_store_root=obligation_store_root(primary=tmp_path),
        observe=observer,
        now=100.0,
    )

    assert outcome.state == LAUNCH_PROTECTED
    assert observer.calls == [_OPERATION]
    assert outcome.payload()["target"] == {"identity": "gate:g-1", "kind": "gate"}


def test_a_dispatched_gate_is_attached_by_its_own_identity(tmp_path: Path) -> None:
    _declare_coverage(primary=tmp_path)
    gate_store_root = tmp_path / "gate-runs"
    _start_gate(gate_store_root=gate_store_root, run_id="g-1")
    store = obligation_store_root(primary=tmp_path)

    outcome = register_launch(
        intent=_intent(primary=tmp_path),
        coverage=host_coverage_reading(path=coverage_declaration_path(primary=tmp_path)),
        obligation_store_root=store,
        observe=gate_launch_observer(gate_store_root=gate_store_root, run_id="g-1"),
        now=100.0,
    )

    assert (outcome.state, outcome.coverage_state) == (LAUNCH_PROTECTED, COVERAGE_VERIFIED)
    assert outcome.reconciliation is None
    assert outcome.target is not None
    assert outcome.target.kind == GATE_TARGET_KIND
    recorded = read_obligation_record(
        path=obligation_record_path(obligation_store_root=store, operation_id=_OPERATION)
    )
    assert recorded.payload is not None
    assert recorded.payload["target"] == outcome.target.record_payload()
    assert recorded.payload["result_epoch"] == 4


def test_a_delegated_pane_is_attached_by_its_own_identity(tmp_path: Path) -> None:
    _declare_coverage(primary=tmp_path)
    with _herdr_peer(terminal_id="t-delegate") as socket_path:
        outcome = register_launch(
            intent=_intent(primary=tmp_path),
            coverage=host_coverage_reading(path=coverage_declaration_path(primary=tmp_path)),
            obligation_store_root=obligation_store_root(primary=tmp_path),
            observe=pane_launch_observer(
                socket_path=socket_path, pane_id="w1:pF", timeout_seconds=5.0
            ),
            now=100.0,
        )

    assert outcome.state == LAUNCH_PROTECTED
    assert outcome.target is not None
    assert outcome.target.kind == PANE_TARGET_KIND
    assert "t-delegate" in outcome.target.identity


def test_an_unobservable_pane_leaves_the_obligation_pending(tmp_path: Path) -> None:
    _declare_coverage(primary=tmp_path)

    outcome = register_launch(
        intent=_intent(primary=tmp_path),
        coverage=host_coverage_reading(path=coverage_declaration_path(primary=tmp_path)),
        obligation_store_root=obligation_store_root(primary=tmp_path),
        observe=pane_launch_observer(
            socket_path=tmp_path / "absent.sock", pane_id="w1:pF", timeout_seconds=0.5
        ),
        now=100.0,
    )

    assert (outcome.state, outcome.diagnostic) == (
        LAUNCH_ATTACHMENT_PENDING,
        DIAGNOSTIC_TARGET_UNOBSERVED,
    )
    assert outcome.payload()["target"] is None


def test_a_partial_launch_is_completed_by_the_ordinary_retry(tmp_path: Path) -> None:
    """The crash window: intent recorded, no attachment, then the retry repairs it."""
    _declare_coverage(primary=tmp_path)
    gate_store_root = tmp_path / "gate-runs"
    store = obligation_store_root(primary=tmp_path)
    coverage = host_coverage_reading(path=coverage_declaration_path(primary=tmp_path))
    observer = gate_launch_observer(gate_store_root=gate_store_root, run_id="g-1")

    partial = register_launch(
        intent=_intent(primary=tmp_path),
        coverage=coverage,
        obligation_store_root=store,
        observe=observer,
        now=100.0,
    )
    _start_gate(gate_store_root=gate_store_root, run_id="g-1")
    repaired = register_launch(
        intent=_intent(primary=tmp_path),
        coverage=coverage,
        obligation_store_root=store,
        observe=observer,
        now=200.0,
    )
    settled = register_launch(
        intent=_intent(primary=tmp_path),
        coverage=coverage,
        obligation_store_root=store,
        observe=observer,
        now=300.0,
    )

    assert partial.state == LAUNCH_ATTACHMENT_PENDING
    assert (repaired.state, repaired.reconciliation) == (LAUNCH_PROTECTED, RECONCILE_ATTACHED)
    assert (settled.state, settled.reconciliation) == (
        LAUNCH_PROTECTED,
        RECONCILE_ALREADY_ATTACHED,
    )
    recorded = read_obligation_record(
        path=obligation_record_path(obligation_store_root=store, operation_id=_OPERATION)
    )
    assert recorded.payload is not None
    assert recorded.payload["original_deadline"] == "2026-10-15T12:00:00Z"
    assert recorded.payload["intent_recorded_at"] == 100.0
    assert recorded.payload["attached_at"] == 200.0


def test_a_retry_that_still_cannot_observe_stays_pending(tmp_path: Path) -> None:
    _declare_coverage(primary=tmp_path)
    store = obligation_store_root(primary=tmp_path)
    coverage = host_coverage_reading(path=coverage_declaration_path(primary=tmp_path))
    observer = gate_launch_observer(gate_store_root=tmp_path / "gate-runs", run_id="g-1")

    _ = register_launch(
        intent=_intent(primary=tmp_path),
        coverage=coverage,
        obligation_store_root=store,
        observe=observer,
        now=100.0,
    )
    retried = register_launch(
        intent=_intent(primary=tmp_path),
        coverage=coverage,
        obligation_store_root=store,
        observe=observer,
        now=200.0,
    )

    assert (retried.state, retried.reconciliation) == (
        LAUNCH_ATTACHMENT_PENDING,
        RECONCILE_EFFECT_UNOBSERVABLE,
    )
    assert retried.protected is False


@pytest.mark.parametrize("run_id", ["g-absent", "g-1"])
def test_the_gate_observer_answers_only_for_a_gate_that_exists(tmp_path: Path, run_id: str) -> None:
    gate_store_root = tmp_path / "gate-runs"
    _start_gate(gate_store_root=gate_store_root, run_id="g-1")

    observed = gate_launch_observer(gate_store_root=gate_store_root, run_id=run_id)(
        operation_id=_OPERATION
    )

    assert (observed is None) == (run_id == "g-absent")
