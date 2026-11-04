"""Consumer-tier acceptance for the seven-day admission allowance.

Binds `SPECIFICATION/scenarios.md` "Scenario 231 — Admission skips a Claude
candidate whose seven-day allowance is exhausted" and the seven-day sentences
of `SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance", paragraph "Admission filters candidates by projected
Claude session headroom". One case per gherkin block.

WHAT MAKES THIS A SCENARIO BINDING RATHER THAN A UNIT TEST IS THE SEAM IT
INJECTS. Everything from the real `dispatcher.main(argv=["loop", ...])` down
through admission, the preflight filter, the committed dials, the chain
resolution and the real provider READ is production code; the only things stood
in are the two that leave the process -- the Fabro launch, and `urlopen`, which
is handed a response carrying REAL provider header names. So the weekly status
that decides each case enters the system the way a live one does, as four
headers on one response, rather than as a reading a test constructed. A
helper-level call cannot fail the way a wired-up pass can: the header names,
the fraction-to-percentage conversion, the committed floor, the chain order and
the journal projection are each a place the decision can be lost, and only the
whole pass exercises all of them.

SO THIS MODULE REPLACES THE SUITE'S OWN HEADROOM STAND-IN, and that is the one
thing to understand before editing it. `tests/conftest.py`'s autouse
`_hermetic_session_headroom_reading` answers every admission pass with an
untouched window so no test can reach a provider; a case running under it
reports a weekly reading of ABSENT whatever response this fixture builds, which
is a pass earned by the stand-in rather than by the code. Each case therefore
re-arms the PRODUCTION read and injects `urlopen` beneath it, which is one
layer LOWER and no less hermetic -- no socket is opened either way. The control
is the credential identity: every case asserts the journaled reading is
fingerprinted from the token this dispatch projects, which the stand-in's own
fixed identity cannot satisfy, so a case that silently fell back to it fails
rather than passing vacuously.

THE SKIP IS READ OFF THE SELECTED CANDIDATE, not off the skip list alone.
"Per-node selection continues to the next eligible candidate" is a claim about
what the dispatch then RAN on, so each case asserts the candidate the node
selected -- and the refused case asserts the dispatch LAUNCHED, since a build
that emptied the chain instead would record the same skip and refuse the item.

THE ADMITTED CASES ARE THE CONTROLS, and they are the same repository, the same
dials and the same four headers, differing only in the weekly status. Without
them "the candidate was skipped" is equally consistent with a filter that skips
every covered candidate, which would idle the factory on every healthy account.

Everything is HERMETIC: no credential value leaves this file, no provider is
reached, and no tenant is written.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from dataclasses import replace
from email.message import Message
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from urllib.request import Request

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_admission as admission_module
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_io as headroom_io,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import SEVEN_DAY_SKIP_KIND
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    ABSENT_SEVEN_DAY_READING,
    SEVEN_DAY_REJECTED_STATUS,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    SESSION_HEADROOM_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_gate import (
    session_headroom_policy,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"
_NODE = "implement"

# The credential this dispatch projects. One spelling, used by the fixture
# that puts it in the environment and by the control that fingerprints it,
# so the two cannot drift and the control cannot pass against some other
# account's reading.
_TOKEN = "test-oauth-token"

# The provider's four unified rate-limit headers, spelled here as the response
# a live account answers with. The five-hour pair is ample in every case, so
# only the weekly pair can decide anything.
_FIVE_HOUR_UTILIZATION = "anthropic-ratelimit-unified-5h-utilization"
_FIVE_HOUR_RESET = "anthropic-ratelimit-unified-5h-reset"
_SEVEN_DAY_UTILIZATION = "anthropic-ratelimit-unified-7d-utilization"
_SEVEN_DAY_STATUS = "anthropic-ratelimit-unified-7d-status"

# The committed Claude primary and the uncovered fallback behind it. Coverage
# follows resolved agent provenance, so the STRUCTURED `claude-acp` form is the
# only way to put a covered candidate at position zero.
_CLAUDE_DOMAIN = "claude-subscription"
_CLAUDE_KEY = "claude-opus-5"
_FALLBACK_DOMAIN = "fallback-domain"
_FALLBACK_KEY = "fallback-model"

_FLEET_MANIFEST_TEXT = (
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [\n'
    '    { "repo": "livespec", "class": "core" },\n'
    '    { "repo": "repo", "class": "impl-plugin" }\n'
    "  ]\n"
    "}\n"
)

_WORKFLOW_TOML = (
    '_version = 1\n\n[workflow]\ngraph = "graph.toml"\n\n'
    '[run.inputs]\nimplement_adapter = "npx -y claude-acp"\n\n'
    '[run.environment]\nid = "fabro-sandbox"\n'
)

_GRAPH = (
    "digraph ImplementWorkItem {\n"
    '    graph [stall_timeout="7200s"]\n'
    '    start [shape=Mdiamond, label="Start"]\n'
    '    exit  [shape=Msquare, label="Exit"]\n'
    '    implement [backend="acp", acp.command="{{ inputs.implement_adapter }}",'
    ' timeout="1800s"]\n'
    "    start -> implement\n"
    "    implement -> exit\n"
    "}\n"
)


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic dispatch environment plus a fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("seven-day-admission")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TOKEN)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    for _ntfy in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones."
        "fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-weekly",
        type="task",
        status="ready",
        title="A dispatched slice",
        description=(
            "Implement the slice.\n"
            "\n"
            "## Definition of Done\n"
            "\n"
            "- The dispatched slice lands its change.\n"
            "\n"
            "References: ## Effective acceptance criteria\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-22T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-then-human",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    return replace(base, **overrides)  # pyright: ignore[reportArgumentType]


def _repo(*, tmp_path: Path, floor_percent: int) -> tuple[Path, Path]:
    """A dispatch target declaring the floor and one covered chain."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Chad Woolley",
                    "operator_email": "thewoolleyman@gmail.com",
                },
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {
                        "wip_cap": 5,
                        "session_headroom_floor_percent": floor_percent,
                        "acp_nodes": {
                            _NODE: {
                                "agent": "claude-acp",
                                "model": _CLAUDE_KEY,
                                "effort": "high",
                                "availability_key": _CLAUDE_DOMAIN,
                                "candidate_key": _CLAUDE_KEY,
                                "display_name": "Claude Opus 5",
                                "fallbacks": [
                                    {
                                        "display_name": "Fallback adapter",
                                        "candidate_key": _FALLBACK_KEY,
                                        "availability_key": _FALLBACK_DOMAIN,
                                        "command": "fallback-acp",
                                        "args": ["--stdio"],
                                        "env": {"FALLBACK_BASE_URL": "https://fallback.example"},
                                    }
                                ],
                            }
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    # The workflow is committed INSIDE the target, which is what makes the
    # preflight resolve THIS graph: the chain resolution reads the dispatch
    # target's own `.fabro/workflows/implement-work-item/`, and a workflow
    # parked outside the repo leaves it resolving the plugin's BUNDLED graph --
    # whose other nodes are single-candidate built-in Claude adapters, so a
    # refused weekly allowance empties all of them and the dispatch is refused
    # before this scenario's own node is ever selected.
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    committed = workflow / "workflow.toml"
    _ = committed.write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow / "graph.toml").write_text(_GRAPH, encoding="utf-8")
    return repo, committed


def _headers(**values: str) -> Message:
    message = Message()
    for name, value in values.items():
        message[name] = value
    return message


def _provider_response(*, weekly_status: str | None, weekly_utilization: str | None) -> Message:
    """One response with ample five-hour room and whatever the week says."""
    values = {_FIVE_HOUR_UTILIZATION: "0.05", _FIVE_HOUR_RESET: "2026-10-22T17:00:00Z"}
    if weekly_utilization is not None:
        values[_SEVEN_DAY_UTILIZATION] = weekly_utilization
    if weekly_status is not None:
        values[_SEVEN_DAY_STATUS] = weekly_status
    return _headers(**values)


def _inject_provider(
    *, monkeypatch: pytest.MonkeyPatch, headers: Message, calls: list[Request]
) -> None:
    """Re-arm the PRODUCTION read and stand in one layer below it.

    The suite's autouse `_hermetic_session_headroom_reading` answers the
    admission pass with a fixed untouched window, which would report an absent
    weekly reading whatever response this builds -- so the policy is rebuilt
    here with the production `read`, and the transport beneath it is what
    answers. No socket is opened either way; the module docstring records why
    the lower seam is the one this binding needs.
    """

    def _urlopen(request: Request, *, timeout: float) -> MagicMock:
        _ = timeout
        calls.append(request)
        response = MagicMock()
        response.status = 200
        response.headers = headers
        response.read.return_value = b'{"type":"message"}'
        response.__enter__.return_value = response
        return response

    monkeypatch.setattr(headroom_io, "urlopen", _urlopen)
    monkeypatch.setattr(
        admission_module,
        "session_headroom_policy",
        lambda **kwargs: session_headroom_policy(
            **{**kwargs, "read": headroom_io.read_projected_session_headroom}
        ),
    )


def _green_recording(launches: list[str]) -> Callable[..., DispatchOutcome]:
    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        launches.append(plan.work_item_id)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=11,
            merge_sha="feed01",
            detail="merged",
        )

    return _run_dispatch


def _loop(*, repo: Path, workflow: Path) -> int:
    return main(
        argv=[
            "loop",
            "--repo",
            str(repo),
            "--budget",
            "5",
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )


def _journal_records(*, repo: Path) -> list[dict[str, Any]]:
    text = (repo / _JOURNAL).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _headroom_record(*, repo: Path) -> dict[str, Any]:
    [record] = [
        entry
        for entry in _journal_records(repo=repo)
        if entry.get("stage") == SESSION_HEADROOM_STAGE
    ]
    return record


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def _drive(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    weekly_status: str | None,
    weekly_utilization: str | None = "1.0",
    floor_percent: int = 20,
) -> tuple[Path, int, list[str], list[Request]]:
    repo, workflow = _repo(tmp_path=tmp_path, floor_percent=floor_percent)
    append_work_item(path=_config(), item=_item())
    calls: list[Request] = []
    _inject_provider(
        monkeypatch=monkeypatch,
        headers=_provider_response(
            weekly_status=weekly_status, weekly_utilization=weekly_utilization
        ),
        calls=calls,
    )
    launches: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _green_recording(launches))

    exit_code = _loop(repo=repo, workflow=workflow)

    return repo, exit_code, launches, calls


def _assert_production_read(*, assessment: dict[str, Any]) -> None:
    """The reading came from the production read on the projected credential.

    The control for every case: the suite's own headroom stand-in journals a
    FIXED identity of its own, so a case that silently ran under it reports an
    identity this cannot match -- and every weekly assertion beside it would
    then be a reading of the stand-in rather than of the response the case
    built.
    """
    assert assessment["credential_identity"] == headroom_io.projected_credential_identity(
        token=_TOKEN
    )


def test_a_seven_day_exhaustion_skips_the_candidate_and_selection_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Block one: skipped by a seven-day skip, and the fallback carries the run."""
    repo, exit_code, launches, calls = _drive(
        tmp_path=tmp_path, monkeypatch=monkeypatch, weekly_status=SEVEN_DAY_REJECTED_STATUS
    )

    # The dispatch PROCEEDED: a build that emptied the chain would record the
    # same skip and refuse the item.
    assert exit_code == 0
    assert launches == ["bd-ib-weekly"]
    assert _stored()["bd-ib-weekly"].status == "active"
    # One bounded request answered both windows.
    assert len(calls) == 1
    record = _headroom_record(repo=repo)
    selection = record["node_selections"][_NODE]
    assert selection["selected_candidate_key"] == _FALLBACK_KEY
    [skipped] = selection["headroom_skipped"]
    assert skipped["candidate_key"] == _CLAUDE_KEY
    assert skipped["headroom_skip_kind"] == SEVEN_DAY_SKIP_KIND
    # The journal records the weekly figures beside the five-hour ones.
    [assessment] = record["assessments"]
    _assert_production_read(assessment=assessment)
    assert assessment["seven_day"] == {
        "utilization_percent": 100.0,
        "status": SEVEN_DAY_REJECTED_STATUS,
        "unobservable": None,
    }
    assert assessment["remaining_percent"] == 95.0


@pytest.mark.parametrize(
    ("weekly_status", "weekly_utilization", "expected_weekly"),
    [
        (
            "allowed_warning",
            "0.9",
            {"utilization_percent": 90.0, "status": "allowed_warning", "unobservable": None},
        ),
        (
            None,
            None,
            {
                "utilization_percent": None,
                "status": None,
                "unobservable": ABSENT_SEVEN_DAY_READING,
            },
        ),
    ],
    ids=["warning", "absent"],
)
def test_a_warning_or_absent_seven_day_reading_skips_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    weekly_status: str | None,
    weekly_utilization: str | None,
    expected_weekly: dict[str, Any],
) -> None:
    """Block two: the covered primary is selected, and the reading is journaled."""
    repo, exit_code, launches, _ = _drive(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        weekly_status=weekly_status,
        weekly_utilization=weekly_utilization,
    )

    assert exit_code == 0
    assert launches == ["bd-ib-weekly"]
    record = _headroom_record(repo=repo)
    selection = record["node_selections"][_NODE]
    assert selection["headroom_skipped"] == []
    assert selection["selected_candidate_key"] == _CLAUDE_KEY
    [assessment] = record["assessments"]
    _assert_production_read(assessment=assessment)
    assert assessment["seven_day"] == expected_weekly


def test_a_floor_of_zero_disables_the_seven_day_skip_and_still_journals_the_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Block three: the dial switches the weekly skip off, the reading survives."""
    repo, exit_code, launches, calls = _drive(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        weekly_status=SEVEN_DAY_REJECTED_STATUS,
        floor_percent=0,
    )

    assert exit_code == 0
    assert launches == ["bd-ib-weekly"]
    # The bounded reading attempt is retained, which is what the clause asks of
    # a disabled floor rather than switching the request off too.
    assert len(calls) == 1
    record = _headroom_record(repo=repo)
    assert record["session_headroom_floor_percent"] == 0
    selection = record["node_selections"][_NODE]
    assert selection["headroom_skipped"] == []
    assert selection["selected_candidate_key"] == _CLAUDE_KEY
    [assessment] = record["assessments"]
    _assert_production_read(assessment=assessment)
    assert assessment["seven_day"]["status"] == SEVEN_DAY_REJECTED_STATUS
