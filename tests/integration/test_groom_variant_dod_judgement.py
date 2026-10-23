"""Integration-tier acceptance for the groom exemption of the SEMANTIC judgement.

The cousin of `test_groom_variant_criteria_wall.py`, one clause on. That module
binds the MECHANICAL half of the Definition-of-Done gate — the parse that counts
gradeable assertions — against `SPECIFICATION/contracts.md` section
"Consensus-gated automated groom cut", which says a groom target "carries the
approved draft in place of an acceptance". This module binds the SEMANTIC half,
the `dod_gate` judgement of "Judged before admission" and "Judged again before
dispatch", whose own clauses scope it to an "implement-kind item" in both
positions.

WHY THE MECHANICAL EXEMPTION DOES NOT ALREADY COVER THIS. The two halves run as
separate wall rows at separate call sites, and the semantic one reaches a model
rather than a parse, so an exemption wired into one of them leaves the other
holding exactly the item the groom door prepared. A groom target has no
gradeable criteria by construction, so the judgement holds it, the dispatch
exits 5 and the drain then drops it "until its effective criteria or referenced
headings change" — which is what the groom run was going to produce. That is a
closed loop, and its symptom is a groom door that silently stops opening.

WHY EVERY CASE IS A PAIR OVER ONE FIXTURE. An exemption is worthless as a
one-sided assertion: a build whose judgement had been removed altogether would
satisfy "the groom dispatch launched" perfectly. Each leg therefore differs from
its control in NOTHING but the item's `dispatch_workflow` pin, written through
the production writer, and the control must still be refused by the judgement.
The item carries a WELL-FORMED Definition of Done in both legs, which is what
makes the control evidence about this row rather than the mechanical one: the
criteria parse to one gradeable assertion and the reference resolves, so the
mechanical row passes and the refusal under test is the only one left.

WHY THE JUDGE IS COUNTED AND NOT ONLY ANSWERED. "Exempt" has to mean the
judgement is NOT TAKEN, not that its verdict is discarded — the clause's whole
economy is about the model call. Each exempt leg therefore asserts the judge
executable was invoked ZERO times, which a build that judged and then ignored
the answer cannot satisfy.

THE JUDGE IS STOOD IN AT THE EXECUTABLE, as in both Scenario 174 modules, so the
argv, the shipped prompt read and the exit-code mapping are all exercised.
"""

from __future__ import annotations

import json
import stat
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_workflow import record_dispatch_workflow
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-groomjudge"
_EXIT_PRECONDITION_ERROR = 3
_EXIT_UNGRADEABLE_CRITERIA = 5

_HEADING = "## Effective acceptance criteria"
_HELD_FINDING = "bd-ib-groomjudge: the References line omits the governing scenario."
_HELD_REPLY = '{"outcome": "failed", "failure_reason": "' + _HELD_FINDING + '"}'

# How many times the judge executable is invoked by ONE taking of the
# judgement. Two since `bd-ib-m76p2n`: the spec-stated judgement the
# governing-heading verdict comes from, and the rubric judgement itself. Both
# are headless `claude -p` calls through the same resolver, so both land in the
# ledger this module counts. The number is NAMED rather than written as a
# literal at each control, because its meaning is "the judgement was taken" and
# a bare 2 beside a bare 0 reads as an arbitrary pair.
_TAKEN_JUDGE_CALLS = 2

_GROOM_VARIANT = "groom-cut"
_IMPLEMENT_VARIANT = "slice"
_GROOM_DIR = f".fabro/workflows/{_GROOM_VARIANT}"
_IMPLEMENT_DIR = f".fabro/workflows/{_IMPLEMENT_VARIANT}"
_RESERVED_DIR = ".fabro/workflows/implement-work-item"

_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
)

# The kind rides `[run.inputs]`, which is where `_workflow_variant_kind` reads
# it from. The implement leg declares NOTHING rather than declaring `implement`
# explicitly, because an undeclared kind is what every variant registered
# before that key existed looks like — the shape the exemption must not open on.
_GROOM_WORKFLOW_TOML = (
    '[workflow]\ngraph = "workflow.fabro"\n\n'
    '[run.environment]\nid = "fabro-sandbox"\n\n'
    '[run.inputs]\nworkflow_kind = "groom"\n'
)
_IMPLEMENT_WORKFLOW_TOML = (
    '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "fabro-sandbox"\n'
)

_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic dispatch environment + a fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("groom-variant-dod-judgement")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:groom-variant-dod-judgement")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _seed_item(*, repo: Path, **overrides: object) -> WorkItem:
    """One item whose Definition of Done the MECHANICAL half already admits.

    One gradeable bullet and a reference line naming a heading the fixture's own
    spec tree holds, so `definition_of_done_findings` reports nothing and the
    criteria wall passes. The judgement is then the only row left that can
    refuse, which is what makes the implement-pinned control evidence about it.
    """
    base = WorkItem(
        id=_ITEM_ID,
        type="feature",
        status="ready",
        title="An epic awaiting decomposition",
        description=(
            "## Definition of Done\n"
            "\n"
            "- The dispatched slice lands its change.\n"
            "\n"
            f"References: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        # AI-dispositive, so both halves of the gate are armed: `human-only` is
        # the per-item escape, and using it here would make every leg pass for a
        # reason that has nothing to do with the variant.
        acceptance_policy="ai-only",
        acceptance_criteria=None,
    )
    item = replace(base, **overrides)
    append_work_item(path=_config(repo=repo), item=item)
    return item


def _write_workflow(*, repo: Path, directory: str, manifest_text: str) -> None:
    workflow = repo / directory
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(manifest_text, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")


def _repo(*, tmp_path: Path) -> Path:
    """One target registering both a groom-kind and an implement-kind variant."""
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nThe criteria clause.\n", encoding="utf-8"
    )
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
                        "wip_cap": 3,
                        "acceptance_mode": "ai-only",
                        "workflows": {
                            _GROOM_VARIANT: _GROOM_DIR,
                            _IMPLEMENT_VARIANT: _IMPLEMENT_DIR,
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    _write_workflow(repo=repo, directory=_GROOM_DIR, manifest_text=_GROOM_WORKFLOW_TOML)
    _write_workflow(repo=repo, directory=_IMPLEMENT_DIR, manifest_text=_IMPLEMENT_WORKFLOW_TOML)
    # The target's own reserved workflow, so a dispatch that named no variant
    # resolves inside this tmp tree rather than reaching the bundled payload.
    _write_workflow(repo=repo, directory=_RESERVED_DIR, manifest_text=_IMPLEMENT_WORKFLOW_TOML)
    return repo


def _install_judge(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real holding judge that also records every invocation it receives."""
    ledger = tmp_path / "judge-calls"
    script = tmp_path / "fake-judge"
    _ = script.write_text(
        f"#!/bin/sh\necho call >> {ledger}\ncat <<'REPLY'\n{_HELD_REPLY}\nREPLY\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))
    return ledger


def _judge_calls(*, ledger: Path) -> int:
    return len(ledger.read_text(encoding="utf-8").splitlines()) if ledger.is_file() else 0


def _recording_run_dispatch(*, calls: list[str]) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in recording that a factory run WAS created."""

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        calls.append(plan.work_item_id)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="dispatched",
        )

    return _run_dispatch


def _dispatch(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    subcommand: str = "dispatch",
) -> tuple[int, list[str]]:
    """Drive one real dispatch and report its exit code plus what it launched."""
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording_run_dispatch(calls=calls))
    argv = [subcommand, "--repo", str(repo), "--item", _ITEM_ID, "--no-close-on-merge"]
    if subcommand == "loop":
        argv += ["--budget", "3"]
    return main(argv=argv), calls


def _stored(*, repo: Path) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config(repo=repo)))[_ITEM_ID]


def test_a_groom_pinned_dispatch_is_not_judged_and_reaches_the_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pre-dispatch wall exempts a groom-kind dispatch, spending nothing."""
    repo = _repo(tmp_path=tmp_path)
    ledger = _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _ = _seed_item(repo=repo)
    record_dispatch_workflow(
        path=_config(repo=repo), work_item_id=_ITEM_ID, workflow=_GROOM_VARIANT
    )

    exit_code, calls = _dispatch(repo=repo, monkeypatch=monkeypatch)

    assert (exit_code, calls) == (0, [_ITEM_ID])
    assert exit_code != _EXIT_UNGRADEABLE_CRITERIA
    # Exempt means NOT JUDGED, not "judged and then forgiven".
    assert _judge_calls(ledger=ledger) == 0


def test_an_implement_pinned_dispatch_is_still_refused_by_the_judgement(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control: the same item, the same repo, a non-groom variant, refused.

    Without this the exemption above is indistinguishable from a judgement that
    had been removed. The refusal is read for the JUDGE'S OWN finding text
    rather than for the exit code alone, because the mechanical row shares that
    code and a refusal from it would prove nothing about this one.
    """
    repo = _repo(tmp_path=tmp_path)
    ledger = _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _ = _seed_item(repo=repo)
    record_dispatch_workflow(
        path=_config(repo=repo), work_item_id=_ITEM_ID, workflow=_IMPLEMENT_VARIANT
    )

    exit_code, calls = _dispatch(repo=repo, monkeypatch=monkeypatch)

    assert (exit_code, calls) == (_EXIT_UNGRADEABLE_CRITERIA, [])
    assert exit_code != _EXIT_PRECONDITION_ERROR
    assert _HELD_FINDING in capsys.readouterr().err
    assert _judge_calls(ledger=ledger) == _TAKEN_JUDGE_CALLS


def test_the_drain_exempts_the_same_groom_pinned_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exemption is a property of the candidate, so the drain honours it too.

    The two dispatch paths reach the wall through separate call sites, so an
    exemption wired into only one of them would leave the drain refusing exactly
    the item the door prepared for it.
    """
    repo = _repo(tmp_path=tmp_path)
    ledger = _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _ = _seed_item(repo=repo)
    record_dispatch_workflow(
        path=_config(repo=repo), work_item_id=_ITEM_ID, workflow=_GROOM_VARIANT
    )

    exit_code, calls = _dispatch(repo=repo, monkeypatch=monkeypatch, subcommand="loop")

    assert (exit_code, calls) == (0, [_ITEM_ID])
    assert _judge_calls(ledger=ledger) == 0


def test_the_approve_valve_admits_a_groom_pinned_item_without_judging_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admission call site carries the same scoping as the dispatch one.

    `acceptance_eligibility` already exempts the groom variant mechanically, so
    an item this valve's own parse cleared was still being held at
    `pending-approval` by the judgement one line below it — the inversion the
    variant decision exists to prevent, reintroduced beside it.
    """
    repo = _repo(tmp_path=tmp_path)
    ledger = _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _ = _seed_item(repo=repo, status="pending-approval", admission_policy="manual")
    record_dispatch_workflow(
        path=_config(repo=repo), work_item_id=_ITEM_ID, workflow=_GROOM_VARIANT
    )

    result = run_action(repo=repo, action_id=f"approve:{_ITEM_ID}")

    assert result["status"] == "green"
    assert _stored(repo=repo).status == "ready"
    assert _judge_calls(ledger=ledger) == 0


def test_the_approve_valve_still_holds_an_implement_pinned_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control for the valve: the same item, a non-groom pin, held.

    Read on the judge's own finding and on the rested status, because a valve
    that refused every approval would leave the item at `pending-approval` too.
    """
    repo = _repo(tmp_path=tmp_path)
    ledger = _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _ = _seed_item(repo=repo, status="pending-approval", admission_policy="manual")
    record_dispatch_workflow(
        path=_config(repo=repo), work_item_id=_ITEM_ID, workflow=_IMPLEMENT_VARIANT
    )

    result = run_action(repo=repo, action_id=f"approve:{_ITEM_ID}")

    assert result["status"] != "green"
    assert _HELD_FINDING in str(result)
    assert _stored(repo=repo).status == "pending-approval"
    assert _judge_calls(ledger=ledger) == _TAKEN_JUDGE_CALLS
