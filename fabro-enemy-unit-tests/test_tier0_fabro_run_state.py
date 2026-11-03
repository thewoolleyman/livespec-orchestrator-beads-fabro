"""Tier 0 Enemy Unit Tests for the server's run-state read.

The ACP availability-evidence scan reads each in-window failed run's record,
and since bd-ib-fhmpik it takes that record from `GET /api/v1/runs/<id>/state`
with gzip, not from `fabro inspect --json`. The CLI gives up at a fixed 30 s,
and one 10.4 MB record took longer than that, so the unreadable run blanked
every Anthropic and Codex candidate fleet-wide. These cases measure what the
deployed engine serves on that route: that it answers compressed, and that it
carries the same conclusion and status the inspect record carries.

Like its tier 0 siblings this suite sits outside `tests/` so the hermetic
`just check` aggregate never needs a live Fabro server or credentials. Invoke
it explicitly:

    just fabro-enemy-tier0
"""

from __future__ import annotations

from typing import Any, cast

from _tier0_support import (
    TIMEOUT_SECONDS,
    _completed_run_id,
    _FabroTier0Config,
    _inspect_record,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_compressed import (
    CompressedUrllibTransport,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpPort

__all__: list[str] = []

_CLIENT_ERROR_FLOOR = 400
# A VALID ULID the factory cannot hold; see `test_tier0_fabro_run_files`.
_ABSENT_RUN_ID = "01ENEMYTESTABSENTZZZZZZZZZ"


def _compressed_face(*, port: FabroPort) -> FabroHttpPort:
    return FabroHttpPort(target=port.target, transport=CompressedUrllibTransport())


def test_the_run_state_read_carries_the_inspect_record_s_conclusion_and_status(
    *,
    config: _FabroTier0Config,
    port: FabroPort,
) -> None:
    """The compressed state read and `fabro inspect` agree on what grading reads."""
    run_id = config.completed_run_id or _completed_run_id(port=port)

    state = _compressed_face(port=port).run_state(run_id=run_id, timeout_seconds=TIMEOUT_SECONDS)
    inspected = port.inspect(run_id=run_id, timeout_seconds=TIMEOUT_SECONDS)

    assert state.succeeded, f"status {state.status}: {state.error}"
    assert isinstance(state.payload, dict), state.body[:200]
    record = cast("dict[str, Any]", state.payload)
    reference = _inspect_record(value=inspected.payload)
    assert record.get("status") == reference.get("status")
    assert record.get("conclusion") == reference.get("conclusion")
    assert isinstance(record.get("checkpoints"), list)
    assert isinstance(record.get("stages"), dict)


def test_the_run_state_read_of_a_run_the_factory_does_not_hold_is_refused(
    *,
    port: FabroPort,
) -> None:
    """A refusal must REACH the server: status 0 would make the reader retry, not fall back."""
    result = _compressed_face(port=port).run_state(
        run_id=_ABSENT_RUN_ID, timeout_seconds=TIMEOUT_SECONDS
    )

    assert not result.succeeded
    assert result.status >= _CLIENT_ERROR_FLOOR, f"status {result.status}: {result.error}"
