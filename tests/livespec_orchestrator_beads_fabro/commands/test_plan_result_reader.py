"""Tests for the shared reader's own three steps: parse, resolve, then one source.

`tests/integration/test_plan_result_reader_scenario146.py` binds the scenario
end to end. This module covers what the reader itself owns and the integration
tier cannot observe: the fail-closed ORDER of the three steps, and the UTC
observation time it resolves when a caller injects none.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import IssueDraft, make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNOBSERVABLE,
    SOURCE_REFERENCE,
    SOURCE_REPOSITORY_RESOLUTION,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_reader import (
    UNPARSED_TARGET,
    read_result,
)

_ITEM_ID = "bd-ib-reader"


@dataclass(kw_only=True)
class _Runner:
    """A refusing runner that records every argv the reader issued through it.

    Refusing rather than answering, because the cases here are about WHICH step
    the reader reached: a recorded call proves the reader got past the parse and
    the resolution, and an empty record proves it did not.
    """

    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        self.calls.append(tuple(argv))
        return CommandResult(exit_code=1, stdout="", stderr="unreached")


def _project(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}),
        encoding="utf-8",
    )
    client = make_beads_client(config=store_config(repo=repo))
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM_ID,
            issue_type="feature",
            title=_ITEM_ID,
            description="",
            assignee=None,
            created_at="2026-10-08T00:00:00Z",
        )
    )
    client.update_issue(issue_id=_ITEM_ID, status="done")
    return repo


def _reference(*, repo: str = "repo") -> dict[str, object]:
    return {"repo": repo, "item_status": {"item_id": _ITEM_ID, "status": "done"}}


def test_an_unobservable_reference_is_refused_before_any_source_is_read(
    tmp_path: Path,
) -> None:
    """The order is load-bearing: an unparseable reference names no target to read.

    The runner records every call, so a reader that resolved and read first would
    be caught here rather than merely producing the same verdict by a worse route.
    """
    runner = _Runner()
    observation = read_result(project_root=_project(tmp_path=tmp_path), reference=[], runner=runner)
    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert observation.source == SOURCE_REFERENCE
    assert observation.target == UNPARSED_TARGET
    assert runner.calls == []


def test_an_unresolvable_repository_is_refused_before_any_source_is_read(
    tmp_path: Path,
) -> None:
    runner = _Runner()
    observation = read_result(
        project_root=_project(tmp_path=tmp_path),
        reference=_reference(repo="a-repository-nobody-configured"),
        runner=runner,
    )
    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert observation.source == SOURCE_REPOSITORY_RESOLUTION
    assert observation.repo == "a-repository-nobody-configured"
    assert _ITEM_ID in observation.target
    assert runner.calls == []


def test_a_resolved_forge_reference_reaches_the_forge_adapter(tmp_path: Path) -> None:
    """The positive control for the two order cases above.

    Each of those asserts that NO command ran, which a reader that never reached
    any adapter would also satisfy. This case shows the same runner does receive
    the forge read once the parse and the resolution both succeed.
    """
    runner = _Runner()
    observation = read_result(
        project_root=_project(tmp_path=tmp_path),
        reference={"repo": "repo", "pull_request_state": {"number": 9, "state": "MERGED"}},
        runner=runner,
    )
    assert observation.status == OBSERVATION_UNOBSERVABLE
    assert runner.calls == [("gh", "pr", "view", "9", "--json", "state,updatedAt")]


def test_an_uninjected_observation_time_is_resolved_as_utc(tmp_path: Path) -> None:
    """The clause requires a UTC observation time, so the default must be one.

    A caller forced to supply the instant could supply a local one; resolving it
    through the repository's canonical helper makes the default correct. The format
    is asserted rather than the value, which no test can pin.
    """
    observation = read_result(
        project_root=_project(tmp_path=tmp_path), reference=_reference(), runner=_Runner()
    )
    assert observation.status == OBSERVATION_SATISFIED
    assert observation.observed_at.endswith("Z")
    assert len(observation.observed_at) == len("2026-10-08T12:00:00Z")


def test_an_injected_observation_time_is_reported_verbatim(tmp_path: Path) -> None:
    """Both tracking callers' boundaries must be deterministic against an injected clock."""
    observation = read_result(
        project_root=_project(tmp_path=tmp_path),
        reference=_reference(),
        runner=_Runner(),
        now="2026-10-08T12:00:00Z",
    )
    assert observation.observed_at == "2026-10-08T12:00:00Z"


def test_a_refused_reference_still_reports_the_repository_it_named(tmp_path: Path) -> None:
    """A refusal after the repository field was read keeps that identity.

    The clause requires every observation to report its repository, and an
    unobservable reading that dropped a perfectly good identity would be
    unattributable to the obligation that produced it. The control is the pair:
    a value that is not an object at all has no identity to keep, and reports
    none rather than inventing one.
    """
    repo = _project(tmp_path=tmp_path)
    named = read_result(
        project_root=repo,
        reference={"repo": "repo", "shell": "test -f a.md"},
        runner=_Runner(),
    )
    assert named.status == OBSERVATION_UNOBSERVABLE
    assert named.repo == "repo"
    anonymous = read_result(project_root=repo, reference="item_status", runner=_Runner())
    assert anonymous.status == OBSERVATION_UNOBSERVABLE
    assert anonymous.repo == ""
