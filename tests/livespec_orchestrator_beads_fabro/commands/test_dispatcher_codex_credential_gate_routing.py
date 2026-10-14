"""The pre-dispatch wall's Codex credential gate, SCOPED to Codex routing.

`bd-ib-meejjz`. The gate grades the host Codex credential against a floor that
sums every node timeout in the selected graph, and spends one bounded provider
renewal trying to lift it above that floor. Both happened on every dispatch,
including the ones this repository actually runs: since `b7d80ca7` all eight
resolved candidates are `claude-acp/anthropic/...`, so no node would ever reach
the credential being graded. The cost was twofold -- dispatches refused as a
token nobody would use aged out, and every node timeout capped by a floor
derived from a credential that is not in the run.

WHAT IS MEASURED HERE, AND WHY IT IS A LOG RATHER THAN AN EXIT CODE. "Does not
grade" and "makes no renewal request" are claims about INTERACTIONS, and an
end-state assertion cannot carry either: a build that read the credential,
renewed it, graded it and then happened to admit the selection reaches the
identical exit code and the identical empty journal. So the host credential
read, the renewal request and the gate's own clock all append to ONE log, and
the all-Claude case asserts that log is EMPTY.

THE CODEX-ROUTED CONTROL IS NOT OPTIONAL. Without it every assertion below is
equally satisfied by deleting the gate, which is the one outcome this change
must not produce. The control runs the SAME stale credential through the SAME
wall with a routing that names the `codex-acp` agent, and requires the full
sequence -- read, clock, renew, re-read, re-clock -- followed by a refusal.

THE WALL IS THE SURFACE, not the gate primitive, and that is deliberate. The
scoping has to hold for the thing both dispatch paths actually run; a gate that
accepted a routing argument while the wall never resolved one would satisfy a
test aimed at the primitive and change nothing about any dispatch.
"""

from __future__ import annotations

import argparse
import base64
import importlib
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_codex_auth
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_deadline import (
    CredentialLifetimeRequirement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CODEX_FRESHNESS_MARGIN_SECONDS,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_NOW = 1_000_000

# The lifetime the freshness gate requires: run budget plus the documented
# margin. Every credential below is positioned against this one figure.
_REQUIRED_REMAINING = 18_000

_REQUIREMENT = CredentialLifetimeRequirement(
    allowance_seconds=_REQUIRED_REMAINING - CODEX_FRESHNESS_MARGIN_SECONDS,
    margin_seconds=CODEX_FRESHNESS_MARGIN_SECONDS,
    detail="test-resolved requirement",
)

# The bounded renewal request is capped at two minutes, so the clock may move by
# that much between the pre-request reading and the post-request grading.
_RENEWAL_ELAPSED = 120

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_WALL_MODULE = f"{_PACKAGE}._dispatcher_pre_dispatch_wall"
_GATE_MODULE = f"{_PACKAGE}._dispatcher_codex_credential_gate"
_ROUTING_MODULE = f"{_PACKAGE}._dispatcher_codex_routing"


class _RecordingJournal:
    """A journal that keeps what was appended instead of serializing it."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def append(self, *, record: dict[str, Any]) -> None:
        self.records.append(record)


class _StubOutcome:
    """A stand-in `CodexRenewalOutcome` carrying the two fields diagnostics read."""

    def __init__(self, *, answered: bool, detail: str) -> None:
        self.answered = answered
        self.detail = detail


def _auth_json_with_exp(*, exp: int) -> str:
    """Build a host Codex `auth.json` whose access-token JWT carries `exp`."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": f"header.{payload}.sig",
                "refresh_token": "host-refresh-token",
                "id_token": "id-token-value",
                "account_id": "acct-123",
            },
        }
    )


def _work_item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="Scope the Codex credential gate to dispatches that route to Codex",
        description="Three surfaces apply the Codex credential unconditionally.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-14T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _wall_args(*, repo: Path) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(repo / "journal.jsonl"),
        item="bd-ib-meejjz",
        as_json=False,
        skip_ledger_check=True,
        workflow_name=None,
    )


def _stub_wall_siblings(*, monkeypatch: pytest.MonkeyPatch, wall: ModuleType) -> None:
    """Neutralize every wall refusal EXCEPT the credential gate under test.

    Each sibling reaches the forge, the ledger or committed configuration for
    its own reasons, and any one of them answering first would shadow the gate
    this module is about. The resolved requirement is stood in for the same
    reason: it reads the selected workflow's registry entry, run config and
    node-timeout policy off a repository that does not exist here, and a
    workflow-fault deferral would skip the gate for a reason unrelated to
    routing -- which would make every assertion below pass vacuously.
    """
    monkeypatch.setattr(wall, "implementation_pr_override_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "fabro_currency_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "pre_dispatch_criteria_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "proof_assets_refusal_for_items", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "proof_credentials_refusal_for_items", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "credential_wrapper_text", lambda **_kwargs: "")
    monkeypatch.setattr(wall, "selection_credential_requirement", lambda **_kwargs: _REQUIREMENT)


def _stub_credential_source(
    *,
    monkeypatch: pytest.MonkeyPatch,
    log: list[str],
    readings: tuple[str, ...],
) -> None:
    """Stand in the host credential, the renewal and the gate's own clock.

    Every stand-in appends to ONE log, which is what makes "the credential was
    never touched" an observable claim rather than an inference from a return
    value.
    """
    remaining = list(readings)
    gate = importlib.import_module(_GATE_MODULE)

    def _read() -> str:
        log.append("read-credential")
        return remaining.pop(0)

    def _renew() -> _StubOutcome:
        log.append("renew")
        return _StubOutcome(answered=True, detail="the renewal request was answered")

    instants = iter(range(_NOW, _NOW + 10 * _RENEWAL_ELAPSED, _RENEWAL_ELAPSED))

    def _clock() -> int:
        now = next(instants)
        log.append(f"clock:{now}")
        return now

    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", _read)
    monkeypatch.setattr(
        _dispatcher_codex_auth, "renew_host_codex_credential", _renew, raising=False
    )
    monkeypatch.setattr(gate, "wall_clock_epoch", _clock)


def _stub_routing(
    *, monkeypatch: pytest.MonkeyPatch, wall: ModuleType, routes_codex: bool, detail: str
) -> None:
    """Stand this dispatch's resolved routing in at the wall's own seam.

    `raising=False` because the seam does not exist until this change lands; a
    build without it leaves the stand-in unread and grades the credential
    anyway, which is exactly what the assertions below detect.
    """
    routing = importlib.import_module(_ROUTING_MODULE)
    decision = routing.CodexRouting(routes_codex=routes_codex, detail=detail)
    monkeypatch.setattr(
        wall, "codex_routing_for_dispatch", lambda **_kwargs: decision, raising=False
    )


def test_an_all_claude_dispatch_is_neither_graded_nor_refused_on_codex_lifetime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case this work-item exists for: an expired credential nobody will use.

    The credential handed to the wall expired ten seconds ago, so a wall that
    graded it at all would refuse. Admission alone is therefore the proof that
    the remaining lifetime did not decide this dispatch -- and the empty log is
    the proof that the credential was not read in order to reach that answer.
    """
    wall = importlib.import_module(_WALL_MODULE)
    log: list[str] = []
    _stub_wall_siblings(monkeypatch=monkeypatch, wall=wall)
    _stub_credential_source(
        monkeypatch=monkeypatch,
        log=log,
        readings=(_auth_json_with_exp(exp=_NOW - 10), _auth_json_with_exp(exp=_NOW - 10)),
    )
    _stub_routing(
        monkeypatch=monkeypatch,
        wall=wall,
        routes_codex=False,
        detail="no resolved ACP candidate key names the codex-acp agent",
    )

    exit_code = wall.pre_dispatch_wall_exit(
        args=_wall_args(repo=tmp_path),
        repo=tmp_path,
        items=[_work_item(item_id="bd-ib-meejjz")],
        journal=_RecordingJournal(),
    )

    assert exit_code is None
    assert log == []


def test_an_all_claude_dispatch_spends_no_bounded_codex_renewal_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No PROVIDER request is made for a credential this dispatch will not use.

    Separate from the admission assertion above because the renewal is the one
    thing the gate does that is observable OUTSIDE this host: an implementation
    that skipped only the refusal, and renewed first, would admit exactly as
    above while still spending a provider request per dispatch.
    """
    wall = importlib.import_module(_WALL_MODULE)
    log: list[str] = []
    _stub_wall_siblings(monkeypatch=monkeypatch, wall=wall)
    _stub_credential_source(
        monkeypatch=monkeypatch,
        log=log,
        readings=(_auth_json_with_exp(exp=_NOW - 10), _auth_json_with_exp(exp=_NOW - 10)),
    )
    _stub_routing(
        monkeypatch=monkeypatch,
        wall=wall,
        routes_codex=False,
        detail="no resolved ACP candidate key names the codex-acp agent",
    )

    _ = wall.pre_dispatch_wall_exit(
        args=_wall_args(repo=tmp_path),
        repo=tmp_path,
        items=[_work_item(item_id="bd-ib-meejjz")],
        journal=_RecordingJournal(),
    )

    assert "renew" not in log


def test_a_codex_routed_dispatch_is_graded_renewed_and_refused_exactly_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CONTROL: the same stale credential, routed to Codex, still refuses.

    Every assertion in the two cases above is also satisfied by deleting the
    gate, so this is what separates scoping it from retiring it. The sequence is
    asserted in order rather than as a set: the re-read and the SECOND clock
    reading after the renewal are what make the shortfall a measurement of the
    credential as it then stands, and a build that graded the pre-request
    reading would produce the same refusal from stale evidence.
    """
    wall = importlib.import_module(_WALL_MODULE)
    log: list[str] = []
    _stub_wall_siblings(monkeypatch=monkeypatch, wall=wall)
    _stub_credential_source(
        monkeypatch=monkeypatch,
        log=log,
        readings=(_auth_json_with_exp(exp=_NOW - 10), _auth_json_with_exp(exp=_NOW - 10)),
    )
    _stub_routing(
        monkeypatch=monkeypatch,
        wall=wall,
        routes_codex=True,
        detail="resolved ACP candidate keys naming the codex-acp agent: codex-acp/openai/gpt-5.1",
    )

    exit_code = wall.pre_dispatch_wall_exit(
        args=_wall_args(repo=tmp_path),
        repo=tmp_path,
        items=[_work_item(item_id="bd-ib-meejjz")],
        journal=_RecordingJournal(),
    )

    assert exit_code == EXIT_PRECONDITION_ERROR
    assert log == [
        "read-credential",
        f"clock:{_NOW}",
        "renew",
        "read-credential",
        f"clock:{_NOW + _RENEWAL_ELAPSED}",
    ]
    assert "C-mode dispatch refused" in capsys.readouterr().err
