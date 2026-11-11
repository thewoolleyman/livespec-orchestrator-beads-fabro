"""A preserved descendant must refuse a resume before it can discard work."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_preserved_descendant"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_resume_preserved_descendant.py"
)


def test_a_descending_preservation_refusal_names_the_ref_tip_head_and_plain_dispatch() -> None:
    """The remedial dispatch cannot hide which preserved work would be lost."""
    assert _MODULE_PATH.is_file()
    module: Any = importlib.import_module(_MODULE_NAME)

    refusal = module.descending_preservation_refusal(
        preservation_ref="refs/heads/needs-human/run-1",
        preservation_tip="b" * 40,
        published_head="a" * 40,
    )

    assert "refs/heads/needs-human/run-1" in refusal
    assert "b" * 40 in refusal
    assert "a" * 40 in refusal
    assert "dispatch" in refusal


class _Runner:
    """A readable preserved tip that descends from the pull request head."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        joined = " ".join(argv)
        if "merge-base --is-ancestor" in joined:
            return CommandResult(exit_code=0, stdout="", stderr="")
        if "^{tree}" in joined:
            tree = "1" * 40 if "a" * 40 in joined else "2" * 40
            return CommandResult(exit_code=0, stdout=f"{tree}\n", stderr="")
        raise AssertionError(f"unexpected command: {joined}")


def test_a_same_run_descending_ref_with_more_work_is_a_resume_refusal() -> None:
    """A resume onto the older published head would lose the preservation's commit."""
    module: Any = importlib.import_module(_MODULE_NAME)
    assert hasattr(module, "preserved_descendant")

    outcome = module.preserved_descendant(
        runner=_Runner(),
        repo=Path("/repo"),
        preservation=RecoverySeed(
            source_run_id="run-1",
            remote="origin",
            commit_sha="b" * 40,
            preservation_ref="refs/heads/needs-human/run-1",
            preservation_tip_sha="b" * 40,
        ),
        published_head="a" * 40,
        head_is_later=False,
    )

    assert outcome.preservation_ref == "refs/heads/needs-human/run-1"
    assert outcome.preservation_tip == "b" * 40
    assert outcome.published_head == "a" * 40
