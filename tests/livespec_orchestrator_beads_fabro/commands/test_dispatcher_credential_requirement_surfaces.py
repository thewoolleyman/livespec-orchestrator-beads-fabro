"""Status, manual renewal and the gate all grade against ONE resolved requirement.

WHAT THIS BINDS. The second assertion of `bd-ib-yx7pdm`: credential status and
manual-renewal eligibility must report the SAME effective requirement dispatch
uses for the selected workflow. Before the requirement was resolved per
dispatch, each of these three surfaces carried its own figure, and the two
diverging IS the defect: the manual-renewal guard sat at 360 seconds while the
dispatch gate demanded 18000, so every lifetime between them refused dispatch
while the sanctioned refresh reported "not due" and told a human to run `codex
login`. Measured 2026-10-04 at a remaining lifetime of 13517 seconds.

WHY EACH SURFACE IS ASSERTED AGAINST THE PRODUCTION DERIVATION rather than a
literal. A literal would keep agreeing with itself while the requirement moved
underneath it, which is exactly the failure the resolver exists to retire. Each
case below resolves the figure through `operator_credential_requirement` for the
same repository the surface reads, so "the two agree" is an observation rather
than a consequence of the test handing both the same constant.

THE REFUSAL HALF IS PAIRED WITH THE POSITIVE HALF IN EVERY CASE, because a
surface that refused everything would satisfy the refusal assertions alone, and
a surface that never refused would satisfy the positive ones alone. The DoD's
own note is explicit about this: an implementation that always refuses, or
always reports an unknown bound, can satisfy an only-when predicate vacuously.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_codex_auth
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth import (
    run_codex_cred_status,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_cred_refresh_command import (
    run_codex_cred_refresh_with,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_credential_gate import (
    CODEX_CREDENTIAL_REQUIREMENT_STAGE,
    codex_credential_refusal_for_items,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_freshness import (
    graded_freshness,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_requirement import (
    operator_credential_requirement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CODEX_FRESHNESS_MARGIN_SECONDS,
)

_NOW = 1_700_000_000

_WORKFLOW_TOML = """_version = 1

[workflow]
graph = "workflow.fabro"

[run.checkpoint]
commit_timeout = "10m"
"""

_GRAPH = """digraph Fixture {
    graph [
        default_max_retries=0
        stall_timeout="7200s"
    ]

    start [shape=Mdiamond]
    exit  [shape=Msquare]

    work [
        timeout="1800s"
    ]

    start -> work
    work -> exit
}
"""

# A run config declaring no [workflow] graph: nothing to derive an allowance
# from, so every surface below must refuse rather than invent one.
_UNRESOLVABLE_TOML = '_version = 1\n\n[run]\ngoal = "fixture"\n'


def _repo(*, tmp_path: Path, workflow_toml: str = _WORKFLOW_TOML) -> Path:
    workflow_dir = tmp_path / ".fabro/workflows/implement-work-item"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    _ = (workflow_dir / "workflow.toml").write_text(workflow_toml, encoding="utf-8")
    _ = (workflow_dir / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": {}}}), encoding="utf-8"
    )
    return tmp_path


def _auth_json(*, exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {"access_token": f"header.{payload}.sig", "refresh_token": "r"},
        }
    )


def _required_seconds(*, repo: Path) -> int:
    """The figure DISPATCH grades against, read off the production derivation."""
    requirement = operator_credential_requirement(repo=repo)
    assert not isinstance(requirement, str), requirement
    assert hasattr(requirement, "required_seconds"), requirement
    return requirement.required_seconds


class _AppServerRunner:
    """Records the app-server conversation the refresher hands it."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], Path, list[str], float]] = []

    def run(
        self, *, argv: list[str], cwd: Path, request_lines: list[str], timeout_seconds: float
    ) -> CommandResult:
        # The WHOLE conversation is recorded, not just the argv: the cases below
        # assert the list is EMPTY, and a recorder that dropped most of each call
        # would make "no request was spent" a weaker claim than it reads as.
        self.calls.append((argv, cwd, request_lines, timeout_seconds))
        return CommandResult(exit_code=0, stdout="{}\n", stderr="")


def test_status_reports_the_same_requirement_dispatch_grades_against(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The status command's guard IS the dispatch requirement, not its own number.

    Read out of the emitted payload rather than off the resolver, because the
    claim is about what an OPERATOR is told: a status whose internal figure
    agreed with dispatch while printing something else would satisfy a
    resolver-level assertion and still mislead the human reading it at 3am.
    """
    repo = _repo(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        _dispatcher_codex_auth, "read_host_codex_auth", lambda: _auth_json(exp=_NOW + 10)
    )
    monkeypatch.setattr(_dispatcher_codex_auth.time, "time", lambda: _NOW)

    exit_code = run_codex_cred_status(
        args=argparse.Namespace(as_json=True, observe_identity_state=None)
    )

    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert exit_code in (0, 1)
    assert str(_required_seconds(repo=repo)) in payload["message"]


def test_status_refuses_when_the_requirement_cannot_be_resolved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A status that cannot state its own requirement refuses instead of guessing.

    The control for the case above: without it, "status printed the dispatch
    figure" is equally consistent with a surface that prints whatever it
    resolved and never checks that it resolved anything.
    """
    repo = _repo(tmp_path=tmp_path, workflow_toml=_UNRESOLVABLE_TOML)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        _dispatcher_codex_auth, "read_host_codex_auth", lambda: _auth_json(exp=_NOW + 10)
    )

    exit_code = run_codex_cred_status(
        args=argparse.Namespace(as_json=True, observe_identity_state=None)
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "declares no [workflow] graph" in captured.err
    # No status payload at all: a refusal must not also emit a `refresh_due`
    # computed from a requirement nobody established.
    assert captured.out == ""


def test_manual_renewal_eligibility_derives_from_the_same_requirement(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The renewal guard is the dispatch requirement, so the dead zone is empty.

    A credential one second BELOW the dispatch requirement must be renewal-due.
    That is the whole point of deriving the guard: every lifetime that refuses
    dispatch is a lifetime the sanctioned refresh is willing to act on, so the
    interval where dispatch refused and the refresher declined is empty by
    construction rather than by two numbers happening to line up.
    """
    repo = _repo(tmp_path=tmp_path)
    required = _required_seconds(repo=repo)
    runner = _AppServerRunner()

    exit_code = run_codex_cred_refresh_with(
        args=argparse.Namespace(as_json=True, dry_run=True),
        cwd=lambda: repo,
        now_epoch=lambda: _NOW,
        read_host_codex_auth=lambda: _auth_json(exp=_NOW + required - 1),
        runner_factory=lambda: runner,
    )

    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["would_invoke_codex"] is True
    assert str(required) in payload["before"]["message"]


def test_manual_renewal_declines_above_the_same_requirement(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One second ABOVE the requirement is not due, so the timer costs nothing.

    Paired with the case above across the SAME boundary: the two differ by two
    seconds of credential lifetime and nothing else, which is what makes the
    boundary the derived requirement rather than some other threshold.
    """
    repo = _repo(tmp_path=tmp_path)
    required = _required_seconds(repo=repo)
    runner = _AppServerRunner()

    exit_code = run_codex_cred_refresh_with(
        args=argparse.Namespace(as_json=True, dry_run=False),
        cwd=lambda: repo,
        now_epoch=lambda: _NOW,
        read_host_codex_auth=lambda: _auth_json(exp=_NOW + required + 1),
        runner_factory=lambda: runner,
    )

    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["outcome"] == "noop-not-due"
    assert payload["would_invoke_codex"] is False
    # And no provider request was spent proving it.
    assert runner.calls == []


def test_manual_renewal_refuses_when_the_requirement_cannot_be_resolved(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Eligibility derived from nothing is no eligibility, so it refuses.

    Spending a provider request against a guard nobody established, or
    declining against one, would both report an eligibility that was never
    computed. The runner is asserted untouched so the refusal is known to land
    BEFORE the request rather than after it.
    """
    repo = _repo(tmp_path=tmp_path, workflow_toml=_UNRESOLVABLE_TOML)
    runner = _AppServerRunner()

    exit_code = run_codex_cred_refresh_with(
        args=argparse.Namespace(as_json=True, dry_run=False),
        cwd=lambda: repo,
        now_epoch=lambda: _NOW,
        read_host_codex_auth=lambda: _auth_json(exp=_NOW + 10),
        runner_factory=lambda: runner,
    )

    assert exit_code == 1
    assert runner.calls == []
    assert capsys.readouterr().out == ""


def test_the_gate_journals_an_unresolvable_requirement_under_its_own_stage() -> None:
    """The gate records WHICH question defeated it, not a generic refusal.

    `CODEX_CREDENTIAL_REQUIREMENT_STAGE` is distinct from the gate's own
    credential-shortfall stage, and the distinction is what tells an operator
    whether the credential was short or the requirement was unknown — two faults
    with different remedies that share one exit code.
    """
    records: list[dict[str, Any]] = []

    class _Journal:
        def append(self, *, record: dict[str, Any]) -> None:
            records.append(record)

    refusal = "credential lifetime requirement unresolved: fixture"

    returned = codex_credential_refusal_for_items(
        work_item_ids=("bd-ib-fixture",),
        requirement=refusal,
        journal=_Journal(),
    )

    assert returned == refusal
    assert [record["stage"] for record in records] == [CODEX_CREDENTIAL_REQUIREMENT_STAGE]


def test_manual_renewal_below_the_requirement_actually_spends_the_request(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Derived eligibility is ACTED on, not merely reported.

    The third leg the other two cases cannot supply. `would_invoke_codex` being
    True under `--dry-run` says the guard classified the credential as due; it
    says nothing about whether the refresher then does anything, and a build
    that classified correctly and never sent the request would satisfy both
    earlier cases. This one runs without `--dry-run` over the same
    below-requirement credential and reads the request off the runner.

    The outcome is `still-stale` and the exit code 1 BY CONSTRUCTION: the
    hermetic runner answers the RPC but cannot advance a real expiry, so the
    re-read sees the same lifetime. That is the honest classification — a
    renewal that was answered and changed nothing is not a success — and
    asserting it here pins that the refresher reports what it measured rather
    than what it attempted.
    """
    repo = _repo(tmp_path=tmp_path)
    required = _required_seconds(repo=repo)
    runner = _AppServerRunner()

    exit_code = run_codex_cred_refresh_with(
        args=argparse.Namespace(as_json=True, dry_run=False),
        cwd=lambda: repo,
        now_epoch=lambda: _NOW,
        read_host_codex_auth=lambda: _auth_json(exp=_NOW + required - 1),
        runner_factory=lambda: runner,
    )

    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert payload["invoked_codex"] is True
    assert exit_code == 1
    assert payload["outcome"] == "still-stale"
    # ONE request, addressed to the app-server rather than a model turn.
    assert len(runner.calls) == 1
    argv, call_cwd, request_lines, timeout_seconds = runner.calls[0]
    assert argv == ["codex", "app-server"]
    assert call_cwd == repo
    assert timeout_seconds == 120.0
    assert [json.loads(line)["method"] for line in request_lines] == [
        "initialize",
        "initialized",
        "account/read",
    ]


@pytest.mark.parametrize(
    ("offset", "admitted"),
    [
        pytest.param(-1, False, id="below"),
        pytest.param(0, False, id="equal"),
        pytest.param(1, True, id="above"),
    ],
)
def test_admission_requires_the_lifetime_to_exceed_the_requirement(
    tmp_path: Path, offset: int, *, admitted: bool
) -> None:
    """The boundary is STRICT: equality does not exceed, so equality refuses.

    The ratified assertion is that the remaining lifetime EXCEEDS the maximum
    enforced credential-use duration plus the documented margin. The comparator
    was `>=`, which admitted a credential whose remaining lifetime EQUALS that
    figure -- and equality is not academic here: it is precisely the credential
    that would finish its last enforced second with zero margin left, which is
    the state the margin exists to prevent.

    All three points are asserted because no single one pins a comparator: the
    below case passes under both `>` and `>=`, the above case passes under both,
    and only the EQUAL case tells them apart.
    """
    repo = _repo(tmp_path=tmp_path)
    required = _required_seconds(repo=repo)

    verdict = graded_freshness(
        source_auth_json=_auth_json(exp=_NOW + required + offset),
        now_epoch=_NOW,
        run_budget_seconds=required - CODEX_FRESHNESS_MARGIN_SECONDS,
    )

    assert verdict is not None
    assert verdict.fresh_enough is admitted


@pytest.mark.parametrize(
    ("offset", "due"),
    [
        pytest.param(-1, True, id="below"),
        pytest.param(0, True, id="equal"),
        pytest.param(1, False, id="above"),
    ],
)
def test_renewal_eligibility_mirrors_the_strict_admission_boundary(
    tmp_path: Path, offset: int, capsys: pytest.CaptureFixture[str], *, due: bool
) -> None:
    """The dead zone is EMPTY at the boundary, not merely near it.

    Admission refuses at equality, so renewal must be DUE at equality too. While
    the guard used `<` the two disagreed at exactly one lifetime: dispatch
    refused it while the sanctioned refresher reported "not due" and told a
    human to run `codex login`. One second wide is still a dead zone, and it is
    the same defect deriving this guard was adopted to retire.
    """
    repo = _repo(tmp_path=tmp_path)
    required = _required_seconds(repo=repo)
    runner = _AppServerRunner()

    exit_code = run_codex_cred_refresh_with(
        args=argparse.Namespace(as_json=True, dry_run=True),
        cwd=lambda: repo,
        now_epoch=lambda: _NOW,
        read_host_codex_auth=lambda: _auth_json(exp=_NOW + required + offset),
        runner_factory=lambda: runner,
    )

    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["would_invoke_codex"] is due
