"""Integration-tier binding for Scenario 130's Fabro currency admission."""

from __future__ import annotations

import argparse
import importlib
import json
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_loop_command,
    _dispatcher_pre_dispatch_wall,
    _dispatcher_run_commands,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency_gate import (
    FabroCurrencyDecision,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_fabro_currency_gate.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency_gate"
_SERVING_COMMIT = "abcdef1234567890"


@dataclass(kw_only=True)
class _Runner:
    results: list[CommandResult]
    calls: list[list[str]]

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
        return self.results.pop(0)


def _command(*, stdout: str, exit_code: int = 0, stderr: str = "") -> CommandResult:
    return CommandResult(exit_code=exit_code, stdout=stdout, stderr=stderr)


def _releases(*, records: list[dict[str, object]]) -> str:
    return json.dumps([records])


def _none(**_kwargs: object) -> None:
    return None


def test_an_out_of_window_base_refuses_with_complete_publication_evidence(
    tmp_path: Path,
) -> None:
    """Publication time alone chooses the base and proves the 30-day breach."""
    assert _MODULE_PATH.is_file()
    gate = importlib.import_module(_MODULE_NAME)
    runner = _Runner(
        results=[
            _command(stdout=f"fabro 0.300.0 ({_SERVING_COMMIT} 2026-08-02)\n"),
            _command(
                stdout=_releases(
                    records=[
                        {
                            "tag_name": "v100.0.0-draft",
                            "published_at": None,
                            "draft": True,
                            "prerelease": True,
                        },
                        {
                            "tag_name": "v100.0.0-rc.1",
                            "published_at": "2026-10-09T00:00:00Z",
                            "draft": True,
                            "prerelease": True,
                        },
                        {
                            "tag_name": "v99.0.0",
                            "published_at": "2026-08-01T00:00:00Z",
                            "draft": False,
                            "prerelease": False,
                        },
                        {
                            "tag_name": "v1.0.0-nightly.0",
                            "published_at": "2026-09-01T00:00:00Z",
                            "draft": False,
                            "prerelease": True,
                        },
                    ]
                )
            ),
            _command(stdout='{"status": "diverged"}'),
            _command(stdout='{"status": "ahead"}'),
        ],
        calls=[],
    )

    decision = gate.fabro_currency_admission(
        target=FactoryTarget(name="hp", server="https://factory.example", dev_token=None),
        fabro_bin="/opt/fabro-hp",
        repo=tmp_path,
        runner=runner,
        now=datetime(2026, 10, 10, tzinfo=timezone.utc),
        cache_path=tmp_path / "release-observation.json",
    )

    assert decision.admitted is False
    assert decision.message == (
        "ERROR: Fabro currency admission refused factory hp: serving integration commit "
        "abcdef1234567890 resolves to base v99.0.0 published 2026-08-01T00:00:00Z; "
        "newest observed release v1.0.0-nightly.0 was published 2026-09-01T00:00:00Z; "
        "release metadata was observed 2026-10-10T00:00:00Z; the base is more than "
        "30 calendar days behind the newest release. Rebuild factory-integration on an "
        "eligible published fabro-sh/fabro release, re-pin factory hp, and retry dispatch.\n"
    )
    assert runner.calls == [
        ["/opt/fabro-hp", "--version"],
        [
            "gh",
            "api",
            "--paginate",
            "--slurp",
            "repos/fabro-sh/fabro/releases?per_page=100",
        ],
        [
            "gh",
            "api",
            "repos/fabro-sh/fabro/compare/v1.0.0-nightly.0...abcdef1234567890",
        ],
        [
            "gh",
            "api",
            "repos/fabro-sh/fabro/compare/v99.0.0...abcdef1234567890",
        ],
    ]


def test_a_serving_commit_without_a_published_release_ancestor_is_refused(
    tmp_path: Path,
) -> None:
    runner = _Runner(
        results=[
            _command(stdout=f"fabro 0.401.0 ({_SERVING_COMMIT} 2026-10-10)\n"),
            _command(
                stdout=_releases(
                    records=[
                        {
                            "tag_name": "v0.401.0-nightly.0",
                            "published_at": "2026-10-09T02:00:00Z",
                            "draft": False,
                            "prerelease": True,
                        },
                        {
                            "tag_name": "v0.400.0",
                            "published_at": "2026-10-08T01:00:00Z",
                            "draft": False,
                            "prerelease": False,
                        },
                    ]
                )
            ),
            _command(stdout='{"status": "diverged"}'),
            _command(stdout='{"status": "behind"}'),
        ],
        calls=[],
    )
    decision = None
    with suppress(StopIteration):
        decision = importlib.import_module(_MODULE_NAME).fabro_currency_admission(
            target=FactoryTarget(name="edge", server="https://edge.example", dev_token=None),
            fabro_bin="/opt/fabro-edge",
            repo=tmp_path,
            runner=runner,
            now=datetime(2026, 10, 10, 3, tzinfo=timezone.utc),
            cache_path=tmp_path / "release-observation.json",
        )

    assert decision is not None
    assert decision.admitted is False
    assert decision.message == (
        "ERROR: Fabro currency admission refused factory edge: serving integration commit "
        "abcdef1234567890 has no published fabro-sh/fabro release-tag ancestor; newest "
        "observed release v0.401.0-nightly.0 was published 2026-10-09T02:00:00Z; release "
        "metadata was observed 2026-10-10T03:00:00Z. Rebuild factory-integration on an "
        "exact published release, re-pin factory edge, and retry dispatch.\n"
    )


def test_a_failed_refresh_refuses_instead_of_reusing_a_stale_observation(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "release-observation.json"
    _ = cache_path.write_text(
        json.dumps(
            {
                "observed_at": "2026-10-02T02:59:59Z",
                "releases": [
                    {
                        "tag_name": "v0.399.0",
                        "published_at": "2026-10-01T00:00:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    runner = _Runner(
        results=[
            _command(stdout=f"fabro 0.399.0 ({_SERVING_COMMIT} 2026-10-01)\n"),
            _command(stdout="[[]]", exit_code=1, stderr="GitHub unavailable"),
        ],
        calls=[],
    )
    decision = None
    with suppress(IndexError):
        decision = importlib.import_module(_MODULE_NAME).fabro_currency_admission(
            target=FactoryTarget(name="hp", server="https://factory.example", dev_token=None),
            fabro_bin="/opt/fabro-hp",
            repo=tmp_path,
            runner=runner,
            now=datetime(2026, 10, 10, 3, tzinfo=timezone.utc),
            cache_path=cache_path,
        )

    assert decision is not None
    assert decision.admitted is False
    assert decision.message == (
        "ERROR: Fabro currency admission refused factory hp: serving integration commit "
        "abcdef1234567890; cached release metadata observed 2026-10-02T02:59:59Z is "
        "older than seven days, and refresh failed at 2026-10-10T03:00:00Z (GitHub "
        "unavailable); newest observed release v0.399.0 was published "
        "2026-10-01T00:00:00Z. Restore the fabro-sh/fabro GitHub Releases observation "
        "and retry dispatch.\n"
    )
    assert runner.calls == [
        ["/opt/fabro-hp", "--version"],
        [
            "gh",
            "api",
            "--paginate",
            "--slurp",
            "repos/fabro-sh/fabro/releases?per_page=100",
        ],
    ]


@pytest.mark.parametrize(
    ("version_result", "failed_condition"),
    [
        (
            _command(stdout="", exit_code=1, stderr="version unavailable"),
            "fabro --version failed with exit 1 (version unavailable)",
        ),
        (
            _command(
                stdout=f"fabro 0.401.0 ({_SERVING_COMMIT} 2026-10-09)\n",
                exit_code=7,
                stderr="serving build probe failed",
            ),
            "fabro --version failed with exit 7 (serving build probe failed)",
        ),
        (
            _command(stdout="fabro version unknown\n"),
            "fabro --version output did not identify the serving integration commit",
        ),
    ],
)
def test_an_unidentifiable_serving_build_refuses_with_release_evidence(
    tmp_path: Path,
    version_result: CommandResult,
    failed_condition: str,
) -> None:
    runner = _Runner(
        results=[
            version_result,
            _command(
                stdout=_releases(
                    records=[
                        {
                            "tag_name": "v0.401.0-nightly.0",
                            "published_at": "2026-10-09T00:00:00Z",
                            "draft": False,
                            "prerelease": True,
                        }
                    ]
                )
            ),
        ],
        calls=[],
    )

    decision = importlib.import_module(_MODULE_NAME).fabro_currency_admission(
        target=FactoryTarget(name="edge", server="https://edge.example", dev_token=None),
        fabro_bin="/opt/fabro-edge",
        repo=tmp_path,
        runner=runner,
        now=datetime(2026, 10, 10, tzinfo=timezone.utc),
        cache_path=tmp_path / "release-observation.json",
    )

    assert decision.admitted is False
    assert decision.message == (
        "ERROR: Fabro currency admission refused factory edge: serving integration commit "
        f"is unknown because {failed_condition}; newest observed release "
        "v0.401.0-nightly.0 was published 2026-10-09T00:00:00Z; release metadata was "
        "observed 2026-10-10T00:00:00Z. Restore factory edge's Fabro binary so "
        "`fabro --version` reports its serving integration commit, then retry dispatch.\n"
    )


def test_a_cold_cache_refresh_failure_refuses_without_a_traceback(tmp_path: Path) -> None:
    runner = _Runner(
        results=[
            _command(stdout=f"fabro 0.401.0 ({_SERVING_COMMIT} 2026-10-09)\n"),
            _command(stdout="", exit_code=1, stderr="GitHub unavailable"),
        ],
        calls=[],
    )

    decision = importlib.import_module(_MODULE_NAME).fabro_currency_admission(
        target=FactoryTarget(name="edge", server="https://edge.example", dev_token=None),
        fabro_bin="/opt/fabro-edge",
        repo=tmp_path,
        runner=runner,
        now=datetime(2026, 10, 10, tzinfo=timezone.utc),
        cache_path=tmp_path / "missing-observation.json",
    )

    assert decision.admitted is False
    assert decision.message == (
        "ERROR: Fabro currency admission refused factory edge: serving integration commit "
        "abcdef1234567890; no cached release metadata observation exists, and refresh "
        "failed at 2026-10-10T00:00:00Z (GitHub unavailable); newest observed release "
        "and observation time are unavailable. Restore the fabro-sh/fabro GitHub Releases "
        "observation and retry dispatch.\n"
    )


def test_a_malformed_cache_is_refreshed_instead_of_raising(tmp_path: Path) -> None:
    cache_path = tmp_path / "truncated-observation.json"
    _ = cache_path.write_text('{"observed_at":', encoding="utf-8")
    runner = _Runner(
        results=[
            _command(stdout=f"fabro 0.401.0 ({_SERVING_COMMIT} 2026-10-09)\n"),
            _command(
                stdout=_releases(
                    records=[
                        {
                            "tag_name": "v0.401.0-nightly.0",
                            "published_at": "2026-10-09T00:00:00Z",
                            "draft": False,
                            "prerelease": True,
                        }
                    ]
                )
            ),
            _command(stdout='{"status": "identical"}'),
        ],
        calls=[],
    )

    decision = importlib.import_module(_MODULE_NAME).fabro_currency_admission(
        target=FactoryTarget(name="edge", server="https://edge.example", dev_token=None),
        fabro_bin="/opt/fabro-edge",
        repo=tmp_path,
        runner=runner,
        now=datetime(2026, 10, 10, tzinfo=timezone.utc),
        cache_path=cache_path,
    )

    assert decision == FabroCurrencyDecision(admitted=True, message="")
    assert runner.calls == [
        ["/opt/fabro-edge", "--version"],
        [
            "gh",
            "api",
            "--paginate",
            "--slurp",
            "repos/fabro-sh/fabro/releases?per_page=100",
        ],
        [
            "gh",
            "api",
            "repos/fabro-sh/fabro/compare/v0.401.0-nightly.0...abcdef1234567890",
        ],
    ]


@pytest.mark.parametrize(
    "release_stdout",
    [
        "not-json",
        "{}",
        "[{}]",
        "[[]]",
        '[ [{"tag_name": "v0.401.0", "published_at": null, "draft": false}] ]',
    ],
)
def test_an_unusable_successful_release_response_refuses_without_a_traceback(
    tmp_path: Path,
    release_stdout: str,
) -> None:
    runner = _Runner(
        results=[
            _command(stdout=f"fabro 0.401.0 ({_SERVING_COMMIT} 2026-10-09)\n"),
            _command(stdout=release_stdout),
        ],
        calls=[],
    )

    decision = importlib.import_module(_MODULE_NAME).fabro_currency_admission(
        target=FactoryTarget(name="edge", server="https://edge.example", dev_token=None),
        fabro_bin="/opt/fabro-edge",
        repo=tmp_path,
        runner=runner,
        now=datetime(2026, 10, 10, tzinfo=timezone.utc),
        cache_path=tmp_path / "missing-observation.json",
    )

    assert decision.admitted is False
    assert (
        "no cached release metadata observation exists, and refresh failed at "
        "2026-10-10T00:00:00Z (GitHub Releases returned unusable metadata:"
    ) in decision.message
    assert "newest observed release and observation time are unavailable" in decision.message
    assert runner.calls == [
        ["/opt/fabro-edge", "--version"],
        [
            "gh",
            "api",
            "--paginate",
            "--slurp",
            "repos/fabro-sh/fabro/releases?per_page=100",
        ],
    ]


@pytest.mark.parametrize(
    "compare_result",
    [
        _command(stdout="", exit_code=1, stderr="GitHub compare unavailable"),
        _command(stdout="not-json"),
        _command(stdout='{"unexpected": "shape"}'),
    ],
)
def test_failed_or_malformed_ancestry_evidence_refuses_with_context(
    tmp_path: Path,
    compare_result: CommandResult,
) -> None:
    runner = _Runner(
        results=[
            _command(stdout=f"fabro 0.401.0 ({_SERVING_COMMIT} 2026-10-09)\n"),
            _command(
                stdout=_releases(
                    records=[
                        {
                            "tag_name": "v0.401.0-nightly.0",
                            "published_at": "2026-10-09T00:00:00Z",
                            "draft": False,
                            "prerelease": True,
                        }
                    ]
                )
            ),
            compare_result,
        ],
        calls=[],
    )

    decision = importlib.import_module(_MODULE_NAME).fabro_currency_admission(
        target=FactoryTarget(name="edge", server="https://edge.example", dev_token=None),
        fabro_bin="/opt/fabro-edge",
        repo=tmp_path,
        runner=runner,
        now=datetime(2026, 10, 10, tzinfo=timezone.utc),
        cache_path=tmp_path / "release-observation.json",
    )

    assert decision.admitted is False
    assert decision.message.startswith(
        "ERROR: Fabro currency admission refused factory edge: serving integration commit "
        "abcdef1234567890; could not determine whether published release "
        "v0.401.0-nightly.0 is an ancestor of the serving commit ("
    )
    assert (
        "; newest observed release v0.401.0-nightly.0 was published "
        "2026-10-09T00:00:00Z; release metadata was observed 2026-10-10T00:00:00Z. "
        "Restore fabro-sh/fabro compare evidence and retry dispatch.\n"
    ) in decision.message


def test_the_0254_transition_is_visible_before_its_fixed_deadline_and_expires(
    tmp_path: Path,
) -> None:
    def _carrier_runner() -> _Runner:
        return _Runner(
            results=[
                _command(stdout=f"fabro 0.254.0 ({_SERVING_COMMIT} 2026-06-01)\n"),
                _command(
                    stdout=_releases(
                        records=[
                            {
                                "tag_name": "v0.410.0-nightly.0",
                                "published_at": "2026-11-10T00:00:00Z",
                                "draft": False,
                                "prerelease": True,
                            },
                            {
                                "tag_name": "v0.254.0",
                                "published_at": "2026-06-01T00:00:00Z",
                                "draft": False,
                                "prerelease": False,
                            },
                        ]
                    )
                ),
                _command(stdout='{"status": "diverged"}'),
                _command(stdout='{"status": "ahead"}'),
            ],
            calls=[],
        )

    gate = importlib.import_module(_MODULE_NAME)
    before = gate.fabro_currency_admission(
        target=FactoryTarget(name="hp", server="https://factory.example", dev_token=None),
        fabro_bin="/opt/fabro-hp",
        repo=tmp_path,
        runner=_carrier_runner(),
        now=datetime(2026, 11, 13, 23, 59, 59, tzinfo=timezone.utc),
        cache_path=tmp_path / "before.json",
    )
    at_deadline = gate.fabro_currency_admission(
        target=FactoryTarget(name="hp", server="https://factory.example", dev_token=None),
        fabro_bin="/opt/fabro-hp",
        repo=tmp_path,
        runner=_carrier_runner(),
        now=datetime(2026, 11, 14, tzinfo=timezone.utc),
        cache_path=tmp_path / "deadline.json",
    )

    assert before.admitted is True
    assert before.message == (
        "NOTICE: Fabro currency admission admits factory hp under the bd-ib-6tcjfx "
        "transition: serving integration commit abcdef1234567890 resolves to the "
        "out-of-window v0.254.0 base published 2026-06-01T00:00:00Z; this "
        "non-renewable exception expires at 2026-11-14T00:00:00Z.\n"
    )
    assert at_deadline.admitted is False
    assert "base v0.254.0 published 2026-06-01T00:00:00Z" in at_deadline.message
    assert "the base is more than 30 calendar days behind" in at_deadline.message


@dataclass(kw_only=True)
class _WallHarness:
    item: WorkItem
    journal: object
    target: FactoryTarget
    selected_targets: list[tuple[str, str]]
    downstream: list[str]
    reclaims: list[str]


def _wall_harness() -> _WallHarness:
    return _WallHarness(
        item=WorkItem(
            id="bd-ib-j9x",
            type="task",
            status="ready",
            title="Gate every dispatch entry",
            description="## Definition of Done\n\n- The shared wall refuses before claim.\n",
            origin="freeform",
            gap_id=None,
            rank="b1G",
            assignee=None,
            depends_on=(),
            captured_at="2026-10-10T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
        ),
        journal=object(),
        target=FactoryTarget(
            name="edge",
            server="https://edge.example",
            dev_token=None,
            fabro_bin="/opt/fabro-edge",
        ),
        selected_targets=[],
        downstream=[],
        reclaims=[],
    )


def test_the_currency_wall_uses_the_github_app_token_refreshing_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _wall_harness()
    refreshing_runner = _Runner(results=[], calls=[])
    runner_resolution_calls: list[object] = []
    admission_runners: list[object] = []

    def _post_verdict_runner(*, runner: object) -> _Runner:
        runner_resolution_calls.append(runner)
        return refreshing_runner

    def _admission(**kwargs: object) -> FabroCurrencyDecision:
        admission_runners.append(kwargs["runner"])
        return FabroCurrencyDecision(admitted=True, message="")

    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "post_verdict_runner",
        _post_verdict_runner,
        raising=False,
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "selected_dispatch_factory_target",
        lambda **_kwargs: harness.target,
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "factory_effective_fabro_bin",
        lambda **_kwargs: "/opt/fabro-edge",
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "fabro_currency_admission",
        _admission,
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "pre_dispatch_criteria_refusal",
        _none,
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "proof_assets_refusal_for_items",
        _none,
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "proof_credentials_refusal_for_items",
        _none,
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "selection_credential_requirement",
        lambda **_kwargs: _dispatcher_pre_dispatch_wall.WorkflowFaultDeferral(
            message="not under test"
        ),
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "reclaim_stale_publish_branches",
        _none,
    )

    wall_exit = _dispatcher_pre_dispatch_wall.pre_dispatch_wall_exit(
        args=argparse.Namespace(
            fabro_bin="/opt/fabro-global",
            workflow_name=None,
        ),
        repo=tmp_path,
        items=[harness.item],
        journal=harness.journal,
    )

    assert wall_exit is None
    assert runner_resolution_calls == [None]
    assert admission_runners == [refreshing_runner]


def _stub_currency_wall(
    *,
    monkeypatch: pytest.MonkeyPatch,
    harness: _WallHarness,
    runners: list[_Runner],
    cache_root: Path,
) -> None:
    def _deferred(**_kwargs: object) -> object:  # pragma: no cover - refusal returns first
        return _dispatcher_pre_dispatch_wall.WorkflowFaultDeferral(message="not under test")

    def _selected(**_kwargs: object) -> FactoryTarget:
        return harness.target

    def _effective_bin(**_kwargs: object) -> str:
        harness.selected_targets.append((harness.target.name, "/opt/fabro-edge"))
        return "/opt/fabro-edge"

    def _reclaim(**_kwargs: object) -> None:  # pragma: no cover - refusal forbids reclaim
        harness.reclaims.append("reclaimed")

    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "pre_dispatch_criteria_refusal",
        _none,
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "proof_assets_refusal_for_items",
        _none,
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "proof_credentials_refusal_for_items",
        _none,
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "selection_credential_requirement",
        _deferred,
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "selected_dispatch_factory_target",
        _selected,
        raising=False,
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "factory_effective_fabro_bin",
        _effective_bin,
        raising=False,
    )

    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "ShellCommandRunner",
        lambda: runners.pop(0),
    )

    def _refreshing_runner(*, runner: object) -> _Runner:
        assert runner is None
        return runners.pop(0)

    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "post_verdict_runner",
        _refreshing_runner,
        raising=False,
    )
    cache_paths = iter(cache_root / f"observation-{index}.json" for index in range(3))
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "fabro_release_cache_path",
        lambda **_kwargs: next(cache_paths),
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "reclaim_stale_publish_branches",
        _reclaim,
    )


def _stub_dispatch_entries(*, monkeypatch: pytest.MonkeyPatch, harness: _WallHarness) -> None:
    outcome = DispatchOutcome(
        work_item_id=harness.item.id,
        status="green",
        stage="done",
        pr_number=None,
        merge_sha=None,
        detail="stood in",
    )

    def _preamble(**_kwargs: object) -> tuple[None, None]:
        return None, None

    def _prepare(**_kwargs: object) -> tuple[list[WorkItem], object]:
        return [harness.item], harness.journal

    def _target(**_kwargs: object) -> tuple[WorkItem, bool]:
        return harness.item, False

    def _admit(**_kwargs: object) -> DispatchOutcome:  # pragma: no cover - must not claim
        harness.downstream.append("direct-claim")
        return outcome

    def _tail(**_kwargs: object) -> int:  # pragma: no cover - refusal returns before tail
        return 0

    def _start(**_kwargs: object) -> argparse.Namespace:
        return argparse.Namespace(
            janitor=None,
            items=[harness.item],
            journal=harness.journal,
        )

    def _candidates(**_kwargs: object) -> list[WorkItem]:
        return [harness.item]

    def _wave(**_kwargs: object) -> list[DispatchOutcome]:  # pragma: no cover - must not claim
        harness.downstream.append("loop-claim")
        return []

    monkeypatch.setattr(
        _dispatcher_run_commands,
        "dispatch_preamble",
        _preamble,
    )
    monkeypatch.setattr(_dispatcher_run_commands, "arm_otel_egress", _none)
    monkeypatch.setattr(
        _dispatcher_run_commands,
        "prepare",
        _prepare,
    )
    monkeypatch.setattr(
        _dispatcher_run_commands,
        "_target_item",
        _target,
    )
    monkeypatch.setattr(
        _dispatcher_run_commands,
        "_admit_and_dispatch_target",
        _admit,
    )
    monkeypatch.setattr(
        _dispatcher_run_commands,
        "dispatch_tail_exit",
        _tail,
    )
    monkeypatch.setattr(
        _dispatcher_loop_command,
        "_start_loop",
        _start,
    )
    monkeypatch.setattr(
        _dispatcher_loop_command,
        "candidates",
        _candidates,
    )
    monkeypatch.setattr(
        _dispatcher_loop_command,
        "dispatch_loop_wave",
        _wave,
    )


def _dispatch_entry_codes(*, repo: Path, item_id: str) -> tuple[int, int, int]:
    common = {
        "repo": str(repo),
        "skip_ledger_check": True,
        "workflow_name": None,
        "workflow": None,
        "fabro_bin": "/opt/fabro-global",
        "budget": 1,
        "dry_run": False,
        "as_json": False,
    }
    direct_code = _dispatcher_run_commands.run_dispatch_command(
        args=argparse.Namespace(**common, item=item_id)
    )
    hand_picked_code = _dispatcher_loop_command.run_loop_command(
        args=argparse.Namespace(**common, items=[item_id])
    )
    autonomous_code = _dispatcher_loop_command.run_loop_command(
        args=argparse.Namespace(**common, items=[])
    )
    return direct_code, hand_picked_code, autonomous_code


def _current_decision_from_cache(
    *, tmp_path: Path, target: FactoryTarget
) -> tuple[FabroCurrencyDecision, _Runner]:
    cache_path = tmp_path / "fresh-observation.json"
    _ = cache_path.write_text(
        json.dumps(
            {
                "observed_at": "2026-10-09T00:00:00Z",
                "releases": [
                    {
                        "tag_name": "v0.401.0-nightly.0",
                        "published_at": "2026-10-09T00:00:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    runner = _Runner(
        results=[
            _command(stdout=f"fabro 0.401.0 ({_SERVING_COMMIT} 2026-10-09)\n"),
            _command(stdout='{"status": "identical"}'),
        ],
        calls=[],
    )
    current = importlib.import_module(_MODULE_NAME).fabro_currency_admission(
        target=target,
        fabro_bin="/opt/fabro-edge",
        repo=tmp_path,
        runner=runner,
        now=datetime(2026, 10, 10, tzinfo=timezone.utc),
        cache_path=cache_path,
    )
    return current, runner


def test_every_dispatch_entry_reaches_the_target_aware_wall_before_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _wall_harness()

    def _refusal_runner() -> _Runner:
        return _Runner(
            results=[
                _command(stdout=f"fabro 0.300.0 ({_SERVING_COMMIT} 2026-08-01)\n"),
                _command(
                    stdout=_releases(
                        records=[
                            {
                                "tag_name": "v0.401.0-nightly.0",
                                "published_at": "2026-10-09T00:00:00Z",
                                "draft": False,
                                "prerelease": True,
                            },
                            {
                                "tag_name": "v0.300.0",
                                "published_at": "2026-08-01T00:00:00Z",
                                "draft": False,
                                "prerelease": False,
                            },
                        ]
                    )
                ),
                _command(stdout='{"status": "diverged"}'),
                _command(stdout='{"status": "ahead"}'),
            ],
            calls=[],
        )

    runners = [_refusal_runner() for _index in range(3)]
    _stub_currency_wall(
        monkeypatch=monkeypatch,
        harness=harness,
        runners=runners,
        cache_root=tmp_path,
    )
    _stub_dispatch_entries(monkeypatch=monkeypatch, harness=harness)
    codes = _dispatch_entry_codes(repo=tmp_path, item_id=harness.item.id)

    assert codes == (EXIT_PRECONDITION_ERROR,) * 3
    assert harness.selected_targets == [("edge", "/opt/fabro-edge")] * 3
    assert harness.downstream == []
    assert harness.reclaims == []
    assert runners == []
    current, runner = _current_decision_from_cache(tmp_path=tmp_path, target=harness.target)
    assert current == FabroCurrencyDecision(admitted=True, message="")
    assert runner.calls == [
        ["/opt/fabro-edge", "--version"],
        [
            "gh",
            "api",
            "repos/fabro-sh/fabro/compare/v0.401.0-nightly.0...abcdef1234567890",
        ],
    ]


def test_an_autonomous_rework_reaches_the_currency_wall_before_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _wall_harness()
    runner = _Runner(
        results=[
            _command(stdout=f"fabro 0.300.0 ({_SERVING_COMMIT} 2026-08-01)\n"),
            _command(
                stdout=_releases(
                    records=[
                        {
                            "tag_name": "v0.401.0-nightly.0",
                            "published_at": "2026-10-09T00:00:00Z",
                            "draft": False,
                            "prerelease": True,
                        },
                        {
                            "tag_name": "v0.300.0",
                            "published_at": "2026-08-01T00:00:00Z",
                            "draft": False,
                            "prerelease": False,
                        },
                    ]
                )
            ),
            _command(stdout='{"status": "diverged"}'),
            _command(stdout='{"status": "ahead"}'),
        ],
        calls=[],
    )
    _stub_currency_wall(
        monkeypatch=monkeypatch,
        harness=harness,
        runners=[runner],
        cache_root=tmp_path,
    )
    monkeypatch.setattr(_dispatcher_pre_dispatch_wall, "ShellCommandRunner", lambda: runner)
    _stub_dispatch_entries(monkeypatch=monkeypatch, harness=harness)
    monkeypatch.setattr(_dispatcher_loop_command, "candidates", lambda **_kwargs: [])
    monkeypatch.setattr(
        _dispatcher_loop_command,
        "projected_rework_candidates",
        lambda **_kwargs: (harness.item,),
        raising=False,
    )

    code = _dispatcher_loop_command.run_loop_command(
        args=argparse.Namespace(
            repo=str(tmp_path),
            skip_ledger_check=True,
            workflow_name=None,
            workflow=None,
            fabro_bin="/opt/fabro-global",
            budget=1,
            dry_run=False,
            as_json=False,
            items=[],
        )
    )

    assert code == EXIT_PRECONDITION_ERROR
    assert harness.selected_targets == [("edge", "/opt/fabro-edge")]
    assert harness.downstream == []
    assert harness.reclaims == []
    assert runner.results == []
