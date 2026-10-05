"""The `plan_close_proof` conformance verdict, armed, over a fixture tenant.

Binds the fourth assertion of `bd-ib-wbdgil` and the plan-record conformance
clause of `SPECIFICATION/contracts.md` (v115): "`plan_close_proof` (error): an
epic whose `plan_slug` names a live or archived directory, whose close timestamp
is later than 2026-10-04 ... carries no `verified` plan Proof of Done record on
its timeline (the archive gate's third leg, made visible after the fact). An epic
closed on or before that date is out of this check's scope and MUST NOT be
reported by it."

WHY THE FIXTURE CARRIES BOTH ARMS AND THREE CONTROLS. "The offender is reported"
is equally consistent with a check that reports every closed plan epic, and "the
pre-ratification epic is silent" with a check that reports nothing at all. So one
tenant carries four closed plan epics: the offender (closed after the date, no
verified record), the pre-ratification epic (closed before it, ALSO with no
verified record — which is the whole point: it is unproved in exactly the way the
offender is, and the only thing separating them is the timestamp), a
post-ratification epic that DOES carry a verified record, and an epic whose
`plan_slug` names no directory at all.

WHY THE LEDGER READ IS INJECTED AND THE DIRECTORIES ARE REAL. A closed beads
record carries the native `closed_at` field, which the in-memory fake's public
write surface does not stamp, so the rows arrive through the narrow read-only
stub the check ships a seam for. Everything else is production code: the arming
gate, the plan-directory walk over a real `tmp_path` tree, the record parse, the
scope rule and the structured report.

WHY THE ARMING GATE IS ASSERTED IN BOTH DIRECTIONS. An unarmed run reporting
nothing is indistinguishable from a fixture that produces nothing, so the
self-skip case re-runs the SAME fixture armed and requires the verdict to appear.
That is the discipline the eleven shipped plan-record verdicts are asserted under.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "plan_close_proof.py"

_RUN_LEVER = "LIVESPEC_RUN_PLAN_RECORD_CONFORMANCE"
_CRED_ENV = "BEADS_DOLT_PASSWORD"

_OFFENDER = "bd-ib-unproved"
_LEGACY = "bd-ib-legacy"
_PROVED = "bd-ib-proved"
_UNANCHORED = "bd-ib-unanchored"
_UNDATED = "bd-ib-undated"

_ASSERTION = "The released build runs in a real operator session."


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("plan_close_proof_under_test", _CHECK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before exec so any dataclass can resolve its own module via
    # `cls.__module__` under Python 3.10's kw_only detection.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


assert _CHECK_PATH.is_file()
_CHECK = _load_check()

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (  # noqa: E402
    PROOF_MODE_HOST_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (  # noqa: E402
    BuildIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (  # noqa: E402
    RecordAssertion,
    render_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (  # noqa: E402
    VERDICT_CAPTURED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (  # noqa: E402
    PLAN_PROOF_RECORD_TITLE,
)


def _epic(*, epic_id: str, slug: str, closed_at: str) -> dict[str, Any]:
    """One closed plan epic, `omitempty`-sparse exactly as `bd` exports one."""
    record: dict[str, Any] = {
        "id": epic_id,
        "issue_type": "epic",
        "status": "closed",
        "metadata": {"plan_slug": slug},
    }
    if closed_at:
        record["closed_at"] = closed_at
    return record


def _record(*, verdict: str, identity: str) -> dict[str, Any]:
    """One plan record comment, rendered through the production renderer."""
    return {
        "text": render_proof_record(
            title=PLAN_PROOF_RECORD_TITLE,
            verdict=verdict,
            identity=f"session {identity}",
            timestamp="2026-10-06T00:00:00Z",
            build=BuildIdentity(release_tag="v0.167.0", installed_build=None, commit="c0ffee1"),
            assertions=(
                RecordAssertion(
                    text=_ASSERTION,
                    proof_mode=PROOF_MODE_HOST_CAPTURED,
                    governing_scenario=None,
                    steps=("Run the released build.",),
                    proof="ok\n",
                    reproduced=None if verdict == VERDICT_CAPTURED else True,
                ),
            ),
        )
    }


class _Tenant:
    """The narrow read-only ledger the check's own seam accepts.

    A stub rather than the in-memory fake because a closed beads record carries
    the native `closed_at` field and the fake's public write surface does not
    stamp one — the shape this check's whole scope rule turns on.
    """

    def __init__(self, *, records: list[dict[str, Any]]) -> None:
        self.records = records
        self.timelines: dict[str, list[dict[str, Any]]] = {}
        self.read: list[str] = []

    def list_issues(self) -> list[dict[str, Any]]:
        return [dict(record) for record in self.records]

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        self.read.append(issue_id)
        return [dict(one) for one in self.timelines.get(issue_id, [])]


def _anchor(*, repo: Path, slug: str, epic_id: str) -> None:
    directory = repo / "plan" / "archive" / slug
    directory.mkdir(parents=True)
    _ = (directory / "associated_work_item_id").write_text(f"{epic_id}\n", encoding="utf-8")


def _tenant(*, repo: Path) -> _Tenant:
    """Four closed plan epics: one offender, one legacy, and three controls."""
    tenant = _Tenant(
        records=[
            _epic(epic_id=_OFFENDER, slug="unproved-plan", closed_at="2026-10-06T10:00:00Z"),
            # Closed ON the ratification date, the boundary the clause excludes.
            _epic(epic_id=_LEGACY, slug="legacy-plan", closed_at="2026-10-04T23:59:59Z"),
            _epic(epic_id=_PROVED, slug="proved-plan", closed_at="2026-10-06T11:00:00Z"),
            # An epic whose slug names NO directory: out of scope by the clause's
            # own wording, and the row every tenant has once an epic is filed
            # through capture-work-item rather than the plan front-end.
            _epic(epic_id=_UNANCHORED, slug="no-such-plan", closed_at="2026-10-06T12:00:00Z"),
        ]
    )
    tenant.timelines[_PROVED] = [
        _record(verdict=VERDICT_CAPTURED, identity="capturing"),
        _record(verdict=VERDICT_VERIFIED, identity="replaying"),
    ]
    # The legacy epic's timeline carries a CAPTURE and no replay, so its silence
    # is about the scope rule rather than about an empty timeline.
    tenant.timelines[_LEGACY] = [_record(verdict=VERDICT_CAPTURED, identity="capturing")]
    for slug, epic_id in (
        ("unproved-plan", _OFFENDER),
        ("legacy-plan", _LEGACY),
        ("proved-plan", _PROVED),
    ):
        _anchor(repo=repo, slug=slug, epic_id=epic_id)
    return tenant


@pytest.fixture(name="armed")
def _armed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[_Tenant]:
    monkeypatch.setenv(_RUN_LEVER, "1")
    monkeypatch.setenv(_CRED_ENV, "fixture-tenant-password")
    monkeypatch.chdir(tmp_path)
    return _tenant(repo=tmp_path)


def _findings(*, captured: str) -> list[dict[str, object]]:
    return [
        {key: line[key] for key in ("check_id", "subject", "verdict")}
        for line in (json.loads(one) for one in captured.splitlines() if one.strip())
        if "verdict" in line
    ]


def _lines(*, captured: str) -> list[dict[str, Any]]:
    return [json.loads(one) for one in captured.splitlines() if one.strip()]


def test_an_epic_closed_after_ratification_without_a_verified_record_is_reported(
    armed: _Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = _CHECK.main(client=armed)

    captured = capsys.readouterr().err
    assert exit_code == 1
    # The WHOLE verdict set, so the offender cannot be one hit among several and
    # the three controls cannot be silently reported alongside it.
    assert _findings(captured=captured) == [
        {"check_id": "plan_close_proof", "subject": _OFFENDER, "verdict": "error"}
    ]
    # The clause requires a remediation sentence, and it must name the act that
    # clears the finding rather than restating the verdict.
    [reported] = [one for one in _lines(captured=captured) if "remediation" in one]
    assert "verified plan Proof of Done record" in reported["remediation"]


def test_the_pre_ratification_epic_is_out_of_scope_and_the_proved_one_is_silent(
    armed: _Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = _CHECK.main(client=armed)

    subjects = {finding["subject"] for finding in _findings(captured=capsys.readouterr().err)}
    assert _LEGACY not in subjects
    assert _PROVED not in subjects
    assert _UNANCHORED not in subjects
    # The epic whose slug names no directory is never even read: the scope filter
    # runs ahead of the timeline read rather than as a filter on its results.
    assert _UNANCHORED not in armed.read


def test_the_armed_only_lever_governs_the_run_and_its_absence_self_skips(
    armed: _Tenant, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(_RUN_LEVER)

    unarmed = _CHECK.main(client=armed)

    unarmed_output = capsys.readouterr().err
    assert unarmed == 0
    assert _findings(captured=unarmed_output) == []
    assert [(one["run_lever"], one["credential"]) for one in _lines(captured=unarmed_output)] == [
        (_RUN_LEVER, _CRED_ENV)
    ]
    # No ledger was read: the gate is ahead of the tenant read, not a filter on it.
    assert armed.read == []

    # The control, on the SAME fixture: armed, the verdict appears. Without it, a
    # tenant that produces nothing would satisfy the assertions above.
    monkeypatch.setenv(_RUN_LEVER, "1")
    rearmed = _CHECK.main(client=armed)

    assert rearmed == 1
    assert _findings(captured=capsys.readouterr().err) == [
        {"check_id": "plan_close_proof", "subject": _OFFENDER, "verdict": "error"}
    ]


def test_an_unreadable_close_instant_is_reported_rather_than_excused(
    armed: _Tenant, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A closed record with no `closed_at` cannot be shown to be out of scope.

    Beads omits a field at its ZERO value and a close instant has none, so a
    closed record missing it is an anomaly rather than a sparse normal row. The
    check reports it: declaring it out of scope would be a gauge that passes when
    it cannot observe its own input.
    """
    armed.records.append(_epic(epic_id=_UNDATED, slug="undated-plan", closed_at=""))
    _anchor(repo=tmp_path, slug="undated-plan", epic_id=_UNDATED)

    exit_code = _CHECK.main(client=armed)

    assert exit_code == 1
    assert {finding["subject"] for finding in _findings(captured=capsys.readouterr().err)} == {
        _OFFENDER,
        _UNDATED,
    }


def test_a_live_plan_directory_is_in_scope_and_an_open_epic_is_not(
    armed: _Tenant, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The clause says "a live or archived directory", and "closed" is the trigger.

    Both halves are asserted on one run because each alone passes against the
    wrong rule: a check keyed only on `plan/archive/` would miss the live-directory
    epic, and one that ignored status would report the open epic beside it.
    """
    live = tmp_path / "plan" / "live-plan"
    live.mkdir(parents=True)
    _ = (live / "associated_work_item_id").write_text("bd-ib-live\n", encoding="utf-8")
    armed.records.append(_epic(epic_id="bd-ib-live", slug="live-plan", closed_at="2026-10-07Z"))
    still_open = tmp_path / "plan" / "open-plan"
    still_open.mkdir(parents=True)
    _ = (still_open / "associated_work_item_id").write_text("bd-ib-open\n", encoding="utf-8")
    armed.records.append(
        {
            "id": "bd-ib-open",
            "issue_type": "epic",
            "status": "active",
            "metadata": {"plan_slug": "open-plan"},
        }
    )

    exit_code = _CHECK.main(client=armed)

    assert exit_code == 1
    assert {finding["subject"] for finding in _findings(captured=capsys.readouterr().err)} == {
        _OFFENDER,
        "bd-ib-live",
    }
