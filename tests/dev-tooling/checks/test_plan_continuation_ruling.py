"""The `plan_continuation_ruling` conformance verdict, armed, over a fixture tenant.

Binds `bd-ib-7iyfo5` and the plan-record conformance clause of
`SPECIFICATION/contracts.md` (v124): "A `plan_continuation_ruling` check (error)
MUST report a `plan-continuation: authorized` ruling lacking any of its
`until:`, `by:`, `directive:` or `recorded-attended: true` lines, or a
`plan-continuation: revoked` ruling lacking its `by:` line".

WHY THE FIXTURE CARRIES CONTROLS ON EVERY SCOPE AXIS. "The offender is reported"
is equally consistent with a check that reports every ruling, and "the closed
epic is silent" with a check that reports nothing. So one tenant carries the
offender (an open live plan with a ruling missing its directive), a complete
ruling on the same kind of plan, the SAME malformed ruling on a closed epic, on an
epic whose plan is archived, and on an epic with no `plan_slug` at all, so only
the scope rule can separate them.

WHY THE ARMING GATE IS ASSERTED IN BOTH DIRECTIONS. An unarmed run reporting
nothing is indistinguishable from a fixture that produces nothing, so the
self-skip case re-runs the SAME fixture armed and requires the verdict to appear.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    PLAN_SCOPE_PREFIX,
    plan_comment_body,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "plan_continuation_ruling.py"

_RUN_LEVER = "LIVESPEC_RUN_PLAN_RECORD_CONFORMANCE"
_CRED_ENV = "BEADS_DOLT_PASSWORD"

_OFFENDER = "bd-ib-offender"
_COMPLETE = "bd-ib-complete"
_CLOSED = "bd-ib-closed"
_ARCHIVED = "bd-ib-archived"
_UNANCHORED = "bd-ib-unanchored"

_MISSING_DIRECTIVE = (
    "plan-continuation: authorized\n"
    "until: archive\n"
    "by: maintainer\n"
    "recorded-attended: true"
)
_COMPLETE_RULING = (
    "plan-continuation: authorized\n"
    "until: archive\n"
    "by: maintainer\n"
    "directive: carry the plan to the archive\n"
    "recorded-attended: true"
)


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "plan_continuation_ruling_under_test", _CHECK_PATH
    )
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


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _epic(*, epic_id: str, slug: str | None, ruling: str, closed: bool = False) -> None:
    metadata: dict[str, object] = {"rank": "a1"}
    if slug is not None:
        metadata["plan_slug"] = slug
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id=epic_id,
            issue_type="epic",
            title="plan",
            description="plan anchor",
            assignee=None,
            created_at="2026-10-10T00:00:00Z",
            metadata=metadata,
            labels=["origin:freeform"],
        )
    )
    _fake().add_comment(
        issue_id=epic_id,
        body=plan_comment_body(
            prefix=PLAN_SCOPE_PREFIX,
            author="maintainer",
            now="2026-10-10T12:00:00Z",
            body=ruling,
        ),
    )
    if closed:
        _fake().close_issue(issue_id=epic_id, reason="done")


@pytest.fixture
def tenant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    reset_fake_singleton()
    for slug in ("offender-plan", "complete-plan", "closed-plan"):
        (tmp_path / "plan" / slug).mkdir(parents=True)
    (tmp_path / "plan" / "archive" / "archived-plan").mkdir(parents=True)
    _epic(epic_id=_OFFENDER, slug="offender-plan", ruling=_MISSING_DIRECTIVE)
    _epic(epic_id=_COMPLETE, slug="complete-plan", ruling=_COMPLETE_RULING)
    _epic(epic_id=_CLOSED, slug="closed-plan", ruling=_MISSING_DIRECTIVE, closed=True)
    _epic(epic_id=_ARCHIVED, slug="archived-plan", ruling=_MISSING_DIRECTIVE)
    _epic(epic_id=_UNANCHORED, slug=None, ruling=_MISSING_DIRECTIVE)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _arm(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_RUN_LEVER, "1")
    monkeypatch.setenv(_CRED_ENV, "probe-only-not-a-secret")


def _errors(*, stderr: str) -> list[dict[str, object]]:
    rows = [json.loads(line) for line in stderr.splitlines() if line.startswith("{")]
    return [row for row in rows if row.get("level") == "error"]


def test_only_the_open_live_plans_malformed_ruling_is_reported(
    tenant: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = tenant
    _arm(monkeypatch=monkeypatch)
    assert _CHECK.main(config=_config()) == 1
    errors = _errors(stderr=capsys.readouterr().err)
    assert [row["subject"] for row in errors] == [_OFFENDER]
    assert errors[0]["check_id"] == "plan_continuation_ruling"
    assert errors[0]["missing"] == ["directive:"]


def test_an_unarmed_run_skips_and_the_same_fixture_armed_reports(
    tenant: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = tenant
    monkeypatch.delenv(_RUN_LEVER, raising=False)
    assert _CHECK.main(config=_config()) == 0
    assert _errors(stderr=capsys.readouterr().err) == []
    _arm(monkeypatch=monkeypatch)
    assert _CHECK.main(config=_config()) == 1


def test_a_tenant_whose_rulings_are_complete_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reset_fake_singleton()
    (tmp_path / "plan" / "complete-plan").mkdir(parents=True)
    _epic(epic_id=_COMPLETE, slug="complete-plan", ruling=_COMPLETE_RULING)
    monkeypatch.chdir(tmp_path)
    _arm(monkeypatch=monkeypatch)
    assert _CHECK.main(config=_config()) == 0
    assert _errors(stderr=capsys.readouterr().err) == []


def test_a_repository_without_a_plan_tree_has_no_live_slugs(tmp_path: Path) -> None:
    assert _CHECK.live_plan_slugs(repo_root=tmp_path) == frozenset()


def test_a_record_whose_metadata_is_not_an_object_is_out_of_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reset_fake_singleton()
    (tmp_path / "plan" / "offender-plan").mkdir(parents=True)
    monkeypatch.setattr(
        FakeBeadsClient,
        "list_issues",
        lambda _self: [{"id": _OFFENDER, "status": "active", "metadata": "not-an-object"}],
    )
    monkeypatch.chdir(tmp_path)
    _arm(monkeypatch=monkeypatch)
    assert _CHECK.main(config=_config()) == 0
