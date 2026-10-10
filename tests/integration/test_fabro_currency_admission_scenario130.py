"""Integration-tier binding for Scenario 130's Fabro currency admission."""

from __future__ import annotations

import importlib
import json
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

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
