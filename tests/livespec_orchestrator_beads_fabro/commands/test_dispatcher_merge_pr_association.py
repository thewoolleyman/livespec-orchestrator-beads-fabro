"""Tests for resolving the recorded pull request from the merge sha.

The Dispatcher discovers a pull request BY BRANCH NAME, which is a
different identity from "the pull request whose commits carry the merge
sha". These tests pin the correction that closes the gap, and — just as
importantly — pin the cases where the correction deliberately DECLINES to
act (an ambiguous, absent, or unreachable association), leaving the
acceptance pass's cross-check to route the mismatch rather than replacing
a detectable wrong answer with an undetectable guess.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    FabroRunResult,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
    build_plan,
)


def _module() -> ModuleType:
    module_path = (
        Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
        / "_dispatcher_merge_pr_association.py"
    )
    assert module_path.is_file()
    return importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_merge_pr_association"
    )


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _ScriptedRunner:
    """Returns a canned result per argv prefix match; everything else exit 0."""

    script: list[tuple[str, CommandResult]] = field(default_factory=list)
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
        joined = " ".join(argv)
        for needle, result in self.script:
            if needle in joined:
                return result
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _FakeLauncher:
    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: object,
        journal: object,
    ) -> FabroRunResult:
        _ = (plan, runner, journal)
        return FabroRunResult(command=CommandResult(exit_code=0, stdout="", stderr=""))


def _api_result(*, payload: object) -> CommandResult:
    return CommandResult(exit_code=0, stdout=json.dumps(payload), stderr="")


def _merged_view(*, number: int = 1807, merge_sha: str | None = "abc123") -> PrView:
    return PrView(
        number=number,
        state="MERGED",
        auto_merge_armed=True,
        merge_state_status="CLEAN",
        merge_sha=merge_sha,
    )


def _resolve(
    *, tmp_path: Path, runner: _ScriptedRunner, merged: PrView
) -> tuple[PrView, _RecordingJournal]:
    module = _module()
    journal = _RecordingJournal()
    view = module.pr_view_for_merge_sha(
        repo=tmp_path,
        work_item_id="bd-ib-llev",
        merged=merged,
        runner=runner,
        journal=journal,
    )
    return view, journal


# ---------------------------------------------------------------------------
# associated_pr_numbers_for_merge
# ---------------------------------------------------------------------------


def test_association_lookup_asks_the_forge_which_prs_contain_the_commit(tmp_path: Path) -> None:
    module = _module()
    runner = _ScriptedRunner(
        script=[("commits/abc123/pulls", _api_result(payload=[{"number": 1807}]))]
    )

    assert module.associated_pr_numbers_for_merge(
        repo=tmp_path, merge_sha="abc123", runner=runner
    ) == (1807,)
    assert runner.calls[0][:2] == ["gh", "api"]
    assert "/repos/{owner}/{repo}/commits/abc123/pulls" in runner.calls[0]


def test_association_lookup_is_none_when_the_forge_call_fails(tmp_path: Path) -> None:
    # None is "could not ask", NOT "no PR contains this commit" — the
    # caller must not read a failed call as evidence about the commit.
    module = _module()
    runner = _ScriptedRunner(
        script=[("commits/abc123/pulls", CommandResult(exit_code=1, stdout="", stderr="boom"))]
    )

    assert (
        module.associated_pr_numbers_for_merge(repo=tmp_path, merge_sha="abc123", runner=runner)
        is None
    )


def test_association_lookup_is_none_when_the_payload_is_unreadable(tmp_path: Path) -> None:
    module = _module()
    unparseable = _ScriptedRunner(
        script=[("commits/abc123/pulls", CommandResult(exit_code=0, stdout="{[", stderr=""))]
    )
    not_a_list = _ScriptedRunner(
        script=[("commits/abc123/pulls", _api_result(payload={"number": 1807}))]
    )

    assert (
        module.associated_pr_numbers_for_merge(
            repo=tmp_path, merge_sha="abc123", runner=unparseable
        )
        is None
    )
    assert (
        module.associated_pr_numbers_for_merge(repo=tmp_path, merge_sha="abc123", runner=not_a_list)
        is None
    )


def test_association_lookup_skips_entries_that_carry_no_usable_number(tmp_path: Path) -> None:
    module = _module()
    runner = _ScriptedRunner(
        script=[
            (
                "commits/abc123/pulls",
                _api_result(
                    payload=["not-a-dict", {"number": "1807"}, {"number": True}, {"number": 1809}]
                ),
            )
        ]
    )

    assert module.associated_pr_numbers_for_merge(
        repo=tmp_path, merge_sha="abc123", runner=runner
    ) == (1809,)


# ---------------------------------------------------------------------------
# pr_view_for_merge_sha
# ---------------------------------------------------------------------------


def test_recording_is_untouched_and_unasked_when_there_is_no_merge_sha(tmp_path: Path) -> None:
    runner = _ScriptedRunner()

    view, journal = _resolve(tmp_path=tmp_path, runner=runner, merged=_merged_view(merge_sha=None))

    assert view.number == 1807
    assert runner.calls == []
    assert journal.records == []


def test_recording_is_confirmed_when_the_branch_pr_contains_the_merge_sha(tmp_path: Path) -> None:
    runner = _ScriptedRunner(
        script=[("commits/abc123/pulls", _api_result(payload=[{"number": 1807}]))]
    )

    view, journal = _resolve(tmp_path=tmp_path, runner=runner, merged=_merged_view())

    assert view.number == 1807
    assert journal.records[-1]["stage"] == "pr-merge-sha-recording"
    assert journal.records[-1]["outcome"] == "confirmed"
    assert journal.records[-1]["associated_pr_numbers"] == [1807]


def test_recording_is_corrected_to_the_pr_that_contains_the_merge_sha(tmp_path: Path) -> None:
    runner = _ScriptedRunner(
        script=[("commits/abc123/pulls", _api_result(payload=[{"number": 1809}]))]
    )

    view, journal = _resolve(tmp_path=tmp_path, runner=runner, merged=_merged_view())

    assert view.number == 1809
    # Everything else about the merged view survives the correction.
    assert (view.state, view.merge_sha) == ("MERGED", "abc123")
    assert journal.records[-1]["outcome"] == "corrected"
    assert journal.records[-1]["branch_pr_number"] == 1807


def test_recording_stands_when_the_forge_names_several_candidate_prs(tmp_path: Path) -> None:
    # Ambiguity is left for the acceptance cross-check to route; picking one
    # would trade a DETECTABLE wrong answer for an undetectable one.
    runner = _ScriptedRunner(
        script=[("commits/abc123/pulls", _api_result(payload=[{"number": 1809}, {"number": 1811}]))]
    )

    view, journal = _resolve(tmp_path=tmp_path, runner=runner, merged=_merged_view())

    assert view.number == 1807
    assert journal.records[-1]["outcome"] == "uncorrected"
    assert journal.records[-1]["associated_pr_numbers"] == [1809, 1811]


def test_recording_stands_when_the_forge_associates_no_pr_with_the_commit(tmp_path: Path) -> None:
    runner = _ScriptedRunner(script=[("commits/abc123/pulls", _api_result(payload=[]))])

    view, journal = _resolve(tmp_path=tmp_path, runner=runner, merged=_merged_view())

    assert view.number == 1807
    assert journal.records[-1]["outcome"] == "uncorrected"
    assert journal.records[-1]["associated_pr_numbers"] == []


def test_recording_stands_and_says_so_when_the_forge_cannot_be_reached(tmp_path: Path) -> None:
    runner = _ScriptedRunner(
        script=[("commits/abc123/pulls", CommandResult(exit_code=1, stdout="", stderr="offline"))]
    )

    view, journal = _resolve(tmp_path=tmp_path, runner=runner, merged=_merged_view())

    assert view.number == 1807
    assert journal.records[-1]["outcome"] == "unavailable"
    assert journal.records[-1]["merge_sha"] == "abc123"


# ---------------------------------------------------------------------------
# Engine wiring: the OUTCOME carries the corrected number
# ---------------------------------------------------------------------------


def test_dispatch_outcome_records_the_pr_that_contains_the_merge_sha(tmp_path: Path) -> None:
    pr_view = _api_result(
        payload={
            "number": 1807,
            "state": "MERGED",
            "autoMergeRequest": {"enabledAt": "2026-08-29T00:00:00Z"},
            "mergeStateStatus": "CLEAN",
            "mergeCommit": {"oid": "abc123"},
            "statusCheckRollup": [],
        }
    )
    runner = _ScriptedRunner(
        script=[
            ("commits/abc123/pulls", _api_result(payload=[{"number": 1809}])),
            ("gh pr view", pr_view),
        ]
    )
    journal = _RecordingJournal()

    outcome = run_dispatch(
        plan=build_plan(
            repo=tmp_path,
            work_item_id="bd-ib-llev",
            workflow_toml=tmp_path / "wf.toml",
            goal_file=tmp_path / "goal.md",
            fabro_bin="fabro",
            janitor=None,
            janitor_checkout=tmp_path / "janitor-co",
        ),
        runner=runner,
        journal=journal,
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=1, interval_seconds=0.0),
        fabro_launcher=_FakeLauncher(),
    )

    assert outcome.status == "green"
    assert outcome.merge_sha == "abc123"
    # The branch view said #1807; the forge says #1809 carries abc123.
    assert outcome.pr_number == 1809
    assert "pr-merge-sha-recording" in [record.get("stage") for record in journal.records]
