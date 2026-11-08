"""Tests for identifying terminal trees whose refs use operator aliases."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult


@dataclass(kw_only=True)
class _Runner:
    """A forge seam whose one reply carries no identifier this item recognises."""

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
        _ = cwd, timeout_seconds, env, stdin
        self.calls.append(argv)
        return CommandResult(
            exit_code=0,
            stdout=json.dumps(
                {
                    "data": {
                        "repository": {
                            "refs": {
                                "nodes": [
                                    {
                                        "name": "other-item",
                                        "target": {
                                            "oid": "a" * 40,
                                            "message": "fix: other work\n\nFabro-Run: another-run\n",
                                            "committedDate": "2026-11-08T00:00:00Z",
                                        },
                                    }
                                ]
                            }
                        }
                    }
                }
            ),
            stderr="",
        )


def test_a_valid_listing_without_this_items_run_does_not_supply_a_seed() -> None:
    """A terminal tree belongs only to the item run its trailer actually names."""
    module_path = Path(
        ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
        "_dispatcher_needs_human_refs.py"
    )
    assert module_path.is_file()
    from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_refs import (
        trailer_carried_seed,
    )

    runner = _Runner()

    assert (
        trailer_carried_seed(
            runner=runner,
            repo=Path("/repo"),
            earlier_run_ids=("this-items-run",),
        )
        is None
    )
    assert runner.calls[0][:3] == ["gh", "api", "graphql"]


def test_a_trailer_alias_seeds_the_run_and_audits_every_matching_tree_it_passed_over() -> None:
    """A terminal ref is recognised by its tip trailer, not merely its ref name."""
    from livespec_orchestrator_beads_fabro.commands import _dispatcher_needs_human_refs

    assert hasattr(_dispatcher_needs_human_refs, "select_needs_human_trees")
    from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_refs import (
        NeedsHumanRef,
        NeedsHumanRefs,
        select_needs_human_trees,
    )

    selection = select_needs_human_trees(
        refs=NeedsHumanRefs(
            refs=(
                NeedsHumanRef(
                    name="alias-new",
                    commit_sha="a" * 40,
                    message="fix: latest\n\nFabro-Run: run-u\n",
                    committed_at="2026-11-08T02:00:00Z",
                ),
                NeedsHumanRef(
                    name="alias-old",
                    commit_sha="b" * 40,
                    message="fix: old\n\nFactory-Run-Id: run-u\n",
                    committed_at="2026-11-08T01:00:00Z",
                ),
            )
        ),
        earlier_run_ids=("run-u",),
    )

    assert selection.seed is not None
    assert selection.seed.preservation_ref == "refs/heads/needs-human/alias-new"
    assert selection.passed_over == (("refs/heads/needs-human/alias-old", "b" * 40),)
