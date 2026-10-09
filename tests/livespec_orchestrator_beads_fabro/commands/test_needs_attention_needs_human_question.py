"""Tests for the needs-human enrichment of the `resolve-blocked` valve lane."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_needs_attention_needs_human_question.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._needs_attention_needs_human_question"

_HP_SERVER = "https://hp.example:32276"
_VPS_SERVER = "https://vps.example:32276"
_RUN_ID = "01NEEDSHUMAN"
_ITEM = "bd-ib-blocked"
_TITLE = "b3.S1 — publish the needs-human question"
_DEFAULT = f"Resolve human-needed block for work-item {_ITEM}: {_TITLE}"
_PROMPT = "loop cannot auto-resolve this work-item; run terminated, work preserved by reference"
_REF = f"refs/heads/needs-human/{_RUN_ID}"
_BACKGROUNDED_COMMAND = "mise exec -- just check-coverage 2>&1 | tail -200"
_BACKGROUNDED_CAUSE = (
    f"ACP tool call toolu_012SANITIZED ({_BACKGROUNDED_COMMAND}) continued in "
    "background as task bai98447y; Fabro terminated the turn before the agent "
    "could start conflicting work"
)
_PLAIN_CAUSE = "review script exited 1: the implementation does not satisfy criterion 3"


@dataclass(kw_only=True)
class _Runner:
    """One fake `fabro` CLI, keyed by the run id the argv names."""

    inspect_by_run: dict[str, str] = field(default_factory=dict)
    exit_code: int = 0
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
        return CommandResult(
            exit_code=self.exit_code,
            stdout=self.inspect_by_run.get(argv[2], "[]"),
            stderr="",
        )


def test_the_valve_summary_carries_the_run_handle_question_and_answer_actions(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The whole contract, on one fixture run that TERMINATED at needs_human."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    runner = _terminated_runner()

    summary = module.needs_human_question_summary(
        project_root=repo,
        item_id=_ITEM,
        default_summary=_DEFAULT,
        runner=runner,
    )

    # The lane it enriches is preserved verbatim, never replaced.
    assert summary.startswith(_DEFAULT)
    # The run handle: the run id and the factory server it lived on.
    assert _RUN_ID in summary
    assert _HP_SERVER in summary
    assert "factory hp" in summary
    # The question payload: why the loop stopped, what it said, where work survived.
    assert "review|deterministic|acp turn failed" in summary
    assert _PROMPT in summary
    assert _REF in summary
    # The answer action-id is the EXISTING resolve-blocked valve; no attach and
    # no resume route is offered, because a terminated run has neither.
    assert f"resolve-blocked:{_ITEM}:ready" in summary
    assert f"resolve-blocked:{_ITEM}:backlog" in summary
    for forbidden in ("fabro attach", "answer:", "resume"):
        assert forbidden not in summary


def test_needs_attention_json_emits_exactly_one_enriched_item_for_the_run(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """End to end: one blocked item, one attention item, carrying the payload.

    Driven through the composed envelope a console consumes rather than the
    gather, because an enrichment that does not survive composition is worth
    nothing.
    """
    from livespec_orchestrator_beads_fabro.commands import _needs_attention_work_items

    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    runner = _terminated_runner()
    monkeypatch.setattr(
        _needs_attention_work_items,
        "needs_human_question_summary",
        lambda *, project_root, item_id, default_summary: module.needs_human_question_summary(
            project_root=project_root,
            item_id=item_id,
            default_summary=default_summary,
            runner=runner,
        ),
    )

    lanes = _needs_attention_work_items.human_valves(
        project_root=repo,
        items=[_blocked_item()],
        index={},
        manifest=_manifest(project_root=repo),
    )
    composed = _compose(repo=repo, lanes=lanes)

    parked = [entry for entry in composed if entry["id"] == f"valve:resolve-blocked:{_ITEM}"]
    assert len(parked) == 1
    assert parked[0]["handoff"]["action_id"] == f"resolve-blocked:{_ITEM}:ready"
    assert parked[0]["kind"] == "human-valve"
    for fragment in (_RUN_ID, _HP_SERVER, _PROMPT, _REF):
        assert fragment in parked[0]["summary"]


def test_the_run_is_inspected_against_the_factory_the_item_was_dispatched_to(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A default-host probe for a run that lives on another host finds nothing.

    Two proofs: the argv names a `--server`, and it names the DECLARED server of
    the item's own stamped factory rather than the repository default.
    """
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    runner = _terminated_runner()
    asked_for: list[str] = []

    def _stamped(*, path: object, work_item_id: str) -> str:
        _ = path
        asked_for.append(work_item_id)
        return "vps"

    monkeypatch.setattr(module, "dispatch_factory_for", _stamped)

    summary = module.needs_human_question_summary(
        project_root=repo,
        item_id=_ITEM,
        default_summary=_DEFAULT,
        runner=runner,
    )

    assert asked_for == [_ITEM]
    assert [call[1] for call in runner.calls] == ["inspect"]
    assert runner.calls[0][runner.calls[0].index("--server") + 1] == _VPS_SERVER
    assert _VPS_SERVER in summary
    assert "factory vps" in summary


def test_an_agent_reported_ending_reads_differently_from_an_engine_escalation(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """No loop failure signature is informative, not a failed read."""
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    runner = _terminated_runner(engine_routed=False)

    summary = module.needs_human_question_summary(
        project_root=repo,
        item_id=_ITEM,
        default_summary=_DEFAULT,
        runner=runner,
    )

    assert "the implementer reported a needs-human ending" in summary
    assert "no loop failure signature" in summary


def test_a_failed_push_tells_the_human_a_rework_starts_from_scratch(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    runner = _terminated_runner(
        stderr=(
            "LIVESPEC_NEEDS_HUMAN_PUSH_FAILED: tree not pushed\n" f"LIVESPEC_NEEDS_HUMAN: {_PROMPT}"
        )
    )

    summary = module.needs_human_question_summary(
        project_root=repo,
        item_id=_ITEM,
        default_summary=_DEFAULT,
        runner=runner,
    )

    assert "could NOT push its tree" in summary
    assert "from scratch" in summary


def test_a_transport_fault_cause_is_classified_and_a_plain_one_is_not(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The loop signature names the stage; only the cause can name the fault.

    The two legs are one case because either alone is uninformative: a build
    that labelled EVERY cause a transport fault passes the first, and a build
    that labelled none passes the second. The classified leg also asserts the
    raw cause survives beside its label, since the label says what to do and the
    cause says what happened.
    """
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)

    classified = module.needs_human_question_summary(
        project_root=repo,
        item_id=_ITEM,
        default_summary=_DEFAULT,
        runner=_terminated_runner(cause=_BACKGROUNDED_CAUSE),
    )
    plain = module.needs_human_question_summary(
        project_root=repo,
        item_id=_ITEM,
        default_summary=_DEFAULT,
        runner=_terminated_runner(cause=_PLAIN_CAUSE),
    )

    assert f"Innermost cause: {_BACKGROUNDED_CAUSE}." in classified
    assert "transport fault (backgrounded-tool)" in classified
    assert f"the backgrounded command was `{_BACKGROUNDED_COMMAND}`" in classified
    assert f"Innermost cause: {_PLAIN_CAUSE}." in plain
    assert "transport fault" not in plain


def test_a_run_record_with_no_needs_human_account_says_nothing_extra(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    runner = _terminated_runner(stderr="nothing to see", checkpoints=[])

    summary = module.needs_human_question_summary(
        project_root=repo,
        item_id=_ITEM,
        default_summary=_DEFAULT,
        runner=runner,
    )

    assert summary == _DEFAULT


def test_no_preserved_ref_recorded_still_answers_the_rework_question(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    runner = _terminated_runner(stderr="LIVESPEC_NEEDS_HUMAN:   ")

    summary = module.needs_human_question_summary(
        project_root=repo,
        item_id=_ITEM,
        default_summary=_DEFAULT,
        runner=runner,
    )

    assert "recorded no preserved ref" in summary
    assert "carries no needs-human message" in summary


def test_every_unreadable_step_costs_the_enrichment_and_never_the_valve(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A lane that vanished on a network fault would read as a decision made."""
    module = importlib.import_module(_MODULE_NAME)
    unreadable = tmp_path / "unconfigured"
    unreadable.mkdir()
    _ = (unreadable / ".livespec.jsonc").write_text("{ not json", encoding="utf-8")
    configured = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    no_run = _repo(tmp_path=tmp_path / "norun", monkeypatch=monkeypatch, journal=False)
    serverless = _repo(
        tmp_path=tmp_path / "serverless", monkeypatch=monkeypatch, default_factory="ambient"
    )
    failing = _terminated_runner()
    failing.exit_code = 1

    for root, runner in (
        (unreadable, _terminated_runner()),
        (no_run, _terminated_runner()),
        (serverless, _terminated_runner()),
        (configured, failing),
    ):
        assert (
            module.needs_human_question_summary(
                project_root=root,
                item_id=_ITEM,
                default_summary=_DEFAULT,
                runner=runner,
            )
            == _DEFAULT
        )


def test_the_ledger_stamp_outranks_the_journal_and_the_journal_takes_the_newest(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Attribution precedence decides WHICH run is inspected for this item."""
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch, journal_runs=("01OLD", _RUN_ID))
    runner = _terminated_runner()

    _ = module.needs_human_question_summary(
        project_root=repo,
        item_id=_ITEM,
        default_summary=_DEFAULT,
        runner=runner,
    )
    journal_pick = runner.calls[0][2]

    stamped = _terminated_runner()

    def _ledger_stamped(*, repo: Path) -> _Attribution:
        _ = repo
        return _Attribution(
            metadata_run_ids={"01ANOTHERITEM": "bd-ib-elsewhere", "01STAMPED": _ITEM},
            journal_run_ids={"01OLD": _ITEM},
        )

    monkeypatch.setattr(module, "repo_run_attribution", _ledger_stamped)
    _ = module.needs_human_question_summary(
        project_root=repo,
        item_id=_ITEM,
        default_summary=_DEFAULT,
        runner=stamped,
    )

    assert journal_pick == _RUN_ID
    assert stamped.calls[0][2] == "01STAMPED"


def test_the_default_seam_is_the_production_shell_runner(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Omitting `runner` must open the real subprocess seam, not silently no-op."""
    module = importlib.import_module(_MODULE_NAME)
    repo = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    runner = _terminated_runner()
    monkeypatch.setattr(module, "ShellCommandRunner", lambda: runner)

    summary = module.needs_human_question_summary(
        project_root=repo,
        item_id=_ITEM,
        default_summary=_DEFAULT,
    )

    assert _RUN_ID in summary


@dataclass(frozen=True, kw_only=True)
class _Attribution:
    """A stand-in run attribution carrying only the ledger-metadata leg."""

    metadata_run_ids: dict[str, str]
    journal_run_ids: dict[str, str] = field(default_factory=dict)


def _compose(*, repo: Path, lanes: object) -> list[dict[str, object]]:
    from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
        ConformanceContext,
        composed_conformant,
    )
    from livespec_orchestrator_beads_fabro.commands.needs_attention import render_json

    attention = composed_conformant(
        context=ConformanceContext(project_root=repo, repo="livespec-orchestrator-beads-fabro"),
        spec_next=None,
        impl_next=None,
        human_valve_lanes=lanes,  # pyright: ignore[reportArgumentType]
        plan_threads=(),
    )
    payload = json.loads(render_json(attention=attention))
    return list(payload["attention"])


def _manifest(*, project_root: Path) -> object:
    from livespec_orchestrator_beads_fabro.commands._cross_repo import load_manifest

    return load_manifest(project_root=project_root)


def _terminated_runner(
    *,
    stderr: str | None = None,
    engine_routed: bool = True,
    checkpoints: list[object] | None = None,
    cause: str | None = None,
) -> _Runner:
    """A fake `fabro inspect` for a run that terminated at the needs_human node.

    `engine_routed=False` is the agent-reported ending: it rode a conditional
    edge off a node that SUCCEEDED, so the loop recorded no failure signature.
    `cause` adds the engine's failure block, whose innermost element is the one
    field that can be classified — the loop signature carries only the generic
    `ACP turn failed` label.
    """
    checkpoint: dict[str, object] = {"next_node_id": "needs_human"}
    if engine_routed:
        checkpoint["loop_failure_signatures"] = {"review|deterministic|acp turn failed": 1}
    if cause is not None:
        checkpoint["node_outcomes"] = {
            "review": {
                "failure": {
                    "category": "deterministic",
                    "signature": "review|deterministic|acp turn failed",
                    "causes": ["ACP protocol error", cause],
                }
            }
        }
    record: dict[str, object] = {
        "run_id": _RUN_ID,
        "status": {"kind": "failed"},
        "checkpoints": checkpoints if checkpoints is not None else [{"checkpoint": checkpoint}],
        "nodes": [
            {
                "id": "needs_human",
                "output": {
                    "stderr": stderr
                    if stderr is not None
                    else f"LIVESPEC_NEEDS_HUMAN_PRESERVED: {_REF}\nLIVESPEC_NEEDS_HUMAN: {_PROMPT}"
                },
            }
        ],
    }
    return _Runner(
        inspect_by_run={_RUN_ID: json.dumps([record]), "01STAMPED": json.dumps([record])}
    )


def _blocked_item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="task",
        status="blocked",
        title=_TITLE,
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason="needs-human",
    )


def _repo(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    journal: bool = True,
    journal_runs: tuple[str, ...] = (_RUN_ID,),
    default_factory: str = "hp",
) -> Path:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", "fabro")
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {
                        "default_factory": default_factory,
                        "factories": {
                            "hp": {"server": _HP_SERVER},
                            "vps": {"server": _VPS_SERVER},
                            "ambient": {},
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    if journal:
        path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
        path.parent.mkdir(parents=True)
        # A sibling item's run rides the same journal, so the item filter is
        # exercised rather than assumed.
        records = [{"work_item_id": "bd-ib-sibling", "run_id": "01SIBLING"}]
        records.extend({"work_item_id": _ITEM, "run_id": run_id} for run_id in journal_runs)
        _ = path.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n",
            encoding="utf-8",
        )
    return repo
