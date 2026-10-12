"""The run-branch checkpoint declaration of the shipped `implement-work-item` payload.

WHAT THIS BINDS, AND WHY IT IS A TEST RATHER THAN A COMMENT. The engine
checkpoints the run branch between nodes, and `[run.checkpoint]` is where this
repository tells it how. Both keys here were set the other way until 2026-10-12,
with a rationale written in the file itself, and the setting that rationale chose
killed 27 hp runs between 2026-10-09 and 2026-10-12: the checkpoint commit ran
this repository's pre-commit aggregate, and a node that ended with an
unfinished tree -- a coverage gate still red, a Red awaiting its Green -- turned
a REPAIRABLE tree into run death at `workflow_error`. The measurement is
`plan/checkpoint-commit-hook-failures/research/001-measured-checkpoint-failures-2026-10-12.md`;
the ledger item is `bd-ib-jb53pu`.

So the declaration is asserted here, through a real TOML parse, because that is
what the engine reads and because a value reverted by a well-meaning edit would
otherwise announce nothing until runs started dying again.

WHY THE THIRD CASE EXISTS. `commit_timeout` is not a local choice: the Dispatcher
bills it THREE TIMES PER ATTEMPT into the credential-lifetime floor
(`_dispatcher_credential_requirement`, which reads it precisely because a
repository that raised it raises that cost threefold), and the Codex freshness
gate then demands that floor of a ten-day token. The old `"15m"` put the floor at
796830 seconds -- 9.22 days, which is most of a Codex token's whole life. The
case asserts the figure the shipped declaration now resolves AND re-resolves the
same payload at `"15m"` as its control, so the bound is proved to be cleared BY
this checkpoint budget rather than by some unrelated narrowing of the graph.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PAYLOAD = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_SHIPPED_WORKFLOW = _PAYLOAD / "workflow.toml"


def _checkpoint() -> dict[str, Any]:
    """The shipped `[run.checkpoint]` table, parsed as the engine parses it.

    `tomli`, not the stdlib `tomllib`: this suite runs on 3.10, where the stdlib
    module does not exist yet. Parsed rather than grepped because the property
    is the VALUE the engine resolves, and a line-shaped assertion would pass for
    a commented-out declaration.
    """
    import tomli

    document: dict[str, Any] = tomli.loads(_SHIPPED_WORKFLOW.read_text(encoding="utf-8"))
    checkpoint: dict[str, Any] = document["run"]["checkpoint"]
    return checkpoint


def test_the_run_branch_checkpoint_skips_this_repositorys_commit_hooks() -> None:
    """`skip_git_hooks` is true, so a checkpoint commit cannot be refused by a gate.

    The engine passes `--no-verify` to the checkpoint commit ONLY when this key
    is true (`sandbox_git.rs` on the deployed 0.254.0 build), so with it false
    every checkpoint re-runs the repository's pre-commit aggregate. That run is
    the THIRD of the same suite in one node cycle -- the janitor node runs the
    declared check suite after implement, and `publish_draft`'s pre-push runs the
    aggregate again -- and it is the only one of the three whose failure is fatal
    rather than routed into a fix loop.

    `is True` rather than a truthiness test: TOML's `1` and `"true"` are not
    booleans, and the engine's own deserializer would refuse them, so a case that
    accepted them would certify a configuration no run could load.
    """
    assert _checkpoint()["skip_git_hooks"] is True
