"""The order guard's endpoint, as an ordinary dispatched sandbox projects it.

Slice S2 ships the sandbox-side order guard
(`.claude/hooks/livespec_tdd_order_span.py`) and slice S3 ships the host-side
aggregate (`_dispatcher_tdd_order_sink`) plus the two terminal calibration
fields that read it. Both halves were proven, and the WIRE BETWEEN THEM was
not: the guard resolves its receiver from `LIVESPEC_SANDBOX_OTEL_ENDPOINT`
alone and deliberately defaults to nothing, while
`_dispatcher_projection.cc_otel_overlay_env` projected only
`OTEL_EXPORTER_OTLP_ENDPOINT`. So every decision an ordinary dispatch reached
resolved NO endpoint, posted nothing, and left both calibration fields absent
— measured on live run 01M47AGX4BB5FJJR0K6AW1736W, whose sandbox environment
carried the exporter endpoint and no sandbox-endpoint key at all.

This module is the regression that binds the two surfaces through the REAL
path and nothing else: a live `OtelReceiver` on an ephemeral loopback port, a
real `TddOrderSink`, the SHIPPED hook emitter, and the production calibration
projection. The environment the hook is handed is EXACTLY the dict
`cc_otel_overlay_env` returns — never a hand-assembled one with the key added
— because a test that supplies the variable itself proves the emitter works
and says nothing about whether a dispatch supplies it. That substitution is
precisely the gap this file exists to close.

The endpoint is the RESOLVED per-dispatch one, threaded from the receiver's
own bound port through `resolve_sandbox_otel_endpoint`. Nothing here names a
host, a port, or a cache path, so the test cannot pass by agreeing with a
constant that production does not use.

Four controls, each of which would fail if the one below it were the real
mechanism:

- An ALLOWED write records an observed zero and a clean first-write flag,
  which is what makes `0` / `False` distinguishable from absence rather than
  merely plausible.
- The aggregate is reachable by THIS dispatch's id and by no other, so the
  positive reading is keyed to the dispatch that earned it.
- A dispatch with NO observed decision leaves both fields unobserved — `None`,
  never a healthy-looking zero or false.
- With no projection in the environment at all the hook posts NOTHING, which
  is the no-network behaviour a human session outside any dispatch depends on.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    SANDBOX_OTEL_ENDPOINT_ENV_VAR,
    cc_otel_overlay_env,
    resolve_sandbox_otel_endpoint,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_order_sink import TddOrderSink
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe import gather_tdd_signals
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_signals import (
    TddSignals,
    tdd_signal_fields,
    tdd_span_fields,
)
from livespec_orchestrator_beads_fabro.commands._otel_receive import (
    HeartbeatSink,
    OtelReceiver,
    ReceiverConfig,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"
_SPAN_PATH = _HOOKS_DIR / "livespec_tdd_order_span.py"
_POLICY_PATH = _HOOKS_DIR / "livespec_tdd_order_policy.py"

_WORK_ITEM_ID = "bd-ib-swm6te"
_DISPATCH_ID = "7c1d4a9f2b3e46d7a8f05c1e9b6d2043"
_OTHER_DISPATCH_ID = "00004a9f2b3e46d7a8f05c1e9b6d2043"

_ORDER_REFUSALS_KEY = "tdd.order_refusals"
_FIRST_WRITE_BEFORE_RED_KEY = "tdd.first_product_write_before_red"

_PRODUCT_PATH = (
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_projection.py"
)


def _load(*, path: Path, name: str) -> ModuleType:
    """Load one `.claude/hooks/` module by file location.

    That tree is repo-local dev tooling and is not an importable package, so
    the SHIPPED bytes are reached the same way `tests/hooks/` reaches them.
    The file-exists assertion comes first so a missing module fails as an
    assertion rather than at collection.
    """
    assert path.is_file(), f"module not implemented yet: {path}"
    if str(_HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_span() -> ModuleType:
    return _load(path=_SPAN_PATH, name="livespec_tdd_order_span_for_projection")


def _load_policy() -> ModuleType:
    return _load(path=_POLICY_PATH, name="livespec_tdd_order_policy_for_projection")


def _refusal() -> Any:
    """One REFUSED product write at a head that is not an open Red."""
    policy = _load_policy()
    return policy.Decision(
        decision=policy.REFUSE,
        reason=policy.REASON_CLOSED_HEAD,
        head_state=policy.HEAD_CLOSED,
        path=_PRODUCT_PATH,
        tool="Edit",
    )


def _allowance() -> Any:
    """One ALLOWED product write at an open Red — the healthy verdict."""
    policy = _load_policy()
    return policy.Decision(
        decision=policy.ALLOW,
        reason=policy.REASON_OPEN_RED,
        head_state=policy.HEAD_OPEN_RED,
        path=_PRODUCT_PATH,
        tool="Edit",
    )


class _FakeExporter:
    """Egress stand-in: the Honeycomb leg is not what this file measures.

    The sink records at INGEST, before egress, so a successful export is not a
    precondition for the aggregate — and standing the exporter in is what
    keeps this test off the network.
    """

    def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
        _ = (spans, dataset)
        return True


class _FailingProbeRunner:
    """A `CommandRunner` whose `gh pr view` probe reports failure.

    The commit-derived calibration fields are deliberately left unobservable
    here: this file measures the ORDER fields, and a scripted commit series
    would add a second derivation that could be wrong without saying which
    half the assertion was about. A failing probe is a real arm of
    `commit_signals_for_dispatch`, so the gather reaches its `None` honestly
    rather than by being handed a shape it never sees in production.
    """

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env)
        return CommandResult(exit_code=1, stdout="", stderr="no pull request")


@dataclass(frozen=True, kw_only=True)
class _LiveReceiver:
    """A started receiver, its order sink, and the URL a sandbox would use."""

    receiver: OtelReceiver
    tdd_order: TddOrderSink
    base_url: str


@pytest.fixture
def live_receiver(tmp_path: Path) -> Iterator[_LiveReceiver]:
    """A real ephemeral-port OTLP receiver wired to a real order sink."""
    sink = TddOrderSink(path=tmp_path / "fabro-dispatch-journal-tdd-order.json")
    receiver = OtelReceiver(
        config=ReceiverConfig(host="127.0.0.1", port=0),
        exporter=_FakeExporter(),
        heartbeat=HeartbeatSink(path=tmp_path / "hb.json"),
        tdd_order=sink,
    )
    receiver.start()
    try:
        yield _LiveReceiver(
            receiver=receiver,
            tdd_order=sink,
            base_url=f"http://127.0.0.1:{receiver.bound_port}",
        )
    finally:
        receiver.stop()


def _dispatched_sandbox_env(*, endpoint_lever: str) -> dict[str, str]:
    """The sandbox environment an ordinary dispatch projects — and ONLY that.

    Both steps are the production ones: the host resolves the per-dispatch
    endpoint through `resolve_sandbox_otel_endpoint`, then
    `cc_otel_overlay_env` assembles the dict the run-config overlay writes
    into the sandbox. Nothing is added afterwards, which is what makes the
    emission below a measurement of the PROJECTION rather than of the emitter.
    """
    endpoint = resolve_sandbox_otel_endpoint(
        environ={SANDBOX_OTEL_ENDPOINT_ENV_VAR: endpoint_lever}
    )
    return cc_otel_overlay_env(
        work_item_id=_WORK_ITEM_ID,
        dispatch_id=_DISPATCH_ID,
        endpoint=endpoint,
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_WORK_ITEM_ID,
        type="bug",
        status="active",
        title="Project the order-guard telemetry endpoint into dispatched sandboxes",
        description="Close the producer-consumer gap.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_criteria="- One assertion.\n- Two assertions.\n",
    )


def _gathered(*, sink: TddOrderSink) -> TddSignals:
    """This dispatch's calibration signals, through the production gather."""
    return gather_tdd_signals(
        repo=_REPO_ROOT,
        item=_item(),
        outcome=DispatchOutcome(
            work_item_id=_WORK_ITEM_ID,
            status="green",
            stage="done",
            pr_number=4242,
            merge_sha=None,
            detail="published",
        ),
        records=(
            {
                "stage": "dispatch-id",
                "work_item_id": _WORK_ITEM_ID,
                "dispatch_id": _DISPATCH_ID,
            },
        ),
        sink=sink,
        runner=_FailingProbeRunner(),
    )


# --- the projected endpoint carries a real decision to the real receiver ---


def test_a_dispatched_sandbox_decision_reaches_the_receiver_and_the_calibration_fields(
    live_receiver: _LiveReceiver,
) -> None:
    """The ordinary dispatched environment alone is enough to deliver a verdict."""
    span = _load_span()
    sandbox_env = _dispatched_sandbox_env(endpoint_lever=live_receiver.base_url)

    assert span.emit_for_decision(decision=_refusal(), environ=sandbox_env) == span.EMITTED

    signals = _gathered(sink=live_receiver.tdd_order)
    assert signals.order_refusals == 1
    assert signals.first_product_write_before_red is True
    projected = tdd_span_fields(signals=signals)
    assert projected[_ORDER_REFUSALS_KEY] == 1
    assert projected[_FIRST_WRITE_BEFORE_RED_KEY] is True


def test_an_allowed_write_at_an_open_red_records_an_observed_zero(
    live_receiver: _LiveReceiver,
) -> None:
    """An observed clean run reads `0` / `False` — distinguishable from absence.

    This is the positive control for the negative case below: without it, a
    sink that recorded nothing at all would be indistinguishable from one
    recording a healthy run.
    """
    span = _load_span()
    sandbox_env = _dispatched_sandbox_env(endpoint_lever=live_receiver.base_url)

    assert span.emit_for_decision(decision=_allowance(), environ=sandbox_env) == span.EMITTED

    signals = _gathered(sink=live_receiver.tdd_order)
    assert signals.order_refusals == 0
    assert signals.first_product_write_before_red is False


def test_the_delivered_decision_is_keyed_by_the_dispatch_that_earned_it(
    live_receiver: _LiveReceiver,
) -> None:
    """The aggregate is reachable by THIS dispatch's id and by no other.

    Read through the sink directly rather than through `gather_tdd_signals`,
    and the difference is the measurement. The gather looks the aggregate up
    most-specific-first and falls back to the WORK-ITEM id, which is the
    deliberate rescue for a dispatch whose id never reached the journal — so a
    foreign dispatch id asked of the gather still resolves this item's entry,
    and reading absence there would be reading the fallback, not the keying.
    Asking the sink for the foreign id ALONE is what can return nothing.
    """
    span = _load_span()
    sandbox_env = _dispatched_sandbox_env(endpoint_lever=live_receiver.base_url)

    assert span.emit_for_decision(decision=_refusal(), environ=sandbox_env) == span.EMITTED

    mine = live_receiver.tdd_order.signals_for(keys=(_DISPATCH_ID,))
    assert mine.order_refusals == 1
    assert mine.first_product_write_before_red is True

    foreign = live_receiver.tdd_order.signals_for(keys=(_OTHER_DISPATCH_ID,))
    assert foreign.order_refusals is None
    assert foreign.first_product_write_before_red is None


# --- absence stays absence ------------------------------------------------


def test_a_dispatch_with_no_observed_decision_leaves_both_fields_unobserved(
    tmp_path: Path,
) -> None:
    """No decision observed is `None` on both fields — never zero, never false."""
    sink = TddOrderSink(path=tmp_path / "fabro-dispatch-journal-tdd-order.json")

    signals = _gathered(sink=sink)
    assert signals.order_refusals is None
    assert signals.first_product_write_before_red is None

    projected = tdd_span_fields(signals=signals)
    assert _ORDER_REFUSALS_KEY not in projected
    assert _FIRST_WRITE_BEFORE_RED_KEY not in projected

    journalled = tdd_signal_fields(signals=signals)
    assert journalled[_ORDER_REFUSALS_KEY] is None
    assert journalled[_FIRST_WRITE_BEFORE_RED_KEY] is None


def test_with_no_projection_in_the_environment_the_hook_posts_nothing(
    live_receiver: _LiveReceiver,
) -> None:
    """Outside a configured dispatch the guard stays silent and off the network."""
    span = _load_span()

    assert span.emit_for_decision(decision=_refusal(), environ={}) == span.NO_ENDPOINT

    signals = _gathered(sink=live_receiver.tdd_order)
    assert signals.order_refusals is None
    assert signals.first_product_write_before_red is None
