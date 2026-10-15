"""Tests for `set-merge-hold` — the one human valve that also writes the forge.

Every assertion about what the valve DID reads the ledger back through the store
seam rather than trusting the payload the valve returned: a valve that reported
green while writing nothing is precisely the failure a return-value assertion
cannot see.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-ready"
_MERGE_HOLD_PREFIX = "merge-hold:"
_VALVE_MODULE = "livespec_orchestrator_beads_fabro.commands._drive_merge_hold_valve"

# The head the fixture's pull request carries, and the head its proof record
# names. Equal by default, because that is the only state a release may arm;
# each guard case moves exactly one of them.
_HEAD = "a" * 40
_OTHER_HEAD = "b" * 40


@dataclass(frozen=True, kw_only=True)
class _Run:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class _Runner:
    """The injected command seam, replaying one canned result per call."""

    def __init__(self, *, results: list[_Run]) -> None:
        self.results = results
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> _Run:
        self.calls.append(argv)
        _ = cwd
        return self.results.pop(0)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _labels() -> list[str]:
    raw = _fake().show_issue(issue_id=_ITEM_ID)["labels"]
    assert isinstance(raw, list)
    return [str(label) for label in raw]


def _held() -> bool:
    return any(label.startswith(_MERGE_HOLD_PREFIX) for label in _labels())


def _status() -> str:
    return str(_fake().show_issue(issue_id=_ITEM_ID)["status"])


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {
      "tenant": "livespec-impl-beads",
      "prefix": "bd",
      "server_user": "livespec-impl-beads",
      "database": "livespec-impl-beads",
      "bd_path": "bd",
      "fake": true
    }
  }
}
""",
        encoding="utf-8",
    )
    append_work_item(path=_config(), item=_item())
    return repo


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="Ready",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-07-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)


def _pr_json(
    *,
    number: int = 7,
    state: str = "OPEN",
    armed: bool = False,
    merge_sha: str | None = None,
    head: str = _HEAD,
) -> str:
    payload: dict[str, object] = {
        "number": number,
        "state": state,
        "autoMergeRequest": {"enabledAt": "2026-09-06T00:00:00Z"} if armed else None,
        "mergeStateStatus": "CLEAN",
        "headRefOid": head,
    }
    if merge_sha is not None:
        payload["mergeCommit"] = {"oid": merge_sha}
    return json.dumps(payload)


def _contract_record(*, work_item_id: str, merge_mode: object) -> dict[str, object]:
    return {
        "stage": "dispatch-id",
        "work_item_id": work_item_id,
        "integration_contract": {
            "schema_version": 1,
            "fields": {
                "merge_mode": {
                    "key": "dispatcher.merge_mode",
                    "arm": "declared",
                    "value": merge_mode,
                }
            },
        },
    }


def _journal(repo: Path, *, records: list[dict[str, object]]) -> None:
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def _view_argv(*, branch: str = "feat/bd-ib-ready") -> tuple[str, ...]:
    return (
        "gh",
        "pr",
        "view",
        branch,
        "--json",
        "number,state,autoMergeRequest,mergeCommit,headRefOid",
    )


def _ps_json(*, run_ids: tuple[str, ...] = ()) -> str:
    """A `fabro ps -a --json` payload naming `run_ids` as live for this item."""
    return json.dumps(
        [
            {"run_id": run_id, "status": "running", "goal": f"Work-item: {_ITEM_ID}"}
            for run_id in run_ids
        ]
    )


def _records_json(*, verdict: str = "verified", head: str | None = _HEAD) -> str:
    """A `gh pr view <n> --json comments` payload carrying one anchoring record."""
    body = f"Proof of Done — {verdict} — run r — 2026-10-15T00:00:00Z\n"
    if head is not None:
        body += f"Publish-branch head: {head}\n"
    return json.dumps({"comments": [{"body": body, "url": "https://forge.invalid/c/1"}]})


def _guard_answers(
    *,
    ps: str | None = None,
    records: str | None = None,
) -> list[_Run]:
    """The two readings the v145 arm guard takes, in the order it takes them.

    LIVENESS FIRST, then the proof records: the guard's own ordering, and a
    fixture that supplied them the other way round would pass while the guard
    compared a head a live run was already rewriting.
    """
    return [
        _Run(returncode=0, stdout=_ps_json() if ps is None else ps),
        _Run(returncode=0, stdout=_records_json() if records is None else records),
    ]


def _hold(repo: Path) -> None:
    """Put the item under hold with no pull request in sight, for release tests."""
    result = run_human_valve_action(
        repo=repo,
        action_id=f"set-merge-hold:{_ITEM_ID}:on",
        runner=_Runner(results=[_Run(returncode=1)]),
    )
    assert result["status"] == "green"


def test_hold_writes_the_label_and_leaves_the_status_unchanged(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runner = _Runner(results=[_Run(returncode=1)])

    run_human_valve_action(repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:on", runner=runner)

    assert _held()
    assert _status() == "active"
    assert runner.calls == [_view_argv()]


def test_release_without_an_open_pull_request_removes_the_label_and_writes_no_forge_request(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _hold(repo)
    runner = _Runner(results=[_Run(returncode=1)])

    run_human_valve_action(repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:off", runner=runner)

    assert not _held()
    assert _status() == "active"
    assert runner.calls == [_view_argv()]


def test_release_on_an_already_merged_pull_request_only_removes_the_label(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _hold(repo)
    runner = _Runner(
        results=[_Run(returncode=0, stdout=_pr_json(state="MERGED", merge_sha="abc1234"))]
    )

    run_human_valve_action(repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:off", runner=runner)

    assert not _held()
    assert runner.calls == [_view_argv()]


def test_hold_disarms_an_already_armed_pull_request(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runner = _Runner(results=[_Run(returncode=0, stdout=_pr_json(armed=True)), _Run(returncode=0)])

    run_human_valve_action(repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:on", runner=runner)

    assert _held()
    assert _status() == "active"
    assert runner.calls == [_view_argv(), ("gh", "pr", "merge", "7", "--disable-auto")]


def test_hold_writes_no_forge_request_when_the_pull_request_is_open_and_unarmed(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runner = _Runner(results=[_Run(returncode=0, stdout=_pr_json())])

    run_human_valve_action(repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:on", runner=runner)

    assert _held()
    assert runner.calls == [_view_argv()]


def test_hold_is_refused_naming_the_merge_when_the_pull_request_already_merged(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    runner = _Runner(
        results=[_Run(returncode=0, stdout=_pr_json(state="MERGED", merge_sha="abc1234"))]
    )

    result = run_human_valve_action(
        repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:on", runner=runner
    )

    assert not _held()
    assert result["domain_error"] == "already-merged"
    assert "#7" in str(result["summary"])
    assert "abc1234" in str(result["summary"])
    assert runner.calls == [_view_argv()]


def test_hold_refusal_names_the_pull_request_even_with_no_merge_commit(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runner = _Runner(results=[_Run(returncode=0, stdout=_pr_json(state="MERGED"))])

    result = run_human_valve_action(
        repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:on", runner=runner
    )

    assert not _held()
    assert "#7" in str(result["summary"])


def test_an_unparseable_pull_request_view_reads_as_no_pull_request(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runner = _Runner(results=[_Run(returncode=0, stdout="not json")])

    run_human_valve_action(repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:on", runner=runner)

    assert _held()
    assert runner.calls == [_view_argv()]


def test_release_arms_auto_merge_with_the_journaled_merge_method(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _hold(repo)
    _journal(repo, records=[_contract_record(work_item_id=_ITEM_ID, merge_mode="squash")])
    runner = _Runner(
        results=[_Run(returncode=0, stdout=_pr_json()), *_guard_answers(), _Run(returncode=0)]
    )

    run_human_valve_action(repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:off", runner=runner)

    assert not _held()
    assert _status() == "active"
    assert runner.calls[-1] == ("gh", "pr", "merge", "7", "--squash", "--auto", "--delete-branch")


def test_the_armed_method_is_the_newest_one_this_item_journaled(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _hold(repo)
    _journal(
        repo,
        records=[
            _contract_record(work_item_id="bd-ib-other", merge_mode="squash"),
            {"stage": "dispatch-id", "work_item_id": _ITEM_ID, "integration_contract": "not-a-map"},
            _contract_record(work_item_id=_ITEM_ID, merge_mode=5),
            _contract_record(work_item_id=_ITEM_ID, merge_mode="squash"),
            _contract_record(work_item_id=_ITEM_ID, merge_mode="rebase"),
        ],
    )
    runner = _Runner(
        results=[_Run(returncode=0, stdout=_pr_json()), *_guard_answers(), _Run(returncode=0)]
    )

    run_human_valve_action(repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:off", runner=runner)

    assert runner.calls[-1] == ("gh", "pr", "merge", "7", "--rebase", "--auto", "--delete-branch")


def test_release_is_refused_and_the_hold_stands_when_no_merge_method_was_journaled(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _hold(repo)
    runner = _Runner(results=[_Run(returncode=0, stdout=_pr_json()), *_guard_answers()])

    result = run_human_valve_action(
        repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:off", runner=runner
    )

    assert _held()
    assert result["domain_error"] == "unresolved-merge-method"
    assert runner.calls[0] == _view_argv()
    # The guard passed and no arming was issued, which is what makes this a
    # method refusal rather than a guarded one.
    assert not any(call[:3] == ("gh", "pr", "merge") for call in runner.calls)


def test_release_is_refused_when_the_journaled_merge_mode_has_no_forge_flag(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _hold(repo)
    _journal(repo, records=[_contract_record(work_item_id=_ITEM_ID, merge_mode="merge")])
    runner = _Runner(results=[_Run(returncode=0, stdout=_pr_json()), *_guard_answers()])

    result = run_human_valve_action(
        repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:off", runner=runner
    )

    assert _held()
    assert result["domain_error"] == "unresolved-merge-method"


def test_a_failed_arm_is_reported_after_the_hold_was_removed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _hold(repo)
    _journal(repo, records=[_contract_record(work_item_id=_ITEM_ID, merge_mode="rebase")])
    runner = _Runner(
        results=[
            _Run(returncode=0, stdout=_pr_json()),
            *_guard_answers(),
            _Run(returncode=1, stderr="boom"),
        ]
    )

    result = run_human_valve_action(
        repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:off", runner=runner
    )

    assert not _held()
    assert result["domain_error"] == "arm-failed"
    assert "boom" in str(result["summary"])


def test_release_refuses_while_a_run_of_the_item_is_live(tmp_path: Path) -> None:
    """The v145 arm guard's first measurement: a live run means no arming.

    `SPECIFICATION/contracts.md` section "Definition-of-Done and Proof-of-Done
    stages" -> "Scripted publication and proof-head integrity" (v145) says the
    host-side hold release "MUST NOT arm while a run of the item is live". The
    hazard is not a double-write: a live run that reaches `pr_refresh` disarms
    the pull request and rebases it, so an arming written beside it either
    vanishes or survives into a head the run then pushes -- and an armed pull
    request with green checks merges on the FORGE's schedule, so the forge lands
    a tree no record names.

    The hold is asserted to STAND and the refusal to name the run, because a
    refusal that removed the label would leave the next release unguarded and a
    refusal naming no run gives an operator nothing to wait for.
    """
    repo = _repo(tmp_path)
    _hold(repo)
    _journal(repo, records=[_contract_record(work_item_id=_ITEM_ID, merge_mode="rebase")])
    runner = _Runner(
        results=[
            _Run(returncode=0, stdout=_pr_json()),
            _Run(returncode=0, stdout=_ps_json(run_ids=("01MLIVE",))),
        ]
    )

    result = run_human_valve_action(
        repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:off", runner=runner
    )

    assert _held()
    assert result["domain_error"] == "live-run"
    assert "01MLIVE" in str(result["summary"])
    assert not any(call[:3] == ("gh", "pr", "merge") for call in runner.calls)


def test_release_refuses_when_liveness_could_not_be_measured(tmp_path: Path) -> None:
    """An unanswered `fabro ps` is not a factory known to hold nothing.

    The control for the case above, and the direction that matters: an empty
    live set and an unreadable one are the same tuple, so a guard that armed on
    the second would turn the refusal into a merge and leave a record that reads
    exactly like a healthy release. The refusal says the measurement failed
    rather than naming a run, because none was observed.
    """
    repo = _repo(tmp_path)
    _hold(repo)
    _journal(repo, records=[_contract_record(work_item_id=_ITEM_ID, merge_mode="rebase")])
    runner = _Runner(
        results=[_Run(returncode=0, stdout=_pr_json()), _Run(returncode=1, stderr="no answer")]
    )

    result = run_human_valve_action(
        repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:off", runner=runner
    )

    assert _held()
    assert result["domain_error"] == "live-run"
    assert "did not answer" in str(result["summary"])
    assert not any(call[:3] == ("gh", "pr", "merge") for call in runner.calls)


def test_release_refuses_a_head_no_proof_record_names(tmp_path: Path) -> None:
    """The v145 arm guard's second measurement: only a proved head may be armed.

    The clause says the release "MUST arm only a pull request whose current head
    is named by the latest `verified` or `carried_forward` record of the item's
    latest run". Here the record names one head and the pull request carries
    another -- the state an earlier run's refresh, or a hand push, leaves -- and
    arming it would merge a tree nothing graded, indistinguishable at every
    surface from any other green merge.

    BOTH heads are named in the refusal, because an operator has to be able to
    tell which side moved before deciding whether to re-dispatch.
    """
    repo = _repo(tmp_path)
    _hold(repo)
    _journal(repo, records=[_contract_record(work_item_id=_ITEM_ID, merge_mode="rebase")])
    runner = _Runner(
        results=[
            _Run(returncode=0, stdout=_pr_json(head=_OTHER_HEAD)),
            *_guard_answers(),
        ]
    )

    result = run_human_valve_action(
        repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:off", runner=runner
    )

    assert _held()
    assert result["domain_error"] == "unproved-head"
    assert _OTHER_HEAD in str(result["summary"])
    assert _HEAD in str(result["summary"])
    assert not any(call[:3] == ("gh", "pr", "merge") for call in runner.calls)


@pytest.mark.parametrize(
    ("records", "named"),
    [
        (None, "could not be asked"),
        (json.dumps({"comments": []}), "no verified or carried_forward"),
        (_records_json(head=None), "no single full"),
    ],
)
def test_release_refuses_when_the_proved_head_could_not_be_established(
    tmp_path: Path, records: str | None, named: str
) -> None:
    """Three absences, one code, three messages -- each naming its own reading.

    A forge that would not answer, a pull request carrying no anchoring record,
    and an anchoring record naming no single head are different facts with
    different remedies, and none of them establishes a head this release may
    arm. They share the valve code because a caller routes on the code; the
    prose is the only place the missing reading is named, which is what the
    clause's "naming the measurement that failed" asks for.
    """
    repo = _repo(tmp_path)
    _hold(repo)
    _journal(repo, records=[_contract_record(work_item_id=_ITEM_ID, merge_mode="rebase")])
    answers = (
        [_Run(returncode=0, stdout=_ps_json()), _Run(returncode=1, stderr="unreadable")]
        if records is None
        else _guard_answers(records=records)
    )
    runner = _Runner(results=[_Run(returncode=0, stdout=_pr_json()), *answers])

    result = run_human_valve_action(
        repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:off", runner=runner
    )

    assert _held()
    assert result["domain_error"] == "unproved-head"
    assert named in str(result["summary"])
    assert not any(call[:3] == ("gh", "pr", "merge") for call in runner.calls)


def test_a_carried_forward_record_supersedes_the_verified_head_it_carries(
    tmp_path: Path,
) -> None:
    """The LATEST anchor decides, by position and across both verdicts.

    A refresh that carried a proof forward names the NEW head in a
    `carried_forward` record while the older `verified` record still names the
    pre-refresh one. Reading per verdict would let that older record win and
    refuse a release of exactly the head the carry-forward proved -- so the
    positive case is the one that matters here, not another refusal.
    """
    repo = _repo(tmp_path)
    _hold(repo)
    _journal(repo, records=[_contract_record(work_item_id=_ITEM_ID, merge_mode="rebase")])
    chained = json.dumps(
        {
            "comments": [
                {
                    "body": (
                        f"Proof of Done — verified — run r — 2026-10-15T00:00:00Z\n"
                        f"Publish-branch head: {_OTHER_HEAD}\n"
                    ),
                    "url": "https://forge.invalid/c/1",
                },
                {
                    "body": (
                        f"Proof of Done — carried_forward — run r — 2026-10-15T01:00:00Z\n"
                        f"Publish-branch head: {_HEAD}\n"
                    ),
                    "url": "https://forge.invalid/c/2",
                },
            ]
        }
    )
    runner = _Runner(
        results=[
            _Run(returncode=0, stdout=_pr_json()),
            *_guard_answers(records=chained),
            _Run(returncode=0),
        ]
    )

    result = run_human_valve_action(
        repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:off", runner=runner
    )

    assert result["status"] == "green"
    assert not _held()
    assert runner.calls[-1] == ("gh", "pr", "merge", "7", "--rebase", "--auto", "--delete-branch")


def test_a_failed_disarm_is_reported_after_the_hold_was_written(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runner = _Runner(
        results=[
            _Run(returncode=0, stdout=_pr_json(armed=True)),
            _Run(returncode=1, stderr="nope"),
        ]
    )

    result = run_human_valve_action(
        repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:on", runner=runner
    )

    assert _held()
    assert result["domain_error"] == "disarm-failed"
    assert "nope" in str(result["summary"])


def test_a_value_other_than_on_or_off_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    runner = _Runner(results=[])

    result = run_human_valve_action(
        repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:maybe", runner=runner
    )

    assert not _held()
    assert result["domain_error"] == "invalid-action-id"
    assert runner.calls == []


def test_the_default_runner_shells_out_to_gh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    valve = importlib.import_module(_VALVE_MODULE)
    calls: list[tuple[object, ...]] = []

    def fake_run(*args: object, **kwargs: object) -> _Run:
        calls.append(args)
        assert kwargs["cwd"] == repo
        assert kwargs["check"] is False
        assert kwargs["capture_output"] is True
        return _Run(returncode=1)

    monkeypatch.setattr(valve, "run", fake_run)

    run_human_valve_action(repo=repo, action_id=f"set-merge-hold:{_ITEM_ID}:on")

    assert _held()
    assert calls[0][0] == _view_argv()
