"""A run-files read the factory refuses is the files-read step, not an empty tree."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree import (
    preserved_tree_message,
    publish_run_tree,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    STEP_FILES_READ,
    PublishFailure,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import (
    FabroHttpPort,
    FabroHttpResult,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroTarget

_RUN_ID = "01M4YJGC55V86C9V1X07QG3Y2H"


@dataclass(kw_only=True)
class _RefusingTransport:
    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        _ = method
        _ = url
        _ = headers
        _ = body
        _ = timeout_seconds
        return FabroHttpResult(
            status=401,
            body="Authentication required",
            error=None,
            payload=None,
            succeeded=False,
        )


@dataclass(kw_only=True)
class _RefusingRunner:
    """Any call here is a defect: nothing may be published after a failed read."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd
        _ = timeout_seconds
        _ = env
        _ = stdin
        msg = f"nothing may be published after an unreadable run-files read: {argv}"
        raise AssertionError(msg)


def test_a_factory_that_refuses_the_read_fails_at_the_files_read_step_and_publishes_nothing() -> (
    None
):
    failed = publish_run_tree(
        port=FabroHttpPort(
            target=FabroTarget(server_url="https://factory.example:32276"),
            transport=_RefusingTransport(),
        ),
        runner=_RefusingRunner(),
        repo=Path("/nonexistent"),
        work_item_id="bd-ib-na2xvm",
        run_id=_RUN_ID,
        base_commit="5d511335aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    assert isinstance(failed, PublishFailure)
    assert failed.step == STEP_FILES_READ
    assert "401" in failed.detail


def test_the_commit_message_says_the_commit_is_a_recovery_artifact() -> None:
    message = preserved_tree_message(work_item_id="bd-ib-na2xvm", run_id=_RUN_ID)
    assert message.startswith(f"fabro({_RUN_ID}): preserved tree of a checkpoint-failed run")
    assert "NOT a commit to land" in message
    assert "bd-ib-na2xvm" in message
