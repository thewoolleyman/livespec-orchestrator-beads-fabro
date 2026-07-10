"""Tests for the staged self-update + canary (work-item livespec-impl-beads-ddu).

Covers `_dispatcher_self_update` (the PURE self-merge detection + canary
verdict + promotion decision) and its wiring into
`dispatcher._self_update_after_merge`. The load-bearing safety property
under test (the dark-factory operability gate): a self-merge whose canary
PASSES promotes the staged candidate to the active pinned copy; a
self-merge whose canary FAILS keeps the last-known-good pinned copy and
ALARMS — it NEVER promotes a broken self-update. The fail-open invariant
mirrors the cost gate / notifier: the self-update stage runs after the
verdict and a probe / canary error is journaled and swallowed, never
raised.

Self-machinery hang-guard: the CANARY is MOCKED in every test — no test
ever launches a real fabro run (the canary is a cheap, side-effect-free
self-check, driven here through an injected `CommandRunner` fake / a
scripted exit code). The credential-hygiene assertion is direct: the
alarm body ships ONLY the work-item id, the outcome class, and the run
id.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    DISPATCHER_SCRIPT_PREFIXES,
    SELF_UPDATE_BREACH_CLASS,
    CanaryVerdict,
    PromotionDecision,
    canary_self_check_argv,
    canary_verdict,
    is_self_merge,
    parse_pr_files,
    pr_files_argv,
    promotion_decision,
)

# Importing the module-private wiring helpers directly (the test tier
# verifies the self-update wiring); importing them avoids the SLF001
# attribute-access ban while keeping the names addressable, the same
# pattern test_dispatcher_notify uses for the notify internals.
from livespec_orchestrator_beads_fabro.commands.dispatcher import (
    _candidate_dispatcher_bin,  # pyright: ignore[reportPrivateUsage]
    _resolve_merged_paths,  # pyright: ignore[reportPrivateUsage]
    _self_update_after_merge,  # pyright: ignore[reportPrivateUsage]
    _self_update_after_verdict,  # pyright: ignore[reportPrivateUsage]
)

# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _ScriptedRunner:
    """A `CommandRunner` that replays one canned result and records the argv."""

    results: list[CommandResult]
    seen_argv: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        self.seen_argv.append(list(argv))
        return self.results.pop(0)


@dataclass(kw_only=True)
class _RaisingRunner:
    """A `CommandRunner` that raises — drives the fail-open supervisor."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env)
        raise RuntimeError("canary subprocess blew up")


@dataclass(kw_only=True)
class _RecordingPoster:
    """A `NotifyPoster` fake that records every alarm body it is handed."""

    bodies: list[str] = field(default_factory=list)

    def post(self, *, url: str, body: str, title: str, timeout_seconds: float) -> bool:
        _ = (url, title, timeout_seconds)
        self.bodies.append(body)
        return True


# A merged-file list that touches the dispatcher's OWN command package.
_SELF_MERGE_PATHS = (
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_engine.py",
    "tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_engine.py",
)

# A merged-file list that touches only unrelated docs / spec.
_NON_SELF_MERGE_PATHS = (
    "SPECIFICATION/spec.md",
    "README.md",
)


# ---------------------------------------------------------------------------
# Pure layer: is_self_merge
# ---------------------------------------------------------------------------


def test_self_merge_when_a_path_touches_the_dispatcher_command_package() -> None:
    assert is_self_merge(merged_paths=_SELF_MERGE_PATHS) is True


def test_self_merge_when_a_short_path_touches_dispatcher_engine() -> None:
    assert is_self_merge(merged_paths=("commands/_dispatcher_engine.py",)) is True


def test_self_merge_when_a_short_path_touches_dispatcher_entrypoint() -> None:
    assert is_self_merge(merged_paths=("commands/dispatcher.py",)) is True


def test_self_merge_when_a_path_touches_the_bin_wrapper() -> None:
    assert is_self_merge(merged_paths=(".claude-plugin/scripts/bin/dispatcher.py",)) is True


def test_self_merge_when_a_path_equals_the_bootstrap_file_prefix() -> None:
    # `_bootstrap.py` is a FILE prefix (not a directory), so it matches by
    # equality, never by startswith — covering the file-prefix branch.
    assert is_self_merge(merged_paths=(".claude-plugin/scripts/_bootstrap.py",)) is True


def test_not_a_self_merge_when_only_docs_and_spec_change() -> None:
    assert is_self_merge(merged_paths=_NON_SELF_MERGE_PATHS) is False


def test_not_a_self_merge_for_an_empty_path_list() -> None:
    # An unobservable / empty file list must NEVER force a stage-and-canary
    # (the engine routes a missing list as its own degraded path).
    assert is_self_merge(merged_paths=()) is False


def test_not_a_self_merge_for_a_blank_path_string() -> None:
    # A blank entry is skipped, never treated as the dispatcher's code.
    assert is_self_merge(merged_paths=("   ",)) is False


def test_bin_file_prefix_does_not_match_a_mere_startswith() -> None:
    # `_bootstrap.py` is a FILE prefix: a path that merely STARTS WITH the
    # string but is not equal to it must NOT count (the file-prefix branch
    # uses equality, not startswith).
    assert is_self_merge(merged_paths=(".claude-plugin/scripts/_bootstrap.py.bak",)) is False


def test_dispatcher_script_prefixes_are_all_repo_relative_posix() -> None:
    # Guard the prefix table shape: repo-relative, POSIX `/`, no leading
    # slash, and the directory prefixes end in `/` (so nested files match).
    for prefix in DISPATCHER_SCRIPT_PREFIXES:
        assert not prefix.startswith("/")
        assert "\\" not in prefix


# ---------------------------------------------------------------------------
# Pure layer: canary argv + verdict
# ---------------------------------------------------------------------------


def test_canary_self_check_argv_runs_candidate_ledger_check_against_scratch() -> None:
    argv = canary_self_check_argv(
        candidate_bin="/pin/candidate/bin/dispatcher.py",
        scratch_root="/tmp/canary-scratch",
    )
    # The canary is the candidate's OWN ledger-check against a throwaway
    # project root — never a fabro run (the self-machinery hang-guard).
    assert argv == [
        "python3",
        "/pin/candidate/bin/dispatcher.py",
        "ledger-check",
        "--project-root",
        "/tmp/canary-scratch",
        "--json",
    ]
    assert "fabro" not in argv
    assert "run" not in argv


def test_canary_verdict_pass_on_clean_exit() -> None:
    assert CanaryVerdict.PASS.value == "pass"
    assert canary_verdict(exit_code=0) is CanaryVerdict.PASS


def test_canary_verdict_fail_on_nonzero_exit() -> None:
    assert CanaryVerdict.FAIL.value == "fail"
    assert canary_verdict(exit_code=1) is CanaryVerdict.FAIL


def test_canary_verdict_fail_on_timeout_exit() -> None:
    # The ShellCommandRunner converts a timed-out canary into exit 124, so
    # a HANGING candidate fails the canary rather than stalling promotion.
    assert canary_verdict(exit_code=124) is CanaryVerdict.FAIL


# ---------------------------------------------------------------------------
# Pure layer: promotion decision
# ---------------------------------------------------------------------------


def test_promotion_decision_promotes_on_pass_without_alarm() -> None:
    decision = promotion_decision(verdict=CanaryVerdict.PASS)
    assert decision == PromotionDecision(
        promote=True,
        alarm=False,
        reason=decision.reason,
    )
    assert decision.promote is True
    assert decision.alarm is False


def test_promotion_decision_keeps_and_alarms_on_fail() -> None:
    decision = promotion_decision(verdict=CanaryVerdict.FAIL)
    # Fail-closed: a failed canary NEVER promotes, and it alarms.
    assert decision.promote is False
    assert decision.alarm is True


# ---------------------------------------------------------------------------
# Wiring: the staged-self-update stage in dispatcher.py
# ---------------------------------------------------------------------------


def test_wiring_promotes_on_passing_canary_and_does_not_alarm() -> None:
    journal = _RecordingJournal()
    poster = _RecordingPoster()
    runner = _ScriptedRunner(
        results=[
            CommandResult(exit_code=0, stdout="true\n", stderr=""),
            CommandResult(
                exit_code=0,
                stdout="https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro",
                stderr="",
            ),
            CommandResult(exit_code=0, stdout="[]", stderr=""),
        ],
    )
    _self_update_after_merge(
        work_item_id="livespec-impl-beads-ddu",
        merged_paths=_SELF_MERGE_PATHS,
        candidate_bin="/pin/candidate/bin/dispatcher.py",
        scratch_root="/tmp/canary-scratch",
        repo=Path("/data/projects/livespec-orchestrator-beads-fabro"),
        journal=journal,
        runner=runner,
        poster=poster,
    )
    # The canary ran (the candidate's ledger-check, never fabro).
    assert runner.seen_argv[-1] == canary_self_check_argv(
        candidate_bin="/pin/candidate/bin/dispatcher.py",
        scratch_root="/tmp/canary-scratch",
    )
    # Promotion was journaled, no alarm fired.
    stages = [record["stage"] for record in journal.records]
    assert "self-update-promoted" in stages
    assert poster.bodies == []


def test_wiring_keeps_last_known_good_and_alarms_on_failing_canary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The alarm POSTs only when an ntfy topic is configured (an unset topic
    # makes the notifier a silent no-op); configure the dedicated dispatcher
    # topic so the failing-canary alarm reaches the recording poster.
    monkeypatch.setenv("CLAUDE_NTFY_DISPATCHER_TOPIC", "livespec-dispatcher-test")
    journal = _RecordingJournal()
    poster = _RecordingPoster()
    runner = _ScriptedRunner(
        results=[
            CommandResult(exit_code=0, stdout="true\n", stderr=""),
            CommandResult(
                exit_code=0,
                stdout="https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro",
                stderr="",
            ),
            CommandResult(exit_code=1, stdout="", stderr="boom"),
        ],
    )
    _self_update_after_merge(
        work_item_id="livespec-impl-beads-ddu",
        merged_paths=_SELF_MERGE_PATHS,
        candidate_bin="/pin/candidate/bin/dispatcher.py",
        scratch_root="/tmp/canary-scratch",
        repo=Path("/data/projects/livespec-orchestrator-beads-fabro"),
        journal=journal,
        runner=runner,
        poster=poster,
    )
    stages = [record["stage"] for record in journal.records]
    # Fail-closed: kept the last-known-good copy, did NOT promote.
    assert "self-update-kept-last-known-good" in stages
    assert "self-update-promoted" not in stages
    # An alarm fired through the notify seam.
    assert len(poster.bodies) == 1
    body = poster.bodies[0]
    # Credential hygiene: ONLY the work-item id, the breach class, and the
    # run id — never a path, stderr blob, or candidate-bin string.
    assert "livespec-impl-beads-ddu" in body
    assert SELF_UPDATE_BREACH_CLASS in body
    assert "/pin/candidate" not in body
    assert "boom" not in body


def test_wiring_skips_when_the_merge_is_not_a_self_merge() -> None:
    journal = _RecordingJournal()
    poster = _RecordingPoster()
    runner = _ScriptedRunner(
        results=[
            CommandResult(exit_code=0, stdout="true\n", stderr=""),
            CommandResult(
                exit_code=0,
                stdout="https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro",
                stderr="",
            ),
        ],
    )
    _self_update_after_merge(
        work_item_id="livespec-impl-beads-ddu",
        merged_paths=_NON_SELF_MERGE_PATHS,
        candidate_bin="/pin/candidate/bin/dispatcher.py",
        scratch_root="/tmp/canary-scratch",
        repo=Path("/data/projects/livespec-orchestrator-beads-fabro"),
        journal=journal,
        runner=runner,
        poster=poster,
    )
    # Not a self-merge: the canary never ran, nothing promoted, no alarm.
    assert (
        canary_self_check_argv(
            candidate_bin="/pin/candidate/bin/dispatcher.py",
            scratch_root="/tmp/canary-scratch",
        )
        not in runner.seen_argv
    )
    stages = [record["stage"] for record in journal.records]
    assert "self-update-skipped" in stages
    assert "self-update-promoted" not in stages
    assert poster.bodies == []


def test_wiring_is_fail_open_when_the_canary_runner_raises() -> None:
    journal = _RecordingJournal()
    poster = _RecordingPoster()
    # The runner raises mid-canary: the fail-open supervisor must journal
    # `self-update-error` and SWALLOW it — never re-raise (the verdict is
    # already final; the self-update stage can never crash the dispatcher).
    _self_update_after_merge(
        work_item_id="livespec-impl-beads-ddu",
        merged_paths=_SELF_MERGE_PATHS,
        candidate_bin="/pin/candidate/bin/dispatcher.py",
        scratch_root="/tmp/canary-scratch",
        repo=Path("/data/projects/livespec-orchestrator-beads-fabro"),
        journal=journal,
        runner=_RaisingRunner(),
        poster=poster,
    )
    stages = [record["stage"] for record in journal.records]
    assert "self-update-error" in stages
    # Nothing promoted; the error did not masquerade as a promotion.
    assert "self-update-promoted" not in stages


def test_wiring_default_runner_and_poster_are_not_required() -> None:
    # The wiring resolves a production `ShellCommandRunner` / `HttpNotifyPoster`
    # when none is injected (mirroring `_cost_gate_after_verdict`). Drive the
    # not-a-self-merge path so the defaults are constructed but no real
    # subprocess / network call happens.
    journal = _RecordingJournal()
    _self_update_after_merge(
        work_item_id="livespec-impl-beads-ddu",
        merged_paths=_NON_SELF_MERGE_PATHS,
        candidate_bin="/pin/candidate/bin/dispatcher.py",
        scratch_root="/tmp/canary-scratch",
        repo=Path("/data/projects/livespec-orchestrator-beads-fabro"),
        journal=journal,
    )
    stages = [record["stage"] for record in journal.records]
    assert "self-update-skipped" in stages


# ---------------------------------------------------------------------------
# Pure layer: pr-files argv + parser
# ---------------------------------------------------------------------------


def test_pr_files_argv_reads_the_merged_prs_changed_files() -> None:
    assert pr_files_argv(branch="feat/ddu") == [
        "gh",
        "pr",
        "view",
        "feat/ddu",
        "--json",
        "files",
    ]


def test_parse_pr_files_extracts_repo_relative_paths() -> None:
    stdout = json.dumps(
        {
            "files": [
                {
                    "path": ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/dispatcher.py"
                },
                {"path": "README.md"},
            ]
        }
    )
    assert parse_pr_files(stdout=stdout) == (
        ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/dispatcher.py",
        "README.md",
    )


def test_parse_pr_files_no_signal_on_unparseable_payload() -> None:
    assert parse_pr_files(stdout="not json") == ()


def test_parse_pr_files_no_signal_on_non_dict_payload() -> None:
    assert parse_pr_files(stdout=json.dumps([1, 2, 3])) == ()


def test_parse_pr_files_no_signal_when_files_key_is_not_a_list() -> None:
    assert parse_pr_files(stdout=json.dumps({"files": "oops"})) == ()


def test_parse_pr_files_skips_non_dict_and_pathless_and_blank_entries() -> None:
    stdout = json.dumps(
        {
            "files": [
                "not-a-dict",
                {"noPathKey": "x"},
                {"path": ""},
                {"path": 7},
                {"path": "kept.py"},
            ]
        }
    )
    assert parse_pr_files(stdout=stdout) == ("kept.py",)


# ---------------------------------------------------------------------------
# Wiring: the wave-level _self_update_after_verdict stage
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class _QueueRunner:
    """A `CommandRunner` that replays a queue of canned results in order."""

    results: list[CommandResult]
    seen_argv: list[list[str]] = field(default_factory=list)
    seen_envs: list[dict[str, str] | None] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds)
        self.seen_argv.append(list(argv))
        self.seen_envs.append(env)
        return self.results.pop(0)


def _outcome(*, status: str, pr_number: int | None) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="livespec-impl-beads-ddu",
        status=status,
        stage="done",
        pr_number=pr_number,
        merge_sha="feed01",
        detail="x",
    )


def test_candidate_dispatcher_bin_points_at_the_primarys_bin_wrapper() -> None:
    # Resolved off the package-root walk; it must terminate at the bin
    # wrapper the next dispatcher invocation would run.
    assert (
        _candidate_dispatcher_bin().as_posix().endswith(".claude-plugin/scripts/bin/dispatcher.py")
    )


def test_resolve_merged_paths_reads_branch_then_pr_files() -> None:
    runner = _QueueRunner(
        results=[
            CommandResult(exit_code=0, stdout="feat/ddu\n", stderr=""),
            CommandResult(
                exit_code=0,
                stdout=json.dumps({"files": [{"path": "README.md"}]}),
                stderr="",
            ),
        ]
    )
    paths = _resolve_merged_paths(repo=Path("/repo"), runner=runner)
    assert paths == ("README.md",)
    # The pr-files query used the branch the rev-parse reported.
    assert runner.seen_argv[1] == pr_files_argv(branch="feat/ddu")


def test_resolve_merged_paths_no_signal_when_gh_fails() -> None:
    runner = _QueueRunner(
        results=[
            CommandResult(exit_code=0, stdout="master\n", stderr=""),
            CommandResult(exit_code=1, stdout="", stderr="gh boom"),
        ]
    )
    assert _resolve_merged_paths(repo=Path("/repo"), runner=runner) == ()


def test_resolve_merged_paths_falls_back_to_master_when_rev_parse_fails() -> None:
    runner = _QueueRunner(
        results=[
            CommandResult(exit_code=1, stdout="", stderr="detached"),
            CommandResult(exit_code=0, stdout=json.dumps({"files": []}), stderr=""),
        ]
    )
    _ = _resolve_merged_paths(repo=Path("/repo"), runner=runner)
    assert runner.seen_argv[1] == pr_files_argv(branch="master")


def test_after_verdict_skips_non_green_and_pr_less_outcomes() -> None:
    journal = _RecordingJournal()
    poster = _RecordingPoster()
    runner = _QueueRunner(results=[])  # never consulted: nothing to gate
    _self_update_after_verdict(
        outcomes=[
            _outcome(status="failed", pr_number=7),
            _outcome(status="green", pr_number=None),
        ],
        repo=Path("/repo"),
        journal=journal,
        runner=runner,
        poster=poster,
    )
    assert runner.seen_argv == []
    assert journal.records == []


def test_after_verdict_refreshes_github_token_for_self_update_subprocesses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The self-update PR probe and canary do not inherit stale GH_TOKEN."""
    monkeypatch.setenv("CLAUDE_NTFY_DISPATCHER_TOPIC", "livespec-dispatcher-test")
    self_merge_files = json.dumps(
        {
            "files": [
                {
                    "path": ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/dispatcher.py"
                }
            ]
        }
    )
    runner = _QueueRunner(
        results=[
            CommandResult(exit_code=0, stdout="feat/ddu\n", stderr=""),
            CommandResult(exit_code=0, stdout=self_merge_files, stderr=""),
            CommandResult(exit_code=0, stdout="true\n", stderr=""),
            CommandResult(
                exit_code=0,
                stdout="https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro",
                stderr="",
            ),
            CommandResult(exit_code=1, stdout="", stderr="canary crashed"),
        ]
    )
    minted = iter(["tok-1", "tok-2", "tok-3", "tok-4", "tok-5"])
    _self_update_after_verdict(
        outcomes=[_outcome(status="green", pr_number=42)],
        repo=tmp_path,
        journal=_RecordingJournal(),
        runner=runner,
        poster=_RecordingPoster(),
        token_supplier=lambda: next(minted),
    )
    assert all(env is not None for env in runner.seen_envs)
    assert [env["GH_TOKEN"] for env in runner.seen_envs if env is not None] == [
        "tok-1",
        "tok-2",
        "tok-3",
        "tok-4",
        "tok-5",
    ]


def test_after_verdict_default_runner_fails_closed_on_github_supplier_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unresolvable provider accessor never falls back to ambient GH_TOKEN."""
    runner = _QueueRunner(results=[])
    monkeypatch.setattr(dispatcher, "ShellCommandRunner", lambda: runner)
    monkeypatch.setattr(dispatcher, "_github_token_supplier", lambda: "missing app env")
    journal = _RecordingJournal()
    _self_update_after_verdict(
        outcomes=[_outcome(status="green", pr_number=42)],
        repo=tmp_path,
        journal=journal,
        poster=_RecordingPoster(),
    )
    assert runner.seen_argv == []
    assert [record["stage"] for record in journal.records] == ["self-update-skipped"]


def test_after_verdict_runs_the_gate_for_a_green_pr_self_merge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_NTFY_DISPATCHER_TOPIC", "livespec-dispatcher-test")
    journal = _RecordingJournal()
    poster = _RecordingPoster()
    self_merge_files = json.dumps(
        {
            "files": [
                {
                    "path": ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/dispatcher.py"
                }
            ]
        }
    )
    # rev-parse -> pr files (a self-merge) -> a FAILING canary.
    runner = _QueueRunner(
        results=[
            CommandResult(exit_code=0, stdout="feat/ddu\n", stderr=""),
            CommandResult(exit_code=0, stdout=self_merge_files, stderr=""),
            CommandResult(exit_code=0, stdout="true\n", stderr=""),
            CommandResult(
                exit_code=0,
                stdout="https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro",
                stderr="",
            ),
            CommandResult(exit_code=1, stdout="", stderr="canary crashed"),
        ]
    )
    _self_update_after_verdict(
        outcomes=[_outcome(status="green", pr_number=42)],
        repo=tmp_path,
        journal=journal,
        runner=runner,
        poster=poster,
    )
    stages = [record["stage"] for record in journal.records]
    # The self-merge canary failed -> kept the last-known-good copy + alarmed.
    assert "self-update-kept-last-known-good" in stages
    assert "self-update-promoted" not in stages
    assert len(poster.bodies) == 1


def test_after_verdict_defaults_runner_and_poster() -> None:
    # No injected seams: the not-green outcome short-circuits before any
    # default seam is exercised, so no real subprocess / network happens.
    journal = _RecordingJournal()
    _self_update_after_verdict(
        outcomes=[_outcome(status="failed", pr_number=None)],
        repo=Path("/repo"),
        journal=journal,
    )
    assert journal.records == []
