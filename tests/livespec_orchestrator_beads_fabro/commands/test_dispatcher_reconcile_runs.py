"""Tests for the whole-inventory reconciliation pass over every factory."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_runs as reconcile
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_reconcile_runs_inputs as inputs_module,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_body import (
    PRESERVE_POINTER_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_export import (
    ExportOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroTarget
from livespec_orchestrator_beads_fabro.commands._run_attribution import (
    GOAL_TEXT_ONLY,
    RunAttribution,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_HP_DEV_TOKEN_VALUE = "hp-fixture-dev-token"
_VPS_DEV_TOKEN_VALUE = "vps-fixture-dev-token"
_HP = FactoryTarget(name="hp", server="https://hp.example:32276", dev_token=_HP_DEV_TOKEN_VALUE)
_VPS = FactoryTarget(name="vps", server="https://vps.example:32276", dev_token=_VPS_DEV_TOKEN_VALUE)
# The factory an operator host has NOT exported a dev token for, and which no
# `~/.fabro/auth.json` entry covers either: every HTTP route it offers is 401.
_UNAUTHENTICATED = FactoryTarget(name="hp", server="https://hp.example:32276", dev_token=None)
_QUESTIONS_BODY = json.dumps(
    {
        "data": [
            {
                "id": "q-1",
                "options": [{"key": "A", "label": "[A] Abandon (leave open for triage)"}],
                "stage": "escalate",
            }
        ],
        "meta": {"has_more": False},
    }
)


@dataclass(kw_only=True)
class _Runner:
    """One fake `fabro` CLI, keyed by the server the argv names."""

    ps_by_server: dict[str, str] = field(default_factory=dict)
    inspect_by_run: dict[str, str] = field(default_factory=dict)
    failing_servers: frozenset[str] = frozenset()
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        server = argv[argv.index("--server") + 1] if "--server" in argv else ""
        if argv[1] == "ps":
            if server in self.failing_servers:
                return CommandResult(exit_code=7, stdout="", stderr="unreachable")
            return CommandResult(exit_code=0, stdout=self.ps_by_server.get(server, "[]"), stderr="")
        if argv[1] == "inspect":
            return CommandResult(
                exit_code=0, stdout=self.inspect_by_run.get(argv[2], "[]"), stderr=""
            )
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Transport:
    calls: list[str] = field(default_factory=list)

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        _ = (headers, body, timeout_seconds)
        self.calls.append(f"{method} {url}")
        answered = _QUESTIONS_BODY if url.endswith("/questions") else "{}"
        return FabroHttpResult(
            status=200,
            body=answered,
            error=None,
            payload=None,
            succeeded=True,
        )


@dataclass(kw_only=True)
class _RefusingTransport:
    """What an unauthenticated port meets on every route: 401, no body."""

    calls: list[str] = field(default_factory=list)

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        _ = (body, timeout_seconds)
        self.calls.append(f"{method} {url}")
        assert "Authorization" not in headers
        return FabroHttpResult(status=401, body="", error=None, payload=None, succeeded=False)


@dataclass(kw_only=True)
class _Journal:
    written: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.written.append(record)


@dataclass(kw_only=True)
class _Ledger:
    """A ledger fake that CAN record a write, so "no write" is a real finding.

    The mutating verbs are here deliberately even though the reconciler's seam
    is typed as comments-only: an assertion against a fake that could not have
    recorded a status write proves nothing about whether one was attempted.
    """

    comments: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    verbs: list[str] = field(default_factory=list)

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        self.verbs.append(f"list_comments:{issue_id}")
        return list(self.comments.get(issue_id, []))

    def add_comment(self, *, issue_id: str, body: str) -> None:
        self.verbs.append(f"add_comment:{issue_id}")
        self.comments.setdefault(issue_id, []).append({"id": f"c-{issue_id}", "text": body})

    def update_issue(self, *, issue_id: str, **fields: object) -> None:
        _ = fields
        self.verbs.append(f"update_issue:{issue_id}")

    def close_issue(self, *, issue_id: str, reason: str | None) -> None:
        _ = reason
        self.verbs.append(f"close_issue:{issue_id}")


def test_a_closed_item_run_is_exported_then_terminated_and_journaled(tmp_path: Path) -> None:
    runner = _Runner(ps_by_server={_HP.server or "": _ps(run_id="01ORPHAN", kind="blocked")})
    transport = _Transport()
    journal = _Journal()
    ledger = _Ledger()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            transport=transport,
            journal=journal,
            ledger=ledger,
            items=[_item(id="bd-ib-orphan", status="closed")],
        ),
        factories=[_HP],
    )

    assert [
        (run.run_id, run.orphan_reason, run.termination_route) for run in summary.reconciled
    ] == [("01ORPHAN", "item-not-active", "questions-answer")]
    # The export precedes the termination: the comment verbs are recorded
    # before any HTTP verb reaches the factory.
    assert ledger.verbs[0] == "list_comments:bd-ib-orphan"
    assert "add_comment:bd-ib-orphan" in ledger.verbs
    assert transport.calls[0].startswith(
        "GET https://hp.example:32276/api/v1/runs/01ORPHAN/questions"
    )
    assert [record["stage"] for record in journal.written] == ["orphan-run-reconciled"]
    assert journal.written[0]["export_comment_id"] == "c-bd-ib-orphan"


def test_an_unresolved_credential_is_journaled_before_the_rm_fallback(tmp_path: Path) -> None:
    runner = _Runner(
        ps_by_server={_UNAUTHENTICATED.server or "": _ps(run_id="01ORPHAN", kind="blocked")}
    )
    transport = _RefusingTransport()
    journal = _Journal()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            transport=transport,
            journal=journal,
            ledger=_Ledger(),
            items=[_item(id="bd-ib-orphan", status="closed")],
        ),
        factories=[_UNAUTHENTICATED],
    )

    assert [run.termination_route for run in summary.reconciled] == ["rm-force"]
    # The unauthenticated record is written BEFORE the reconciled one, so the
    # degrade is legible as this host carrying no credential rather than as the
    # factory having refused each route on its merits.
    assert [record["stage"] for record in journal.written] == [
        "terminate-route-unauthenticated",
        "orphan-run-reconciled",
        "orphan-run-reconcile-rm-fallback",
    ]
    assert journal.written[0]["run_id"] == "01ORPHAN"
    assert "~/.fabro/auth.json" in str(journal.written[0]["detail"])


def test_an_actual_termination_emits_queryable_ownership_and_cancellation_spans(
    tmp_path: Path,
) -> None:
    spans_path = tmp_path / "reconcile-spans.jsonl"
    runner = _Runner(ps_by_server={_HP.server or "": _ps(run_id="01ORPHAN", kind="running")})

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            transport=_Transport(),
            journal=_Journal(),
            ledger=_Ledger(),
            items=[_item(id="bd-ib-orphan", status="closed")],
            telemetry_spans_path=spans_path,
            cancelling_actor="timer:reconcile-runs",
        ),
        factories=[_HP],
    )

    assert summary.reconciled[0].termination_succeeded is True
    spans = _spans(path=spans_path)
    assert [span["name"] for span in spans] == [
        "dispatcher.reconcile-runs-termination",
        "dispatcher.calibration",
    ]
    termination = _span_attrs(span=spans[0])
    assert termination == {
        "fabro.run_id": "01ORPHAN",
        "work.item.id": "bd-ib-orphan",
        "livespec.tenant": "bd-ib",
        "reconcile.orphan_reason": "item-not-active",
        "fabro.status.kind": "running",
        "reconcile.termination_route": "cancel",
        "reconcile.termination_succeeded": True,
        "reconcile.attribution_source": "journal",
        "reconcile.cancelling_actor": "timer:reconcile-runs",
    }
    calibration = _span_attrs(span=spans[1])
    assert calibration["work.item.id"] == "bd-ib-orphan"
    assert calibration["fabro.failure.category"] == "canceled"
    assert calibration["reconcile.cancelling_actor"] == "timer:reconcile-runs"


def test_a_failing_factory_is_journaled_and_the_other_still_reconciles(tmp_path: Path) -> None:
    runner = _Runner(
        ps_by_server={_VPS.server or "": _ps(run_id="01ORPHAN", kind="running")},
        failing_servers=frozenset({_HP.server or ""}),
    )
    journal = _Journal()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            transport=_Transport(),
            journal=journal,
            ledger=_Ledger(),
            items=[_item(id="bd-ib-orphan", status="done")],
        ),
        factories=[_HP, _VPS],
    )

    assert [(error.factory_name, error.reason) for error in summary.errors] == [
        ("hp", "factory-ps-failed")
    ]
    assert [(run.factory_name, run.termination_route) for run in summary.reconciled] == [
        ("vps", "cancel")
    ]
    assert [record["stage"] for record in journal.written] == [
        "orphan-run-reconciled",
        "orphan-run-reconcile-error",
    ]


def test_a_factory_without_a_server_url_is_refused_rather_than_surveyed(tmp_path: Path) -> None:
    runner = _Runner()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            transport=_Transport(),
            journal=_Journal(),
            ledger=_Ledger(),
            items=[],
        ),
        factories=[FactoryTarget(name="implicit", server=None, dev_token=None)],
    )

    assert runner.calls == []
    assert [error.reason for error in summary.errors] == ["factory-server-url-missing"]


def test_no_bare_fabro_target_is_ever_constructed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[FabroTarget] = []

    def _record(**kwargs: object) -> FabroTarget:
        target = FabroTarget(**kwargs)  # pyright: ignore[reportArgumentType]
        built.append(target)
        return target

    # The port is opened by the seams module, which is where the target is
    # built; patching the survey module would patch a name that is not there.
    monkeypatch.setattr(inputs_module, "FabroTarget", _record)

    _ = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=_Runner(),
            transport=_Transport(),
            journal=_Journal(),
            ledger=_Ledger(),
            items=[],
        ),
        factories=[_HP, _VPS, FactoryTarget(name="implicit", server=None, dev_token=None)],
    )

    assert [target.server_url for target in built] == [_HP.server, _VPS.server]
    assert all(target.server_url is not None for target in built)


def test_a_dry_run_emits_the_orphan_set_and_mutates_nothing(tmp_path: Path) -> None:
    runner = _Runner(ps_by_server={_HP.server or "": _ps(run_id="01ORPHAN", kind="blocked")})
    transport = _Transport()
    journal = _Journal()
    ledger = _Ledger()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            transport=transport,
            journal=journal,
            ledger=ledger,
            items=[_item(id="bd-ib-orphan", status="closed")],
        ),
        factories=[_HP, FactoryTarget(name="implicit", server=None, dev_token=None)],
        dry_run=True,
    )

    assert [run.run_id for run in summary.reconciled] == ["01ORPHAN"]
    assert summary.dry_run is True
    assert journal.written == []
    assert ledger.verbs == []
    assert transport.calls == []
    assert [call[1] for call in runner.calls] == ["ps"]


def test_an_item_missing_orphan_preserves_its_pointer_in_the_journal(tmp_path: Path) -> None:
    runner = _Runner(
        ps_by_server={
            _HP.server or "": _ps(run_id="01GONE", kind="starting", work_item_id="bd-ib-gone")
        }
    )
    journal = _Journal()
    ledger = _Ledger()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            transport=_Transport(),
            journal=journal,
            ledger=ledger,
            items=[],
        ),
        factories=[_HP],
    )

    assert [run.orphan_reason for run in summary.reconciled] == ["item-missing"]
    assert [record["stage"] for record in journal.written] == [
        "orphan-run-reconcile-export",
        "orphan-run-reconciled",
    ]
    body = journal.written[0]["pointer_body"]
    assert isinstance(body, str)
    assert body.startswith(PRESERVE_POINTER_MARKER)
    assert ledger.verbs == []


@pytest.mark.parametrize(
    ("tenant_prefix", "foreign_work_item_id"),
    [
        ("livespec", "livespec-console-beads-fabro-x.1"),
        ("bd-ib", "livespec-console-beads-fabro-x.1"),
    ],
)
def test_goal_text_alone_never_authorizes_termination_of_a_foreign_run(
    tmp_path: Path,
    tenant_prefix: str,
    foreign_work_item_id: str,
) -> None:
    runner = _Runner(
        ps_by_server={
            _HP.server or "": _ps(
                run_id="01FOREIGN",
                kind="running",
                work_item_id=foreign_work_item_id,
            )
        }
    )
    transport = _Transport()
    journal = _Journal()
    ledger = _Ledger()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            transport=transport,
            journal=journal,
            ledger=ledger,
            items=[],
            id_prefix=tenant_prefix,
            journal_text=json.dumps(
                {
                    "stage": "orphan-run-reconciled",
                    "run_id": "01FOREIGN",
                    "work_item_id": foreign_work_item_id,
                }
            ),
        ),
        factories=[_HP],
    )

    assert summary.reconciled == ()
    assert summary.errors == ()
    assert journal.written == []
    assert ledger.verbs == []
    assert transport.calls == []
    assert [call[1] for call in runner.calls] == ["ps"]


def test_an_unverified_export_leaves_the_run_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        reconcile,
        "export_orphan_reference",
        lambda **_: ExportOutcome(
            exported=False,
            comment_id=None,
            journal_body=None,
            detail="read-back failed",
        ),
    )
    runner = _Runner(ps_by_server={_HP.server or "": _ps(run_id="01ORPHAN", kind="blocked")})
    transport = _Transport()
    journal = _Journal()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            transport=transport,
            journal=journal,
            ledger=_Ledger(),
            items=[_item(id="bd-ib-orphan", status="closed")],
        ),
        factories=[_HP],
    )

    assert summary.reconciled == ()
    assert [error.reason for error in summary.errors] == ["export-not-verified"]
    assert transport.calls == []
    assert [call[1] for call in runner.calls] == ["ps"]
    assert [record["stage"] for record in journal.written] == ["orphan-run-reconcile-error"]


def test_the_ledger_attribution_reaches_the_join_and_spares_a_stamped_run(tmp_path: Path) -> None:
    """`ReconcileInputs.attribution` is threaded to the join, not merely stored.

    The run's goal text names `bd-ib-orphan`, which is `closed` — the shape the
    regex-only join reconciles. The ledger stamps the same run onto the ACTIVE
    `bd-ib-live`, so nothing may be terminated.
    """
    runner = _Runner(ps_by_server={_HP.server or "": _ps(run_id="01ORPHAN", kind="running")})
    journal = _Journal()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            transport=_Transport(),
            journal=journal,
            ledger=_Ledger(),
            items=[
                _item(id="bd-ib-orphan", status="closed"),
                _item(id="bd-ib-live", status="active"),
            ],
            attribution=RunAttribution(metadata_run_ids={"01ORPHAN": "bd-ib-live"}),
        ),
        factories=[_HP],
    )

    assert summary.reconciled == ()
    assert summary.errors == ()
    assert journal.written == []


def test_the_reconciler_is_handed_no_ledger_status_write_seam(tmp_path: Path) -> None:
    ledger = _Ledger()

    _ = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=_Runner(ps_by_server={_HP.server or "": _ps(run_id="01ORPHAN", kind="blocked")}),
            transport=_Transport(),
            journal=_Journal(),
            ledger=ledger,
            items=[_item(id="bd-ib-orphan", status="closed")],
        ),
        factories=[_HP],
    )

    assert {verb.split(":", maxsplit=1)[0] for verb in ledger.verbs} == {
        "list_comments",
        "add_comment",
    }


def test_a_targeted_pass_leaves_every_other_items_orphan_alone(tmp_path: Path) -> None:
    """`only_work_item_id` narrows what is ACTED ON, not what is classified."""
    runner = _Runner(
        ps_by_server={
            _HP.server or "": json.dumps(
                [
                    _run(run_id="01MINE", kind="blocked", work_item_id="bd-ib-mine"),
                    _run(run_id="01THEIRS", kind="blocked", work_item_id="bd-ib-theirs"),
                ]
            )
        }
    )

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            transport=_Transport(),
            journal=_Journal(),
            ledger=_Ledger(),
            items=[
                _item(id="bd-ib-mine", status="closed"),
                _item(id="bd-ib-theirs", status="closed"),
            ],
            only_work_item_id="bd-ib-mine",
        ),
        factories=[_HP],
    )

    assert [run.run_id for run in summary.reconciled] == ["01MINE"]
    assert summary.errors == ()


def test_the_ledger_fake_would_record_a_status_write_if_one_were_attempted() -> None:
    """The control for the untouched-item assertions below.

    Asserting "no status write happened" against a fake that has no way to
    record one proves nothing, so this establishes the instrument can return a
    hit before the next test reads a miss as a finding.
    """
    ledger = _Ledger()

    ledger.update_issue(issue_id="bd-ib-parked", status="ready", labels=["needs-human"])
    ledger.close_issue(issue_id="bd-ib-parked", reason="done")

    assert ledger.verbs == ["update_issue:bd-ib-parked", "close_issue:bd-ib-parked"]


def test_a_parked_run_past_grace_is_abandoned_and_its_item_is_untouched(tmp_path: Path) -> None:
    runner = _Runner(
        ps_by_server={
            _HP.server or "": _ps(run_id="01PARKED", kind="blocked", work_item_id="bd-ib-parked")
        },
        inspect_by_run={"01PARKED": json.dumps([{"status": {"kind": "blocked"}, "blocked_at": 0}])},
    )
    transport = _Transport()
    journal = _Journal()
    ledger = _Ledger()
    item = _item(id="bd-ib-parked", status="blocked", blocked_reason="needs-human")
    before = asdict(item)

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            transport=transport,
            journal=journal,
            ledger=ledger,
            items=[item],
            now_epoch=1801.0,
        ),
        factories=[_HP],
    )

    assert [
        (run.run_id, run.orphan_reason, run.termination_route) for run in summary.reconciled
    ] == [("01PARKED", "blocked-past-grace", "questions-answer")]
    assert summary.held == ()
    # The export is read back before the run is touched, and the route is the
    # interview Abandon answer rather than cancel.
    assert ledger.verbs[0] == "list_comments:bd-ib-parked"
    assert transport.calls[0].startswith(
        "GET https://hp.example:32276/api/v1/runs/01PARKED/questions"
    )
    assert any(call.startswith("POST") and "/answer" in call for call in transport.calls)
    assert not any("/cancel" in call for call in transport.calls)
    # The item is left exactly as it was, and no write verb was even reached.
    assert asdict(item) == before
    assert (item.status, item.blocked_reason) == ("blocked", "needs-human")
    assert {verb.split(":", maxsplit=1)[0] for verb in ledger.verbs} == {
        "list_comments",
        "add_comment",
    }
    assert [record["stage"] for record in journal.written] == ["orphan-run-reconciled"]
    assert (journal.written[0]["parked_seconds"], journal.written[0]["grace_seconds"]) == (
        1801.0,
        1800,
    )


def test_a_parked_run_inside_grace_is_projected_and_never_terminated(tmp_path: Path) -> None:
    runner = _Runner(
        ps_by_server={
            _HP.server or "": _ps(run_id="01YOUNG", kind="blocked", work_item_id="bd-ib-parked")
        },
        inspect_by_run={"01YOUNG": json.dumps([{"blocked_at": "1970-01-01T00:00:00Z"}])},
    )
    transport = _Transport()
    journal = _Journal()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            transport=transport,
            journal=journal,
            ledger=_Ledger(),
            items=[_item(id="bd-ib-parked", status="blocked", blocked_reason="needs-human")],
            now_epoch=300.0,
        ),
        factories=[_HP],
    )

    assert summary.reconciled == ()
    assert [(run.run_id, run.hold_reason, run.seconds_remaining) for run in summary.held] == [
        ("01YOUNG", "blocked-within-grace", 1500.0)
    ]
    assert transport.calls == []
    assert journal.written == []
    assert [call[1] for call in runner.calls] == ["ps", "inspect"]


def test_a_parked_run_whose_park_cannot_be_measured_is_not_terminated(tmp_path: Path) -> None:
    runner = _Runner(
        ps_by_server={
            _HP.server or "": _ps(run_id="01OPAQUE", kind="blocked", work_item_id="bd-ib-parked")
        },
        inspect_by_run={"01OPAQUE": json.dumps([{"status": {"kind": "blocked"}}])},
    )
    transport = _Transport()

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            transport=transport,
            journal=_Journal(),
            ledger=_Ledger(),
            items=[_item(id="bd-ib-parked", status="active")],
            now_epoch=1_000_000.0,
        ),
        factories=[_HP],
    )

    assert summary.reconciled == ()
    assert [(run.run_id, run.hold_reason, run.parked_seconds) for run in summary.held] == [
        ("01OPAQUE", "blocked-park-unmeasured", None)
    ]
    assert transport.calls == []


def test_a_zero_grace_inspects_nothing_and_holds_nothing(tmp_path: Path) -> None:
    runner = _Runner(
        ps_by_server={
            _HP.server or "": _ps(run_id="01PARKED", kind="blocked", work_item_id="bd-ib-parked")
        }
    )

    summary = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            transport=_Transport(),
            journal=_Journal(),
            ledger=_Ledger(),
            items=[_item(id="bd-ib-parked", status="blocked", blocked_reason="needs-human")],
            grace_seconds=0,
        ),
        factories=[_HP],
    )

    assert summary.held == ()
    # With the arm off, the moot-question reading stands and terminates at once.
    assert [run.orphan_reason for run in summary.reconciled] == ["item-not-active"]
    # No `inspect` was spent: a disabled arm measures nothing.
    assert [call[1] for call in runner.calls] == ["ps", "dump"]


def _inputs(
    *,
    tmp_path: Path,
    runner: _Runner,
    transport: _Transport,
    journal: _Journal,
    ledger: _Ledger,
    items: list[WorkItem],
    id_prefix: str = "bd-ib",
    journal_text: str | None = None,
    telemetry_spans_path: Path | None = None,
    cancelling_actor: str | None = None,
    only_work_item_id: str | None = None,
    attribution: RunAttribution = GOAL_TEXT_ONLY,
    now_epoch: float | None = None,
    grace_seconds: int = 1800,
) -> ReconcileInputs:
    return ReconcileInputs(
        repo=tmp_path,
        fabro_bin="fabro",
        id_prefix=id_prefix,
        items=items,
        only_work_item_id=only_work_item_id,
        journaled=journaled_runs(
            text=_fixture_journal_text(runner=runner) if journal_text is None else journal_text
        ),
        runner=runner,
        journal=journal,
        ledger=ledger,
        attribution=attribution,
        http=transport,
        blocked_run_grace_seconds=grace_seconds,
        now_epoch=now_epoch,
        telemetry_spans_path=telemetry_spans_path,
        cancelling_actor=cancelling_actor,
    )


def _fixture_journal_text(*, runner: _Runner) -> str:
    records: list[str] = []
    for raw_runs in runner.ps_by_server.values():
        for run in json.loads(raw_runs):
            goal = str(run["goal"])
            work_item_id = goal.splitlines()[0].removeprefix("Work-item: ")
            records.append(
                json.dumps(
                    {
                        "stage": "dispatch-run-stamp",
                        "run_id": run["run_id"],
                        "work_item_id": work_item_id,
                    }
                )
            )
    return "\n".join(records)


def _spans(*, path: Path) -> list[dict[str, Any]]:
    request = json.loads(path.read_text(encoding="utf-8"))
    return request["resourceSpans"][0]["scopeSpans"][0]["spans"]


def _span_attrs(*, span: dict[str, Any]) -> dict[str, object]:
    attrs: dict[str, object] = {}
    for attribute in span["attributes"]:
        encoded = attribute["value"]
        value = next(iter(encoded.values()))
        attrs[attribute["key"]] = value
    return attrs


def _ps(*, run_id: str, kind: str, work_item_id: str = "bd-ib-orphan") -> str:
    return json.dumps([_run(run_id=run_id, kind=kind, work_item_id=work_item_id)])


def _run(*, run_id: str, kind: str, work_item_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "goal": f"Work-item: {work_item_id}\nRepo: /tmp/repo",
        "status": {"kind": kind},
    }


def _item(*, id: str, status: str, blocked_reason: str | None = None) -> WorkItem:
    return WorkItem(
        id=id,
        type="task",
        status=status,
        blocked_reason=blocked_reason,
        title=id,
        description=id,
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-08-30T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
